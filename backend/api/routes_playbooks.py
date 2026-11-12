"""
Playbooks API Route Handlers
============================
Handles OKF playbook listing, details, cryptographic HMAC-SHA256 integrity verification,
and tenant/clearance-enforced soft deletion (admin & process_owner only).
"""

import os
import re
import glob
import json
import shutil
import datetime
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.context import (
    KB_DIR,
    SOPS_DIR,
    PATTERNS_DIR,
    PROJECT_ROOT,
    DRAFTS_DIR,
    read_manifest,
    write_manifest,
    governance_ledger,
    retrieval_index,
    parse_yaml_frontmatter,
    resolve_sop_access_meta,
    _build_canonical_meta_map,
    _inside,
)
from auth.config import get_default_tenant
from auth.models import (
    ROLE_SET,
    ROLE_ADMIN,
    ROLE_PROCESS_OWNER,
)
from auth.dependencies import (
    AuthAccessError,
    authenticate_request,
    enforce_tenant_access,
    enforce_clearance_access,
)
from utils.security import verify_playbook_before_execution

# Deleted playbooks are moved here (never erased) so a mistaken delete can be undone by hand.
TRASH_DIR = os.path.join(KB_DIR, "_trash")
_SOP_ID_RE = re.compile(r"[A-Za-z0-9_-]+")


def _rel(path: str) -> str:
    """Project-relative path for display; falls back to the full path if it is on another drive."""
    try:
        return os.path.relpath(path, PROJECT_ROOT).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


async def api_list_sops(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=ROLE_SET,
        human_only=False,
        check_csrf=False,
    )
    canonical_map = _build_canonical_meta_map()
    playbook_files = glob.glob(os.path.join(SOPS_DIR, "**", "*.md"), recursive=True)
    playbooks = []

    for path in playbook_files:
        if os.path.basename(path).lower() == "index.md":
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            frontmatter, _ = parse_yaml_frontmatter(content)
            category = frontmatter.get("category", os.path.basename(os.path.dirname(path)))
            sop_id = frontmatter.get("sop_id", os.path.splitext(os.path.basename(path))[0])

            access_meta = resolve_sop_access_meta(
                sop_id,
                canonical_map=canonical_map,
                frontmatter=frontmatter,
            )
            if access_meta["tenant_id"] != principal.tenant_id:
                continue
            if not principal.can_access_tier(access_meta["classification_level"]):
                continue
            if not principal.is_human and access_meta.get("state") != "published":
                continue

            # Integrity verification
            is_valid_sig, sig_reason, _ = verify_playbook_before_execution(path)

            playbooks.append({
                "sop_id": sop_id,
                "title": frontmatter.get("title", sop_id),
                "platform": frontmatter.get("platform", "system"),
                "category": category,
                "target_os": frontmatter.get("target_os", "windows"),
                "description": frontmatter.get("description", ""),
                "tenant_id": access_meta["tenant_id"],
                "classification_level": access_meta["classification_level"],
                "confidence_score": frontmatter.get("confidence_score", 0.95),
                "confidence_level": frontmatter.get("confidence_level", "High"),
                "step_count": len(frontmatter.get("steps", [])),
                "steps": frontmatter.get("steps", []),
                "file_path": _rel(path),
                "integrity": {
                    "is_valid": is_valid_sig,
                    "reason": sig_reason,
                    "status": "VALID_HMAC_SHA256" if is_valid_sig else "FAILED_VERIFICATION"
                }
            })
        except Exception as e:
            print(f"[API Error] Failed parsing playbook {path}: {e}")

    return JSONResponse({
        "playbooks": playbooks,
        "total": len(playbooks)
    })


