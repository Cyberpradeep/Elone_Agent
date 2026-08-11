from shared.providers.system_ops import SystemOpsProvider
from shared.providers.mock import MockProvider
from shared.providers.auth0 import Auth0Provider

# Active providers for system operations, mock testing platform, and Auth0
PROVIDERS = [SystemOpsProvider(), MockProvider(), Auth0Provider()]

# ── Auto-discovered from BaseProvider.provider_name ──
PROVIDER_NAMES = [p.provider_name for p in PROVIDERS]
PROVIDER_TOOL_MAP = {p.provider_name: p.get_tool_metadata() for p in PROVIDERS}

# System catalog containing active communication and system operation tools
TOOL_CATALOG = []
for tools in PROVIDER_TOOL_MAP.values():
    TOOL_CATALOG.extend(tools)


def get_tool_names(catalog: list) -> set:
    return {tool["tool_name"] for tool in catalog}


def get_function_names(catalog: list, tool_name: str) -> set:
    funcs = set()
    for tool in catalog:
        if tool.get("tool_name") == tool_name or tool_name in str(tool):
            for f in tool.get("functions", []):
                funcs.add(f["function_name"])
    if not funcs:
        for tool in catalog:
            for f in tool.get("functions", []):
                funcs.add(f["function_name"])
    return funcs


def get_required_inputs(catalog: list, tool_name: str, function_name: str):
    for tool in catalog:
        if tool.get("tool_name") == tool_name or tool_name in str(tool):
            for f in tool.get("functions", []):
                if f["function_name"] == function_name:
                    return f.get("required_inputs", [])
    # Global function search fallback
    for tool in catalog:
        for f in tool.get("functions", []):
            if f["function_name"] == function_name:
                return f.get("required_inputs", [])
    return None

