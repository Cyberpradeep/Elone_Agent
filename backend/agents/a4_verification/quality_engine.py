"""
Agent A4: Quality Scoring Engine
================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.4 & 12)
Mathematical quality formula:
  Q = 0.4*C + 0.4*T + 20 - 5*B
Status thresholds:
  Ready (>= 85%), Needs Attention (70-84%), Failed Checks (< 70%), Quarantined.
"""

from typing import Dict, Any


def compute_quality_score(
    total_non_blank_lines: int,
    mapped_source_lines: int,
    total_quotes: int,
    verified_quotes: int,
    schema_valid: bool = True,
    blocking_issues_count: int = 0,
    is_quarantined: bool = False,
) -> Dict[str, Any]:
    """Calculates mathematical quality score and assigns readiness status per Section 12."""
    completeness = round((mapped_source_lines / max(1, total_non_blank_lines)) * 100.0, 1)
    completeness = min(100.0, max(0.0, completeness))

    if total_quotes == 0:
        traceability = 100.0
    else:
        traceability = round((verified_quotes / max(1, total_quotes)) * 100.0, 1)
    traceability = min(100.0, max(0.0, traceability))

    schema_points = 20.0 if schema_valid else 0.0
    blocking_penalty = 5.0 * max(0, blocking_issues_count)
    raw_score = (0.4 * completeness) + (0.4 * traceability) + schema_points - blocking_penalty
    quality_score = round(max(0.0, min(100.0, raw_score)), 1)

    if is_quarantined:
        status = "Quarantined"
    elif not schema_valid or traceability < 50.0:
        status = "Failed checks"
    elif completeness >= 85.0 and traceability >= 95.0 and blocking_issues_count == 0:
        status = "Ready"
    else:
        status = "Needs attention"

    return {
        "completeness": completeness,
        "traceability": traceability,
        "schema_valid": schema_valid,
        "blocking_issues_count": blocking_issues_count,
        "quality_score": quality_score,
        "status": status,
        "is_ready": (status == "Ready"),
    }


__all__ = [
    "compute_quality_score",
]