async def api_get_sop(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=ROLE_SET,
        human_only=False,
        check_csrf=False,
    )
    sop_id = request.path_params.get("sop_id", "").strip()
    clean_id = sop_id.replace(".md", "")
    if not clean_id or clean_id.lower() == "index" or not _SOP_ID_RE.fullmatch(clean_id):
        return JSONResponse({"error": "Invalid SOP id."}, status_code=400)

    playbook_files = glob.glob(os.path.join(SOPS_DIR, "**", "*.md"), recursive=True)
    target_path = None
    for p in playbook_files:
        name = os.path.splitext(os.path.basename(p))[0]
        if name.lower() == clean_id.lower() or os.path.basename(p).lower() == f"{clean_id.lower()}.md":
            target_path = p
            break

    if not target_path or not os.path.exists(target_path):
        return JSONResponse({"error": f"SOP '{sop_id}' not found"}, status_code=404)

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()

        frontmatter, body = parse_yaml_frontmatter(content)
        real_sop_id = frontmatter.get("sop_id", clean_id)
        access_meta = resolve_sop_access_meta(real_sop_id, frontmatter=frontmatter)

        enforce_tenant_access(principal, access_meta["tenant_id"], request=request)
        enforce_clearance_access(principal, access_meta["classification_level"], request=request)
        if not principal.is_human and access_meta.get("state") != "published":
            raise AuthAccessError(403, "Agents may only read published playbooks.", "not_authorized")

        category = frontmatter.get("category", os.path.basename(os.path.dirname(target_path)))

        is_valid_sig, sig_reason, _ = verify_playbook_before_execution(target_path)

        rulebook_path = os.path.join(PATTERNS_DIR, category, f"rules_{real_sop_id}.md")
        rulebook_content = None
        if os.path.exists(rulebook_path):
            with open(rulebook_path, "r", encoding="utf-8") as rf:
                rulebook_content = rf.read()

        return JSONResponse({
            "sop_id": real_sop_id,
            "tenant_id": access_meta["tenant_id"],
            "classification_level": access_meta["classification_level"],
            "frontmatter": frontmatter,
            "markdown_body": body,
            "raw_content": content,
            "steps": frontmatter.get("steps", []),
            "file_path": _rel(target_path),
            "integrity": {
                "is_valid": is_valid_sig,
                "status": "VALID_HMAC_SHA256" if is_valid_sig else "FAILED_VERIFICATION",
                "reason": sig_reason,
            },
            "rulebook": {
                "exists": os.path.exists(rulebook_path),
                "path": _rel(rulebook_path) if os.path.exists(rulebook_path) else None,
                "content": rulebook_content,
            }
        })
    except AuthAccessError:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_verify_sop_integrity(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=ROLE_SET,
        human_only=False,
        check_csrf=True,
    )
    sop_id = request.path_params.get("sop_id", "").strip()
    clean_id = sop_id.replace(".md", "")
    if not clean_id or clean_id.lower() == "index" or not _SOP_ID_RE.fullmatch(clean_id):
        return JSONResponse({"error": "Invalid SOP id."}, status_code=400)

    playbook_files = glob.glob(os.path.join(SOPS_DIR, "**", "*.md"), recursive=True)
    target_path = None
    for p in playbook_files:
        name = os.path.splitext(os.path.basename(p))[0]
        if name.lower() == clean_id.lower() or os.path.basename(p).lower() == f"{clean_id.lower()}.md":
            target_path = p
            break

    if not target_path or not os.path.exists(target_path):
        return JSONResponse({"error": f"SOP '{sop_id}' not found"}, status_code=404)

    with open(target_path, "r", encoding="utf-8") as f:
        frontmatter, _ = parse_yaml_frontmatter(f.read())
    real_sop_id = frontmatter.get("sop_id", clean_id)
    access_meta = resolve_sop_access_meta(real_sop_id, frontmatter=frontmatter)

    enforce_tenant_access(principal, access_meta["tenant_id"], request=request)
    enforce_clearance_access(principal, access_meta["classification_level"], request=request)
    if not principal.is_human and access_meta.get("state") != "published":
        raise AuthAccessError(403, "Agents may only verify published playbooks.", "not_authorized")

    is_valid, reason, meta = verify_playbook_before_execution(target_path)
    return JSONResponse({
        "sop_id": real_sop_id,
        "tenant_id": access_meta["tenant_id"],
        "classification_level": access_meta["classification_level"],
        "is_valid": is_valid,
        "status": "AUTHENTIC" if is_valid else "TAMPERED_OR_CORRUPT",
        "reason": reason,
        "metadata": meta,
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })


