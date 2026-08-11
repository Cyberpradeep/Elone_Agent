"""API Tool Call execution runner for Execution Agent."""

import json
from typing import Tuple, Dict, Any
from execution_tools import resolve_step_placeholders, execute_comm_tool


def execute_tool_step(
    target_step: Dict[str, Any],
    step_num: int,
    len_steps: int,
    entities: Dict[str, Any],
    variables: Dict[str, Any]
) -> Tuple[str, str, int, str]:
    """Executes an API Tool Call step via backend tool catalog providers (Auth0 / Okta / Mock).

    Returns: (stdout_json, stderr, exit_code, executed_tool_label)
    """
    resolved_step = resolve_step_placeholders(target_step, entities, variables)
    provider_name = resolved_step.get("provider", "mock")
    function_name = resolved_step.get("function_name", "execute_tool")
    comm_inputs = resolved_step.get("comm_inputs") or {}

    tool_label = f"[TOOL CALL: {provider_name}.{function_name}]"

    print(f"\n--------------------------------------------------")
    print(f"--- [API TOOL RUNNER - STEP {step_num}/{len_steps}] ---")
    print(f"  Description: {target_step.get('sop_step_description')}")
    print(f"  Provider: {provider_name}")
    print(f"  Function: {function_name}")
    print(f"  Inputs: {comm_inputs}")
    print(f"--------------------------------------------------")

    try:
        # Dynamic execution via tool catalog helper with strict provider matching
        res = execute_comm_tool(function_name, comm_inputs, provider_name=provider_name)
        stdout_str = json.dumps(res, indent=2) if isinstance(res, dict) else str(res)

        print(f"  [API Tool Runner Output]: {stdout_str}")
        return stdout_str, "", 0, tool_label
    except Exception as e:
        err_msg = f"API Tool Execution Exception ({provider_name}.{function_name}): {str(e)}"
        print(f"  [API Tool Runner Error]: {err_msg}")
        return "", err_msg, 1, tool_label
