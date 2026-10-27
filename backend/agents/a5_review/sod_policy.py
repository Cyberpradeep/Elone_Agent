"""
Agent A5: Separation of Duties (SoD) Policy Engine
===================================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.5 & 13)
Enforces:
1. uploader != reviewer (self-approval prohibited)
2. last_editor != reviewer (self-signoff on revisions prohibited)
3. actor_type == "human" (automated AI approvals strictly blocked)
"""

from typing import Tuple, Optional, List, Dict, Any
from schemas.governance_models import (
    SeparationOfDutiesViolation,
    NotHumanActorError,
    PublicationGateResult,
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


__all__ = [
    "verify_separation_of_duties",
    "validate_human_reviewer",
    "evaluate_publication_gates",
]
