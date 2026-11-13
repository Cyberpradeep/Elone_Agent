"""
Governance API Route Handlers
=============================
Implements REST endpoints for the 14-state orchestrator, review tasks,
separation-of-duties decisions, draft revisions & resubmissions, publication gatekeeper,
downstream search, quarantine incidents, and admin-only pipeline configuration.
"""

import logging

_log = logging.getLogger(__name__)

import os
import re
import copy
import glob
import json
import datetime
from starlette.concurrency import run_in_threadpool

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.context import (
    governance_ledger,
    retrieval_index,
    SOPS_DIR,
    DRAFTS_DIR,
    read_manifest,
    write_manifest,
    set_manifest_entry,
    resolve_tenant_upload,
    resolve_sop_access_meta,
    resolve_draft_access_meta,
    read_draft_file,
    _find_job_for_sop,
)
from auth.models import (
    CLEARANCE_RANKS,
    HUMAN_ROLES,
    ROLE_SET,
    ROLE_ADMIN,
    ROLE_PROCESS_OWNER,
    ROLE_SECURITY_REVIEWER,
)
from gemini_monitor.monitor import get_job_progress
from auth.dependencies import (
    AuthAccessError,
    authenticate_request,
    enforce_tenant_access,
    enforce_clearance_access,
    enforce_review_task_eligibility,
    get_client_ip,
    log_auth_event,
)
from schemas.governance_models import (
    SeparationOfDutiesViolation,
    NotHumanActorError,
    GateFailureError,
    StaleApprovalError,
    NotApprovedError,
)
from agents.a6_hub.publisher import (
    compute_canonical_sha256,
    evaluate_draft_publication_gates,
    evaluate_publication_gates,
    write_okf_playbook,
)
from agents.a6_hub.retrieval_catalog import normalize_clearance
from agents.a5_review.draft_store import purge_staged_draft
from agents.a1_ingestion import extract_ordered_sop_content
from agents.a2_structuring.canonical_builder import (
    build_canonical_sop_from_draft,
    sync_canonical_to_playbook,
    write_canonical_sop_json,
    _locate_quote,
)
from schemas.canonical_sop_schema import validate_canonical_sop_dict
from agents.a4_verification.quote_tracer import verify_quote_trace
from agents.a3_security.ast_sandbox import scan_commands_for_ast_threats


def _read_draft(sop_id: str):
    return read_draft_file(sop_id)


_SYSTEM_ACTORS = frozenset({
    "orchestrator",
    "a1_ingestion",
    "a2_structuring",
    "a3_scanner",
    "a3_ast_sandbox",
    "a4_verification",
    "a5_coordinator",
    "a6_hub",
})


def _resolve_server_last_editor(job=None, draft_data=None, sop_id: str = None):
    """Derives last_editor strictly from server-side draft metadata and job audit history."""
    if draft_data is None and sop_id:
        try:
            _, draft_data = _read_draft(sop_id)
        except Exception:
            draft_data = None
    if isinstance(draft_data, dict):
        top_editor = str(draft_data.get("last_editor") or "").strip()
        if top_editor:
            return top_editor
        canon = draft_data.get("canonical_draft")
        if isinstance(canon, dict):
            lc = canon.get("lifecycle")
            if isinstance(lc, dict):
                lc_editor = str(lc.get("last_editor") or "").strip()
                if lc_editor:
                    return lc_editor
    if job is not None:
        for h in reversed(getattr(job, "history", None) or []):
            if not isinstance(h, dict):
                continue
            actor = str(h.get("actor") or "").strip()
            if not actor or actor.lower() in _SYSTEM_ACTORS:
                continue
            details = h.get("details") if isinstance(h.get("details"), dict) else {}
            reason_l = str(h.get("reason") or "").strip().lower()
            is_draft_edit = (
                details.get("draft_edit") is True
                or reason_l.startswith((
                    "steps edited by process owner",
                    "steps revised by process owner",
                    "canonical json edited by process owner",
                    "canonical json revised by process owner",
                ))
                or (h.get("from_state") == "awaiting_review" and h.get("to_state") == "awaiting_review")
            )
            if is_draft_edit:
                return actor
    return None


def _draft_last_editor(sop_id: str):
    return _resolve_server_last_editor(sop_id=sop_id)


def _job_for_sop(sop_id: str, tenant_id: str = None, preferred_states=None):
    matches = [
        job for job in list(governance_ledger._jobs.values())
        if job.sop_id == sop_id and (tenant_id is None or job.tenant_id == tenant_id)
    ]
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
        "changes_requested": 4,
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


async def api_governance_jobs(request: Request):
    """Lists caller tenant's SOP lifecycle jobs and their current state machine status."""
    principal = authenticate_request(
        request,
        allowed_roles=HUMAN_ROLES,
        human_only=True,
        check_csrf=False,
    )
    try:
        governance_ledger.load()
    except Exception as _exc:
        _log.warning("api_governance_jobs: ledger reload failed, using in-memory state (%s: %s)", type(_exc).__name__, _exc)

    jobs = []
    for job in list(governance_ledger._jobs.values()):
        if job.tenant_id != principal.tenant_id:
            continue
        d = job.to_dict()
        p_calls = get_job_progress(job.job_id)
        if p_calls:
            d["progress_calls"] = p_calls
        jobs.append(d)
    return JSONResponse({"jobs": jobs, "total": len(jobs)})


async def api_governance_job_detail(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=HUMAN_ROLES,
        human_only=True,
        check_csrf=False,
    )
    job_id = request.path_params.get("job_id")
    job = governance_ledger.get_job(job_id)
    if not job:
        return JSONResponse({"error": f"Job '{job_id}' not found."}, status_code=404)
    enforce_tenant_access(principal, job.tenant_id, request=request)
    d = job.to_dict()
    p_calls = get_job_progress(job.job_id)
    if p_calls:
        d["progress_calls"] = p_calls
    return JSONResponse(d)


