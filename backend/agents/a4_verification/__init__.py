"""
Agent A4: Verification & Quality Engine Agent
=============================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.4)
- Stage 1: Quality Scoring Engine (0.4C + 0.4T + 20 - 5B)
- Stage 2: Verbatim Quote Tracer (+/-1 Line Window Matching)
- Stage 3: Faithfulness & Procedural Plan Linkage Validator
"""

from agents.a4_verification.quality_engine import (
    compute_quality_score,
)
from agents.a4_verification.quote_tracer import (
    verify_quote_trace,
    verify_canonical_quotes,
)
from agents.a4_verification.plan_validator import (
    validate_plan_faithfulness,
    validate_plan_faithfulness_and_linkage,
)

__all__ = [
    "compute_quality_score",
    "verify_quote_trace",
    "verify_canonical_quotes",
    "validate_plan_faithfulness",
    "validate_plan_faithfulness_and_linkage",
]
