"""
Agent A6: SOP Hub & Downstream Catalog Agent
============================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.6, 14 & 18)
- Stage 1: Downstream Clearance Retrieval Catalog (L0-L3 gates, instant purge)
- Stage 2: Production SOP Publisher
- Stage 3: Reflection Rulebook Management
"""

from agents.a5_review.sod_policy import evaluate_publication_gates
from agents.a6_hub.retrieval_catalog import (
    DownstreamRetrievalIndex,
    IndexedSOP,
    RetrievalResult,
    RetrievalAuditRecord,
    normalize_clearance,
    format_citation,
    CLEARANCE_RANKS,
    CLEARANCE_DESCRIPTIONS,
    PERSONA_DEFAULT_CLEARANCE,
)

__all__ = [
    "evaluate_publication_gates",
    "DownstreamRetrievalIndex",
    "IndexedSOP",
    "RetrievalResult",
    "RetrievalAuditRecord",
    "normalize_clearance",
    "format_citation",
    "CLEARANCE_RANKS",
    "CLEARANCE_DESCRIPTIONS",
    "PERSONA_DEFAULT_CLEARANCE",
]
