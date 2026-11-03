"""
Ingestion API Route Handlers
============================
Handles document uploads, Gate 1 validation, staging intake, and JIT plan preview.
"""

import os
import asyncio
import hashlib
import datetime
import threading
from starlette.concurrency import run_in_threadpool

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from starlette.routing import Route

from api.context import (
    UPLOADS_DIR,
    DRAFTS_DIR,
    LOGS_DIR,
    MANIFEST_PATH,
    governance_ledger,
    read_manifest,
)
from utils.security import sanitize_filename, redact_sensitive_dlp
from utils.cancellation import IngestionCancelled, bind_cancel, reset_cancel
from config.settings import get_max_file_size_bytes, get_max_file_size_mb
from agents.a1_ingestion import (
    validate_sop_file,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    extract_ordered_sop_content,
)
import agents.a2_structuring.execution_planner as jit_converter
from agents.a2_structuring.canonical_builder import build_canonical_sop_from_draft
from scheduler import run_ingestion_cycle


async def api_list_uploads(request: Request):
    manifest = read_manifest()
    manifest_updated = False
    files = []

    # Build draft index: raw_filename -> {sop_id, modified}
    drafts_by_file = {}
    if os.path.exists(DRAFTS_DIR):
        for df_name in os.listdir(DRAFTS_DIR):
            if df_name.endswith(".draft.json"):
                df_path = os.path.join(DRAFTS_DIR, df_name)
                try:
                    with open(df_path, "r", encoding="utf-8") as f:
                        d_data = json.load(f)
                    raw_fn = d_data.get("raw_filename")
                    if raw_fn:
                        drafts_by_file[raw_fn] = {
                            "sop_id": d_data.get("sop_id"),
                            "modified": datetime.datetime.fromtimestamp(os.stat(df_path).st_mtime).isoformat(),
                        }
                except Exception:
                    pass

    if os.path.exists(UPLOADS_DIR):
        for name in os.listdir(UPLOADS_DIR):
            if name.startswith("_") or os.path.isdir(os.path.join(UPLOADS_DIR, name)):
                continue

            full_path = os.path.join(UPLOADS_DIR, name)
            stat = os.stat(full_path)
            ext = os.path.splitext(name)[1].lower()
            manifest_info = manifest.get(name, {})

            # Fallback: if not in manifest or status is pending, check if a draft exists
            if (not manifest_info or manifest_info.get("status") == "pending") and name in drafts_by_file:
                d_info = drafts_by_file[name]
                manifest_info = {
                    "status": "success",
                    "sop_id": d_info["sop_id"],
                    "processed_at": d_info["modified"],
                }
                manifest[name] = manifest_info
                manifest_updated = True

            # Pre-validate file against Gate 1
            is_valid_gate1, gate1_err, meta = validate_sop_file(full_path)

            files.append({
                "filename": name,
                "extension": ext,
                "size_bytes": stat.st_size,
                "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "status": manifest_info.get("status", "pending"),
                "sop_id": manifest_info.get("sop_id"),
                "processed_at": manifest_info.get("processed_at"),
                "gate1_passed": is_valid_gate1,
                "gate1_error": gate1_err,
                "page_count": meta.get("page_count"),
                "mime_type": meta.get("mime_type"),
            })

    if manifest_updated:
        try:
            with open(MANIFEST_PATH, "w", encoding="utf-8") as mf:
                json.dump(manifest, mf, indent=2)
        except Exception:
            pass

    return JSONResponse({
        "files": files,
        "total_files": len(files),
        "allowed_extensions": sorted(list(ALLOWED_EXTENSIONS)),
        "max_size_mb": get_max_file_size_mb()
    })


