from typing import Dict, List, Any
from langchain_core.tools import tool

# pyrefly: ignore [missing-import]
from tools.platforms import (
    PLATFORM_SUMMARIES,
    DETAILED_TOOL_SCHEMAS,
    find_platform_schema,
    get_all_valid_platform_names,
)


@tool("list_available_platforms")
def list_available_platforms() -> List[Dict[str, str]]:
    """List all registered IT tool platforms and their high-level capability summaries.

    Use this tool when you need an overview of all available platforms (e.g., 'solandra',
    'auth0', 'airretailer', 'email', 'mock') before fetching specific function details.
    """
    return PLATFORM_SUMMARIES


@tool("get_platform_tools")
def get_platform_tools(platform_name: str) -> Dict[str, Any]:
    """Fetch all available API functions, required input parameters, and response schemas
    for a specific platform or provider.

    Args:
        platform_name: Name of the platform or tool provider (e.g., 'solandra', 'coreid',
                       'auth0', 'email', 'airretailer', 'mock').
    """
    schema = find_platform_schema(platform_name)
    if schema:
        return schema

    valid_platforms = get_all_valid_platform_names()
    return {
        "found": False,
        "platform": platform_name,
        "error": f"Platform '{platform_name}' is not available in the tool catalog.",
        "available_platforms": valid_platforms,
        "directive": (
            f"No registered platform tool exists for '{platform_name}'. "
            "Do NOT invent or hallucinate tool calls in 'steps'. "
            f"Record any action requiring '{platform_name}' under 'source_action_coverage' as "
            "'unsupported_required' with step_number=null and a clear reason explaining that "
            f"no platform tool is available for '{platform_name}'."
        ),
    }


DYNAMIC_CATALOG_TOOLS = [get_platform_tools, list_available_platforms]