async def api_governance_review_tasks(request: Request):
    """Lists human review tasks filtered by caller tenant and token clearance."""
    principal = authenticate_request(
        request,
        allowed_roles=HUMAN_ROLES,
        human_only=True,
        check_csrf=False,
    )
    try:
        governance_ledger.load()
    except Exception as _exc:
        _log.warning("api_governance_review_tasks: ledger reload failed, using in-memory state (%s: %s)", type(_exc).__name__, _exc)

    tasks = []
    for job in list(governance_ledger._jobs.values()):
        if not job.review_task or job.tenant_id != principal.tenant_id:
            continue
        draft_meta = resolve_draft_access_meta(job.sop_id, job=job)
        sop_tier = draft_meta["classification_level"]
        if not principal.can_access_tier(sop_tier):
            continue

        task_dict = dict(job.review_task)
        due_str = task_dict.get("due_date")
        is_overdue = False
        if due_str and task_dict.get("status") == "pending":
            try:
                due_dt = datetime.datetime.fromisoformat(due_str)
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=datetime.timezone.utc)
                is_overdue = datetime.datetime.now(datetime.timezone.utc) > due_dt
            except Exception as _exc:
                _log.debug("api_governance_review_tasks: due date could not be parsed (%s: %s)", type(_exc).__name__, _exc)

        # Under Option A Single-Gate RBAC, only security_reviewer accounts decide review tasks.
        role_ok = principal.has_role(ROLE_SECURITY_REVIEWER)
        last_ed = _resolve_server_last_editor(job=job, sop_id=job.sop_id) or draft_meta.get("last_editor")
        sod_conflict = (
            principal.identity.strip().lower() == str(job.uploaded_by or "").strip().lower()
            or (bool(last_ed) and principal.identity.strip().lower() == str(last_ed).strip().lower())
        )

        task_dict["tenant_id"] = job.tenant_id
        task_dict["sop_tier"] = sop_tier
        task_dict["is_overdue"] = is_overdue
        task_dict["eligible_for_me"] = bool(role_ok and not sod_conflict)
        tasks.append(task_dict)

    return JSONResponse({"tasks": tasks, "total": len(tasks)})


