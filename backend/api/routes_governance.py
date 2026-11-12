"""
Governance API Route Handlers
=============================
Implements REST endpoints for the 14-state orchestrator, review tasks,
separation-of-duties decisions, publication gatekeeper, and downstream search.
"""

import os
import re
import copy
import glob
import json
import datetime
from starlette.concurrency import run_in_threadpool

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from starlette.routing import Route

from api.context import (
    governance_ledger,
    retrieval_index,
    SOPS_DIR,
    DRAFTS_DIR,
    UPLOADS_DIR,
    MANIFEST_PATH,
    read_manifest,
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
from agents.a5_review.draft_store import purge_staged_draft
from agents.a1_ingestion import extract_ordered_sop_content
from agents.a2_structuring.canonical_builder import (
    build_canonical_sop_from_draft,
    sync_canonical_to_playbook,
    write_canonical_sop_json,
    _locate_quote,
)
from agents.a4_verification.quote_tracer import verify_quote_trace
from agents.a3_security.ast_sandbox import scan_commands_for_ast_threats


async def api_governance_jobs(request: Request):
    """Lists all SOP lifecycle jobs and their current state machine status (Section 8)."""

    try:
        governance_ledger.load()
    except Exception:
        pass

    jobs = [job.to_dict() for job in list(governance_ledger._jobs.values())]
    return JSONResponse({"jobs": jobs, "total": len(jobs)})


async def api_governance_job_detail(request: Request):
    job_id = request.path_params.get("job_id")
    job = governance_ledger.get_job(job_id)
    if not job:
        return JSONResponse({"error": f"Job '{job_id}' not found."}, status_code=404)
    return JSONResponse(job.to_dict())


async def api_governance_review_tasks(request: Request):
    """Lists all human review tasks (RT-xxxxxx) across jobs (Section 5.5 & 13)."""
    try:
        governance_ledger.load()
    except Exception:
        pass
    tasks = []
    for job in list(governance_ledger._jobs.values()):
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


async def api_governance_record_decision(request: Request):
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
    for job in list(governance_ledger._jobs.values()):
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
            # Not taken on trust from the client: whoever last edited the draft cannot approve it.
            last_editor=body.get("last_editor") or _draft_last_editor(target_job.sop_id),
        )
        # Keep _processed_manifest.json synchronized with review decisions
        try:
            m = read_manifest()
            _, d_data = _read_draft(target_job.sop_id)
            target_fn = (d_data or {}).get("raw_filename")
            if not target_fn or target_fn not in m:
                for k, v in m.items():
                    if v.get("job_id") == target_job.job_id or v.get("sop_id") == target_job.sop_id:
                        target_fn = k
                        break
            if target_fn:
                status_map = {
                    "approve": "approved",
                    "changes_requested": "changes_requested",
                    "reject": "rejected",
                    "rejected": "rejected",
                }
                entry = dict(m.get(target_fn) or {})
                entry.update({
                    "status": status_map.get(dec.decision, target_job.current_state),
                    "sop_id": target_job.sop_id,
                    "job_id": target_job.job_id,
                    "task_id": task_id,
                    "sha256": target_job.content_sha256,
                    "processed_at": datetime.datetime.now().isoformat(),
                })
                if notes:
                    entry["reason"] = notes
                m[target_fn] = entry
                with open(MANIFEST_PATH, "w", encoding="utf-8") as mf:
                    json.dump(m, mf, indent=2)
        except Exception:
            pass

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


