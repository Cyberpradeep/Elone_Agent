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

    available = list(DETAILED_TOOL_SCHEMAS.keys())
    return {
        "error": f"Platform '{platform_name}' not found.",
        "available_platforms": available,
        "hint": f"Please choose from: {', '.join(available)}"
    }


DYNAMIC_CATALOG_TOOLS = [get_platform_tools, list_available_platforms]