async def api_governance_record_decision(request: Request):
    """Records human review decision strictly for 'security_reviewer' with tenant, clearance & SoD enforcement."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_SECURITY_REVIEWER,),
        human_only=True,
        check_csrf=True,
    )
    task_id = request.path_params.get("task_id")
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    decision = str(body.get("decision", "approve") or "approve")
    notes = str(body.get("notes", "") or "")
    # Strictly require explicit boolean True from caller; default False (never auto-confirm Gate 6).
    confirmed_classif = body.get("confirmed_classification") is True
    raw_adjusted_level = body.get("adjusted_level")
    adjusted_level = str(raw_adjusted_level).strip().upper() if raw_adjusted_level is not None and str(raw_adjusted_level).strip() else ""
    override_reason = str(body.get("override_reason") or "").strip()

    target_job = None
    for job in list(governance_ledger._jobs.values()):
        if job.review_task and job.review_task.get("task_id") == task_id:
            target_job = job
            break

    if not target_job:
        return JSONResponse({"error": f"Review task '{task_id}' not found."}, status_code=404)

    enforce_tenant_access(principal, target_job.tenant_id, request=request)
    draft_path, saved_draft_data = _read_draft(target_job.sop_id)
    safe_draft_for_meta = saved_draft_data if isinstance(saved_draft_data, dict) else {}
    draft_meta = resolve_draft_access_meta(target_job.sop_id, draft_data=safe_draft_for_meta, job=target_job)
    sop_tier = draft_meta["classification_level"]
    enforce_review_task_eligibility(principal, target_job.review_task, sop_tier, request=request)

    # Derive reviewer, actor_type, last_editor, and ALL 6 publication gates strictly on the server!
    reviewer = principal.identity
    actor_type = principal.actor_type
    server_last_editor = _resolve_server_last_editor(
        job=target_job,
        draft_data=saved_draft_data if isinstance(saved_draft_data, dict) else None,
        sop_id=target_job.sop_id,
    )

    clean_dec = decision.strip().lower()
    gate_check = None
    stamped_draft_data = None
    canon_hash = None
    draft_hash = None
    if clean_dec == "approve":
        eval_draft_data = copy.deepcopy(saved_draft_data) if isinstance(saved_draft_data, dict) else saved_draft_data
        if adjusted_level:
            if adjusted_level not in CLEARANCE_RANKS:
                return JSONResponse(
                    {"error": f"Invalid confidentiality tier '{adjusted_level}'. Must be L0, L1, L2, or L3."},
                    status_code=422,
                )
            enforce_clearance_access(principal, adjusted_level, request=request)
            if isinstance(eval_draft_data, dict) and isinstance(eval_draft_data.get("canonical_draft"), dict):
                cand_classif = eval_draft_data["canonical_draft"].setdefault("classification", {})
                if isinstance(cand_classif, dict):
                    rule_lvl = str(cand_classif.get("rule_level") or "L0").strip().upper()
                    rule_rank = CLEARANCE_RANKS.get(rule_lvl, 0)
                    if CLEARANCE_RANKS[adjusted_level] < rule_rank:
                        return JSONResponse(
                            {"error": f"Cannot downgrade confidentiality tier below deterministic policy floor ({rule_lvl})."},
                            status_code=422,
                        )
                    curr_lvl = str(cand_classif.get("level") or rule_lvl).strip().upper()
                    had_conflict = bool(cand_classif.get("conflict", False)) or (
                        bool(rule_lvl)
                        and bool(cand_classif.get("ai_suggested_level"))
                        and rule_lvl != str(cand_classif.get("ai_suggested_level") or "").strip().upper()
                    )
                    if adjusted_level != curr_lvl or had_conflict:
                        if len(override_reason) < 5:
                            return JSONResponse(
                                {"error": "Provide a brief override reason (at least 5 characters) when changing the confidentiality tier or resolving a conflict."},
                                status_code=422,
                            )
                        tier_floors = {"L0": 5, "L1": 21, "L2": 51, "L3": 76}
                        curr_rank = CLEARANCE_RANKS.get(curr_lvl, 0)
                        try:
                            curr_score = int(cand_classif.get("score") or 5)
                        except (TypeError, ValueError):
                            curr_score = 5
                        if CLEARANCE_RANKS[adjusted_level] > curr_rank:
                            cand_classif["score"] = max(curr_score, tier_floors[adjusted_level])
                        elif adjusted_level != curr_lvl:
                            cand_classif["score"] = max(tier_floors.get(rule_lvl, 5), tier_floors[adjusted_level])
                        cand_classif["level"] = adjusted_level
                        cand_classif["conflict"] = False
                        cand_classif["override_reason"] = override_reason
                        cand_classif["overridden_by"] = reviewer

        gate_check = evaluate_draft_publication_gates(
            target_job,
            eval_draft_data,
            for_publish=False,
            body_confirmed_classification=confirmed_classif,
        )
        if (
            gate_check.passed
            and draft_path
            and isinstance(eval_draft_data, dict)
            and isinstance(eval_draft_data.get("canonical_draft"), dict)
            and isinstance(eval_draft_data.get("draft"), dict)
        ):
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            stamped_draft_data = eval_draft_data
            stamped_canon = stamped_draft_data["canonical_draft"]
            stamped_canon["sop_id"] = target_job.sop_id
            stamped_canon["version"] = target_job.version
            stamped_canon["tenant_id"] = target_job.tenant_id
            stamped_src = stamped_canon.setdefault("source", {})
            if isinstance(stamped_src, dict) and target_job.content_sha256:
                stamped_src["file_sha256"] = target_job.content_sha256
            stamped_classif = stamped_canon.setdefault("classification", {})
            if isinstance(stamped_classif, dict):
                stamped_classif["confirmed"] = True
                stamped_classif["confirmed_by"] = reviewer
                stamped_classif["confirmed_at"] = now_iso
            stamped_lifecycle = stamped_canon.setdefault("lifecycle", {})
            if isinstance(stamped_lifecycle, dict):
                stamped_lifecycle["state"] = "approved"
                approvals = stamped_lifecycle.get("approvals")
                if not isinstance(approvals, list):
                    approvals = []
                approvals.append({
                    "by": reviewer,
                    "at": now_iso,
                    "version": target_job.version,
                    "content_sha256": target_job.content_sha256,
                })
                stamped_lifecycle["approvals"] = approvals
            canon_hash = compute_canonical_sha256(stamped_canon)
            draft_hash = compute_canonical_sha256(stamped_draft_data["draft"])

    prev_state = target_job.current_state
    prev_updated = target_job.updated_at
    prev_task = copy.deepcopy(target_job.review_task)
    prev_decision = target_job.approval_decision
    prev_gates = target_job.gate_results
    prev_hist_len = len(target_job.history)

    try:
        dec = governance_ledger.record_review_decision(
            job_id=target_job.job_id,
            decision=decision,
            reviewer=reviewer,
            actor_type=actor_type,
            notes=notes,
            publication_gate_check=gate_check,
            last_editor=server_last_editor,
            canonical_sha256=canon_hash,
            draft_sha256=draft_hash,
        )
        if stamped_draft_data is not None and draft_path:
            try:
                tmp_df = f"{draft_path}.{os.getpid()}.tmp"
                with open(tmp_df, "w", encoding="utf-8") as df:
                    json.dump(stamped_draft_data, df, indent=2)
                os.replace(tmp_df, draft_path)
            except Exception:
                with governance_ledger._lock:
                    target_job.current_state = prev_state
                    target_job.updated_at = prev_updated
                    target_job.review_task = prev_task
                    target_job.approval_decision = prev_decision
                    target_job.gate_results = prev_gates
                    del target_job.history[prev_hist_len:]
                    governance_ledger._save_unlocked()
                raise

        # Keep _processed_manifest.json synchronized with review decisions (tenant-scoped)
        try:
            m = read_manifest()
            d_data = stamped_draft_data if stamped_draft_data is not None else (
                saved_draft_data if isinstance(saved_draft_data, dict) else None
            )
            target_fn = (d_data or {}).get("raw_filename")
            if not target_fn:
                prefix = f"{target_job.tenant_id}::"
                for k, v in m.items():
                    if not isinstance(v, dict):
                        continue
                    if "::" in k and not k.startswith(prefix):
                        continue
                    if v.get("job_id") == target_job.job_id or v.get("sop_id") == target_job.sop_id:
                        target_fn = k.split("::", 1)[1] if "::" in k else k
                        break
            if target_fn:
                status_map = {
                    "approve": "approved",
                    "changes_requested": "changes_requested",
                    "reject": "rejected",
                    "rejected": "rejected",
                }
                entry = {
                    "status": status_map.get(dec.decision, target_job.current_state),
                    "sop_id": target_job.sop_id,
                    "job_id": target_job.job_id,
                    "task_id": task_id,
                    "sha256": target_job.content_sha256,
                    "tenant_id": target_job.tenant_id,
                    "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                if notes:
                    entry["reason"] = notes
                set_manifest_entry(m, target_job.tenant_id, target_fn, entry)
                write_manifest(m)
        except Exception as _exc:
            _log.warning("api_governance_record_decision: upload manifest was not updated (%s: %s)", type(_exc).__name__, _exc)

        return JSONResponse({
            "status": "success",
            "decision": dec.decision,
            "reviewer": dec.reviewer,
            "job_state": target_job.current_state,
            "canonical_sha256": dec.canonical_sha256,
            "gate_check": gate_check.__dict__ if gate_check else None,
        })
    except AuthAccessError:
        raise
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
    """Publishes an approved SOP strictly from its stored approved draft (never request body)."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER,),
        human_only=True,
        check_csrf=True,
    )
    sop_id = (request.path_params.get("sop_id") or "").strip()
    if not _SOP_ID_RE.fullmatch(sop_id):
        return JSONResponse({"error": "Invalid SOP id."}, status_code=400)
    try:
        await request.json()
    except Exception as _exc:
        _log.debug("api_governance_publish_sop: request has no JSON body (%s: %s)", type(_exc).__name__, _exc)

    target_job = _job_for_sop(sop_id, tenant_id=principal.tenant_id, preferred_states={"approved"})
    if not target_job:
        any_job = _job_for_sop(sop_id)
        if any_job:
            enforce_tenant_access(principal, any_job.tenant_id, request=request)
        return JSONResponse({"error": f"Job for SOP '{sop_id}' not found."}, status_code=404)

    enforce_tenant_access(principal, target_job.tenant_id, request=request)
    draft_path, saved_draft_data = _read_draft(sop_id)
    safe_draft_for_meta = saved_draft_data if isinstance(saved_draft_data, dict) else {}
    draft_meta = resolve_draft_access_meta(sop_id, draft_data=safe_draft_for_meta, job=target_job)
    enforce_clearance_access(principal, draft_meta["classification_level"], request=request)
    if target_job.current_state == "published":
        pub_meta = resolve_sop_access_meta(sop_id)
        enforce_clearance_access(principal, pub_meta["classification_level"], request=request)

    # Ignore request body completely (actor, canonical_sop, gate metrics); use token & stored draft only.
    actor = principal.identity

    try:
        if target_job.current_state != "approved" or not target_job.approval_decision:
            raise NotApprovedError(
                f"Job is in state '{target_job.current_state}', cannot publish. Must be 'approved'."
            )

        if not draft_path or not isinstance(saved_draft_data, dict):
            raise StaleApprovalError(
                f"Approved staged draft for SOP '{sop_id}' is missing or corrupted; re-approval is required before publishing."
            )
        canon_obj = saved_draft_data.get("canonical_draft")
        draft_obj = saved_draft_data.get("draft")
        if not isinstance(canon_obj, dict) or not isinstance(draft_obj, dict) or not draft_obj:
            raise StaleApprovalError(
                f"Approved staged draft for SOP '{sop_id}' is incomplete (missing canonical_draft or draft payload); re-approval is required."
            )

        stored_classif = canon_obj.get("classification") if isinstance(canon_obj.get("classification"), dict) else {}
        stored_level = normalize_clearance(stored_classif.get("level") or draft_meta["classification_level"])
        enforce_clearance_access(principal, stored_level, request=request)

        fm_obj = draft_obj.get("frontmatter") if isinstance(draft_obj.get("frontmatter"), dict) else draft_obj
        stored_sop_ids = [
            str(saved_draft_data.get("sop_id") or "").strip(),
            str(canon_obj.get("sop_id") or "").strip(),
            str(fm_obj.get("sop_id") or "").strip() if isinstance(fm_obj, dict) else "",
        ]
        if any(sid and sid != target_job.sop_id for sid in stored_sop_ids):
            raise StaleApprovalError(
                f"Draft SOP ID mismatch against approved job '{target_job.sop_id}'."
            )
        c_tenant = str(canon_obj.get("tenant_id") or saved_draft_data.get("tenant_id") or "").strip()
        if c_tenant and c_tenant != target_job.tenant_id:
            raise StaleApprovalError(
                f"Draft tenant '{c_tenant}' does not match approved job tenant '{target_job.tenant_id}'."
            )
        src_obj = canon_obj.get("source") if isinstance(canon_obj.get("source"), dict) else {}
        stored_file_sha = str(src_obj.get("file_sha256") or "").strip()
        if stored_file_sha and target_job.content_sha256 and stored_file_sha != target_job.content_sha256:
            raise StaleApprovalError(
                "Stored draft file_sha256 does not match approved job content hash."
            )

        current_canon_hash = compute_canonical_sha256(canon_obj)
        current_draft_hash = compute_canonical_sha256(draft_obj)
        gate_check = evaluate_draft_publication_gates(
            target_job,
            saved_draft_data,
            for_publish=True,
        )

        prev_state = target_job.current_state
        prev_updated = target_job.updated_at
        prev_gates = target_job.gate_results
        prev_hist_len = len(target_job.history)

        governance_ledger.publish_approved_sop(
            job_id=target_job.job_id,
            current_content_sha256=target_job.content_sha256,
            current_version=target_job.version,
            publication_gate_check=gate_check,
            actor=actor,
            current_canonical_sha256=current_canon_hash,
            current_draft_sha256=current_draft_hash,
            require_canonical_hash=True,
        )

        try:
            draft_to_write = copy.deepcopy(draft_obj)
            canonical_sop = copy.deepcopy(canon_obj)
            safe_name = saved_draft_data.get("raw_filename") or f"{sop_id}.txt"

            if not draft_to_write.get("raw_text") and safe_name:
                src_upload = resolve_tenant_upload(target_job.tenant_id, os.path.basename(str(safe_name)))
                if src_upload and os.path.exists(src_upload):
                    try:
                        _, segs = extract_ordered_sop_content(src_upload)
                        draft_to_write["raw_text"] = "\n\n".join(
                            s["content"] for s in segs if s.get("type") == "text"
                        )
                    except Exception as _exc:
                        _log.warning("api_governance_publish_sop: source text could not be re-extracted for the published draft (%s: %s)", type(_exc).__name__, _exc)

            canonical_sop["sop_id"] = target_job.sop_id
            canonical_sop["version"] = target_job.version
            canonical_sop["tenant_id"] = target_job.tenant_id
            canonical_sop.setdefault("lifecycle", {})["state"] = "published"
            canonical_sop["lifecycle"]["published_by"] = actor
            canonical_sop["lifecycle"]["published_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            canonical_sop.setdefault("source", {}).setdefault("file_sha256", target_job.content_sha256)

            saved_playbook_path = write_okf_playbook(
                draft_to_write,
                raw_filename=safe_name,
                tenant_id=target_job.tenant_id,
                uploaded_by=target_job.uploaded_by,
                canonical_data=canonical_sop,
            )
            indexed = retrieval_index.index_published_sop(canonical_sop)
            citation = indexed.citation if hasattr(indexed, "citation") else str(indexed)
        except Exception:
            with governance_ledger._lock:
                target_job.current_state = prev_state
                target_job.updated_at = prev_updated
                target_job.gate_results = prev_gates
                del target_job.history[prev_hist_len:]
                governance_ledger._save_unlocked()
            raise

        purge_staged_draft(sop_id)
        if draft_path and os.path.exists(draft_path):
            try:
                os.remove(draft_path)
            except Exception as _exc:
                _log.warning("api_governance_publish_sop: cleanup of leftover files failed (%s: %s)", type(_exc).__name__, _exc)

        try:
            pub_sop_id = canonical_sop.get("sop_id") or target_job.sop_id
            m = read_manifest()
            target_fn = safe_name if safe_name else None
            if not target_fn:
                prefix = f"{target_job.tenant_id}::"
                for k, v in m.items():
                    if not isinstance(v, dict):
                        continue
                    if "::" in k and not k.startswith(prefix):
                        continue
                    if v.get("job_id") == target_job.job_id or v.get("sop_id") in (sop_id, pub_sop_id):
                        target_fn = k.split("::", 1)[1] if "::" in k else k
                        break
            if target_fn:
                set_manifest_entry(m, target_job.tenant_id, target_fn, {
                    "status": "success",
                    "sop_id": pub_sop_id,
                    "job_id": target_job.job_id,
                    "sha256": target_job.content_sha256,
                    "tenant_id": target_job.tenant_id,
                    "published": True,
                    "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "playbook_path": saved_playbook_path,
                })
                write_manifest(m)
        except Exception as _exc:
            _log.warning("api_governance_publish_sop: upload manifest was not updated (%s: %s)", type(_exc).__name__, _exc)

        return JSONResponse({
            "status": "published",
            "sop_id": target_job.sop_id,
            "tenant_id": target_job.tenant_id,
            "version": target_job.version,
            "citation": citation,
            "job_state": target_job.current_state,
            "playbook_path": saved_playbook_path,
            "canonical_sha256": current_canon_hash,
        })
    except AuthAccessError:
        raise
    except StaleApprovalError as e:
        return JSONResponse({"error": str(e), "error_code": e.error_code}, status_code=409)
    except NotApprovedError as e:
        return JSONResponse({"error": str(e), "error_code": e.error_code}, status_code=400)
    except GateFailureError as e:
        return JSONResponse({"error": str(e), "error_code": e.error_code, "failures": e.failure_reasons}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def api_governance_get_canonical(request: Request):
    """Retrieves Canonical SOP JSON 1.0 document (published accessible to all matching roles; drafts human-only)."""
    principal = authenticate_request(
        request,
        allowed_roles=ROLE_SET,
        human_only=False,
        check_csrf=False,
    )
    sop_id = request.path_params.get("sop_id") or ""
    if not _SOP_ID_RE.fullmatch(sop_id):
        return JSONResponse({"error": "Invalid SOP id."}, status_code=400)

    pattern = os.path.join(SOPS_DIR, "**", f"{sop_id}.canonical.json")
    files = glob.glob(pattern, recursive=True)
    if not files:
        draft_path, draft_data = _read_draft(sop_id)
        if draft_path and draft_data is not None:
            if not principal.is_human:
                raise AuthAccessError(
                    403,
                    "Downstream agents may only read published SOPs, not unapproved drafts.",
                    "not_human",
                )
            d_meta = resolve_draft_access_meta(sop_id, draft_data=draft_data)
            enforce_tenant_access(principal, d_meta["tenant_id"], request=request)
            enforce_clearance_access(principal, d_meta["classification_level"], request=request)
            return JSONResponse(draft_data.get("canonical_draft", {}))
        return JSONResponse({"error": f"Canonical SOP '{sop_id}' not found."}, status_code=404)

    with open(files[0], "r", encoding="utf-8") as f:
        data = json.load(f)
    meta = resolve_sop_access_meta(sop_id, frontmatter=data)
    enforce_tenant_access(principal, meta["tenant_id"], request=request)
    enforce_clearance_access(principal, meta["classification_level"], request=request)
    if not principal.is_human and meta.get("state") != "published":
        raise AuthAccessError(403, "Agents may only access published canonical SOPs.", "not_authorized")
    return JSONResponse(data)


async def api_governance_update_canonical(request: Request):
    """Updates canonical JSON strictly for already-published SOPs (process_owner/admin only within tenant & clearance)."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER, ROLE_ADMIN),
        human_only=True,
        check_csrf=True,
    )
    sop_id = request.path_params.get("sop_id") or ""
    if not _SOP_ID_RE.fullmatch(sop_id):
        return JSONResponse({"error": "Invalid SOP id."}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    existing = glob.glob(os.path.join(SOPS_DIR, "**", f"{sop_id}.canonical.json"), recursive=True)
    if existing:
        with open(existing[0], "r", encoding="utf-8") as f:
            ex_data = json.load(f)
        meta = resolve_sop_access_meta(sop_id, frontmatter=ex_data)
        enforce_tenant_access(principal, meta["tenant_id"], request=request)
        enforce_clearance_access(principal, meta["classification_level"], request=request)
        pub_state = str((ex_data.get("lifecycle") or {}).get("state") or meta.get("state") or "").lower()
        if pub_state != "published":
            return JSONResponse(
                {
                    "error": "Direct canonical updates are only allowed for published SOPs. Edit unapproved drafts via /api/governance/drafts/{sop_id}.",
                    "error_code": "not_published",
                },
                status_code=409,
            )
    else:
        _, draft_data = _read_draft(sop_id)
        job = _job_for_sop(sop_id)
        if draft_data is not None or job is not None:
            d_meta = resolve_draft_access_meta(sop_id, draft_data=draft_data, job=job)
            enforce_tenant_access(principal, d_meta["tenant_id"], request=request)
            enforce_clearance_access(principal, d_meta["classification_level"], request=request)
        else:
            req_tier = normalize_clearance((body.get("classification") or {}).get("level", "L1"))
            enforce_clearance_access(principal, req_tier, request=request)
        return JSONResponse(
            {
                "error": f"SOP '{sop_id}' is not published. Edit unapproved drafts via /api/governance/drafts/{sop_id}.",
                "error_code": "not_published",
            },
            status_code=409,
        )

    req_tier = normalize_clearance((body.get("classification") or {}).get("level") or meta["classification_level"])
    enforce_clearance_access(principal, req_tier, request=request)
    body["sop_id"] = sop_id
    body["tenant_id"] = principal.tenant_id
    body.setdefault("lifecycle", {})["state"] = "published"
    category = body.get("category") or os.path.basename(os.path.dirname(existing[0])) or "general"
    try:
        json_path = write_canonical_sop_json(body, category=category)
        sync_canonical_to_playbook(body, category=category)
        return JSONResponse({"status": "updated", "sop_id": sop_id, "path": json_path})
    except Exception as e:
        return JSONResponse({"error": f"Failed updating canonical SOP: {e}"}, status_code=400)


async def api_governance_sync_playbook(request: Request):
    """Synchronizes canonical JSON to OKF playbook strictly for already-published SOPs (process_owner/admin only)."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER, ROLE_ADMIN),
        human_only=True,
        check_csrf=True,
    )
    sop_id = request.path_params.get("sop_id") or ""
    if not _SOP_ID_RE.fullmatch(sop_id):
        return JSONResponse({"error": "Invalid SOP id."}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    existing = glob.glob(os.path.join(SOPS_DIR, "**", f"{sop_id}.canonical.json"), recursive=True)
    if existing:
        with open(existing[0], "r", encoding="utf-8") as f:
            ex_data = json.load(f)
        meta = resolve_sop_access_meta(sop_id, frontmatter=ex_data)
        enforce_tenant_access(principal, meta["tenant_id"], request=request)
        enforce_clearance_access(principal, meta["classification_level"], request=request)
        pub_state = str((ex_data.get("lifecycle") or {}).get("state") or meta.get("state") or "").lower()
        if pub_state != "published":
            return JSONResponse(
                {
                    "error": "Playbook sync is only allowed for published SOPs. Edit unapproved drafts via /api/governance/drafts/{sop_id}.",
                    "error_code": "not_published",
                },
                status_code=409,
            )
    else:
        _, draft_data = _read_draft(sop_id)
        job = _job_for_sop(sop_id)
        if draft_data is not None or job is not None:
            d_meta = resolve_draft_access_meta(sop_id, draft_data=draft_data, job=job)
            enforce_tenant_access(principal, d_meta["tenant_id"], request=request)
            enforce_clearance_access(principal, d_meta["classification_level"], request=request)
        else:
            canonical_peek = body.get("canonical_sop") or body
            req_tier = normalize_clearance((canonical_peek.get("classification") or {}).get("level", "L1"))
            enforce_clearance_access(principal, req_tier, request=request)
        return JSONResponse(
            {
                "error": f"SOP '{sop_id}' is not published. Playbook sync requires a published SOP.",
                "error_code": "not_published",
            },
            status_code=409,
        )

    canonical_data = body.get("canonical_sop") or body
    req_tier = normalize_clearance((canonical_data.get("classification") or {}).get("level") or meta["classification_level"])
    enforce_clearance_access(principal, req_tier, request=request)
    canonical_data["sop_id"] = sop_id
    canonical_data["tenant_id"] = principal.tenant_id

    try:
        md_path = sync_canonical_to_playbook(canonical_data)
        return JSONResponse({"status": "synced", "sop_id": sop_id, "playbook_path": md_path})
    except Exception as e:
        return JSONResponse({"error": f"Sync failed: {e}"}, status_code=400)


async def api_governance_downstream_search(request: Request):
    """Downstream agent & human retrieval query: tenant, clearance, agent_id & persona derived strictly from token."""
    principal = authenticate_request(
        request,
        allowed_roles=ROLE_SET,
        human_only=False,
        check_csrf=True,
    )
    try:
        body = await request.json()
    except Exception:
        body = {}

    query = str(body.get("query", "") or "")
    department = body.get("department")
    try:
        limit = max(1, min(100, int(body.get("limit", 10))))
    except (TypeError, ValueError):
        limit = 10

    # Never trust tenant_id, clearance_level, agent_id, or agent_persona from body!
    tenant_id = principal.tenant_id
    clearance_level = principal.clearance
    agent_id = principal.agent_id or principal.identity
    agent_persona = principal.agent_persona

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
        "caller_identity": principal.identity,
    })


