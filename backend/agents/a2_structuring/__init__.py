"""
Agent A2: Cleaning & Structuring Agent
======================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.2)
- Stage 1: Triage Router (Intent Classification)
- Stage 2: JIT Execution Planner (6-Stage CoT Synthesis)
- Stage 3: OKF Playbook Builder (HMAC-SHA256 digital stamp)
- Stage 4: Canonical SOP JSON 1.0 Builder & Dual-Export Synchronizer
"""

from agents.a2_structuring.triage_router import run_triage_router, _run_triage_router
from agents.a2_structuring.execution_planner import (
    plan_okf_from_raw,
    convert_raw_sop_to_okf,
)
from agents.a2_structuring.okf_builder import (
    write_okf_playbook,
)
from agents.a2_structuring.canonical_builder import (
    build_canonical_sop_from_draft,
    write_canonical_sop_json,
    sync_canonical_to_playbook,
    sync_canonical_to_okf,
)

__all__ = [
    "run_triage_router",
    "_run_triage_router",
    "plan_okf_from_raw",
    "convert_raw_sop_to_okf",
    "write_okf_playbook",
    "build_canonical_sop_from_draft",
    "write_canonical_sop_json",
    "sync_canonical_to_playbook",
    "sync_canonical_to_okf",
]
