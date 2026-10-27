"""
Agent A3: Security & Confidentiality Agent
==========================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.3)
- Stage 1: Secret Scanner & Terminal Quarantine (Gate 2)
- Stage 2: Confidentiality Scoring Engine (0-100 Score & L0-L3 Tiers)
- Stage 3: AST Command Sandboxing & Malicious Pattern Guard
"""

from agents.a3_security.secret_scanner import (
    scan_for_secrets,
    create_quarantine_incident,
)
from agents.a3_security.confidentiality_engine import (
    compute_confidentiality_score,
    score_to_tier,
    TIER_ORDER,
    TIER_LABELS,
)
from agents.a3_security.ast_sandbox import (
    validate_command_sandbox,
)

__all__ = [
    "scan_for_secrets",
    "create_quarantine_incident",
    "compute_confidentiality_score",
    "score_to_tier",
    "TIER_ORDER",
    "TIER_LABELS",
    "validate_command_sandbox",
]