async def api_governance_downstream_stats(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=ROLE_SET,
        human_only=False,
        check_csrf=False,
    )
    # Ignore any ?tenant_id= query override; always scope to verified token tenant
    stats = retrieval_index.get_stats(tenant_id=principal.tenant_id)
    stats["tenant_id"] = principal.tenant_id
    return JSONResponse(stats)


async def api_governance_quarantine_incidents(request: Request):
    """Lists quarantine incidents restricted strictly to security_reviewer & admin inside caller tenant."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_SECURITY_REVIEWER, ROLE_ADMIN),
        human_only=True,
        check_csrf=False,
    )
    try:
        governance_ledger.load()
    except Exception as _exc:
        _log.warning("api_governance_quarantine_incidents: ledger reload failed, using in-memory state (%s: %s)", type(_exc).__name__, _exc)
    incidents = []
    for job in list(governance_ledger._jobs.values()):
        if job.incident and job.tenant_id == principal.tenant_id:
            inc = dict(job.incident)
            inc.setdefault("tenant_id", job.tenant_id)
            incidents.append(inc)
    return JSONResponse({"incidents": incidents, "count": len(incidents)})


async def api_get_config(request: Request):
    """Returns active dynamic pipeline configuration (Admin only)."""
    authenticate_request(
        request,
        allowed_roles=(ROLE_ADMIN,),
        human_only=True,
        check_csrf=False,
    )
    from config.settings import get_settings
    return JSONResponse(get_settings().get_all())


async def api_update_config(request: Request):
    """Dynamically updates pipeline configuration (Admin only, schema-validated, audited)."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_ADMIN,),
        human_only=True,
        check_csrf=True,
    )
    from config.settings import (
        update_settings, get_settings, validate_config_updates, audit_config_change,
    )
    ip = get_client_ip(request)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    # H1: allowlist + type/range validation. Nothing is saved if any field is invalid.
    clean, errors = validate_config_updates(body)
    if errors:
        audit_config_change(principal.identity, ip, {}, {}, "rejected: " + "; ".join(errors)[:300])
        log_auth_event(
            "config_update_rejected",
            identity=principal.identity, sub=principal.sub, roles=principal.roles,
            tenant_id=principal.tenant_id, clearance=principal.clearance,
            actor_type=principal.actor_type, client_ip=ip, path=str(request.url.path),
            status="rejected", detail="; ".join(errors)[:300],
        )
        return JSONResponse({"error": "Invalid config update", "details": errors}, status_code=422)

    before = json.loads(json.dumps(get_settings().get_all()))
    updated_cfg = update_settings(clean)
    audit_config_change(principal.identity, ip, before, clean, "applied")
    log_auth_event(
        "config_updated",
        identity=principal.identity, sub=principal.sub, roles=principal.roles,
        tenant_id=principal.tenant_id, clearance=principal.clearance,
        actor_type=principal.actor_type, client_ip=ip, path=str(request.url.path),
        status="ok",
        detail=f"keys={','.join(sorted(f'{s}.{k}' for s, v in clean.items() for k in v))}",
    )
    return JSONResponse({
        "status": "success",
        "message": "Pipeline configuration dynamically updated and persisted.",
        "updated_by": principal.identity,
        "config": updated_cfg,
    })