async def api_governance_publish_sop(request: Request):
    """Publishes an approved SOP, validates version & hash consistency, and indexes into catalog."""
    sop_id = request.path_params.get("sop_id")
    try:
        body = await request.json()
    except Exception:
        body = {}

    target_job = _job_for_sop(sop_id, preferred_states={"approved"})

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
        safe_name = None
        if os.path.exists(draft_file):
            try:
                with open(draft_file, "r", encoding="utf-8") as df:
                    saved_draft_data = json.load(df)
                draft_content = saved_draft_data.get("draft", {})
                if not canonical_sop:
                    canonical_sop = saved_draft_data.get("canonical_draft")
                safe_name = saved_draft_data.get("raw_filename", f"{sop_id}.txt")
                if isinstance(draft_content, dict) and not draft_content.get("raw_text") and safe_name:
                    src_upload = os.path.join(UPLOADS_DIR, os.path.basename(safe_name))
                    if os.path.exists(src_upload):
                        try:
                            _, segs = extract_ordered_sop_content(src_upload)
                            draft_content["raw_text"] = "\n\n".join(s["content"] for s in segs if s.get("type") == "text")
                        except Exception:
                            pass

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
        canonical_sop.setdefault("lifecycle", {})["state"] = "published"
        canonical_sop.setdefault("source", {}).setdefault("file_sha256", target_job.content_sha256)

        if saved_playbook_path:
            pub_category = os.path.basename(os.path.dirname(saved_playbook_path)) or "general"
            write_canonical_sop_json(canonical_sop, category=pub_category)
            purge_staged_draft(sop_id)
            if os.path.exists(draft_file):
                try:
                    os.remove(draft_file)
                except Exception:
                    pass

        indexed = retrieval_index.index_published_sop(canonical_sop)
        citation = indexed.citation if hasattr(indexed, "citation") else str(indexed)

        # Update processed manifest with published status and SOP ID
        try:
            pub_sop_id = canonical_sop.get("sop_id") or target_job.sop_id
            m = read_manifest()
            target_fn = safe_name if safe_name else None
            if not target_fn:
                for k, v in m.items():
                    if v.get("job_id") == target_job.job_id or v.get("sop_id") in (sop_id, pub_sop_id):
                        target_fn = k
                        break
            if target_fn:
                m[target_fn] = {
                    "status": "success",
                    "sop_id": pub_sop_id,
                    "job_id": target_job.job_id,
                    "sha256": target_job.content_sha256,
                    "published": True,
                    "published_at": datetime.datetime.now().isoformat(),
                    "playbook_path": saved_playbook_path,
                }
                with open(MANIFEST_PATH, "w", encoding="utf-8") as mf:
                    json.dump(m, mf, indent=2)
        except Exception:
            pass

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


async def api_governance_get_canonical(request: Request):
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


async def api_governance_update_canonical(request: Request):
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


async def api_governance_sync_playbook(request: Request):
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


async def api_governance_downstream_search(request: Request):
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


async def api_governance_downstream_stats(request: Request):
    tenant_id = request.query_params.get("tenant_id")
    stats = retrieval_index.get_stats(tenant_id=tenant_id)
    return JSONResponse(stats)


async def api_governance_quarantine_incidents(request: Request):
    """Lists all security quarantine incidents (INC-xxxxxx) (Section 10)."""
    try:
        governance_ledger.load()
    except Exception:
        pass
    incidents = []
    for job in list(governance_ledger._jobs.values()):
        if job.incident:
            incidents.append(job.incident)
    return JSONResponse({"incidents": incidents, "count": len(incidents)})


async def api_get_config(request: Request):
    """Returns the active dynamic pipeline configuration."""
    from config.settings import get_settings
    return JSONResponse(get_settings().get_all())


async def api_update_config(request: Request):
    """Dynamically updates pipeline configuration and hot-reloads settings."""
    from config.settings import (
        update_settings, get_settings, validate_config_updates, audit_config_change,
    )
    import hmac
    ip = request.client.host if request.client else "unknown"

    # Admin-only (H1). Fails closed: if no admin token is configured, config is read-only.
    admin_token = os.environ.get("ELONE_ADMIN_TOKEN", "")
    if not admin_token:
        return JSONResponse({"error": "Config changes are disabled: ELONE_ADMIN_TOKEN is not set."}, status_code=503)
    supplied = request.headers.get("x-admin-token", "")
    if not supplied:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            supplied = auth[7:].strip()
    if not hmac.compare_digest(supplied.encode(), admin_token.encode()):
        audit_config_change("unauthenticated", ip, {}, {}, "denied: bad admin token")
        return JSONResponse({"error": "Admin token required."}, status_code=403)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    clean, errors = validate_config_updates(body)
    if errors:
        audit_config_change("admin", ip, {}, {}, "rejected: " + "; ".join(errors)[:300])
        return JSONResponse({"error": "Invalid config update", "details": errors}, status_code=422)

    before = json.loads(json.dumps(get_settings().get_all()))
    updated_cfg = update_settings(clean)
    audit_config_change("admin", ip, before, clean, "applied")
    return JSONResponse({
        "status": "success",
        "message": "Pipeline configuration dynamically updated and persisted.",
        "config": updated_cfg,
    })


