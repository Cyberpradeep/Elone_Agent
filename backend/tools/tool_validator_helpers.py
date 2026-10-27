"""
Layer 1 Deterministic Tool Validation Helpers
=============================================
Validates tool_call steps against the registered platform schemas in tools.platforms.
"""

from typing import Dict, List, Any, Optional, Tuple

# pyrefly: ignore [missing-import]
from tools.platforms import (
    DETAILED_TOOL_SCHEMAS,
    find_platform_schema,
    get_all_valid_platform_names,
)


def get_platform_functions(platform_name: str) -> Dict[str, Dict[str, Any]]:
    """Returns a map of {function_name: function_dict} strictly for a given platform."""
    schema = find_platform_schema(platform_name)
    if not schema:
        return {}
    return {fn["function_name"]: fn for fn in schema.get("functions", []) if "function_name" in fn}


def get_platform_required_inputs(platform_name: str, function_name: str) -> List[str]:
    """Returns the list of required inputs for a specific function under a platform."""
    functions_map = get_platform_functions(platform_name)
    fn_schema = functions_map.get(function_name)
    if not fn_schema:
        return []
    return fn_schema.get("required_inputs", [])


def validate_tool_step_schema(step: Dict[str, Any], step_idx: int = 1) -> Tuple[bool, List[str]]:
    """Validates a single tool_call step against DETAILED_TOOL_SCHEMAS.

    Checks:
    1. Platform presence and registration (with alias resolution).
    2. Tool ownership boundary (function belongs strictly to that platform).
    3. Required input parameter completeness in comm_inputs.
    4. Auto-normalizes canonical platform in the step dictionary.

    Returns: (is_valid, error_list)
    """
    errors: List[str] = []
    platform_name = step.get("platform")
    function_name = step.get("function_name")
    comm_inputs = step.get("comm_inputs") or {}

    if not platform_name:
        errors.append(f"Layer 1 Error: Step {step_idx} has step_type='tool_call' but 'platform' is missing.")
        return False, errors

    matching_schema = find_platform_schema(platform_name)

    if not matching_schema:
        valid_platforms = get_all_valid_platform_names()
        errors.append(
            f"Layer 1 Platform Error: Step {step_idx} platform '{platform_name}' is not registered. "
            f"Recognized platforms: {valid_platforms}"
        )
        return False, errors

    # Auto-normalize canonical platform in step
    step["platform"] = matching_schema["platform"]
    if "provider" in step:
        del step["provider"]

    # 2. Strict Tool Ownership Boundary Check
    if not function_name:
        errors.append(f"Layer 1 Error: Step {step_idx} has step_type='tool_call' but 'function_name' is missing.")
        return False, errors

    platform_fns = get_platform_functions(matching_schema["platform"])
    if function_name not in platform_fns:
        available_fns = list(platform_fns.keys())
        plat_label = matching_schema.get("platform") or platform_name
        errors.append(
            f"Layer 1 Tool Boundary Error: Step {step_idx} function '{function_name}' does not exist on platform '{plat_label}'. "
            f"Available functions for this platform: {available_fns}"
        )
        return False, errors

    # 3. Required Input Parameter Completeness Check
    req_inputs = platform_fns[function_name].get("required_inputs") or []
    for req_in in req_inputs:
        if req_in not in comm_inputs or comm_inputs.get(req_in) is None:
            errors.append(
                f"Layer 1 Input Error: Step {step_idx} function '{function_name}' missing required input parameter "
                f"'{req_in}' in comm_inputs."
            )

    return len(errors) == 0, errors