# ---------------------------------------------------------------------------
# Draft step editing (review page). Edits stay in _drafts until published.
# ---------------------------------------------------------------------------

_SOP_ID_RE = re.compile(r"[A-Za-z0-9_-]+")
_MAX = {
    "sop_step_description": 1000,
    "command": 4000,
    "fallback_command": 4000,
    "source_quote": 1000,
    "parse_instruction": 1500,
}


def _merge_document_sections(old: dict, fm: dict, extra: dict, raw_text: str):
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


_EDITABLE_JSON_KEYS = (
    "title", "department", "owner", "version_label", "review_date", "purpose", "scope",
    "preconditions", "roles", "exceptions", "notes", "references", "steps",
)
_PROTECTED_JSON_KEYS = (
    "schema_version", "sop_id", "version", "tenant_id", "title_lines", "metadata_lines", "source",
    "media", "issues", "classification", "quality", "transformations", "lifecycle", "provenance",
)
_PROTECTED_HINTS = {
    "classification": "the confidentiality tier is confirmed with the checkbox on the decision form",
    "quality": "it is computed from the document and your steps when you save",
    "lifecycle": "it is controlled by the review workflow",
}
_EDITABLE_DRAFT_STATES = {"awaiting_review", "changes_requested"}


def _apply_step_edits(path: str, data: dict, steps_in: list, actor: str, canonical_extra: dict = None):
    """Validate + apply edits, rebuild canonical copy using tenant-scoped source upload, write draft atomically."""
    draft = data["draft"]
    fm = draft.get("frontmatter") or draft
    existing = fm.get("steps") or []

    errors, new_steps = [], []
    for i, raw in enumerate(steps_in, start=1):
        ref = raw.get("ref")
        base = copy.deepcopy(existing[ref - 1]) if isinstance(ref, int) and 1 <= ref <= len(existing) else {
            "step_type": "command", "shell": "powershell", "timeout_seconds": 30,
            "platform": None, "function_name": None, "comm_inputs": None, "fallback_sop_id": None,
            "execute_if": None, "step_reasoning": "Added by process owner.",
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

    for i, st in enumerate(new_steps, start=1):
        for threat in scan_commands_for_ast_threats([c for c in (st.get("command"), st.get("fallback_command")) if c]):
            errors.append(f"Step {i}: blocked by the security screen ({threat['description']}).")
    if errors:
        return {"errors": errors}

    warnings, known = [], set()
    for i, st in enumerate(new_steps, start=1):
        for var in re.findall(r"variables\.(\w+)", st.get("execute_if") or ""):
            if var not in known:
                warnings.append(f"Step {i} only runs if variables.{var}, but no earlier step sets it.")
        known |= set(re.findall(r"variables\.(\w+)\s*=", st.get("parse_instruction") or ""))

    old = copy.deepcopy(data.get("canonical_draft") or {})
    draft_meta = resolve_draft_access_meta(data.get("sop_id") or old.get("sop_id") or "", draft_data=data)
    tenant_id = draft_meta["tenant_id"]

    raw_name = os.path.basename(str(data.get("raw_filename") or ""))
    source_path = resolve_tenant_upload(tenant_id, raw_name) if raw_name else None
    if not raw_name or not source_path or not os.path.exists(source_path):
        return {"errors": [f"The source document '{raw_name}' is no longer in the uploads folder, so the quotes cannot be re-verified."]}

    _, segments = extract_ordered_sop_content(source_path)
    raw_text = "\n\n".join(s_["content"] for s_ in segments if s_.get("type") == "text")

    fm_copy = copy.deepcopy(fm)
    fm_copy["steps"] = new_steps
    work_draft = copy.deepcopy(draft)
    if isinstance(work_draft.get("frontmatter"), dict):
        work_draft["frontmatter"] = fm_copy
    else:
        work_draft = fm_copy
    if not work_draft.get("raw_text"):
        work_draft["raw_text"] = raw_text
    rebuilt = build_canonical_sop_from_draft(
        work_draft,
        raw_text=raw_text,
        tenant_id=tenant_id,
        uploaded_by=(old.get("lifecycle") or {}).get("uploaded_by", draft_meta.get("uploaded_by") or "author@corp.com"),
        vlm_reports=work_draft.get("vlm_reports"),
        ai_advisory=work_draft.get("ai_advisory"),
    )
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    old["steps"] = rebuilt["steps"]
    old["quality"] = rebuilt["quality"]
    old["issues"] = rebuilt.get("issues", old.get("issues", []))
    if rebuilt.get("media"):
        old["media"] = rebuilt["media"]
    if canonical_extra:
        _merge_document_sections(old, fm_copy, canonical_extra, raw_text)
    classif_old = old.get("classification")
    if isinstance(classif_old, dict):
        classif_old["confirmed"] = False
        classif_old["confirmed_by"] = None
        classif_old.pop("confirmed_at", None)
    schema_ok, schema_errs, _ = validate_canonical_sop_dict(old)
    if not schema_ok:
        return {"errors": [f"Canonical schema validation failed: {e}" for e in schema_errs]}
    old.setdefault("quality", {})["schema_valid"] = True
    old.setdefault("lifecycle", {}).update({"last_editor": actor, "last_edited_at": now})

    fm["steps"] = fm_copy["steps"]
    if "title" in fm_copy:
        fm["title"] = fm_copy["title"]
    if not draft.get("raw_text"):
        draft["raw_text"] = raw_text
    data["canonical_draft"] = old
    data["last_editor"], data["last_edited_at"] = actor, now

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
    return {"canonical_draft": old, "warnings": warnings, "step_count": len(new_steps)}


async def api_governance_get_draft(request: Request):
    """Returns draft steps & metadata; editable strictly by 'process_owner' in awaiting_review or changes_requested."""
    principal = authenticate_request(
        request,
        allowed_roles=HUMAN_ROLES,
        human_only=True,
        check_csrf=False,
    )
    sop_id = request.path_params.get("sop_id", "")
    _, data = _read_draft(sop_id)
    if not data:
        return JSONResponse({"error": f"No draft found for '{sop_id}'."}, status_code=404)

    job = _job_for_sop(
        sop_id,
        tenant_id=principal.tenant_id,
        preferred_states=_EDITABLE_DRAFT_STATES,
    ) or _job_for_sop(sop_id)
    draft_meta = resolve_draft_access_meta(sop_id, draft_data=data, job=job)
    enforce_tenant_access(principal, draft_meta["tenant_id"], request=request)
    enforce_clearance_access(principal, draft_meta["classification_level"], request=request)

    state = job.current_state if job else None
    is_po = principal.has_role(ROLE_PROCESS_OWNER)
    editable = bool(is_po and state in _EDITABLE_DRAFT_STATES)
    if editable:
        editable_reason = None
    elif not job:
        editable_reason = "No lifecycle job exists for this draft."
    elif not is_po:
        editable_reason = "Only a Process Owner can edit SOP drafts before approval."
    else:
        editable_reason = "This SOP is no longer awaiting review or changes requested, so its steps are locked."

    last_review_decision = None
    if job and isinstance(job.approval_decision, dict) and job.approval_decision.get("decision") == "changes_requested":
        last_review_decision = dict(job.approval_decision)
    elif job and job.history:
        for h in reversed(job.history):
            if h.get("to_state") == "changes_requested":
                last_review_decision = {
                    "decision": "changes_requested",
                    "reviewer": h.get("actor"),
                    "timestamp": h.get("timestamp"),
                    "notes": h.get("reason") or "",
                }
                break

    fm = (data.get("draft") or {}).get("frontmatter") or data.get("draft") or {}
    return JSONResponse({
        "sop_id": sop_id,
        "tenant_id": draft_meta["tenant_id"],
        "sop_tier": draft_meta["classification_level"],
        "task_id": (job.review_task or {}).get("task_id") if job else data.get("task_id"),
        "job_state": state,
        "editable": editable,
        "editable_reason": editable_reason,
        "last_editor": data.get("last_editor"),
        "last_edited_at": data.get("last_edited_at"),
        "last_review_decision": last_review_decision,
        "steps": fm.get("steps") or [],
    })


async def api_governance_update_draft_steps(request: Request):
    """Saves Process Owner's step edits on a draft in 'awaiting_review' or 'changes_requested'."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER,),
        human_only=True,
        check_csrf=True,
    )
    sop_id = request.path_params.get("sop_id", "")
    try:
        body = await request.json()
    except Exception:
        body = {}

    steps_in = body.get("steps")
    if not isinstance(steps_in, list):
        return JSONResponse({"error": "'steps' must be a list."}, status_code=400)

    path, data = _read_draft(sop_id)
    if not data:
        return JSONResponse({"error": f"No draft found for '{sop_id}'."}, status_code=404)

    job = _job_for_sop(
        sop_id,
        tenant_id=principal.tenant_id,
        preferred_states=_EDITABLE_DRAFT_STATES,
    ) or _job_for_sop(sop_id)
    draft_meta = resolve_draft_access_meta(sop_id, draft_data=data, job=job)
    enforce_tenant_access(principal, draft_meta["tenant_id"], request=request)
    enforce_clearance_access(principal, draft_meta["classification_level"], request=request)

    if not job or job.current_state not in _EDITABLE_DRAFT_STATES:
        return JSONResponse(
            {"error": "Steps can only be edited while the SOP is awaiting review or has changes requested."},
            status_code=409,
        )

    actor = principal.identity
    try:
        result = await run_in_threadpool(_apply_step_edits, path, data, steps_in, actor)
    except Exception as e:
        return JSONResponse({"error": f"Could not save the edits: {e}"}, status_code=500)
    if "errors" in result:
        return JSONResponse({"error": result["errors"][0], "errors": result["errors"]}, status_code=422)

    try:
        if job.current_state == "awaiting_review":
            governance_ledger.transition_state(
                job.job_id,
                "awaiting_review",
                actor=actor,
                reason=f"Steps edited by process owner ({result['step_count']} steps).",
            )
        else:
            governance_ledger.record_draft_edit(
                job.job_id,
                actor=actor,
                reason=f"Steps revised by process owner ({result['step_count']} steps).",
            )
    except Exception as e:
        result["warnings"].append(f"Edit saved, but could not be logged in the job history: {e}")
    return JSONResponse({"status": "saved", "last_editor": actor, "job_state": job.current_state, **result})


async def api_governance_update_draft_canonical(request: Request):
    """Saves Process Owner's canonical JSON edits on a draft in 'awaiting_review' or 'changes_requested'."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER,),
        human_only=True,
        check_csrf=True,
    )
    sop_id = request.path_params.get("sop_id", "")
    try:
        body = await request.json()
    except Exception:
        body = {}

    canon = body.get("canonical")
    if not isinstance(canon, dict):
        return JSONResponse({"error": "'canonical' must be a JSON object."}, status_code=400)
    if len(json.dumps(canon)) > 300_000:
        return JSONResponse({"error": "The JSON is too large (limit 300 KB)."}, status_code=413)

    path, data = _read_draft(sop_id)
    if not data:
        return JSONResponse({"error": f"No draft found for '{sop_id}'."}, status_code=404)

    job = _job_for_sop(
        sop_id,
        tenant_id=principal.tenant_id,
        preferred_states=_EDITABLE_DRAFT_STATES,
    ) or _job_for_sop(sop_id)
    draft_meta = resolve_draft_access_meta(sop_id, draft_data=data, job=job)
    enforce_tenant_access(principal, draft_meta["tenant_id"], request=request)
    enforce_clearance_access(principal, draft_meta["classification_level"], request=request)

    if not job or job.current_state not in _EDITABLE_DRAFT_STATES:
        return JSONResponse(
            {"error": "The JSON can only be edited while the SOP is awaiting review or has changes requested."},
            status_code=409,
        )

    current = data.get("canonical_draft") or {}
    problems = []
    for key in canon:
        if key not in _EDITABLE_JSON_KEYS and key not in _PROTECTED_JSON_KEYS:
            problems.append(f"'{key}' is not a field of the canonical SOP.")
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

    actor = principal.identity
    try:
        result = await run_in_threadpool(_apply_step_edits, path, data, edits, actor, canon)
    except Exception as e:
        return JSONResponse({"error": f"Could not save the edits: {e}"}, status_code=500)
    if "errors" in result:
        return JSONResponse({"error": result["errors"][0], "errors": result["errors"]}, status_code=422)
    try:
        if job.current_state == "awaiting_review":
            governance_ledger.transition_state(
                job.job_id,
                "awaiting_review",
                actor=actor,
                reason="Canonical JSON edited by process owner.",
            )
        else:
            governance_ledger.record_draft_edit(
                job.job_id,
                actor=actor,
                reason="Canonical JSON revised by process owner.",
            )
    except Exception as e:
        result["warnings"].append(f"Edit saved, but could not be logged in the job history: {e}")
    return JSONResponse({"status": "saved", "last_editor": actor, "job_state": job.current_state, **result})


