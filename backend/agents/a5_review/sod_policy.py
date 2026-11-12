"""
Agent A5: Separation of Duties (SoD) Policy Engine
===================================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.5 & 13)
Enforces:
1. uploader != reviewer (self-approval prohibited)
2. last_editor != reviewer (self-signoff on revisions prohibited)
3. actor_type == "human" (automated AI approvals strictly blocked)
"""

import copy
import hashlib
import json
from typing import Tuple, Optional, List, Dict, Any
from schemas.governance_models import (
    SeparationOfDutiesViolation,
    NotHumanActorError,
    PublicationGateResult,
)
from schemas.canonical_sop_schema import validate_canonical_sop_dict
from agents.a3_security.secret_scanner import scan_for_secrets
from agents.a3_security.ast_sandbox import scan_commands_for_ast_threats
from agents.a4_verification.quote_tracer import (
    verify_canonical_quotes,
    compute_source_line_coverage,
)


def verify_separation_of_duties(
    uploaded_by: str,
    reviewer: str,
    last_editor: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Enforces non-negotiable Separation of Duties (Section 13).
    The reviewer must be a human distinct from the uploader and the last JSON editor.
    """
    if not reviewer or not str(reviewer).strip():
        return False, "Reviewer identity is required."
    
    clean_reviewer = str(reviewer).strip().lower()
    clean_uploader = str(uploaded_by).strip().lower()

    if clean_uploader == clean_reviewer:
        return False, f"Separation of Duties Violation: Uploader '{uploaded_by}' cannot approve their own SOP."

    if last_editor and str(last_editor).strip().lower() == clean_reviewer:
        return False, f"Separation of Duties Violation: Last editor '{last_editor}' cannot approve their own revisions."

    return True, None


def validate_human_reviewer(actor_type: str) -> None:
    """Blocks non-human approval actors."""
    if str(actor_type).strip().lower() != "human":
        raise NotHumanActorError(f"Approval rejected: Only human reviewers may record decisions (received actor_type='{actor_type}').")


def evaluate_publication_gates(
    secrets_count: int,
    is_quarantined: bool,
    schema_valid: bool,
    schema_errors_count: int,
    traceability_pct: float,
    completeness_pct: float,
    open_blocking_issues_count: int,
    classification_confirmed: bool,
    rule_ai_conflict: bool = False,
) -> PublicationGateResult:
    """Evaluates the 6 mandatory Publication Gates (Section 9.1).
    All 6 gates MUST pass for a document to be approved or published.
    """
    failures: List[str] = []
    gates_detail: Dict[str, Dict[str, Any]] = {}

    # Gate 1: Secret gate passed, no quarantine
    gate1_pass = (secrets_count == 0) and (not is_quarantined)
    gates_detail["gate_1_secrets"] = {
        "title": "Secret Gate & Malware Quarantine",
        "passed": gate1_pass,
        "detail": f"{secrets_count} secrets detected; quarantined={is_quarantined}",
    }
    if not gate1_pass:
        failures.append("Gate 1 Failed: Live secrets detected or document is in quarantine.")

    # Gate 2: Canonical JSON valid (0 schema errors)
    gate2_pass = bool(schema_valid) and (schema_errors_count == 0)
    gates_detail["gate_2_schema"] = {
        "title": "Canonical Schema Validation",
        "passed": gate2_pass,
        "detail": f"schema_valid={schema_valid}, errors={schema_errors_count}",
    }
    if not gate2_pass:
        failures.append(f"Gate 2 Failed: Canonical schema validation failed ({schema_errors_count} errors).")

    # Gate 3: Source traceability >= 90%
    gate3_pass = traceability_pct >= 90.0
    gates_detail["gate_3_traceability"] = {
        "title": "Source Quote Traceability (>= 90%)",
        "passed": gate3_pass,
        "detail": f"{traceability_pct:.1f}% verified verbatim quotes",
    }
    if not gate3_pass:
        failures.append(f"Gate 3 Failed: Source traceability {traceability_pct:.1f}% is below required 90.0%.")

    # Gate 4: Extraction completeness >= 80%
    gate4_pass = completeness_pct >= 80.0
    gates_detail["gate_4_completeness"] = {
        "title": "Extraction Completeness (>= 80%)",
        "passed": gate4_pass,
        "detail": f"{completeness_pct:.1f}% source lines mapped",
    }
    if not gate4_pass:
        failures.append(f"Gate 4 Failed: Extraction completeness {completeness_pct:.1f}% is below required 80.0%.")

    # Gate 5: No open blocking issues or agent conflicts (0 open)
    gate5_pass = (open_blocking_issues_count == 0) and (not rule_ai_conflict)
    gates_detail["gate_5_issues"] = {
        "title": "Zero Open Blocking Issues & Conflicts",
        "passed": gate5_pass,
        "detail": f"{open_blocking_issues_count} open issues; rule_ai_conflict={rule_ai_conflict}",
    }
    if not gate5_pass:
        failures.append(f"Gate 5 Failed: Unresolved blocking issues ({open_blocking_issues_count}) or rule vs AI conflict.")

    # Gate 6: Confidentiality tier confirmed
    gate6_pass = bool(classification_confirmed)
    gates_detail["gate_6_classification"] = {
        "title": "Confidentiality Tier Confirmed",
        "passed": gate6_pass,
        "detail": f"confirmed={classification_confirmed}",
    }
    if not gate6_pass:
        failures.append("Gate 6 Failed: Sensitivity classification level has not been confirmed.")

    all_passed = (len(failures) == 0)
    return PublicationGateResult(
        passed=all_passed,
        gates=gates_detail,
        failure_reasons=failures,
    )


def compute_canonical_sha256(data: Dict[str, Any]) -> str:
    """Computes deterministic SHA-256 hex digest over JSON-serialized canonical structure."""
    serialized = json.dumps(
        data if data is not None else {},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _safe_pct(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if num != num:  # NaN guard
        return None
    return max(0.0, min(100.0, num))


def _collect_text_blobs_for_secret_scan(draft_obj: Dict[str, Any], fm: Dict[str, Any], canon: Dict[str, Any]) -> List[str]:
    blobs: List[str] = []
    seen = set()

    def _add(v: Any):
        if isinstance(v, str):
            s = v.strip()
            if s and s not in seen:
                seen.add(s)
                blobs.append(s)

    _add(draft_obj.get("raw_text"))
    _add(fm.get("title"))
    _add(fm.get("description"))
    for st in fm.get("steps") or []:
        if isinstance(st, dict):
            for key in ("sop_step_description", "description", "command", "fallback_command", "source_quote", "parse_instruction"):
                _add(st.get(key))
            ci = st.get("comm_inputs")
            if isinstance(ci, str):
                _add(ci)
            elif isinstance(ci, dict):
                _add(json.dumps(ci, sort_keys=True))

    _add(canon.get("title"))
    for sec_key in ("purpose", "scope"):
        sec = canon.get(sec_key)
        if isinstance(sec, dict):
            _add(sec.get("text"))
            _add(sec.get("quote"))
    for list_key in ("preconditions", "notes"):
        for item in canon.get(list_key) or []:
            if isinstance(item, dict):
                _add(item.get("text"))
                _add(item.get("quote"))
    for exc in canon.get("exceptions") or []:
        if isinstance(exc, dict):
            _add(exc.get("condition"))
            _add(exc.get("action"))
            _add(exc.get("quote"))
    for st in canon.get("steps") or []:
        if isinstance(st, dict):
            for key in ("action", "input", "expected_outcome", "warning", "quote"):
                _add(st.get(key))
    return blobs


def _collect_commands_for_ast_scan(fm: Dict[str, Any], canon: Dict[str, Any]) -> List[str]:
    commands: List[str] = []
    for st in fm.get("steps") or []:
        if not isinstance(st, dict):
            continue
        for key in ("command", "fallback_command"):
            val = st.get(key)
            if isinstance(val, str) and val.strip():
                commands.append(val)
    for st in canon.get("steps") or []:
        if not isinstance(st, dict):
            continue
        if st.get("step_type") != "tool_call":
            inp = st.get("input")
            if isinstance(inp, str) and inp.strip():
                commands.append(inp)
        warn = st.get("warning")
        if isinstance(warn, str) and warn.strip():
            commands.append(warn)
    return commands


def _collect_coverage_meta(draft_obj: Dict[str, Any], fm: Dict[str, Any], canon: Dict[str, Any]) -> List[str]:
    meta: List[str] = []
    for val in (
        canon.get("title"),
        fm.get("title"),
        fm.get("category"),
        fm.get("description"),
    ):
        if isinstance(val, str) and val.strip():
            meta.append(val)
    for key in ("department", "owner", "version_label", "review_date"):
        cell = canon.get(key)
        if isinstance(cell, dict) and cell.get("value"):
            meta.append(str(cell["value"]))
    for key in ("purpose", "scope"):
        blk = canon.get(key)
        if isinstance(blk, dict) and blk.get("text"):
            meta.append(str(blk["text"]))
    for p in canon.get("preconditions") or []:
        if isinstance(p, dict) and p.get("text"):
            meta.append(str(p["text"]))
    for n_item in canon.get("notes") or []:
        if isinstance(n_item, dict) and n_item.get("text"):
            meta.append(str(n_item["text"]))
    for exc in canon.get("exceptions") or []:
        if isinstance(exc, dict) and exc.get("condition"):
            meta.append(str(exc["condition"]))
    if isinstance(fm.get("trigger_words"), list):
        meta.extend(str(w) for w in fm["trigger_words"] if w is not None)
    for source_dict in (fm, draft_obj):
        if isinstance(source_dict, dict):
            for k, v in source_dict.items():
                if k in ("steps", "source_action_coverage", "raw_text", "enriched_text", "vlm_reports", "knowledge_base_ref", "frontmatter"):
                    continue
                if isinstance(v, (str, int, float)):
                    meta.append(str(v))
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, (str, int, float)):
                            meta.append(str(item))
                        elif isinstance(item, dict):
                            for sub_v in item.values():
                                if isinstance(sub_v, (str, int, float)):
                                    meta.append(str(sub_v))
    return meta


def evaluate_draft_publication_gates(
    job: Any,
    draft_data: Optional[Dict[str, Any]],
    *,
    for_publish: bool = False,
    body_confirmed_classification: Optional[bool] = None,
) -> PublicationGateResult:
    """Computes all 6 Publication Gates strictly from server-side job and stored draft state.

    Never reads gate scores, secret counts, schema booleans, or conflict flags from request bodies.
    """
    job_quarantined = bool(
        getattr(job, "current_state", None) == "quarantined"
        or getattr(job, "incident", None)
        or getattr(job, "purged", False)
    )
    init_confirmed = False if for_publish else (body_confirmed_classification is True)

    canon = draft_data.get("canonical_draft") if isinstance(draft_data, dict) else None
    draft_obj = draft_data.get("draft") if isinstance(draft_data, dict) else None
    if not isinstance(draft_data, dict) or not isinstance(canon, dict) or not isinstance(draft_obj, dict) or not draft_obj:
        return evaluate_publication_gates(
            secrets_count=0,
            is_quarantined=job_quarantined,
            schema_valid=False,
            schema_errors_count=1,
            traceability_pct=0.0,
            completeness_pct=0.0,
            open_blocking_issues_count=0,
            classification_confirmed=init_confirmed,
            rule_ai_conflict=False,
        )

    fm = draft_obj.get("frontmatter") if isinstance(draft_obj.get("frontmatter"), dict) else draft_obj
    quality = canon.get("quality") if isinstance(canon.get("quality"), dict) else {}
    classif = canon.get("classification") if isinstance(canon.get("classification"), dict) else {}

    # Gate 1: Live secret scan + quarantine status
    is_quarantined = job_quarantined or (str(quality.get("status") or "").strip().lower() == "quarantined")
    secrets_count = 0
    for blob in _collect_text_blobs_for_secret_scan(draft_obj, fm if isinstance(fm, dict) else {}, canon):
        _, blob_secrets, _, _ = scan_for_secrets(blob)
        secrets_count += blob_secrets

    # Gate 2: Schema validation, non-empty steps, draft<->canonical parity, and job binding
    schema_valid_raw, schema_errors, _ = validate_canonical_sop_dict(canon)
    schema_errors = list(schema_errors)
    canon_steps = canon.get("steps") if isinstance(canon.get("steps"), list) else []
    fm_steps = fm.get("steps") if isinstance(fm, dict) and isinstance(fm.get("steps"), list) else None
    if not isinstance(fm, dict) or fm_steps is None:
        schema_errors.append("Draft frontmatter must include a steps list.")
    elif len(canon_steps) != len(fm_steps):
        schema_errors.append(f"Step count mismatch between draft ({len(fm_steps)}) and canonical JSON ({len(canon_steps)}).")
    if len(canon_steps) == 0:
        schema_errors.append("Canonical SOP must contain at least one step.")

    job_sop_id = str(getattr(job, "sop_id", "") or "").strip()
    job_tenant = str(getattr(job, "tenant_id", "") or "").strip()
    job_sha = str(getattr(job, "content_sha256", "") or "").strip()
    for field_name, val in (
        ("draft.sop_id", str(draft_data.get("sop_id") or "").strip()),
        ("canonical_draft.sop_id", str(canon.get("sop_id") or "").strip()),
        ("frontmatter.sop_id", str(fm.get("sop_id") or "").strip() if isinstance(fm, dict) else ""),
    ):
        if val and job_sop_id and val != job_sop_id:
            schema_errors.append(f"{field_name} '{val}' does not match job.sop_id '{job_sop_id}'.")

    c_tenant = str(canon.get("tenant_id") or "").strip()
    if c_tenant and job_tenant and c_tenant != job_tenant:
        schema_errors.append(f"canonical_draft.tenant_id '{c_tenant}' does not match job.tenant_id '{job_tenant}'.")

    c_src = canon.get("source") if isinstance(canon.get("source"), dict) else {}
    c_file_sha = str(c_src.get("file_sha256") or "").strip()
    if c_file_sha and job_sha and c_file_sha != job_sha:
        schema_errors.append("canonical_draft.source.file_sha256 does not match job.content_sha256.")

    schema_errors_count = len(schema_errors)
    schema_valid = bool(schema_valid_raw) and (schema_errors_count == 0)

    # Gate 3 (Traceability >= 90%) & Gate 4 (Completeness >= 80%)
    stored_trace = _safe_pct(quality.get("traceability"))
    stored_comp = _safe_pct(quality.get("completeness"))
    raw_text = str(draft_obj.get("raw_text") or "").strip()
    vlm_reports = draft_obj.get("vlm_reports") or []

    if not canon_steps:
        traceability_pct = 0.0
    elif raw_text or vlm_reports:
        source_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        steps_copy = copy.deepcopy(canon_steps)
        _, verified_q, _ = verify_canonical_quotes(
            steps_copy,
            source_lines,
            vlm_reports=vlm_reports,
        )
        recomp_trace = round((verified_q / max(1, len(canon_steps))) * 100.0, 1)
        recomp_trace = max(0.0, min(100.0, recomp_trace))
        traceability_pct = min(stored_trace, recomp_trace) if stored_trace is not None else recomp_trace
    else:
        if stored_trace is None:
            traceability_pct = 0.0
        else:
            verified_flags = sum(1 for st in canon_steps if isinstance(st, dict) and st.get("verified") is True)
            flag_pct = round((verified_flags / max(1, len(canon_steps))) * 100.0, 1)
            traceability_pct = min(stored_trace, flag_pct)

    if raw_text:
        source_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        steps_for_cov = copy.deepcopy(canon_steps)
        verify_canonical_quotes(steps_for_cov, source_lines, vlm_reports=vlm_reports)
        coverage_meta = _collect_coverage_meta(draft_obj, fm if isinstance(fm, dict) else {}, canon)
        total_nb, mapped_cnt, _ = compute_source_line_coverage(
            raw_lines=source_lines,
            steps=steps_for_cov,
            coverage_items=(fm.get("source_action_coverage") or []) if isinstance(fm, dict) else [],
            metadata_fields=coverage_meta,
        )
        recomp_comp = round((mapped_cnt / max(1, total_nb)) * 100.0, 1)
        recomp_comp = max(0.0, min(100.0, recomp_comp))
        completeness_pct = min(stored_comp, recomp_comp) if stored_comp is not None else recomp_comp
    else:
        completeness_pct = stored_comp if stored_comp is not None else 0.0

    # Gate 5: Open blocking issues + live command AST sandbox + rule-vs-AI conflict
    raw_issues = canon.get("issues") or []
    open_issues = 0
    if isinstance(raw_issues, list):
        for iss in raw_issues:
            if not isinstance(iss, dict):
                open_issues += 1
            elif str(iss.get("status") or "open").strip().lower() != "resolved":
                open_issues += 1
    try:
        stored_blocking = max(0, int(quality.get("blocking_issues_count") or 0))
    except (TypeError, ValueError):
        stored_blocking = 1
    ast_threats = scan_commands_for_ast_threats(_collect_commands_for_ast_scan(fm if isinstance(fm, dict) else {}, canon))
    open_blocking_issues_count = max(open_issues, stored_blocking) + len(ast_threats)

    rule_lvl = str(classif.get("rule_level") or "").strip().upper()
    ai_lvl = str(classif.get("ai_suggested_level") or "").strip().upper()
    resolved_by_human = (
        bool(str(classif.get("override_reason") or "").strip())
        and not bool(classif.get("conflict", False))
    )
    rule_ai_conflict = bool(classif.get("conflict", False)) or (
        not resolved_by_human and bool(rule_lvl) and bool(ai_lvl) and rule_lvl != ai_lvl
    )

    # Gate 6: Confidentiality tier confirmation
    if for_publish:
        classification_confirmed = classif.get("confirmed") is True
    else:
        classification_confirmed = body_confirmed_classification is True

    return evaluate_publication_gates(
        secrets_count=secrets_count,
        is_quarantined=is_quarantined,
        schema_valid=schema_valid,
        schema_errors_count=schema_errors_count,
        traceability_pct=traceability_pct,
        completeness_pct=completeness_pct,
        open_blocking_issues_count=open_blocking_issues_count,
        classification_confirmed=classification_confirmed,
        rule_ai_conflict=rule_ai_conflict,
    )


__all__ = [
    "verify_separation_of_duties",
    "validate_human_reviewer",
    "evaluate_publication_gates",
    "compute_canonical_sha256",
    "evaluate_draft_publication_gates",
]