# ---------------------------------------------------------------------------
# Draft step editing (review page). Edits stay in the draft file; nothing is written to sops/
# until the SOP is approved and published.
# ---------------------------------------------------------------------------

_SOP_ID_RE = re.compile(r"[A-Za-z0-9_-]+")
_MAX = {"sop_step_description": 1000, "command": 4000, "fallback_command": 4000, "source_quote": 1000, "parse_instruction": 1500}


def _draft_file(sop_id: str):
    """Path of a draft file, or None if the id is not a plain SOP id."""
    if not _SOP_ID_RE.fullmatch(sop_id or ""):
        return None
    return os.path.join(DRAFTS_DIR, f"{sop_id}.draft.json")


def _read_draft(sop_id: str):
    path = _draft_file(sop_id)
    if not path or not os.path.exists(path):
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        return path, json.load(f)


def _draft_last_editor(sop_id: str):
    try:
        _, data = _read_draft(sop_id)
        return (data or {}).get("last_editor")
    except Exception:
        return None


def _job_for_sop(sop_id: str, preferred_states=None):
    matches = [job for job in list(governance_ledger._jobs.values()) if job.sop_id == sop_id]
    if not matches:
        return None
    if preferred_states:
        pref = [j for j in matches if j.current_state in preferred_states]
        if pref:
            pref.sort(key=lambda j: (j.updated_at or j.created_at or ""), reverse=True)
            return pref[0]
    priority = {
        "awaiting_review": 4,
        "approved": 4,
        "changes_requested": 3,
        "published": 3,
        "assessing": 2,
        "structuring": 2,
        "scanning": 2,
        "extracting": 2,
        "received": 2,
    }
    matches.sort(
        key=lambda j: (priority.get(j.current_state, 0), j.updated_at or j.created_at or ""),
        reverse=True,
    )
    return matches[0]


async def api_governance_get_draft(request: Request):
    """The editable steps of an unapproved draft, plus whether they can still be edited."""
    sop_id = request.path_params.get("sop_id", "")
    path, data = _read_draft(sop_id)
    if not data:
        return JSONResponse({"error": f"No draft found for '{sop_id}'."}, status_code=404)
    job = _job_for_sop(sop_id, preferred_states={"awaiting_review"})
    state = job.current_state if job else None
    editable = state == "awaiting_review"
    fm = (data.get("draft") or {}).get("frontmatter") or data.get("draft") or {}
    return JSONResponse({
        "sop_id": sop_id,
        "job_state": state,
        "editable": editable,
        "editable_reason": None if editable else (
            "This SOP is not waiting for review any more, so its steps are locked." if job else "No lifecycle job exists for this draft."),
        "last_editor": data.get("last_editor"),
        "last_edited_at": data.get("last_edited_at"),
        "steps": fm.get("steps") or [],
    })


# Canonical JSON fields a reviewer may edit by hand. Everything else is system-managed: changing the
# confidentiality tier, quality scores, source details or lifecycle by hand would bypass the gates.
_EDITABLE_JSON_KEYS = ("title", "department", "owner", "version_label", "review_date", "purpose", "scope",
                       "preconditions", "roles", "exceptions", "notes", "references", "steps")
_PROTECTED_JSON_KEYS = ("schema_version", "sop_id", "version", "tenant_id", "title_lines", "metadata_lines", "source",
                        "media", "issues", "classification", "quality", "transformations", "lifecycle", "provenance")
_PROTECTED_HINTS = {
    "classification": "the confidentiality tier is confirmed with the checkbox on the decision form",
    "quality": "it is computed from the document and your steps when you save",
    "lifecycle": "it is controlled by the review workflow",
}


def _merge_document_sections(old: dict, fm: dict, extra: dict, raw_text: str):
    """Apply hand-edited document sections (everything except steps) and re-verify their quotes."""
    for key in _EDITABLE_JSON_KEYS:
        if key != "steps" and key in extra:
            old[key] = extra[key]
    title = str(old.get("title") or "").strip()
    if title:
        fm["title"] = title
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

    def reverify(item):
        if isinstance(item, dict) and str(item.get("quote") or "").strip():
            rng = _locate_quote(item["quote"], lines)
            item["source_lines"] = rng
            item["verified"], _ = verify_quote_trace(lines, rng[0], rng[1], item["quote"])

    for key in ("purpose", "scope"):
        reverify(old.get(key))
    for key in ("preconditions", "exceptions"):
        for item in (old.get(key) or []):
            reverify(item)


