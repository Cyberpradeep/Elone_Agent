"""
Ingestion API Route Handlers
============================
Handles document uploads, Gate 1 validation, staging intake, and JIT plan preview.
Enforces Option A RBAC (process_owner mutations; process_owner & admin upload listing),
tenant-namespaced _uploads/<tenant_id>/, token-derived uploaded_by/tenant_id,
and tenant-scoped _INGESTS & _processed_manifest.json.
"""

import os
import re
import glob
import json
import asyncio
import hashlib
import datetime
import threading
from starlette.concurrency import run_in_threadpool

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.context import (
    SOPS_DIR,
    DRAFTS_DIR,
    LOGS_DIR,
    governance_ledger,
    retrieval_index,
    read_manifest,
    write_manifest,
    get_manifest_entry,
    set_manifest_entry,
    del_manifest_entry,
    tenant_uploads_dir,
    record_upload_owner,
    resolve_tenant_upload,
    list_tenant_uploads,
    record_log_owner,
    resolve_sop_access_meta,
    resolve_draft_access_meta,
    _build_canonical_meta_map,
    parse_yaml_frontmatter,
)
from auth.models import ROLE_ADMIN, ROLE_PROCESS_OWNER
from auth.dependencies import authenticate_request
from utils.security import sanitize_filename, sanitize_slug, redact_sensitive_dlp, scan_raw_sop_for_ast_threats
from utils.cancellation import IngestionCancelled, bind_cancel, reset_cancel
from config.settings import get_max_file_size_bytes, get_max_file_size_mb, get_allowed_extensions
from agents.a1_ingestion import (
    validate_sop_file,
    extract_ordered_sop_content,
)
import agents.a2_structuring.execution_planner as jit_converter
from agents.a2_structuring.canonical_builder import build_canonical_sop_from_draft


_FILE_SHA_CACHE = {}


