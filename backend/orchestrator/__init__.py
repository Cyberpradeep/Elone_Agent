"""
SOP Governance Hub — Orchestrator & Multi-Agent Bus
===================================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5, 6, 8, 10, 15)
- OrchestratorLedger: 14-state lifecycle machine & audit history
- AgentBus: msg/1.0 protocol message routing matrix & event log
"""

from orchestrator.ledger import (
    OrchestratorLedger,
    verify_separation_of_duties,
    validate_human_reviewer,
    evaluate_publication_gates,
)
from orchestrator.bus import (
    AgentBus,
)

# Backwards compatibility alias
GovernanceLedger = OrchestratorLedger

__all__ = [
    "OrchestratorLedger",
    "GovernanceLedger",
    "AgentBus",
    "verify_separation_of_duties",
    "validate_human_reviewer",
    "evaluate_publication_gates",
]

