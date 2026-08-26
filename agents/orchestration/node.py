"""Orchestration Agent Node (Traffic Controller)."""

from typing import Literal
# pyrefly: ignore [missing-import]
from langgraph.types import Command

from shared.state import SupportState
from .guardrails import check_escalation_guardrails
from .fallback import check_cross_sop_referral, apply_fallback_swapping


def orchestration_agent(state: SupportState) -> Command[Literal["execution_agent", "planner_agent", "summarization_agent", "escalation_agent"]]:
    """Deterministic Traffic Controller for LangGraph Workflow.

    1. Enforces Human-in-the-Loop (HITL) Interception & Escalation routing.
    2. Enforces Circuit Breakers (Max retries & execution step limits).
    3. Handles Cross-SOP Referrals (fallback_sop_id -> planner_agent).
    4. Advances current_step_index on SUCCESS and routes to summarization_agent when finished.
    """
    current_plan = state.get("execution_plan") or {}
    steps = current_plan.get("steps") or []
    idx = state.get("current_step_index", 0)
    retry_count = state.get("execution_retry_attempts", 0) or state.get("retry_count", 0)

    # 1. Check Circuit Breakers & Escalation Guardrails
    is_escalated, audit_msg = check_escalation_guardrails(state, idx, len(steps))
    if is_escalated:
        print(f"  {audit_msg}")
        return Command(
            goto="escalation_agent",
            update={
                "workflow_status": "escalated",
                "orchestrator_reasoning": audit_msg,
                "audit_log": [audit_msg]
            }
        )

    # 2. Handle Cross-SOP Referrals (fallback_sop_id)
    if idx < len(steps):
        target_step = steps[idx]
        is_referred, ref_msg, ref_update = check_cross_sop_referral(state, target_step, idx, retry_count)
        if is_referred:
            print(f"  {ref_msg}")
            return Command(goto="planner_agent", update=ref_update)

    # 3. Handle Step Success & Advancement
    if state.get("next_action") == "SUCCESS":
        next_idx = idx + 1
        if next_idx >= len(steps):
            audit_msg = "[Orchestrator] All steps finished successfully -> summarization_agent"
            print(f"  {audit_msg}")
            return Command(
                goto="summarization_agent",
                update={
                    "workflow_status": "completed",
                    "orchestrator_reasoning": "All steps executed successfully.",
                    "audit_log": [audit_msg]
                }
            )
        else:
            audit_msg = f"[Orchestrator] Step {idx + 1} SUCCESS -> Advancing to Step {next_idx + 1}"
            print(f"  {audit_msg}")
            return Command(
                goto="execution_agent",
                update={
                    "current_step_index": next_idx,
                    "execution_retry_attempts": 0,
                    "next_action": None,
                    "audit_log": [audit_msg]
                }
            )

    # 4. Initial Execution or Step Retry Path (With Fallback Swapping)
    is_retry = state.get("next_action") == "RETRY"
    new_retry_count = retry_count + 1 if is_retry else 0

    if is_retry and new_retry_count > 3:
        audit_msg = f"[Orchestrator] Guardrail -> escalation_agent: Execution retry budget exhausted ({new_retry_count} attempts)"
        print(f"  {audit_msg}")
        return Command(
            goto="escalation_agent",
            update={
                "workflow_status": "escalated",
                "orchestrator_reasoning": audit_msg,
                "audit_log": [audit_msg]
            }
        )

    updated_plan = apply_fallback_swapping(current_plan, idx, new_retry_count, state)

    if not is_retry:
        audit_msg = f"[Orchestrator] Dispatching Step {idx + 1}/{len(steps)} -> execution_agent"
    else:
        audit_msg = f"[Orchestrator] Retrying Step {idx + 1}/{len(steps)} (Attempt {new_retry_count}/3) -> execution_agent"

    print(f"  {audit_msg}")
    return Command(
        goto="execution_agent",
        update={
            "execution_plan": updated_plan,
            "execution_retry_attempts": new_retry_count,
            "next_action": None,
            "audit_log": [audit_msg]
        }
    )
