# pyrefly: ignore [missing-import]
from elone_sop import (
    DETAILED_TOOL_SCHEMAS,
    find_platform_schema,
    get_all_valid_platform_names,
)
from shared.providers.system_ops import SystemOpsProvider
from shared.providers.mock import MockProvider
from shared.providers.auth0 import Auth0Provider

# Active providers for system operations, mock testing platform, and Auth0
PROVIDERS = [SystemOpsProvider(), MockProvider(), Auth0Provider()]

# ── Auto-discovered from standalone platform schemas ──
PROVIDER_NAMES = get_all_valid_platform_names()
PROVIDER_TOOL_MAP = DETAILED_TOOL_SCHEMAS

# System catalog containing active communication and system operation tools
TOOL_CATALOG = list(DETAILED_TOOL_SCHEMAS.values())


def get_tool_names(catalog: list) -> set:
    names = set()
    for tool in catalog:
        t_name = tool.get("platform") or tool.get("tool_name")
        if t_name:
            names.add(t_name)
    return names


def get_function_names(catalog: list, tool_name: str) -> set:
    funcs = set()
    for tool in catalog:
        t_name = tool.get("platform") or tool.get("tool_name")
        aliases = tool.get("aliases", [])
        if t_name == tool_name or tool_name in aliases or tool_name in str(tool):
            for f in tool.get("functions", []):
                funcs.add(f["function_name"])
    if not funcs:
        for tool in catalog:
            for f in tool.get("functions", []):
                funcs.add(f["function_name"])
    return funcs


def get_required_inputs(catalog: list, tool_name: str, function_name: str):
    for tool in catalog:
        t_name = tool.get("platform") or tool.get("tool_name")
        aliases = tool.get("aliases", [])
        if t_name == tool_name or tool_name in aliases or tool_name in str(tool):
            for f in tool.get("functions", []):
                if f["function_name"] == function_name:
                    return f.get("required_inputs", [])
    # Global function search fallback
    for tool in catalog:
        for f in tool.get("functions", []):
            if f["function_name"] == function_name:
                return f.get("required_inputs", [])
    return None


