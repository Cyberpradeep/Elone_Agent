from typing import Dict, List, Any
from langchain_core.tools import tool

# pyrefly: ignore [missing-import]
from tools.platforms import (
    PLATFORM_SUMMARIES,
    DETAILED_TOOL_SCHEMAS,
    find_platform_schema,
    get_all_valid_platform_names,
)


def _list_available_platforms_impl() -> List[Dict[str, str]]:
    return PLATFORM_SUMMARIES


def _get_platform_tools_impl(platform_name: str = "", **kwargs: Any) -> Dict[str, Any]:
    target = platform_name or kwargs.get("platform") or kwargs.get("name") or ""
    schema = find_platform_schema(target)
    if schema:
        return schema

    valid_platforms = get_all_valid_platform_names()
    return {
        "found": False,
        "platform": target,
        "error": f"Platform '{target}' is not available in the tool catalog.",
        "available_platforms": valid_platforms,
        "directive": (
            f"No registered platform tool exists for '{target}'. "
            "Do NOT invent or hallucinate tool calls in 'steps'. "
            f"Record any action requiring '{target}' under 'source_action_coverage' as "
            "'unsupported_required' with step_number=null and a clear reason explaining that "
            f"no platform tool is available for '{target}'."
        ),
    }


@tool("list_available_platforms")
def list_available_platforms() -> List[Dict[str, str]]:
    """List all registered IT tool platforms and their high-level capability summaries.

    Use this tool when you need an overview of all available platforms (e.g., 'solandra',
    'auth0', 'airretailer', 'email', 'mock') before fetching specific function details.
    """
    return _list_available_platforms_impl()


@tool("get_platform_tools")
def get_platform_tools(platform_name: str = "") -> Dict[str, Any]:
    """Fetch all available API functions, required input parameters, and response schemas
    for a specific platform or provider.

    Args:
        platform_name: Name of the platform or tool provider (e.g., 'solandra', 'coreid',
                       'auth0', 'email', 'airretailer', 'mock').
    """
    return _get_platform_tools_impl(platform_name=platform_name)


@tool("list_useful_platforms")
def list_useful_platforms() -> List[Dict[str, str]]:
    """Alias for list_available_platforms."""
    return _list_available_platforms_impl()


@tool("call_platform")
def call_platform(platform_name: str = "") -> Dict[str, Any]:
    """Inspect and fetch available API functions for a platform.

    Args:
        platform_name: Name of the platform (e.g., 'solandra', 'coreid', 'auth0').
    """
    return _get_platform_tools_impl(platform_name=platform_name)


@tool("platform_name")
def platform_name(platform_name: str = "") -> Dict[str, Any]:
    """Inspect and fetch available API functions for a platform.

    Args:
        platform_name: Name of the platform (e.g., 'solandra', 'coreid', 'auth0').
    """
    return _get_platform_tools_impl(platform_name=platform_name)


DYNAMIC_CATALOG_TOOLS = [
    get_platform_tools,
    list_available_platforms,
    list_useful_platforms,
    call_platform,
    platform_name,
]
