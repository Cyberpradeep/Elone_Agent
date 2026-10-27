"""
Governance API Route Handlers
=============================
Implements REST endpoints for the 14-state orchestrator, review tasks,
separation-of-duties decisions, publication gatekeeper, and downstream search.
"""

import os
import glob
import json
import datetime
from starlette.responses import JSONResponse
from starlette.routing import Route

from api.context import (
    governance_ledger,
    retrieval_index,
    SOPS_DIR,
    DRAFTS_DIR,
)
from schemas.governance_models import (
    SeparationOfDutiesViolation,
    NotHumanActorError,
    GateFailureError,
    StaleApprovalError,
    NotApprovedError,
)
from agents.a6_hub.publisher import (
    evaluate_publication_gates,
    write_okf_playbook,
)
from agents.a2_structuring.canonical_builder import (
    sync_canonical_to_playbook,
    write_canonical_sop_json,
)


async def api_governance_jobs(request):
    """Lists all SOP lifecycle jobs and their current state machine status (Section 8)."""
    jobs = [job.to_dict() for job in governance_ledger._jobs.values()]
    return JSONResponse({"jobs": jobs, "total": len(jobs)})


async def api_governance_job_detail(request):
    job_id = request.path_params.get("job_id")
    job = governance_ledger.get_job(job_id)
    if not job:
        return JSONResponse({"error": f"Job '{job_id}' not found."}, status_code=404)
    return JSONResponse(job.to_dict())


async def api_governance_review_tasks(request):
    """Lists all human review tasks (RT-xxxxxx) across jobs (Section 5.5 & 13)."""
    tasks = []
    for job in governance_ledger._jobs.values():
        if job.review_task:
            task_dict = dict(job.review_task)
            due_str = task_dict.get("due_date")
            is_overdue = False
            if due_str and task_dict.get("status") == "pending":
                try:
                    due_dt = datetime.datetime.fromisoformat(due_str)
                    if due_dt.tzinfo is None:
                        due_dt = due_dt.replace(tzinfo=datetime.timezone.utc)
                    is_overdue = datetime.datetime.now(datetime.timezone.utc) > due_dt
                except Exception:
                    pass
            task_dict["is_overdue"] = is_overdue
            tasks.append(task_dict)
    return JSONResponse({"tasks": tasks, "total": len(tasks)})