def _sha256_file(path: str, stat=None) -> str:
    if stat is None:
        stat = os.stat(path)
    key = (path, stat.st_size, getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
    cached = _FILE_SHA_CACHE.get(key)
    if cached:
        return cached
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _FILE_SHA_CACHE[key] = digest
    return digest


def _build_published_index(tenant_id: str):
    """Scans knowledge_base/sops/ for live committed .md playbooks belonging to `tenant_id`."""
    by_sop_id = {}
    by_sha = {}
    if not os.path.exists(SOPS_DIR):
        return by_sop_id, by_sha

    canonical_map = _build_canonical_meta_map()

    for path in glob.glob(os.path.join(SOPS_DIR, "**", "*.md"), recursive=True):
        if os.path.basename(path).lower() == "index.md":
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                fm, _ = parse_yaml_frontmatter(f.read())
            sid = str(fm.get("sop_id") or os.path.splitext(os.path.basename(path))[0]).strip()
            access_meta = resolve_sop_access_meta(sid, canonical_map=canonical_map, frontmatter=fm)
            if access_meta["tenant_id"] != tenant_id:
                continue
            sha = str(
                access_meta.get("source_sha256")
                or fm.get("source_file_sha256")
                or fm.get("source_sha256")
                or ""
            ).strip()
            rec = {"sop_id": sid, "path": path, "source_sha256": sha, "tenant_id": tenant_id}
            if sid:
                by_sop_id[sid.lower()] = rec
            if sha:
                by_sha[sha] = rec
        except Exception:
            pass

    for path in glob.glob(os.path.join(SOPS_DIR, "**", "*.canonical.json"), recursive=True):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            sid = str(cdata.get("sop_id") or "").strip()
            access_meta = resolve_sop_access_meta(sid, canonical_map=canonical_map)
            if access_meta["tenant_id"] != tenant_id:
                continue
            src = cdata.get("source") or {}
            text_sha = str(src.get("sha256") or "").strip()
            file_sha = str(src.get("file_sha256") or "").strip()
            if sid and sid.lower() in by_sop_id:
                rec = by_sop_id[sid.lower()]
                if file_sha:
                    by_sha[file_sha] = rec
                    rec["source_sha256"] = file_sha
                elif text_sha:
                    by_sha.setdefault(text_sha, rec)
        except Exception:
            pass

    return by_sop_id, by_sha


def _allocate_job_id(content_hash: str) -> str:
    base = f"job_{content_hash[:10]}"
    if not governance_ledger.get_job(base):
        return base
    idx = 2
    while governance_ledger.get_job(f"{base}_r{idx}"):
        idx += 1
    return f"{base}_r{idx}"


def _sop_id_owned_by_other_tenant(candidate_sop_id: str, tenant_id: str) -> bool:
    draft_path = os.path.join(DRAFTS_DIR, f"{candidate_sop_id}.draft.json")
    if os.path.isfile(draft_path):
        d_meta = resolve_draft_access_meta(candidate_sop_id)
        if d_meta["tenant_id"] != tenant_id:
            return True
    for p in glob.glob(os.path.join(SOPS_DIR, "**", "*.md"), recursive=True):
        if os.path.splitext(os.path.basename(p))[0].lower() == candidate_sop_id.lower():
            if resolve_sop_access_meta(candidate_sop_id)["tenant_id"] != tenant_id:
                return True
    idx = retrieval_index._index.get(candidate_sop_id)
    if idx and idx.tenant_id != tenant_id:
        return True
    for job in list(governance_ledger._jobs.values()):
        if job.sop_id.lower() == candidate_sop_id.lower() and job.tenant_id != tenant_id:
            return True
    return False


def _allocate_sop_id(content_hash: str, tenant_id: str, override_sop_id: str = None) -> str:
    base = sanitize_slug(override_sop_id) if override_sop_id else f"SOP-{content_hash[:6].upper()}"
    if not _sop_id_owned_by_other_tenant(base, tenant_id):
        return base
    t_tag = re.sub(r"[^A-Za-z0-9]", "", tenant_id)[-4:].upper() or "TN"
    cand = f"{base}_{t_tag}"
    if not _sop_id_owned_by_other_tenant(cand, tenant_id):
        return cand
    n = 2
    while _sop_id_owned_by_other_tenant(f"{cand}_{n}", tenant_id):
        n += 1
    return f"{cand}_{n}"


def _latest_jobs_by_sha(tenant_id: str):
    """Selects the latest non-duplicate job per content SHA-256 within `tenant_id`."""
    non_dup = {}
    dup_only = {}
    for job in list(governance_ledger._jobs.values()):
        if job.tenant_id != tenant_id:
            continue
        sha = job.content_sha256
        ts = job.updated_at or job.created_at or ""
        if job.current_state == "duplicate":
            prev = dup_only.get(sha)
            if prev is None or ts >= (prev.updated_at or prev.created_at or ""):
                dup_only[sha] = job
            continue
        prev = non_dup.get(sha)
        if prev is None or ts >= (prev.updated_at or prev.created_at or ""):
            non_dup[sha] = job
    merged = dict(dup_only)
    merged.update(non_dup)
    return merged


async def api_list_uploads(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER, ROLE_ADMIN),
        human_only=True,
        check_csrf=False,
    )
    tenant_id = principal.tenant_id
    manifest = read_manifest()
    manifest_updated = False
    files = []

    pub_by_sop_id, pub_by_sha = _build_published_index(tenant_id)
    latest_jobs_by_sha = _latest_jobs_by_sha(tenant_id)

    # Build draft index scoped strictly to caller's tenant
    drafts_by_file = {}
    if os.path.exists(DRAFTS_DIR):
        for df_name in os.listdir(DRAFTS_DIR):
            if df_name.endswith(".draft.json"):
                df_path = os.path.join(DRAFTS_DIR, df_name)
                try:
                    mtime = os.stat(df_path).st_mtime
                    with open(df_path, "r", encoding="utf-8") as f:
                        d_data = json.load(f)
                    d_sid = d_data.get("sop_id") or os.path.splitext(df_name)[0].replace(".draft", "")
                    d_meta = resolve_draft_access_meta(d_sid, draft_data=d_data)
                    if d_meta["tenant_id"] != tenant_id:
                        continue
                    raw_fn = d_data.get("raw_filename")
                    if raw_fn and (raw_fn not in drafts_by_file or mtime >= drafts_by_file[raw_fn]["mtime"]):
                        drafts_by_file[raw_fn] = {
                            "sop_id": d_sid,
                            "task_id": d_data.get("task_id"),
                            "job_id": d_data.get("job_id"),
                            "mtime": mtime,
                            "modified": datetime.datetime.fromtimestamp(mtime).isoformat(),
                        }
                except Exception:
                    pass

    for name, full_path in list_tenant_uploads(tenant_id):
        stat = os.stat(full_path)
        ext = os.path.splitext(name)[1].lower()
        file_sha = _sha256_file(full_path, stat)
        _m_key, manifest_info = get_manifest_entry(manifest, tenant_id, name)
        manifest_sha = manifest_info.get("sha256")
        manifest_matches_sha = (not manifest_sha) or (manifest_sha == file_sha)

        latest_job = latest_jobs_by_sha.get(file_sha)
        pub_rec = pub_by_sha.get(file_sha)
        if not pub_rec and latest_job and latest_job.sop_id:
            cand = pub_by_sop_id.get(latest_job.sop_id.lower())
            if cand and latest_job.current_state == "published":
                pub_rec = cand
        if not pub_rec and manifest_matches_sha and manifest_info.get("sop_id"):
            cand = pub_by_sop_id.get(str(manifest_info["sop_id"]).lower())
            if cand and (manifest_info.get("published") or manifest_info.get("status") == "success"):
                pub_rec = cand
        if not pub_rec:
            cand = pub_by_sop_id.get(f"sop-{file_sha[:6].lower()}")
            if cand:
                pub_rec = cand

        playbook_exists = pub_rec is not None
        status = "pending"
        sop_id = None
        job_id = latest_job.job_id if latest_job else (manifest_info.get("job_id") if manifest_matches_sha else None)
        job_state = latest_job.current_state if latest_job else None
        task_id = ((latest_job.review_task or {}).get("task_id") if latest_job else None) or (
            manifest_info.get("task_id") if manifest_matches_sha else None
        )
        processed_at = manifest_info.get("processed_at") if manifest_matches_sha else None
        reason = None
        reingest_allowed = True

        if playbook_exists:
            status = "success"
            sop_id = pub_rec["sop_id"]
            processed_at = (
                (manifest_info.get("published_at") if manifest_matches_sha else None)
                or (latest_job.updated_at if latest_job else processed_at)
            )
            reingest_allowed = False
        elif latest_job and latest_job.current_state != "duplicate":
            js = latest_job.current_state
            sop_id = latest_job.sop_id
            processed_at = latest_job.updated_at or processed_at
            if js in ("awaiting_review", "changes_requested", "approved"):
                status = js
                if latest_job.approval_decision and js == "changes_requested":
                    reason = latest_job.approval_decision.get("notes")
                if manifest_info.get("status") == "success":
                    set_manifest_entry(manifest, tenant_id, name, {
                        "status": js,
                        "sop_id": sop_id,
                        "job_id": job_id,
                        "task_id": task_id,
                        "sha256": file_sha,
                        "tenant_id": tenant_id,
                        "processed_at": processed_at,
                    })
                    manifest_updated = True
            elif js == "rejected":
                hist_reason = (latest_job.history[-1].get("reason") if latest_job.history else "") or ""
                dec_notes = (latest_job.approval_decision or {}).get("notes") or ""
                if manifest_matches_sha and manifest_info.get("status") == "unactionable":
                    status = "unactionable"
                    reason = manifest_info.get("reason") or hist_reason
                else:
                    status = "rejected"
                    reason = dec_notes or hist_reason
            elif js == "quarantined":
                status = "quarantined"
                inc = latest_job.incident or {}
                reason = f"Quarantined ({inc.get('secrets_count', 0)} secret(s) detected)" if inc else "Secret gate quarantine"
            elif js in ("failed", "blocked"):
                status = "failed"
                reason = (latest_job.history[-1].get("reason") if latest_job.history else None) or "Pipeline execution failed"
            elif js in ("soft_deleted", "archived", "deactivated"):
                status = "pending"
                sop_id = None
            elif js == "published":
                status = "failed"
                reason = "Playbook file missing from disk (published record orphaned)"
            elif (tenant_id, name) in _INGESTS:
                status = "awaiting_review" if js == "assessing" else js
            else:
                status = "failed"
                reason = f"Interrupted in '{js}' state"
        elif name in drafts_by_file and manifest_matches_sha:
            d_info = drafts_by_file[name]
            status = "awaiting_review"
            sop_id = d_info.get("sop_id")
            task_id = task_id or d_info.get("task_id")
            job_id = job_id or d_info.get("job_id")
            processed_at = d_info.get("modified")
            if manifest_info.get("status") != "awaiting_review":
                set_manifest_entry(manifest, tenant_id, name, {
                    "status": "awaiting_review",
                    "sop_id": sop_id,
                    "job_id": job_id,
                    "task_id": task_id,
                    "sha256": file_sha,
                    "tenant_id": tenant_id,
                    "processed_at": processed_at,
                })
                manifest_updated = True
        elif manifest_info and manifest_matches_sha:
            m_stat = manifest_info.get("status", "pending")
            if m_stat == "success":
                status = "pending"
                sop_id = None
                if del_manifest_entry(manifest, tenant_id, name):
                    manifest_updated = True
            elif m_stat in ("awaiting_review", "changes_requested", "approved", "rejected", "quarantined", "failed", "unactionable"):
                status = m_stat
                sop_id = manifest_info.get("sop_id")
                reason = manifest_info.get("reason") or manifest_info.get("error")
        elif manifest_info and not manifest_matches_sha:
            if del_manifest_entry(manifest, tenant_id, name):
                manifest_updated = True

        is_valid_gate1, gate1_err, meta = validate_sop_file(full_path)

        files.append({
            "filename": name,
            "tenant_id": tenant_id,
            "extension": ext,
            "size_bytes": stat.st_size,
            "sha256": file_sha,
            "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "status": status,
            "sop_id": sop_id,
            "job_id": job_id,
            "job_state": job_state,
            "task_id": task_id,
            "playbook_exists": playbook_exists,
            "reingest_allowed": reingest_allowed and is_valid_gate1,
            "reason": reason,
            "processed_at": processed_at,
            "gate1_passed": is_valid_gate1,
            "gate1_error": gate1_err,
            "page_count": meta.get("page_count"),
            "mime_type": meta.get("mime_type"),
        })

    if manifest_updated:
        try:
            write_manifest(manifest)
        except Exception:
            pass

    return JSONResponse({
        "tenant_id": tenant_id,
        "files": files,
        "total_files": len(files),
        "allowed_extensions": sorted(list(get_allowed_extensions())),
        "max_size_mb": get_max_file_size_mb()
    })


