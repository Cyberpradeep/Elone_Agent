"""Circuit breaker and escalation guardrails for Orchestration Agent."""

from typing import Tuple, Optional
from shared.state import SupportState


def check_escalation_guardrails(state: SupportState, idx: int, len_steps: int) -> Tuple[bool, Optional[str]]:
    """Checks circuit breakers and escalation guardrails (< 1ms).

    Returns: (is_escalated, audit_or_reason_message)
    """
    # 1. HITL Rejection, Explicit Escalation, or Invalid Plan Interception
    if (
        state.get("is_human_rejected")
        or state.get("workflow_status") == "escalated"
        or state.get("next_action") == "ESCALATE"
        or state.get("plan_valid") is False
        or state.get("validator_result") in ["INVALID_PLAN", "WRONG_SOP"]
    ):
        reason = (
            state.get("plan_feedback")
            or state.get("orchestrator_reasoning")
            or state.get("execution_reasoning")
            or "Workflow explicitly escalated, execution plan invalid, or human rejected."
        )
        return True, f"[Orchestrator] Execution halted -> escalation_agent ({reason})"

    retry_count = state.get("execution_retry_attempts", 0) or state.get("retry_count", 0)

    # 2. Circuit Breaker 1: Step Retry Limit (Max 3)
    if state.get("next_action") == "RETRY" and retry_count >= 3:
        return True, "[Orchestrator] Guardrail -> escalation_agent: Execution retry budget exhausted (3 attempts)"

    # 3. Circuit Breaker 2: Total Execution Budget (Max 15 steps run across ticket)
    if idx < len_steps and idx >= 15:
        return True, "[Orchestrator] Guardrail -> escalation_agent: Total ticket execution step limit reached (15 steps)"

    return False, None