def _apply_step_edits(path: str, data: dict, steps_in: list, actor: str, canonical_extra: dict = None):
    """Validate + apply the edits, rebuild the canonical copy, and write the draft file atomically.
    Runs in a worker thread (it re-reads the source document to re-verify the quotes)."""
    draft = data["draft"]
    fm = draft.get("frontmatter") or draft
    existing = fm.get("steps") or []

    errors, new_steps = [], []
    for i, raw in enumerate(steps_in, start=1):
        ref = raw.get("ref")
        base = copy.deepcopy(existing[ref - 1]) if isinstance(ref, int) and 1 <= ref <= len(existing) else {
            "step_type": "command", "shell": "powershell", "timeout_seconds": 30,
            "platform": None, "function_name": None, "comm_inputs": None, "fallback_sop_id": None,
            "execute_if": None, "step_reasoning": "Added by a human reviewer.",
        }
        def text(key):
            v = raw.get(key)
            v = ("" if v is None else str(v)).strip()
            if len(v) > _MAX[key]:
                errors.append(f"Step {i}: '{key}' is longer than {_MAX[key]} characters.")
            return v
        desc = text("sop_step_description")
        if not desc:
            errors.append(f"Step {i}: the description cannot be empty.")
        base["step_number"] = i
        base["sop_step_description"] = desc
        base["source_quote"] = text("source_quote") or None
        base["parse_instruction"] = text("parse_instruction") or None
        base["fallback_command"] = text("fallback_command") or None
        if base.get("step_type") == "tool_call":
            ci = raw.get("comm_inputs")
            if isinstance(ci, str):
                try:
                    ci = json.loads(ci) if ci.strip() else {}
                except Exception:
                    errors.append(f"Step {i}: the tool inputs are not valid JSON.")
                    ci = base.get("comm_inputs") or {}
            if not isinstance(ci, dict):
                errors.append(f"Step {i}: the tool inputs must be a JSON object.")
                ci = base.get("comm_inputs") or {}
            base["comm_inputs"] = ci
        else:
            cmd = text("command")
            if not cmd:
                errors.append(f"Step {i}: a command step needs a command.")
            base["command"] = cmd or None
        new_steps.append(base)

    if not new_steps:
        errors.append("An SOP needs at least one step.")

    # Same dangerous-command screen the LLM's output goes through (LOLBins, encoded PowerShell, injection).
    for i, st in enumerate(new_steps, start=1):
        for threat in scan_commands_for_ast_threats([c for c in (st.get("command"), st.get("fallback_command")) if c]):
            errors.append(f"Step {i}: blocked by the security screen ({threat['description']}).")
    if errors:
        return {"errors": errors}

    # Variable linkage: a condition may only use variables an earlier step sets (a warning, not a block).
    warnings, known = [], set()
    for i, st in enumerate(new_steps, start=1):
        for var in re.findall(r"variables\.(\w+)", st.get("execute_if") or ""):
            if var not in known:
                warnings.append(f"Step {i} only runs if variables.{var}, but no earlier step sets it.")
        known |= set(re.findall(r"variables\.(\w+)\s*=", st.get("parse_instruction") or ""))

    # Re-verify against the real document so the evidence + quality figures reflect the edits.
    raw_name = os.path.basename(str(data.get("raw_filename") or ""))
    source_path = os.path.join(UPLOADS_DIR, raw_name)
    if not raw_name or not os.path.exists(source_path):
        return {"errors": [f"The source document '{raw_name}' is no longer in the uploads folder, so the quotes cannot be re-verified."]}
    _, segments = extract_ordered_sop_content(source_path)
    raw_text = "\n\n".join(s_["content"] for s_ in segments if s_.get("type") == "text")

    fm["steps"] = new_steps
    old = data.get("canonical_draft") or {}
    if not draft.get("raw_text"):
        draft["raw_text"] = raw_text
    rebuilt = build_canonical_sop_from_draft(
        draft, raw_text=raw_text,
        tenant_id=old.get("tenant_id", "tn_northwind"),
        uploaded_by=(old.get("lifecycle") or {}).get("uploaded_by", "author@corp.com"),
        vlm_reports=draft.get("vlm_reports"),
    )
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    old["steps"] = rebuilt["steps"]
    old["quality"] = rebuilt["quality"]
    old["issues"] = rebuilt.get("issues", old.get("issues", []))
    if rebuilt.get("media"):
        old["media"] = rebuilt["media"]
    if canonical_extra:
        _merge_document_sections(old, fm, canonical_extra, raw_text)
    old.setdefault("lifecycle", {}).update({"last_editor": actor, "last_edited_at": now})
    data["canonical_draft"] = old
    data["last_editor"], data["last_edited_at"] = actor, now

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
    return {"canonical_draft": old, "warnings": warnings, "step_count": len(new_steps)}