async def api_upload_file(request: Request):
    """Receive uploaded file via bounded chunk streaming inside knowledge_base/_uploads/<tenant_id>/."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER,),
        human_only=True,
        check_csrf=True,
    )
    try:
        form = await request.form()
        upload = form.get("file")
        if not upload or not hasattr(upload, "filename"):
            return JSONResponse({"error": "No file uploaded"}, status_code=400)

        raw_filename = upload.filename
        safe_name = sanitize_filename(raw_filename)
        ext = os.path.splitext(safe_name)[1].lower()
        allowed_exts = get_allowed_extensions()

        if ext not in allowed_exts:
            return JSONResponse({
                "error": f"Unauthorized extension '{ext}'. Allowed: {', '.join(sorted(allowed_exts))}"
            }, status_code=400)

        max_bytes = get_max_file_size_bytes()
        max_mb = get_max_file_size_mb()
        chunks = []
        total_bytes = 0
        chunk_size = 65536
        while True:
            chunk = await upload.read(chunk_size)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                return JSONResponse({
                    "error": f"File size (>{total_bytes/(1024*1024):.1f}MB) exceeds {max_mb:.0f}MB limit."
                }, status_code=400)
            chunks.append(chunk)

        content = b"".join(chunks)
        dest_dir = tenant_uploads_dir(principal.tenant_id)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, safe_name)
        with open(dest_path, "wb") as f:
            f.write(content)

        file_sha = hashlib.sha256(content).hexdigest()
        record_upload_owner(principal.tenant_id, safe_name, principal.identity, sha256=file_sha)

        is_valid, err, meta = validate_sop_file(dest_path)

        return JSONResponse({
            "success": True,
            "filename": safe_name,
            "tenant_id": principal.tenant_id,
            "uploaded_by": principal.identity,
            "size_bytes": len(content),
            "gate1_passed": is_valid,
            "gate1_error": err,
            "metadata": meta
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


class _IngestControl:
    def __init__(self, actor: str):
        self.event = threading.Event()
        self.actor = actor


_INGESTS: dict = {}  # (tenant_id, safe_name) -> _IngestControl


def _begin_ingest(tenant_id: str, name: str, actor: str):
    key = (tenant_id, name)
    if key in _INGESTS:
        return None
    ctl = _INGESTS[key] = _IngestControl(actor)
    return ctl


def _end_ingest(tenant_id: str, name: str, ctl) -> None:
    key = (tenant_id, name)
    if _INGESTS.get(key) is ctl:
        del _INGESTS[key]


async def _wait_for(event: threading.Event) -> None:
    while not event.is_set():
        await asyncio.sleep(0.2)


def _swallow(task) -> None:
    if not task.cancelled():
        task.exception()


async def _run_cancellable(ctl, fn, *args, **kwargs):
    if ctl.event.is_set():
        raise IngestionCancelled()

    def call():
        token = bind_cancel(ctl.event)
        try:
            return fn(*args, **kwargs)
        finally:
            reset_cancel(token)

    work = asyncio.ensure_future(run_in_threadpool(call))
    watcher = asyncio.ensure_future(_wait_for(ctl.event))
    done, _ = await asyncio.wait({work, watcher}, return_when=asyncio.FIRST_COMPLETED)
    if work in done:
        watcher.cancel()
        return work.result()
    work.add_done_callback(_swallow)
    raise IngestionCancelled()


async def api_cancel_ingest(request: Request):
    """Ask a running ingestion in caller's tenant to stop."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER,),
        human_only=True,
        check_csrf=True,
    )
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = sanitize_filename(os.path.basename(str(body.get("filename", "")).strip()))
    ctl = _INGESTS.get((principal.tenant_id, name))
    if not ctl:
        return JSONResponse({"status": "not_running", "filename": name})
    # Never trust actor from body
    ctl.actor = principal.identity
    ctl.event.set()
    return JSONResponse({"status": "cancelling", "filename": name, "cancelled_by": principal.identity})


