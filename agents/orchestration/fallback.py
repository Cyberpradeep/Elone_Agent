"""Cross-SOP referral and fallback swapping logic for Orchestration Agent."""

from typing import Tuple, Optional, Dict, Any
from shared.state import SupportState


def check_cross_sop_referral(
    state: SupportState,
    target_step: dict,
    idx: int,
    retry_count: int
) -> Tuple[bool, Optional[str], Optional[dict]]:
    """Checks if step failure requires a Cross-SOP referral (fallback_sop_id)."""
    fallback_sop_id = target_step.get("fallback_sop_id")
    if state.get("next_action") == "RETRY" and retry_count >= 2 and fallback_sop_id:
        audit_msg = f"[Orchestrator] Cross-SOP Referral triggered -> planner_agent ({fallback_sop_id})"
        update_dict = {
            "retrieval_query": fallback_sop_id,
            "matched_file_path": fallback_sop_id,
            "orchestrator_reasoning": f"Referring to fallback SOP '{fallback_sop_id}'",
            "audit_log": [audit_msg]
        }
        return True, audit_msg, update_dict

    return False, None, None


def apply_fallback_swapping(
    current_plan: Dict[str, Any],
    idx: int,
    retry_count: int,
    state: SupportState
) -> Dict[str, Any]:
    """Swaps step configuration to fallback command or tool parameters on step retries."""
    updated_plan = dict(current_plan)
    steps = updated_plan.get("steps") or []

    if state.get("next_action") == "RETRY" and idx < len(steps):
        target_step = steps[idx]
        step_type = target_step.get("step_type", "command")
        fallback_cmd = target_step.get("fallback_command")

        if step_type == "tool_call":
            # Tool call step fallback handling
            if fallback_cmd:
                print(f"  [Orchestrator] Swapping Step {idx + 1} Tool Call fallback: '{fallback_cmd}'")
                steps_copy = [dict(s) for s in steps]
                steps_copy[idx]["comm_inputs"] = steps_copy[idx].get("comm_inputs") or {}
                steps_copy[idx]["comm_inputs"]["fallback_parameter"] = fallback_cmd
                updated_plan["steps"] = steps_copy
        else:
            # Command step fallback handling
            if fallback_cmd and target_step.get("command") != fallback_cmd:
                print(f"  [Orchestrator] Swapping Step {idx + 1} command to SOP fallback command: '{fallback_cmd}'")
                steps_copy = [dict(s) for s in steps]
                steps_copy[idx]["command"] = fallback_cmd
                updated_plan["steps"] = steps_copy

    return updated_plan