async def api_delete_sop(request: Request):
    """Soft-deletes a playbook. Restricted strictly to 'admin' and 'process_owner' within matching tenant & clearance."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_ADMIN, ROLE_PROCESS_OWNER),
        human_only=True,
        check_csrf=True,
    )
    sop_id = request.path_params.get("sop_id", "").strip()
    clean_id = sop_id.replace(".md", "")
    if not clean_id or clean_id.lower() == "index" or not _SOP_ID_RE.fullmatch(clean_id):
        return JSONResponse({"error": "Invalid SOP id."}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    # Never trust actor or role from the client body; always derive from verified token.
    actor = principal.identity
    ledger_role = principal.ledger_delete_role() or "owner"
    reason = str(body.get("reason", "")).strip()

    playbooks = [
        p for p in glob.glob(os.path.join(SOPS_DIR, "**", "*.md"), recursive=True)
        if os.path.splitext(os.path.basename(p))[0].lower() == clean_id.lower()
    ]
    if not playbooks:
        return JSONResponse({"error": f"SOP '{sop_id}' not found"}, status_code=404)

    first_fm = {}
    try:
        with open(playbooks[0], "r", encoding="utf-8") as f:
            first_fm, _ = parse_yaml_frontmatter(f.read())
    except Exception:
        pass
    access_meta = resolve_sop_access_meta(first_fm.get("sop_id", clean_id), frontmatter=first_fm)
    enforce_tenant_access(principal, access_meta["tenant_id"], request=request)
    enforce_clearance_access(principal, access_meta["classification_level"], request=request)

    files, catalog_ids, source_shas = set(playbooks), {clean_id}, set()
    for md in playbooks:
        try:
            with open(md, "r", encoding="utf-8") as f:
                fm, _ = parse_yaml_frontmatter(f.read())
            if fm.get("sop_id"):
                catalog_ids.add(str(fm["sop_id"]))
            if fm.get("source_sha256"):
                source_shas.add(str(fm["source_sha256"]))
        except Exception:
            pass
    for p in glob.glob(os.path.join(SOPS_DIR, "**", "*.canonical.json"), recursive=True):
        if os.path.basename(p)[: -len(".canonical.json")].lower() == clean_id.lower():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                c_tenant = cdata.get("tenant_id")
                if c_tenant and c_tenant != "default_tenant" and c_tenant != principal.tenant_id:
                    continue
                files.add(p)
                sha = cdata.get("source", {}).get("file_sha256") or cdata.get("source", {}).get("sha256")
                if sha:
                    source_shas.add(str(sha))
            except Exception:
                pass
    for p in glob.glob(os.path.join(PATTERNS_DIR, "**", "rules_*.md"), recursive=True):
        if os.path.splitext(os.path.basename(p))[0][len("rules_"):].lower() == clean_id.lower():
            files.add(p)
    files = sorted(f for f in files if _inside(f, KB_DIR))

    # Collect SHA hashes only from drafts in this tenant
    if os.path.exists(DRAFTS_DIR):
        for df_name in os.listdir(DRAFTS_DIR):
            if df_name.endswith(".draft.json"):
                df_path = os.path.join(DRAFTS_DIR, df_name)
                try:
                    with open(df_path, "r", encoding="utf-8") as df_file:
                        d_data = json.load(df_file)
                    d_tenant = (d_data.get("canonical_draft") or {}).get("tenant_id")
                    if d_tenant and d_tenant != "default_tenant" and d_tenant != principal.tenant_id:
                        continue
                    d_sop = str(d_data.get("sop_id", "")).lower()
                    d_canon = str(d_data.get("canonical_draft", {}).get("sop_id", "")).lower()
                    if clean_id.lower() in (d_sop, d_canon):
                        catalog_ids.add(d_data.get("sop_id", ""))
                        d_sha = d_data.get("canonical_draft", {}).get("source", {}).get("sha256")
                        if d_sha:
                            source_shas.add(str(d_sha))
                except Exception:
                    pass

    # 1. Move to trash (preserving relative paths) with a manifest.
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", clean_id)
    trash = os.path.join(TRASH_DIR, f"{stamp}_{safe_id}")
    moved, warnings = [], []
    try:
        for src in files:
            rel = os.path.relpath(src, KB_DIR)
            dst = os.path.join(trash, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            moved.append(rel.replace("\\", "/"))
        with open(os.path.join(trash, "_manifest.json"), "w", encoding="utf-8") as mf:
            json.dump({
                "sop_id": clean_id,
                "tenant_id": principal.tenant_id,
                "deleted_by": actor,
                "deleted_role": ledger_role,
                "reason": reason,
                "deleted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "files": moved,
                "source_shas": list(source_shas),
                "restore": "Copy each listed file from this folder back to the same relative path under knowledge_base/.",
            }, mf, indent=2)
    except Exception as e:
        return JSONResponse({"error": f"Delete failed while moving files: {e}", "moved_so_far": moved}, status_code=500)

    # 2. Stop downstream agents retrieving it.
    purged = any(retrieval_index.purge_sop(i, reason="deleted") for i in catalog_ids)

    # 3. Lifecycle: soft-delete matching tenant jobs ONLY via GovernanceLedger.soft_delete_sop (never bypass).
    soft_deleted = []
    all_target_ids = {clean_id.lower(), *[str(c).lower() for c in catalog_ids if c]}
    for job in list(governance_ledger._jobs.values()):
        if job.tenant_id != principal.tenant_id:
            continue
        matches_id = job.sop_id.lower() in all_target_ids or (
            job.review_task and str(job.review_task.get("sop_id", "")).lower() in all_target_ids
        )
        matches_sha = job.content_sha256 in source_shas
        if matches_id or matches_sha:
            try:
                governance_ledger.soft_delete_sop(job.job_id, actor=actor, role=ledger_role)
                soft_deleted.append(job.job_id)
            except Exception as e:
                warnings.append(f"Ledger: could not soft-delete job {job.job_id}: {e}")

    # 4. Refresh the index.md pages that listed it.
    try:
        from agents.a2_structuring.okf_builder import _update_sops_catalog_indexes
        _update_sops_catalog_indexes()
    except Exception as e:
        warnings.append(f"Index pages not refreshed: {e}")

    # 5. Clean processed manifest (tenant-scoped) and drafts so ingestion re-enables cleanly.
    try:
        manifest = read_manifest()
        prefix = f"{principal.tenant_id}::"
        is_default = principal.tenant_id == get_default_tenant()
        to_del = []
        for fn, info in manifest.items():
            if "::" in fn and not fn.startswith(prefix):
                continue
            if "::" not in fn and not is_default:
                continue
            info_sop = str((info or {}).get("sop_id", "")).lower()
            if info_sop in all_target_ids:
                to_del.append(fn)
        for fn in to_del:
            del manifest[fn]
        if to_del:
            write_manifest(manifest)

        if os.path.exists(DRAFTS_DIR):
            for df_name in os.listdir(DRAFTS_DIR):
                if df_name.endswith(".draft.json"):
                    df_path = os.path.join(DRAFTS_DIR, df_name)
                    try:
                        with open(df_path, "r", encoding="utf-8") as df_file:
                            d_data = json.load(df_file)
                        d_tenant = (d_data.get("canonical_draft") or {}).get("tenant_id")
                        if d_tenant and d_tenant != "default_tenant" and d_tenant != principal.tenant_id:
                            continue
                        d_sop = str(d_data.get("sop_id", "")).lower()
                        d_canon = str(d_data.get("canonical_draft", {}).get("sop_id", "")).lower()
                        d_sha = str(d_data.get("canonical_draft", {}).get("source", {}).get("sha256", ""))
                        if d_sop in all_target_ids or d_canon in all_target_ids or (d_sha and d_sha in source_shas):
                            dst_draft = os.path.join(trash, "_drafts", df_name)
                            os.makedirs(os.path.dirname(dst_draft), exist_ok=True)
                            shutil.move(df_path, dst_draft)
                    except Exception:
                        pass
    except Exception as e:
        warnings.append(f"Manifest cleanup notice: {e}")

    return JSONResponse({
        "status": "deleted",
        "sop_id": clean_id,
        "tenant_id": principal.tenant_id,
        "deleted_by": actor,
        "deleted_role": ledger_role,
        "moved": moved,
        "trash_dir": _rel(trash),
        "removed_from_agent_catalog": bool(purged),
        "jobs_soft_deleted": soft_deleted,
        "warnings": warnings,
    })


playbook_router = APIRouter(tags=["Playbooks & Canonical SOPs"])
playbook_router.add_api_route("/api/sops", api_list_sops, methods=["GET"], summary="List Canonical SOP Playbooks")
playbook_router.add_api_route("/api/sops/{sop_id}", api_get_sop, methods=["GET"], summary="Get SOP Details & Frontmatter")
playbook_router.add_api_route("/api/sops/{sop_id}", api_delete_sop, methods=["DELETE"], summary="Delete SOP Playbook")
playbook_router.add_api_route("/api/sops/{sop_id}/verify", api_verify_sop_integrity, methods=["POST"], summary="Verify SOP Cryptographic HMAC Integrity")

playbook_routes = list(playbook_router.routes)
