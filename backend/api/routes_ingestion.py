"""
Ingestion API Route Handlers
============================
Handles document uploads, Gate 1 validation, staging intake, and JIT plan preview.
"""

import os
import hashlib
import datetime
from starlette.responses import JSONResponse
from starlette.routing import Route

from api.context import (
    UPLOADS_DIR,
    DRAFTS_DIR,
    governance_ledger,
    read_manifest,
)
from utils.security import sanitize_filename, redact_sensitive_dlp
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


async def api_list_uploads(request):
    manifest = read_manifest()
    files = []

    if os.path.exists(UPLOADS_DIR):
        for name in os.listdir(UPLOADS_DIR):
            if name.startswith("_") or os.path.isdir(os.path.join(UPLOADS_DIR, name)):
                continue

            full_path = os.path.join(UPLOADS_DIR, name)
            stat = os.stat(full_path)
            ext = os.path.splitext(name)[1].lower()
            manifest_info = manifest.get(name, {})

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

    return JSONResponse({
        "files": files,
        "total_files": len(files),
        "allowed_extensions": sorted(list(ALLOWED_EXTENSIONS)),
        "max_size_mb": get_max_file_size_mb()
    })


async def api_upload_file(request):
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


async def api_ingest_single(request):
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

    try:
        auto_approve = body.get("auto_approve", False)
        override_sop_id = body.get("sop_id")

        with open(target_path, "rb") as f:
            content_bytes = f.read()
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        tenant_id = body.get("tenant_id", "tn_northwind")
        job_id = f"job_{content_hash[:10]}"
        sop_id = override_sop_id or f"SOP-{content_hash[:6].upper()}"

        raw_text, parse_meta = extract_ordered_sop_content(target_path)

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

        draft = jit_converter.plan_okf_from_raw(target_path, override_sop_id=override_sop_id)

        if draft.get("is_executable") is False or draft.get("frontmatter", {}).get("is_executable") is False:
            unexec_reason = draft.get("unexecutable_reason") or draft.get("frontmatter", {}).get("unexecutable_reason") or "SOP is not actionable as an automated procedure."
            governance_ledger.transition_state(job_id, "rejected", reason=unexec_reason)
            return JSONResponse({
                "success": False,
                "status": "unactionable",
                "reason": unexec_reason,
                "job_id": job.job_id,
            }, status_code=200)

        governance_ledger.transition_state(job_id, "assessing")

        canonical_draft = build_canonical_sop_from_draft(
            draft,
            raw_text=raw_text,
            tenant_id=tenant_id,
            uploaded_by=body.get("uploaded_by", "analyst@example.com"),
        )
        conf_score = canonical_draft.get("classification", {}).get("score", 25)
        conf_level = canonical_draft.get("classification", {}).get("level", "L1")

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
    except Exception as e:
        return JSONResponse({
            "success": False,
            "status": "INGESTION_ERROR",
            "error": str(e)
        }, status_code=500)


async def api_run_scan_cycle(request):
    try:
        summary = run_ingestion_cycle()
        return JSONResponse({
            "success": True,
            "summary": summary,
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


async def api_plan_preview(request):
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
        draft = jit_converter.plan_okf_from_raw(target_path)
        return JSONResponse({
            "success": True,
            "draft": draft,
            "filename": safe_name
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


ingestion_routes = [
    Route("/api/uploads", api_list_uploads, methods=["GET"]),
    Route("/api/uploads/upload", api_upload_file, methods=["POST"]),
    Route("/api/uploads/ingest", api_ingest_single, methods=["POST"]),
    Route("/api/uploads/scan", api_run_scan_cycle, methods=["POST"]),
    Route("/api/plan-preview", api_plan_preview, methods=["POST"]),
]