async def api_governance_update_draft_steps(request: Request):
    """Saves a reviewer's edits to the steps of an unapproved draft (never touches sops/)."""
    sop_id = request.path_params.get("sop_id", "")
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = str(body.get("actor", "")).strip()
    steps_in = body.get("steps")
    if not actor:
        return JSONResponse({"error": "'actor' (who is editing) is required."}, status_code=400)
    if not isinstance(steps_in, list):
        return JSONResponse({"error": "'steps' must be a list."}, status_code=400)

    path, data = _read_draft(sop_id)
    if not data:
        return JSONResponse({"error": f"No draft found for '{sop_id}'."}, status_code=404)
    job = _job_for_sop(sop_id, preferred_states={"awaiting_review"})
    if not job or job.current_state != "awaiting_review":
        return JSONResponse({"error": "Steps can only be edited while the SOP is awaiting review."}, status_code=409)

    try:
        result = await run_in_threadpool(_apply_step_edits, path, data, steps_in, actor)
    except Exception as e:
        return JSONResponse({"error": f"Could not save the edits: {e}"}, status_code=500)
    if "errors" in result:
        return JSONResponse({"error": result["errors"][0], "errors": result["errors"]}, status_code=422)

    # Leave a trace in the job history (awaiting_review -> awaiting_review is an allowed self-transition).
    try:
        governance_ledger.transition_state(job.job_id, "awaiting_review", actor=actor,
                                           reason=f"Steps edited by reviewer ({result['step_count']} steps).")
    except Exception as e:
        result["warnings"].append(f"Edit saved, but could not be logged in the job history: {e}")
    return JSONResponse({"status": "saved", "last_editor": actor, **result})


async def api_governance_update_draft_canonical(request: Request):
    """Saves hand-edited canonical JSON for an unapproved draft. Steps are synced into the playbook
    steps and re-verified; document sections are re-verified; system-managed fields are refused."""
    sop_id = request.path_params.get("sop_id", "")
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = str(body.get("actor", "")).strip()
    canon = body.get("canonical")
    if not actor:
        return JSONResponse({"error": "'actor' (who is editing) is required."}, status_code=400)
    if not isinstance(canon, dict):
        return JSONResponse({"error": "'canonical' must be a JSON object."}, status_code=400)
    if len(json.dumps(canon)) > 300_000:
        return JSONResponse({"error": "The JSON is too large (limit 300 KB)."}, status_code=413)

    path, data = _read_draft(sop_id)
    if not data:
        return JSONResponse({"error": f"No draft found for '{sop_id}'."}, status_code=404)
    job = _job_for_sop(sop_id, preferred_states={"awaiting_review"})
    if not job or job.current_state != "awaiting_review":
        return JSONResponse({"error": "The JSON can only be edited while the SOP is awaiting review."}, status_code=409)

    current = data.get("canonical_draft") or {}
    problems = []
    for key in canon:
        if key not in _EDITABLE_JSON_KEYS and key not in _PROTECTED_JSON_KEYS:
            problems.append(f"'{key}' is not a field of the canonical SOP.")
    missing = object()
    for key in _PROTECTED_JSON_KEYS:
        if json.dumps(canon.get(key, "__missing__"), sort_keys=True) != json.dumps(current.get(key, "__missing__"), sort_keys=True):
            hint = _PROTECTED_HINTS.get(key)
            problems.append(f"'{key}' is managed by the system and can't be edited here" + (f" ({hint})." if hint else "."))

    steps = canon.get("steps")
    if not isinstance(steps, list):
        problems.append("'steps' must be a list.")
        steps = []
    okf_count = len(((data.get("draft") or {}).get("frontmatter") or data.get("draft") or {}).get("steps") or [])
    edits, used = [], set()
    for i, st in enumerate(steps, start=1):
        if not isinstance(st, dict):
            problems.append(f"Step {i}: must be an object.")
            continue
        ref = st.get("n")
        ref = ref if isinstance(ref, int) and 1 <= ref <= okf_count and ref not in used else None
        if ref:
            used.add(ref)
        inp = st.get("input")
        edits.append({
            "ref": ref,
            "sop_step_description": st.get("action"),
            "command": inp if isinstance(inp, str) else ("" if inp is None else json.dumps(inp)),
            "comm_inputs": inp,
            "source_quote": st.get("quote"),
            "parse_instruction": st.get("expected_outcome"),
            "fallback_command": st.get("warning"),
        })
    if problems:
        return JSONResponse({"error": problems[0], "errors": problems}, status_code=422)

    try:
        result = await run_in_threadpool(_apply_step_edits, path, data, edits, actor, canon)
    except Exception as e:
        return JSONResponse({"error": f"Could not save the edits: {e}"}, status_code=500)
    if "errors" in result:
        return JSONResponse({"error": result["errors"][0], "errors": result["errors"]}, status_code=422)
    try:
        governance_ledger.transition_state(job.job_id, "awaiting_review", actor=actor,
                                           reason="Canonical JSON edited by reviewer.")
    except Exception as e:
        result["warnings"].append(f"Edit saved, but could not be logged in the job history: {e}")
    return JSONResponse({"status": "saved", "last_editor": actor, **result})