async def api_governance_resubmit_draft(request: Request):
    """Resubmits a 'changes_requested' draft for fresh Security Reviewer sign-off (Process Owner only)."""
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_PROCESS_OWNER,),
        human_only=True,
        check_csrf=True,
    )
    sop_id = (request.path_params.get("sop_id") or "").strip()
    if not _SOP_ID_RE.fullmatch(sop_id):
        return JSONResponse({"error": "Invalid SOP id."}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    path, data = _read_draft(sop_id)
    if not data:
        return JSONResponse({"error": f"No draft found for '{sop_id}'."}, status_code=404)

    job = _job_for_sop(
        sop_id,
        tenant_id=principal.tenant_id,
        preferred_states={"changes_requested", "awaiting_review"},
    ) or _job_for_sop(sop_id)
    draft_meta = resolve_draft_access_meta(sop_id, draft_data=data, job=job)
    enforce_tenant_access(principal, draft_meta["tenant_id"], request=request)
    enforce_clearance_access(principal, draft_meta["classification_level"], request=request)

    if not job:
        return JSONResponse({"error": f"Job for SOP '{sop_id}' not found."}, status_code=404)

    if job.current_state != "changes_requested":
        return JSONResponse(
            {
                "error": f"Cannot resubmit SOP '{sop_id}' from state '{job.current_state}'. Must be 'changes_requested'.",
                "error_code": "invalid_state",
            },
            status_code=409,
        )

    reason = str(body.get("notes") or body.get("reason") or "").strip()
    classif = (data.get("canonical_draft") or {}).get("classification") or {}
    conf_score = int(classif.get("score", 25))
    conf_level = normalize_clearance(classif.get("level", draft_meta["classification_level"]))

    try:
        new_task = governance_ledger.resubmit_for_review(
            job_id=job.job_id,
            actor=principal.identity,
            reason=reason,
            confidentiality_score=conf_score,
            confidentiality_level=conf_level,
        )
    except Exception as e:
        code = getattr(e, "error_code", None)
        status_code = 409 if code == "invalid_state" else 400
        payload = {"error": str(e)}
        if code:
            payload["error_code"] = code
        return JSONResponse(payload, status_code=status_code)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data["task_id"] = new_task.task_id
    data["resubmitted_by"] = principal.identity
    data["resubmitted_at"] = now
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

    try:
        m = read_manifest()
        target_fn = data.get("raw_filename")
        if not target_fn:
            prefix = f"{job.tenant_id}::"
            for k, v in m.items():
                if not isinstance(v, dict):
                    continue
                if "::" in k and not k.startswith(prefix):
                    continue
                if v.get("job_id") == job.job_id or v.get("sop_id") == job.sop_id:
                    target_fn = k.split("::", 1)[1] if "::" in k else k
                    break
        if target_fn:
            set_manifest_entry(m, job.tenant_id, target_fn, {
                "status": "awaiting_review",
                "sop_id": job.sop_id,
                "job_id": job.job_id,
                "task_id": new_task.task_id,
                "sha256": job.content_sha256,
                "tenant_id": job.tenant_id,
                "processed_at": now,
            })
            write_manifest(m)
    except Exception as _exc:
        _log.warning("api_governance_resubmit_draft: upload manifest was not updated (%s: %s)", type(_exc).__name__, _exc)

    return JSONResponse({
        "status": "resubmitted",
        "sop_id": job.sop_id,
        "job_id": job.job_id,
        "job_state": job.current_state,
        "task_id": new_task.task_id,
        "assigned_role": new_task.assigned_role,
        "due_date": new_task.due_date,
    })


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
governance_router.add_api_route("/api/governance/drafts/{sop_id}/resubmit", api_governance_resubmit_draft, methods=["POST"], summary="Resubmit Revised SOP Draft for Security Review")
governance_router.add_api_route("/api/governance/downstream/search", api_governance_downstream_search, methods=["POST"], summary="Search Catalog (Clearance & Tenant Filtered)")
governance_router.add_api_route("/api/governance/downstream/stats", api_governance_downstream_stats, methods=["GET"], summary="Get Downstream Catalog Metrics")
governance_router.add_api_route("/api/governance/incidents", api_governance_quarantine_incidents, methods=["GET"], summary="List Security Quarantine Incidents")
governance_router.add_api_route("/api/config", api_get_config, methods=["GET"], summary="Get Dynamic Pipeline Configuration")
governance_router.add_api_route("/api/config", api_update_config, methods=["POST"], summary="Hot-Reload Dynamic Configuration", operation_id="api_update_config_post")
governance_router.add_api_route("/api/config", api_update_config, methods=["PUT"], summary="Hot-Reload Dynamic Configuration (PUT)", operation_id="api_update_config_put")

governance_routes = list(governance_router.routes)