async def api_upload_file(request: Request):
    """Receive uploaded file and save to knowledge_base/_uploads/."""
    try:
        form = await request.form()
        upload = form.get("file")
        if not upload or not hasattr(upload, "filename"):
            return JSONResponse({"error": "No file uploaded"}, status_code=400)

        raw_filename = upload.filename
        safe_name = sanitize_filename(raw_filename)
        ext = os.path.splitext(safe_name)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            return JSONResponse({
                "error": f"Unauthorized extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            }, status_code=400)

        content = await upload.read()
        max_bytes = get_max_file_size_bytes()
        max_mb = get_max_file_size_mb()
        if len(content) > max_bytes:
            return JSONResponse({
                "error": f"File size ({len(content)/(1024*1024):.1f}MB) exceeds {max_mb:.0f}MB limit."
            }, status_code=400)

        dest_path = os.path.join(UPLOADS_DIR, safe_name)
        with open(dest_path, "wb") as f:
            f.write(content)

        # Immediate Gate 1 validation check
        is_valid, err, meta = validate_sop_file(dest_path)

        return JSONResponse({
            "success": True,
            "filename": safe_name,
            "size_bytes": len(content),
            "gate1_passed": is_valid,
            "gate1_error": err,
            "metadata": meta
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Cancellation. An ingestion runs its slow LLM work in a worker thread, which cannot be killed
# mid-call. "Stop" therefore (1) sets a flag the pipeline checks before every LLM call and
# (2) lets this request return immediately; the thread stops at its next checkpoint and its
# result is discarded. Everything that is saved happens in this request, after the thread.
# ---------------------------------------------------------------------------

class _IngestControl:
    def __init__(self, actor: str):
        self.event = threading.Event()
        self.actor = actor


_INGESTS: dict = {}          # safe filename -> _IngestControl, for ingestions currently running


def _begin_ingest(name: str, actor: str):
    if name in _INGESTS:
        return None
    ctl = _INGESTS[name] = _IngestControl(actor)
    return ctl


def _end_ingest(name: str, ctl) -> None:
    if _INGESTS.get(name) is ctl:
        del _INGESTS[name]


async def _wait_for(event: threading.Event) -> None:
    while not event.is_set():
        await asyncio.sleep(0.2)


def _swallow(task) -> None:
    """Ignore the outcome of a worker thread whose result nobody is waiting for any more."""
    if not task.cancelled():
        task.exception()


async def _run_cancellable(ctl, fn, *args, **kwargs):
    """Run blocking `fn` in a worker thread; give control back at once if the user cancels."""
    if ctl.event.is_set():
        raise IngestionCancelled()

    def call():
        token = bind_cancel(ctl.event)       # lets the pipeline's check_cancelled() see this flag
        try:
            return fn(*args, **kwargs)
        finally:
            reset_cancel(token)

    work = asyncio.ensure_future(run_in_threadpool(call))
    watcher = asyncio.ensure_future(_wait_for(ctl.event))
    done, _ = await asyncio.wait({work, watcher}, return_when=asyncio.FIRST_COMPLETED)
    if work in done:
        watcher.cancel()
        return work.result()                 # re-raises the worker's own error, if any
    work.add_done_callback(_swallow)         # cancelled: the thread winds down in the background
    raise IngestionCancelled()


async def api_cancel_ingest(request: Request):
    """Ask a running ingestion to stop. Body: {"filename": "...", "actor": "<who>"}."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = sanitize_filename(os.path.basename(str(body.get("filename", "")).strip()))
    ctl = _INGESTS.get(name)
    if not ctl:
        return JSONResponse({"status": "not_running", "filename": name})
    actor = str(body.get("actor", "")).strip()
    if actor:
        ctl.actor = actor
    ctl.event.set()
    return JSONResponse({"status": "cancelling", "filename": name})


async def api_ingest_single(request: Request):
    """Trigger complete 14-state lifecycle processing for a single uploaded document.
    Enforces secret scanning and human-in-the-loop review gate (halts before saving to sops/).
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    filename = body.get("filename", "").strip()
    if not filename:
        return JSONResponse({"error": "filename is required"}, status_code=400)

    # Sanitize and resolve file path
    safe_name = sanitize_filename(os.path.basename(filename))
    target_path = os.path.join(UPLOADS_DIR, safe_name)

    if not os.path.exists(target_path):
        return JSONResponse({"error": f"File '{safe_name}' not found in uploads directory"}, status_code=404)

    # Gate 1 check
    is_valid, err_msg, meta = validate_sop_file(target_path)
    if not is_valid:
        return JSONResponse({
            "success": False,
            "status": "REJECTED_GATE_1",
            "reason": f"Input validation rejected: {err_msg}",
            "metadata": meta
        }, status_code=400)

    ctl = _begin_ingest(safe_name, body.get("uploaded_by", "analyst@example.com"))
    if ctl is None:
        return JSONResponse({"success": False, "status": "already_running",
                             "error": f"'{safe_name}' is already being processed."}, status_code=409)
    job = None
    job_id = None
    try:
        auto_approve = body.get("auto_approve", False)
        override_sop_id = body.get("sop_id")

        with open(target_path, "rb") as f:
            content_bytes = f.read()
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        tenant_id = body.get("tenant_id", "tn_northwind")
        job_id = f"job_{content_hash[:10]}"
        sop_id = override_sop_id or f"SOP-{content_hash[:6].upper()}"


        parser_type, segments = await _run_cancellable(ctl, extract_ordered_sop_content, target_path)
        raw_text = "\n\n".join(s["content"] for s in segments if s.get("type") == "text")

        # Secret Scanning Gate (Section 10)
        _, dlp_stats = redact_sensitive_dlp(raw_text)
        secrets_count = dlp_stats.get("passwords", 0) + dlp_stats.get("api_keys", 0) + dlp_stats.get("private_keys", 0)

        job = governance_ledger.start_job(
            job_id=job_id,
            sop_id=sop_id,
            tenant_id=tenant_id,
            content_sha256=content_hash,
            uploaded_by=body.get("uploaded_by", "analyst@example.com"),
        )

        if job.current_state == "duplicate":
            return JSONResponse({
                "success": False,
                "status": "duplicate",
                "job_id": job.job_id,
                "message": "Duplicate document detected (matches existing processed record).",
            }, status_code=409)

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
            return JSONResponse({
                "success": False,
                "status": "quarantined",
                "incident_id": incident.incident_id,
                "job_id": job.job_id,
                "error": f"Live credentials detected ({secrets_count}). Terminal quarantine triggered; file content purged. 0 AI calls made.",
                "incident": incident.__dict__,
            }, status_code=403)

        governance_ledger.transition_state(job_id, "structuring")


        draft = await _run_cancellable(ctl, jit_converter.plan_okf_from_raw, target_path, override_sop_id=override_sop_id, pre_extracted_text=raw_text)


        if draft.get("is_executable") is False or draft.get("frontmatter", {}).get("is_executable") is False:
            unexec_reason = draft.get("unexecutable_reason") or draft.get("frontmatter", {}).get("unexecutable_reason") or "SOP is not actionable as an automated procedure."
            governance_ledger.transition_state(job_id, "rejected", reason=unexec_reason)
            try:
                cur_manifest = read_manifest()
                cur_manifest[safe_name] = {
                    "status": "unactionable",
                    "reason": unexec_reason,
                    "job_id": job.job_id,
                    "processed_at": datetime.datetime.now().isoformat(),
                }
                with open(MANIFEST_PATH, "w", encoding="utf-8") as mf:
                    json.dump(cur_manifest, mf, indent=2)
            except Exception:
                pass
            return JSONResponse({
                "success": False,
                "status": "unactionable",
                "reason": unexec_reason,
                "job_id": job.job_id,
            }, status_code=200)

        governance_ledger.transition_state(job_id, "assessing")

        canonical_draft = await _run_cancellable(
            ctl,
            build_canonical_sop_from_draft,
            draft,
            raw_text=raw_text,
            tenant_id=tenant_id,
            uploaded_by=body.get("uploaded_by", "analyst@example.com"),
        )
        conf_score = canonical_draft.get("classification", {}).get("score", 25)
        conf_level = canonical_draft.get("classification", {}).get("level", "L1")

        if ctl.event.is_set():
            raise IngestionCancelled()

        # Human-in-the-Loop review gate (A5 Coordinator) — HALT HERE BEFORE COMMITTING TO DISK!
        task = governance_ledger.create_review_task(
            job_id=job_id,
            confidentiality_score=conf_score,
            confidentiality_level=conf_level,
        )

        import json
        draft_save_path = os.path.join(DRAFTS_DIR, f"{sop_id}.draft.json")
        with open(draft_save_path, "w", encoding="utf-8") as df:
            json.dump({
                "draft": draft,
                "canonical_draft": canonical_draft,
                "raw_filename": safe_name,
                "task_id": task.task_id,
                "job_id": job_id,
                "sop_id": sop_id,
            }, df, indent=2)

        # Update processed files manifest
        try:
            cur_manifest = read_manifest()
            cur_manifest[safe_name] = {
                "status": "success",
                "sop_id": sop_id,
                "job_id": job_id,
                "task_id": task.task_id,
                "processed_at": datetime.datetime.now().isoformat(),
            }
            with open(MANIFEST_PATH, "w", encoding="utf-8") as mf:
                json.dump(cur_manifest, mf, indent=2)
        except Exception:
            pass

        # Write Comprehensive Ingestion Audit & Debug Trace to knowledge_base/logs/debug/
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
                f"  Uploaded By:          {body.get('uploaded_by', 'analyst@example.com')}",
                f"  Execution Time:       {datetime.datetime.now().isoformat()}",
                "=" * 70,
                "",
                "--- PHASE 1: EXTRACTION & PARSING (AGENT A1) ---",
                f"  Parser Engine:        {parser_type}",
                f"  Extracted Segments:   {len(segments)}",
                f"  Raw Text Length:      {len(raw_text)} chars",
                "",
                "--- PHASE 2: SECURITY & DLP SCANNING (AGENT A3) ---",
                f"  Detected Secrets:     {secrets_count}",
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
                if st.get('step_reasoning'):
                    log_lines.append(f"      - Reasoning:      {st.get('step_reasoning')}")
                if st.get('source_quote'):
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
        except Exception:
            pass

        return JSONResponse({
            "success": True,
            "status": "awaiting_review",
            "job_id": job.job_id,
            "sop_id": sop_id,
            "task_id": task.task_id,
            "assigned_role": task.assigned_role,
            "due_date": task.due_date,
            "confidentiality": canonical_draft.get("classification"),
            "quality": canonical_draft.get("quality"),
            "draft": draft,
            "canonical_draft": canonical_draft,
            "message": "SOP successfully structured and assessed. Human review required before saving to knowledge base."
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
        return JSONResponse({
            "success": False,
            "status": "INGESTION_ERROR",
            "error": str(e)
        }, status_code=500)
    finally:
        _end_ingest(safe_name, ctl)


async def api_run_scan_cycle(request: Request):
    try:
        summary = run_ingestion_cycle()
        return JSONResponse({
            "success": True,
            "summary": summary,
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


async def api_plan_preview(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    filename = body.get("filename", "").strip()
    if not filename:
        return JSONResponse({"error": "filename is required"}, status_code=400)

    safe_name = sanitize_filename(os.path.basename(filename))
    target_path = os.path.join(UPLOADS_DIR, safe_name)

    if not os.path.exists(target_path):
        return JSONResponse({"error": f"File '{safe_name}' not found"}, status_code=404)

    try:
        draft = await run_in_threadpool(jit_converter.plan_okf_from_raw, target_path)
        return JSONResponse({
            "success": True,
            "draft": draft,
            "filename": safe_name
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