async def api_governance_record_decision(request):
    """Records human review decision (approve, changes_requested, reject) with SoD verification."""
    task_id = request.path_params.get("task_id")
    try:
        body = await request.json()
    except Exception:
        body = {}

    decision = body.get("decision", "approve")
    reviewer = body.get("reviewer", "")
    actor_type = body.get("actor_type", "human")
    notes = body.get("notes", "")
    confirmed_classif = body.get("confirmed_classification", True)

    target_job = None
    for job in governance_ledger._jobs.values():
        if job.review_task and job.review_task.get("task_id") == task_id:
            target_job = job
            break

    if not target_job:
        return JSONResponse({"error": f"Review task '{task_id}' not found."}, status_code=404)

    gate_check = None
    if decision.lower() == "approve":
        gate_check = evaluate_publication_gates(
            secrets_count=body.get("secrets_count", 0),
            is_quarantined=target_job.current_state == "quarantined",
            schema_valid=body.get("schema_valid", True),
            schema_errors_count=body.get("schema_errors_count", 0),
            traceability_pct=float(body.get("traceability_pct", 95.0)),
            completeness_pct=float(body.get("completeness_pct", 90.0)),
            open_blocking_issues_count=int(body.get("open_blocking_issues_count", 0)),
            classification_confirmed=bool(confirmed_classif),
            rule_ai_conflict=bool(body.get("rule_ai_conflict", False)),
        )

    try:
        dec = governance_ledger.record_review_decision(
            job_id=target_job.job_id,
            decision=decision,
            reviewer=reviewer,
            actor_type=actor_type,
            notes=notes,
            publication_gate_check=gate_check,
            last_editor=body.get("last_editor"),
        )
        return JSONResponse({
            "status": "success",
            "decision": dec.decision,
            "reviewer": dec.reviewer,
            "job_state": target_job.current_state,
            "gate_check": gate_check.__dict__ if gate_check else None,
        })
    except SeparationOfDutiesViolation as e:
        return JSONResponse({"error": str(e), "error_code": e.error_code}, status_code=403)
    except NotHumanActorError as e:
        return JSONResponse({"error": str(e), "error_code": e.error_code}, status_code=403)
    except GateFailureError as e:
        return JSONResponse({"error": str(e), "error_code": e.error_code, "failures": e.failure_reasons}, status_code=400)
    except Exception as e:
        print(f"[PUBLISH ERROR] {type(e).__name__}: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


async def api_governance_publish_sop(request):
    """Publishes an approved SOP, validates version & hash consistency, and indexes into catalog."""
    sop_id = request.path_params.get("sop_id")
    try:
        body = await request.json()
    except Exception:
        body = {}

    target_job = None
    for job in governance_ledger._jobs.values():
        if job.sop_id == sop_id:
            target_job = job
            break

    if not target_job:
        return JSONResponse({"error": f"Job for SOP '{sop_id}' not found."}, status_code=404)

    gate_check = evaluate_publication_gates(
        secrets_count=0,
        is_quarantined=False,
        schema_valid=True,
        schema_errors_count=0,
        traceability_pct=float(body.get("traceability_pct", 95.0)),
        completeness_pct=float(body.get("completeness_pct", 90.0)),
        open_blocking_issues_count=0,
        classification_confirmed=True,
    )

    try:
        governance_ledger.publish_approved_sop(
            job_id=target_job.job_id,
            current_content_sha256=target_job.content_sha256,
            current_version=target_job.version,
            publication_gate_check=gate_check,
            actor=body.get("actor", "A6_hub"),
        )

        canonical_sop = body.get("canonical_sop")

        # Commit unapproved draft from _drafts to knowledge_base/sops/ upon human publication
        draft_file = os.path.join(DRAFTS_DIR, f"{sop_id}.draft.json")
        saved_playbook_path = None
        if os.path.exists(draft_file):
            try:
                with open(draft_file, "r", encoding="utf-8") as df:
                    saved_draft_data = json.load(df)
                draft_content = saved_draft_data.get("draft", {})
                if not canonical_sop:
                    canonical_sop = saved_draft_data.get("canonical_draft")
                safe_name = saved_draft_data.get("raw_filename", f"{sop_id}.txt")

                saved_playbook_path = write_okf_playbook(draft_content, raw_filename=safe_name)
            except Exception as e:
                print(f"[WARN] Failed to commit draft playbook on publish: {e}")

        if not canonical_sop:
            pattern = os.path.join(SOPS_DIR, "**", f"{sop_id}.canonical.json")
            files = glob.glob(pattern, recursive=True)
            if files:
                with open(files[0], "r", encoding="utf-8") as f:
                    canonical_sop = json.load(f)
            else:
                canonical_sop = {
                    "schema_version": "1.0",
                    "sop_id": target_job.sop_id,
                    "version": target_job.version,
                    "tenant_id": target_job.tenant_id,
                    "title": target_job.sop_id,
                    "source": {"sha256": target_job.content_sha256},
                    "lifecycle": {"state": "published"},
                    "classification": {"level": "L1", "score": 25},
                    "steps": [],
                }
        if canonical_sop.get("lifecycle", {}).get("state") != "published":
            canonical_sop["lifecycle"] = {"state": "published"}

        indexed = retrieval_index.index_published_sop(canonical_sop)
        citation = indexed.citation if hasattr(indexed, "citation") else str(indexed)
        return JSONResponse({
            "status": "published",
            "sop_id": target_job.sop_id,
            "version": target_job.version,
            "citation": citation,
            "job_state": target_job.current_state,
            "playbook_path": saved_playbook_path,
        })
    except StaleApprovalError as e:
        return JSONResponse({"error": str(e), "error_code": e.error_code}, status_code=409)
    except NotApprovedError as e:
        return JSONResponse({"error": str(e), "error_code": e.error_code}, status_code=400)
    except GateFailureError as e:
        return JSONResponse({"error": str(e), "error_code": e.error_code, "failures": e.failure_reasons}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def api_governance_get_canonical(request):
    """Retrieves Canonical SOP JSON 1.0 document."""
    sop_id = request.path_params.get("sop_id")
    pattern = os.path.join(SOPS_DIR, "**", f"{sop_id}.canonical.json")
    files = glob.glob(pattern, recursive=True)
    if not files:
        draft_file = os.path.join(DRAFTS_DIR, f"{sop_id}.draft.json")
        if os.path.exists(draft_file):
            try:
                with open(draft_file, "r", encoding="utf-8") as df:
                    d = json.load(df)
                    return JSONResponse(d.get("canonical_draft", {}))
            except Exception:
                pass
        return JSONResponse({"error": f"Canonical SOP '{sop_id}' not found."}, status_code=404)

    with open(files[0], "r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(data)


async def api_governance_update_canonical(request):
    """Updates Canonical JSON and triggers step auto-sync into .md playbook."""
    sop_id = request.path_params.get("sop_id")
    try:
        body = await request.json()
    except Exception:
        body = {}

    category = body.get("category", "general")
    try:
        json_path = write_canonical_sop_json(body, category=category)
        sync_canonical_to_playbook(body, category=category)
        return JSONResponse({"status": "updated", "sop_id": sop_id, "path": json_path})
    except Exception as e:
        return JSONResponse({"error": f"Failed updating canonical SOP: {e}"}, status_code=400)


async def api_governance_sync_playbook(request):
    """Synchronizes Canonical JSON edits into the OKF Playbook .md file and re-stamps HMAC."""
    sop_id = request.path_params.get("sop_id")
    try:
        body = await request.json()
    except Exception:
        body = {}

    canonical_data = body.get("canonical_sop") or body
    try:
        md_path = sync_canonical_to_playbook(canonical_data)
        return JSONResponse({"status": "synced", "sop_id": sop_id, "playbook_path": md_path})
    except Exception as e:
        return JSONResponse({"error": f"Sync failed: {e}"}, status_code=400)


async def api_governance_downstream_search(request):
    """Downstream agent retrieval index query with clearance tier and tenant isolation (Section 14 & 18)."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    query = body.get("query", "")
    tenant_id = body.get("tenant_id", "tn_northwind")
    clearance_level = body.get("clearance_level", "L1")
    agent_id = body.get("agent_id", "agent_unspecified")
    agent_persona = body.get("agent_persona")
    department = body.get("department")
    limit = int(body.get("limit", 10))

    results = retrieval_index.search(
        query=query,
        tenant_id=tenant_id,
        clearance_level=clearance_level,
        agent_id=agent_id,
        agent_persona=agent_persona,
        department=department,
        limit=limit,
    )
    return JSONResponse({
        "results": [r.__dict__ for r in results],
        "count": len(results),
        "caller_clearance": clearance_level,
        "caller_tenant": tenant_id,
    })


async def api_governance_downstream_stats(request):
    tenant_id = request.query_params.get("tenant_id")
    stats = retrieval_index.get_stats(tenant_id=tenant_id)
    return JSONResponse(stats)


async def api_governance_quarantine_incidents(request):
    """Lists all security quarantine incidents (INC-xxxxxx) (Section 10)."""
    incidents = []
    for job in governance_ledger._jobs.values():
        if job.incident:
            incidents.append(job.incident)
    return JSONResponse({"incidents": incidents, "count": len(incidents)})


async def api_get_config(request):
    """Returns the active dynamic pipeline configuration."""
    from config.settings import get_settings
    return JSONResponse(get_settings().get_all())


async def api_update_config(request):
    """Dynamically updates pipeline configuration and hot-reloads settings."""
    from config.settings import update_settings
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    updated_cfg = update_settings(body)
    return JSONResponse({
        "status": "success",
        "message": "Pipeline configuration dynamically updated and persisted.",
        "config": updated_cfg,
    })


governance_routes = [
    Route("/api/governance/jobs", api_governance_jobs, methods=["GET"]),
    Route("/api/governance/jobs/{job_id}", api_governance_job_detail, methods=["GET"]),
    Route("/api/governance/review-tasks", api_governance_review_tasks, methods=["GET"]),
    Route("/api/governance/review-tasks/{task_id}/decision", api_governance_record_decision, methods=["POST"]),
    Route("/api/governance/sops/{sop_id}/publish", api_governance_publish_sop, methods=["POST"]),
    Route("/api/governance/sops/{sop_id}/canonical", api_governance_get_canonical, methods=["GET"]),
    Route("/api/governance/sops/{sop_id}/canonical", api_governance_update_canonical, methods=["PUT"]),
    Route("/api/governance/sops/{sop_id}/sync-playbook", api_governance_sync_playbook, methods=["POST"]),
    Route("/api/governance/downstream/search", api_governance_downstream_search, methods=["POST"]),
    Route("/api/governance/downstream/stats", api_governance_downstream_stats, methods=["GET"]),
    Route("/api/governance/incidents", api_governance_quarantine_incidents, methods=["GET"]),
    Route("/api/config", api_get_config, methods=["GET"]),
    Route("/api/config", api_update_config, methods=["POST", "PUT"]),
]
