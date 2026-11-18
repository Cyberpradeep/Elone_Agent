"""Deterministic Plan & Tool Step Validator for OKF Engine."""

import re
import json
from typing import Dict, List, Any, Optional, Tuple

from shared.schemas.platforms import (
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
    """Validates a single tool_call step against DETAILED_TOOL_SCHEMAS."""
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

    if not function_name:
        errors.append(f"Layer 1 Error: Step {step_idx} tool call missing 'function_name'.")
        return False, errors

    platform_funcs = get_platform_functions(platform_name)
    if function_name not in platform_funcs:
        errors.append(
            f"Layer 1 Boundary Error: Step {step_idx} function '{function_name}' is not supported by "
            f"platform '{matching_schema['platform']}'. Supported: {list(platform_funcs.keys())}"
        )
        return False, errors

    # Check required inputs
    required_inputs = platform_funcs[function_name].get("required_inputs", [])
    for req in required_inputs:
        if req not in comm_inputs or comm_inputs[req] is None or str(comm_inputs[req]).strip() == "":
            errors.append(
                f"Layer 1 Error: Step {step_idx} tool '{platform_name}.{function_name}' missing required input parameter '{req}' in comm_inputs."
            )

    return len(errors) == 0, errors


def validate_plan_faithfulness_and_linkage(
    raw_sop_text: str,
    execution_plan: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """Layer 1: Fast Deterministic Syntax, Linkage & Tool Validation for Execution Plans."""
    errors: List[str] = []
    steps = execution_plan.get("steps", [])

    if not steps:
        return False, ["Layer 1 Error: Converted SOP contains zero execution steps."]

    extracted_variables = set()

    for idx, step in enumerate(steps, start=1):
        cmd = step.get("command")
        step_type = step.get("step_type", "command")
        output_var = step.get("output_variable")
        parse_instruction = step.get("output_parse_instruction") or step.get("parse_instruction") or ""
        execute_if = step.get("execute_if")

        # Track variables
        if output_var:
            extracted_variables.add(str(output_var).lower())

        if step_type == "tool_call" or step.get("function_name"):
            extracted_variables.update([
                "status", "account_status", "user_id", "found", "verified",
                "unlock_verified", "temporary_password", "ticket_id", "email",
                "employee_id", "result", "message", "access_token", "ip_address"
            ])

        for match in re.findall(r"(?:set|store)\s+(?:variables\.)?(\w+)", parse_instruction, re.IGNORECASE):
            extracted_variables.add(match.lower())

        # Auto-normalize step_type if function_name is provided
        if step_type != "tool_call" and step.get("function_name"):
            target_plat = step.get("platform") or ""
            matching_schema = find_platform_schema(target_plat) if target_plat else None
            if matching_schema and any(fn.get("function_name") == step.get("function_name") for fn in matching_schema.get("functions", [])):
                step["step_type"] = "tool_call"
                step_type = "tool_call"

        # Check command for command step_type
        if step_type == "command":
            if not cmd:
                errors.append(f"Layer 1 Error: Step {idx} has step_type='command' but command is empty.")
            if not step.get("shell"):
                step["shell"] = "powershell"

        # Check tool_call step_type
        if step_type == "tool_call":
            tool_is_valid, tool_errors = validate_tool_step_schema(step, step_idx=idx)
            if not tool_is_valid:
                errors.extend(tool_errors)

        # Precondition linkage check
        if execute_if:
            req_vars = re.findall(r"(?:\{\{)?variables\.(\w+)(?:\}\})?", str(execute_if), re.IGNORECASE)
            for req_var in req_vars:
                if req_var.lower() not in extracted_variables:
                    errors.append(
                        f"Layer 1 Linkage Error: Step {idx} has execute_if condition referencing 'variables.{req_var}', "
                        f"but '{req_var}' was never extracted or returned by any preceding step!"
                    )

    return len(errors) == 0, errors
