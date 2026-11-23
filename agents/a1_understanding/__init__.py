"""Agent A1: Intake & Understanding Subsystem.

Provides:
- Input prompt injection scanning and XML delimiter fencing.
- Sensitive secret and credential scrubbing.
- Domain asset lookup integration from shared/asset_lookup.py.
- Validated contracts.issue.Issue construction.
- Tenant-isolated SOP catalog retrieval with 0.82 confidence and 0.05 ambiguity gates.
"""

from agents.a1_understanding.sanitizer import (
    detect_prompt_injection,
    scrub_sensitive_secrets,
    sanitize_and_fence_text,
)
from agents.a1_understanding.retrieval import (
    match_sop_catalog,
    compute_match_score,
    MatchCandidate,
    RetrievalResult,
    MIN_CONFIDENCE_THRESHOLD,
    AMBIGUITY_DELTA_THRESHOLD,
)
from agents.a1_understanding.intake import (
    intake_ticket,
    IntakeResult,
)

__all__ = [
    "detect_prompt_injection",
    "scrub_sensitive_secrets",
    "sanitize_and_fence_text",
    "match_sop_catalog",
    "compute_match_score",
    "MatchCandidate",
    "RetrievalResult",
    "MIN_CONFIDENCE_THRESHOLD",
    "AMBIGUITY_DELTA_THRESHOLD",
    "intake_ticket",
    "IntakeResult",
]