async def api_ingest_single(request: Request):
    """Trigger complete 14-state lifecycle processing for a single tenant-owned upload."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER,),
        human_only=True,
        check_csrf=True,
    )
    try:
        body = await request.json()
    except Exception:
        body = {}

    filename = str(body.get("filename", "")).strip()
    if not filename:
        return JSONResponse({"error": "filename is required"}, status_code=400)

    safe_name = sanitize_filename(os.path.basename(filename))
    target_path = resolve_tenant_upload(principal.tenant_id, safe_name)

    if not target_path or not os.path.exists(target_path):
        return JSONResponse({"error": f"File '{safe_name}' not found in uploads directory"}, status_code=404)

    is_valid, err_msg, meta = validate_sop_file(target_path)
    if not is_valid:
        return JSONResponse({
            "success": False,
            "status": "REJECTED_GATE_1",
            "reason": f"Input validation rejected: {err_msg}",
            "metadata": meta
        }, status_code=400)

    # Ignore body.uploaded_by & body.tenant_id strictly; derive both from token!
    actor = principal.identity
    tenant_id = principal.tenant_id

    ctl = _begin_ingest(tenant_id, safe_name, actor)
    if ctl is None:
        return JSONResponse({
            "success": False,
            "status": "already_running",
            "error": f"'{safe_name}' is already being processed."
        }, status_code=409)

    job = None
    job_id = None
    content_hash = None
    try:
        override_sop_id = body.get("sop_id")
        reingest = bool(body.get("reingest", False))

        with open(target_path, "rb") as f:
            content_bytes = f.read()
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        sop_id = _allocate_sop_id(content_hash, tenant_id, override_sop_id=override_sop_id)

        pub_by_sop_id, pub_by_sha = _build_published_index(tenant_id)
        live_pub = pub_by_sha.get(content_hash) or pub_by_sop_id.get(sop_id.lower())
        if live_pub:
            return JSONResponse({
                "success": False,
                "status": "duplicate",
                "sop_id": live_pub["sop_id"],
                "message": f"Playbook {live_pub['sop_id']} is already published on disk. Delete the playbook first before re-ingesting.",
            }, status_code=409)

        if reingest:
            for existing in list(governance_ledger._jobs.values()):
                if (
                    existing.tenant_id == tenant_id
                    and existing.content_sha256 == content_hash
                    and existing.current_state == "published"
                ):
                    try:
                        governance_ledger.transition_state(
                            existing.job_id,
                            "soft_deleted",
                            actor=actor,
                            reason="Rescued orphaned published ledger record during re-ingestion (playbook absent on disk).",
                        )
                    except Exception:
                        pass

        job_id = _allocate_job_id(content_hash)

        parser_type, segments = await _run_cancellable(ctl, extract_ordered_sop_content, target_path)
        raw_text = "\n\n".join(s["content"] for s in segments if s.get("type") == "text")

        _, dlp_stats = redact_sensitive_dlp(raw_text)
        secrets_count = dlp_stats.get("passwords", 0) + dlp_stats.get("api_keys", 0) + dlp_stats.get("private_keys", 0)

        job = governance_ledger.start_job(
            job_id=job_id,
            sop_id=sop_id,
            tenant_id=tenant_id,
            content_sha256=content_hash,
            uploaded_by=actor,
            allow_supersede=reingest,
        )

        if job.current_state == "duplicate":
            return JSONResponse({
                "success": False,
                "status": "duplicate",
                "job_id": job.job_id,
                "message": "Duplicate document detected (matches existing processed or awaiting-review record).",
            }, status_code=409)

        if reingest and os.path.exists(DRAFTS_DIR):
            for df_name in os.listdir(DRAFTS_DIR):
                if not df_name.endswith(".draft.json"):
                    continue
                df_path = os.path.join(DRAFTS_DIR, df_name)
                try:
                    with open(df_path, "r", encoding="utf-8") as df:
                        d_data = json.load(df)
                    d_sid = d_data.get("sop_id") or os.path.splitext(df_name)[0].replace(".draft", "")
                    if resolve_draft_access_meta(d_sid, draft_data=d_data)["tenant_id"] != tenant_id:
                        continue
                    remove_it = df_name == f"{sop_id}.draft.json" or d_data.get("raw_filename") == safe_name
                    if remove_it:
                        os.remove(df_path)
                except Exception:
                    pass

        governance_ledger.transition_state(job_id, "extracting")
        governance_ledger.transition_state(job_id, "scanning")

        # Secret Gate Quarantine Check
        if secrets_count > 0:
            secret_types = [k for k, v in dlp_stats.items() if v > 0 and k in ("passwords", "api_keys", "private_keys")]
            incident = governance_ledger.trigger_quarantine(
                job_id=job_id,
                secrets_count=secrets_count,
                secret_types=secret_types,
            )
            try:
                cur_manifest = read_manifest()
                d1 = del_manifest_entry(cur_manifest, tenant_id, safe_name)
                d2 = del_manifest_entry(cur_manifest, tenant_id, os.path.basename(target_path))
                if d1 or d2:
                    write_manifest(cur_manifest)
            except Exception:
                pass
            # H3: actually remove the secret-bearing upload and any parser/image artifacts
            # written for it (the ledger incident ticket stays as the metadata record).
            try:
                os.remove(target_path)
            except OSError:
                pass
            try:
                from agents.a1_ingestion.document_extractor import LOGS_PARSER_DIR
                for name_cand in {safe_name, os.path.basename(target_path)}:
                    for lf in glob.glob(os.path.join(LOGS_PARSER_DIR, f"*_{glob.escape(name_cand)}.log")):
                        try:
                            os.remove(lf)
                        except OSError:
                            pass
            except Exception:
                pass
            try:
                import shutil
                from agents.a1_ingestion.vlm_extractor import IMAGES_LOG_DIR
                raw_base = os.path.splitext(safe_name)[0]
                img_slug = re.sub(r"[^A-Za-z0-9]+", "-", raw_base).strip("-").upper()[:20]
                if img_slug:
                    img_dir = os.path.join(IMAGES_LOG_DIR, img_slug)
                    if os.path.isdir(img_dir):
                        shutil.rmtree(img_dir, ignore_errors=True)
            except Exception:
                pass
            return JSONResponse({
                "success": False,
                "status": "quarantined",
                "incident_id": incident.incident_id,
                "job_id": job.job_id,
                "error": f"Live credentials detected ({secrets_count}). Terminal quarantine triggered; file content purged. 0 AI calls made.",
                "incident": incident.__dict__,
            }, status_code=403)

        # Stage 2 AST Sandbox Check
        ast_threats = scan_raw_sop_for_ast_threats(raw_text)
        if ast_threats:
            unique_descs = list(dict.fromkeys(
                t.get("description", "Malicious command or injection payload")
                for t in ast_threats
            ))
            block_reason = (
                f"AST Sandbox blocked Stage 2 ingestion ({len(ast_threats)} threat(s)): "
                + "; ".join(unique_descs[:3])
            )
            governance_ledger.transition_state(
                job_id,
                "blocked",
                actor="A3_ast_sandbox",
                reason=block_reason,
                details={"ast_threats": ast_threats},
            )
            try:
                cur_manifest = read_manifest()
                set_manifest_entry(cur_manifest, tenant_id, safe_name, {
                    "status": "failed",
                    "error_code": "ast_threat_detected",
                    "reason": block_reason,
                    "error": block_reason,
                    "job_id": job.job_id,
                    "sop_id": sop_id,
                    "sha256": content_hash,
                    "tenant_id": tenant_id,
                    "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                })
                write_manifest(cur_manifest)
            except Exception:
                pass
            return JSONResponse({
                "success": False,
                "status": "blocked",
                "error_code": "ast_threat_detected",
                "job_id": job.job_id,
                "ast_threats": ast_threats,
                "error": f"{block_reason}. 0 AI calls made.",
            }, status_code=403)

        governance_ledger.transition_state(job_id, "structuring")

        draft = await _run_cancellable(
            ctl,
            jit_converter.plan_okf_from_raw,
            target_path,
            override_sop_id=sop_id,
            pre_extracted_text=raw_text,
        )

        if isinstance(draft, dict) and not draft.get("raw_text"):
            draft["raw_text"] = raw_text

        if draft.get("is_executable") is False or draft.get("frontmatter", {}).get("is_executable") is False:
            unexec_reason = (
                draft.get("unexecutable_reason")
                or draft.get("frontmatter", {}).get("unexecutable_reason")
                or "SOP is not actionable as an automated procedure."
            )
            governance_ledger.transition_state(job_id, "rejected", reason=unexec_reason)
            try:
                cur_manifest = read_manifest()
                set_manifest_entry(cur_manifest, tenant_id, safe_name, {
                    "status": "unactionable",
                    "reason": unexec_reason,
                    "job_id": job.job_id,
                    "sop_id": sop_id,
                    "sha256": content_hash,
                    "tenant_id": tenant_id,
                    "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                })
                write_manifest(cur_manifest)
            except Exception:
                pass
            return JSONResponse({
                "success": False,
                "status": "unactionable",
                "reason": unexec_reason,
                "job_id": job.job_id,
            }, status_code=200)

        governance_ledger.transition_state(job_id, "assessing")

        is_ocr = "ocr" in str(parser_type).lower()
        canonical_draft = await _run_cancellable(
            ctl,
            build_canonical_sop_from_draft,
            draft,
            raw_text=raw_text,
            tenant_id=tenant_id,
            uploaded_by=actor,
            vlm_reports=draft.get("vlm_reports") if isinstance(draft, dict) else None,
            dlp_stats=dlp_stats,
            is_ocr=is_ocr,
        )
        if isinstance(canonical_draft.get("source"), dict):
            canonical_draft["source"]["file_sha256"] = content_hash

        conf_score = canonical_draft.get("classification", {}).get("score", 25)
        conf_level = canonical_draft.get("classification", {}).get("level", "L1")

        if ctl.event.is_set():
            raise IngestionCancelled()

        task = governance_ledger.create_review_task(
            job_id=job_id,
            confidentiality_score=conf_score,
            confidentiality_level=conf_level,
        )

        draft_save_path = os.path.join(DRAFTS_DIR, f"{sop_id}.draft.json")
        with open(draft_save_path, "w", encoding="utf-8") as df:
            json.dump({
                "draft": draft,
                "canonical_draft": canonical_draft,
                "raw_filename": safe_name,
                "tenant_id": tenant_id,
                "uploaded_by": actor,
                "task_id": task.task_id,
                "job_id": job_id,
                "sop_id": sop_id,
            }, df, indent=2)

        try:
            cur_manifest = read_manifest()
            set_manifest_entry(cur_manifest, tenant_id, safe_name, {
                "status": "awaiting_review",
                "sop_id": sop_id,
                "job_id": job_id,
                "task_id": task.task_id,
                "sha256": content_hash,
                "tenant_id": tenant_id,
                "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
            write_manifest(cur_manifest)
        except Exception:
            pass

        # Write Debug Audit Trace & record tenant ownership
        try:
            os.makedirs(LOGS_DIR, exist_ok=True)
            now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            clean_stem = os.path.splitext(safe_name)[0]
            debug_log_name = f"{now_str}_{clean_stem}_full_debug.log"
            debug_log_path = os.path.join(LOGS_DIR, debug_log_name)
            steps_list = (draft.get("frontmatter") or draft).get("steps", [])
            log_lines = [
                "=" * 70,
                "  SOP INGESTION PIPELINE — FULL REASONING & EXECUTION AUDIT TRACE",
                "=" * 70,
                f"  Job ID:               {job_id}",
                f"  SOP ID:               {sop_id}",
                f"  Source Document:      {safe_name}",
                f"  Content SHA-256:      {content_hash}",
                f"  Tenant ID:            {tenant_id}",
                f"  Uploaded By:          {actor}",
                f"  Execution Time:       {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
                "=" * 70,
                "",
                "--- PHASE 1: EXTRACTION & PARSING (AGENT A1) ---",
                f"  Parser Engine:        {parser_type}",
                f"  Extracted Segments:   {len(segments)}",
                f"  Raw Text Length:      {len(raw_text)} chars",
                "",
                "--- PHASE 2: SECURITY & DLP SCANNING (AGENT A3) ---",
                f"  Detected Secrets:     {secrets_count}",
                f"  AST Threats Detected: {len(ast_threats)}",
                f"  DLP Statistics:       {json.dumps(dlp_stats)}",
                "  Quarantine Status:    PASSED (Clean)",
                "",
                "--- PHASE 3: JIT PLAYBOOK PLANNING & REASONING (AGENT A2) ---",
                f"  Execution Mode:       {'Automated' if draft.get('is_executable', True) else 'Manual/Unactionable'}",
                f"  Planned Steps Count:  {len(steps_list)}",
                "",
                "  Generated Execution Steps:",
            ]
            for st in steps_list:
                log_lines.append(f"    • Step {st.get('step_number')}: {st.get('sop_step_description')}")
                log_lines.append(f"      - Command/Action: {st.get('command') or st.get('function_name')}")
                if st.get("step_reasoning"):
                    log_lines.append(f"      - Reasoning:      {st.get('step_reasoning')}")
                if st.get("source_quote"):
                    log_lines.append(f"      - Source Quote:   \"{st.get('source_quote')}\"")
            log_lines.extend([
                "",
                "--- PHASE 4: VERIFICATION & QUALITY SCORING (AGENT A4) ---",
                f"  Quality Status:       {canonical_draft.get('quality', {}).get('status', 'Unknown')}",
                f"  Quality Score:        {canonical_draft.get('quality', {}).get('quality_score')}%",
                f"  Completeness:         {canonical_draft.get('quality', {}).get('completeness')}%",
                f"  Quote Traceability:   {canonical_draft.get('quality', {}).get('traceability')}%",
                "",
                "--- PHASE 5: GOVERNANCE & HITL REVIEW GATE (AGENT A5) ---",
                f"  Review Task ID:       {task.task_id}",
                f"  Assigned Role:        {task.assigned_role}",
                f"  Due Date:             {task.due_date}",
                f"  Confidentiality:      Tier {conf_level} (Score: {conf_score})",
                f"  Lifecycle State:      {job.current_state}",
                "=" * 70,
            ])
            with open(debug_log_path, "w", encoding="utf-8") as dlf:
                dlf.write("\n".join(log_lines))
            record_log_owner(debug_log_name, tenant_id)
        except Exception:
            pass

        return JSONResponse({
            "success": True,
            "status": "awaiting_review",
            "tenant_id": tenant_id,
            "uploaded_by": actor,
            "job_id": job.job_id,
            "sop_id": sop_id,
            "task_id": task.task_id,
            "assigned_role": task.assigned_role,
            "due_date": task.due_date,
            "confidentiality": canonical_draft.get("classification"),
            "quality": canonical_draft.get("quality"),
            "draft": draft,
            "canonical_draft": canonical_draft,
            "message": "SOP successfully structured and assessed. Security Reviewer sign-off required before publishing."
        })
    except IngestionCancelled:
        if job is not None and job.current_state != "duplicate":
            try:
                governance_ledger.transition_state(job_id, "failed", actor=ctl.actor, reason=f"Cancelled by {ctl.actor}")
            except Exception:
                pass
        return JSONResponse({
            "success": False,
            "status": "cancelled",
            "job_id": job.job_id if job is not None else None,
            "message": "Processing was stopped. Nothing was saved and no review task was created.",
        }, status_code=200)
    except Exception as e:
        if job is not None and job.current_state in {"received", "extracting", "scanning", "structuring", "assessing", "correcting"}:
            try:
                governance_ledger.transition_state(job_id, "failed", reason=str(e))
            except Exception:
                pass
        try:
            cur_manifest = read_manifest()
            set_manifest_entry(cur_manifest, tenant_id, safe_name, {
                "status": "failed",
                "error": str(e),
                "reason": str(e),
                "job_id": job.job_id if job is not None else None,
                "sha256": content_hash,
                "tenant_id": tenant_id,
                "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
            write_manifest(cur_manifest)
        except Exception:
            pass
        return JSONResponse({
            "success": False,
            "status": "INGESTION_ERROR",
            "error": str(e)
        }, status_code=500)
    finally:
        _end_ingest(tenant_id, safe_name, ctl)


async def api_run_scan_cycle(request: Request):
    authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER,),
        human_only=True,
        check_csrf=True,
    )
    return JSONResponse(
        {
            "success": False,
            "error_code": "UNGOVERNED_SCAN_DISABLED",
            "error": (
                "Batch directory scan (/api/uploads/scan) is disabled because it bypassed "
                "Agent A3 secret/AST quarantine, Agent A4 verification, and Agent A5 dual-custody "
                "HITL review. Ingest individual SOP documents through POST /api/uploads/ingest."
            ),
            "use_endpoint": "/api/uploads/ingest",
        },
        status_code=410,
    )


async def api_plan_preview(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER,),
        human_only=True,
        check_csrf=True,
    )
    try:
        body = await request.json()
    except Exception:
        body = {}

    filename = str(body.get("filename", "")).strip()
    if not filename:
        return JSONResponse({"error": "filename is required"}, status_code=400)

    safe_name = sanitize_filename(os.path.basename(filename))
    target_path = resolve_tenant_upload(principal.tenant_id, safe_name)

    if not target_path or not os.path.exists(target_path):
        return JSONResponse({"error": f"File '{safe_name}' not found"}, status_code=404)

    is_valid, err_msg, meta = validate_sop_file(target_path)
    if not is_valid:
        return JSONResponse({
            "success": False,
            "status": "REJECTED_GATE_1",
            "error": f"Input validation rejected: {err_msg}",
            "metadata": meta,
        }, status_code=400)

    try:
        _, segments = await run_in_threadpool(extract_ordered_sop_content, target_path)
        raw_text = "\n\n".join(s["content"] for s in segments if s.get("type") == "text")

        _, dlp_stats = redact_sensitive_dlp(raw_text)
        secrets_count = (
            dlp_stats.get("passwords", 0)
            + dlp_stats.get("api_keys", 0)
            + dlp_stats.get("private_keys", 0)
        )
        if secrets_count > 0:
            try:
                os.remove(target_path)
            except OSError:
                pass
            try:
                from agents.a1_ingestion.document_extractor import LOGS_PARSER_DIR
                for name_cand in {safe_name, os.path.basename(target_path)}:
                    for lf in glob.glob(os.path.join(LOGS_PARSER_DIR, f"*_{glob.escape(name_cand)}.log")):
                        try:
                            os.remove(lf)
                        except OSError:
                            pass
            except Exception:
                pass
            return JSONResponse({
                "success": False,
                "status": "quarantined",
                "error": f"Live credentials detected ({secrets_count}). Plan preview blocked and file purged. 0 AI calls made.",
            }, status_code=403)

        ast_threats = scan_raw_sop_for_ast_threats(raw_text)
        if ast_threats:
            return JSONResponse({
                "success": False,
                "status": "blocked",
                "error_code": "ast_threat_detected",
                "ast_threats": ast_threats,
                "error": f"AST Sandbox blocked plan preview ({len(ast_threats)} threat(s)). 0 AI calls made.",
            }, status_code=403)

        draft = await run_in_threadpool(
            jit_converter.plan_okf_from_raw,
            target_path,
            pre_extracted_text=raw_text,
        )
        return JSONResponse({
            "success": True,
            "draft": draft,
            "filename": safe_name,
            "tenant_id": principal.tenant_id,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


ingestion_router = APIRouter(tags=["Document Ingestion & Staging"])
ingestion_router.add_api_route("/api/uploads", api_list_uploads, methods=["GET"], summary="List Staged Uploads & Gate 1 Status")
ingestion_router.add_api_route("/api/uploads/upload", api_upload_file, methods=["POST"], summary="Upload Raw SOP File")
ingestion_router.add_api_route("/api/uploads/ingest", api_ingest_single, methods=["POST"], summary="Trigger Ingestion & Structuring Pipeline")
ingestion_router.add_api_route("/api/uploads/ingest/cancel", api_cancel_ingest, methods=["POST"], summary="Cancel Ingestion in Progress")
ingestion_router.add_api_route("/api/uploads/scan", api_run_scan_cycle, methods=["POST"], summary="Scan Uploads Directory for New Files")
ingestion_router.add_api_route("/api/plan-preview", api_plan_preview, methods=["POST"], summary="Dry-Run JIT Execution Plan Preview")

ingestion_routes = list(ingestion_router.routes)