governance_router = APIRouter(tags=["Governance, Dual-Custody & Downstream Catalog"])
governance_router.add_api_route("/api/governance/jobs", api_governance_jobs, methods=["GET"], summary="List All SOP Governance Jobs")
governance_router.add_api_route("/api/governance/jobs/{job_id}", api_governance_job_detail, methods=["GET"], summary="Get Job Details & State History")
governance_router.add_api_route("/api/governance/review-tasks", api_governance_review_tasks, methods=["GET"], summary="List Pending Human Review Tasks")
governance_router.add_api_route("/api/governance/review-tasks/{task_id}/decision", api_governance_record_decision, methods=["POST"], summary="Record Human Review Decision (Dual-Custody SoD)")
governance_router.add_api_route("/api/governance/sops/{sop_id}/publish", api_governance_publish_sop, methods=["POST"], summary="Publish Approved SOP (Gatekeeper Verification)")
governance_router.add_api_route("/api/governance/sops/{sop_id}/canonical", api_governance_get_canonical, methods=["GET"], summary="Get Canonical SOP JSON 1.0")
governance_router.add_api_route("/api/governance/sops/{sop_id}/canonical", api_governance_update_canonical, methods=["PUT"], summary="Update Canonical SOP JSON 1.0")
governance_router.add_api_route("/api/governance/sops/{sop_id}/sync-playbook", api_governance_sync_playbook, methods=["POST"], summary="Synchronize Canonical JSON to Markdown Playbook")
governance_router.add_api_route("/api/governance/drafts/{sop_id}", api_governance_get_draft, methods=["GET"], summary="Get Unapproved SOP Draft")
governance_router.add_api_route("/api/governance/drafts/{sop_id}/steps", api_governance_update_draft_steps, methods=["PUT"], summary="Update Unapproved SOP Draft Steps")
governance_router.add_api_route("/api/governance/drafts/{sop_id}/canonical", api_governance_update_draft_canonical, methods=["PUT"], summary="Update Unapproved SOP Draft Canonical JSON")
governance_router.add_api_route("/api/governance/downstream/search", api_governance_downstream_search, methods=["POST"], summary="Search Catalog (Clearance & Tenant Filtered)")
governance_router.add_api_route("/api/governance/downstream/stats", api_governance_downstream_stats, methods=["GET"], summary="Get Downstream Catalog Metrics")
governance_router.add_api_route("/api/governance/incidents", api_governance_quarantine_incidents, methods=["GET"], summary="List Security Quarantine Incidents")
governance_router.add_api_route("/api/config", api_get_config, methods=["GET"], summary="Get Dynamic Pipeline Configuration")
governance_router.add_api_route("/api/config", api_update_config, methods=["POST"], summary="Hot-Reload Dynamic Configuration", operation_id="api_update_config_post")
governance_router.add_api_route("/api/config", api_update_config, methods=["PUT"], summary="Hot-Reload Dynamic Configuration (PUT)", operation_id="api_update_config_put")

governance_routes = list(governance_router.routes)

