"""Runtime Lifecycle Controls & Operator Management.

Provides operator commands for:
1. Demo Reset Issue (purging DB checkpoints and resetting state to RECEIVED)
2. Safe-Checkpoint Cancellation (step-boundary halting via kill switch)
3. Structured Human Handover packaging for on-call operator escalation
"""

from typing import Any, Dict, Optional
from contracts.state import EngineStateEnum, validate_transition_or_raise
from orchestrator.checkpointer import SqliteCheckpointer
from orchestrator.kill_switch import GLOBAL_KILL_SWITCH


def reset_issue(thread_id: str, checkpointer: SqliteCheckpointer) -> Dict[str, Any]:
    """Purge all checkpoints for an issue thread and reset state to RECEIVED.

    Mandated by Page 3 Demo Requirements to allow repeatable pilot runs.
    """
    checkpointer.delete_thread(thread_id)
    GLOBAL_KILL_SWITCH.disengage_thread(thread_id)
    return {
        "thread_id": thread_id,
        "workflow_state": EngineStateEnum.RECEIVED.value,
        "message": f"Thread {thread_id} checkpoints purged and state reset to RECEIVED.",
    }


def cancel_execution(thread_id: str) -> Dict[str, Any]:
    """Safely cancel an execution thread at the next step boundary."""
    GLOBAL_KILL_SWITCH.engage_thread(thread_id)
    return {
        "thread_id": thread_id,
        "cancelled": True,
        "workflow_state": EngineStateEnum.STOPPED_KILL_SWITCH.value,
        "message": f"Kill switch engaged for thread {thread_id}. Next mutation step will abort.",
    }


def package_human_handover(
    thread_id: str,
    state: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    """Package structured incident context for human operator escalation (NEEDS_HUMAN)."""
    current_state_str = state.get("workflow_state", EngineStateEnum.EXECUTING.value)
    current_state = EngineStateEnum(current_state_str)
    target_state = EngineStateEnum.NEEDS_HUMAN

    # Only validate if not already in terminal state
    if current_state != target_state:
        validate_transition_or_raise(current_state, target_state)

    plan = state.get("plan") or {}
    idx = state.get("current_step_idx", 0)
    steps = plan.get("steps", [])
    failed_step = steps[idx] if idx < len(steps) else None

    return {
        "thread_id": thread_id,
        "workflow_state": target_state.value,
        "escalation_reason": reason,
        "failed_step_index": idx,
        "failed_step": failed_step,
        "completed_outputs": state.get("execution_outputs", []),
        "verification_results": state.get("verification_results", []),
        "recommended_action": "Review step failure and perform manual verification or remediation.",
    }

