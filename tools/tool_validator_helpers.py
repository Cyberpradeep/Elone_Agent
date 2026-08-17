from typing import Dict, List, Any, Optional, Tuple
from tools.tool_schemas import DETAILED_TOOL_SCHEMAS


def find_platform_schema(platform_or_provider: str) -> Optional[Dict[str, Any]]:
    """Finds the detailed platform schema from DETAILED_TOOL_SCHEMAS.
    Supports case-insensitive platform keys (e.g. 'auth0', 'mock', 'email')
    and provider names (e.g. 'auth0_user_management', 'email_service').
    """
    if not platform_or_provider:
        return None

    key = str(platform_or_provider).lower().strip()

    # 1. Exact platform key match
    if key in DETAILED_TOOL_SCHEMAS:
        return DETAILED_TOOL_SCHEMAS[key]

    # 2. Match by provider field in schema
    for plat_key, schema in DETAILED_TOOL_SCHEMAS.items():
        prov = schema.get("provider", "").lower()
        if key == prov or key in prov or prov in key:
            return schema

    return None


def get_platform_functions(platform_or_provider: str) -> Dict[str, Dict[str, Any]]:
    """Returns a map of {function_name: function_dict} strictly for a given platform or provider."""
    schema = find_platform_schema(platform_or_provider)
    if not schema:
        return {}
    return {fn["function_name"]: fn for fn in schema.get("functions", []) if "function_name" in fn}


def get_platform_required_inputs(platform_or_provider: str, function_name: str) -> List[str]:
    """Returns the list of required inputs for a specific function under a platform."""
    functions_map = get_platform_functions(platform_or_provider)
    fn_schema = functions_map.get(function_name)
    if not fn_schema:
        return []
    return fn_schema.get("required_inputs", [])


def get_all_valid_platform_names() -> List[str]:
    """Returns all recognized platform and provider names."""
    names = set(DETAILED_TOOL_SCHEMAS.keys())
    for schema in DETAILED_TOOL_SCHEMAS.values():
        if "provider" in schema:
            names.add(schema["provider"])
        if "platform" in schema:
            names.add(schema["platform"])
    return sorted(list(names))


def validate_tool_step_schema(step: Dict[str, Any], step_idx: int = 1) -> Tuple[bool, List[str]]:
    """Validates a single tool_call step against DETAILED_TOOL_SCHEMAS.

    Checks:
    1. Platform presence and registration.
    2. Tool ownership boundary (function belongs strictly to that platform).
    3. Required input parameter completeness in comm_inputs.
    4. Auto-normalizes missing platform/provider in the step.

    Returns: (is_valid, error_list)
    """
    errors: List[str] = []
    platform_name = step.get("platform")
    provider_name = step.get("provider")
    function_name = step.get("function_name")
    comm_inputs = step.get("comm_inputs") or {}

    target_lookup = platform_name or provider_name
    matching_schema = find_platform_schema(target_lookup) if target_lookup else None

    if not target_lookup:
        errors.append(f"Layer 1 Error: Step {step_idx} has step_type='tool_call' but 'platform'/'provider' is missing.")
        return False, errors

    if not matching_schema:
        valid_platforms = get_all_valid_platform_names()
        errors.append(
            f"Layer 1 Platform Error: Step {step_idx} platform/provider '{target_lookup}' is not registered. "
            f"Recognized platforms: {valid_platforms}"
        )
        return False, errors

    # Auto-populate platform and provider if omitted
    if not step.get("platform") and "platform" in matching_schema:
        step["platform"] = matching_schema["platform"]
    if not step.get("provider") and "provider" in matching_schema:
        step["provider"] = matching_schema["provider"]

    # 2. Strict Tool Ownership Boundary Check
    if not function_name:
        errors.append(f"Layer 1 Error: Step {step_idx} has step_type='tool_call' but 'function_name' is missing.")
        return False, errors

    platform_fns = get_platform_functions(target_lookup)
    if function_name not in platform_fns:
        available_fns = list(platform_fns.keys())
        plat_label = matching_schema.get("platform") or target_lookup
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
