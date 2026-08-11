"""Execution Result Agent Node (Output Verifier & Variable Extractor)."""

from typing import Literal
from langgraph.types import Command

from shared.state import SupportState
from shared.logger import log_agent
from .extractor import extract_variables_and_verdict


@log_agent
def execution_result_agent(state: SupportState) -> Command[Literal["orchestration_agent"]]:
    """Process 2: Output Verification & Variable Extraction Agent Node.

    1. Analyzes CLI stdout/stderr OR API Tool JSON response via extractor.py.
    2. Extracts state variables into clean snake_case dictionary.
    3. Merges extracted variables into state["variables"] and state["entities"].
    4. Sets next_action (SUCCESS/RETRY/ESCALATE) for orchestration routing.
    """
    plan = state.get("execution_plan") or {}
    steps = plan.get("steps") or []
    step_num = state.get("current_step_index", 0)
    target_step = steps[step_num] if step_num < len(steps) else {}

    command = state.get("last_executed_command") or target_step.get("command") or "(unknown command)"
    stdout = state.get("last_executed_stdout") or ""
    stderr = state.get("last_executed_stderr") or ""
    exit_code = state.get("last_executed_exit_code") if state.get("last_executed_exit_code") is not None else 0

    entities = state.get("entities") or {}
    hostname = entities.get("hostname", "unknown_host")
    variables = state.get("variables") or {}

    print(f"\n--------------------------------------------------")
    print(f"--- [EXECUTION RESULT AGENT NODE - STEP {step_num + 1}/{len(steps)}] ---")
    print(f"  Verifying Output for: {command}")
    print(f"  Exit Code: {exit_code}")
    print(f"--------------------------------------------------")

    # Extract variables and determine next_action verdict
    normalized_vars, next_act, reasoning_text = extract_variables_and_verdict(
        target_step=target_step,
        step_num=step_num,
        command=command,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        hostname=hostname,
        variables=variables
    )

    # Merge variables into state
    updated_variables = dict(variables)
    updated_entities = dict(entities)

    for k, v in normalized_vars.items():
        updated_variables[k] = v
        updated_entities[k] = v

    if normalized_vars:
        print(f"  [Variables Extracted]: {normalized_vars}")
    else:
        print(f"  [Variables Extracted]: None")

    execution_results = dict(state.get("execution_results") or {})
    execution_results[step_num + 1] = stdout or stderr or f"Exit Code {exit_code}"

    execution_exit_codes = dict(state.get("execution_exit_codes") or {})
    execution_exit_codes[step_num + 1] = exit_code

    audit_msg = (
        f"[Execution Result Step {step_num + 1}] "
        f"Verdict: {next_act}. Reasoning: {reasoning_text}. Extracted: {normalized_vars}"
    )
    print(f"  {audit_msg}")

    # Update future execution plan steps with dynamic extracted variables (e.g. user_id from search_users)
    updated_plan = dict(plan)
    if normalized_vars and "steps" in updated_plan and isinstance(updated_plan["steps"], list):
        updated_steps = [dict(s) for s in updated_plan["steps"]]
        for future_idx in range(step_num + 1, len(updated_steps)):
            fstep = dict(updated_steps[future_idx])
            if "comm_inputs" in fstep and isinstance(fstep["comm_inputs"], dict):
                finputs = dict(fstep["comm_inputs"])
                for k, v in normalized_vars.items():
                    if k in finputs or f"entities.{k}" in str(finputs.values()) or f"variables.{k}" in str(finputs.values()):
                        finputs[k] = v
                fstep["comm_inputs"] = finputs
            updated_steps[future_idx] = fstep
        updated_plan["steps"] = updated_steps

    return Command(
        goto="orchestration_agent",
        update={
            "execution_plan": updated_plan,
            "variables": updated_variables,
            "entities": updated_entities,
            "next_action": next_act,
            "last_executed_step": step_num + 1,
            "execution_results": execution_results,
            "execution_exit_codes": execution_exit_codes,
            "execution_reasoning": reasoning_text,
            "audit_log": [audit_msg],
        },
    )
