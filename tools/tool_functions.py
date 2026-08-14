from typing import Dict, List, Any
from langchain_core.tools import tool

from tools.tool_schemas import PLATFORM_SUMMARIES, DETAILED_TOOL_SCHEMAS


@tool("list_available_platforms")
def list_available_platforms() -> List[Dict[str, str]]:
    """List all registered IT tool platforms and their high-level capability summaries.

    Use this tool when you need an overview of all available platforms (e.g., 'mock',
    'auth0', 'system', 'airretailer') before fetching specific function details.
    """
    return PLATFORM_SUMMARIES


@tool("get_platform_tools")
def get_platform_tools(platform_name: str) -> Dict[str, Any]:
    """Fetch all available API functions, required input parameters, and response schemas
    for a specific platform or provider.

    Args:
        platform_name: Name of the platform or tool provider (e.g., 'mock', 'auth0',
                       'system', 'airretailer', or provider names like 'l1_testing_platform_api').
    """
    clean_name = platform_name.lower().strip()

    # Exact match on platform key
    if clean_name in DETAILED_TOOL_SCHEMAS:
        return DETAILED_TOOL_SCHEMAS[clean_name]

    # Match on provider name or partial name
    for plat_key, schema in DETAILED_TOOL_SCHEMAS.items():
        if clean_name == schema.get("provider", "").lower() or clean_name in plat_key or plat_key in clean_name:
            return schema

    available = list(DETAILED_TOOL_SCHEMAS.keys())
    return {
        "error": f"Platform '{platform_name}' not found.",
        "available_platforms": available,
        "hint": f"Please choose from: {', '.join(available)}"
    }


# @tool("search_tools_by_keyword")
# def search_tools_by_keyword(query: str) -> List[Dict[str, Any]]:
#     """Search for specific API tool functions across all registered platforms using keywords.

#     Args:
#         query: Search keyword (e.g., 'unlock', 'reset password', 'vpn', 'mfa', 'search user').
#     """
#     query_lower = query.lower().strip()
#     matches = []

#     for plat_key, schema in DETAILED_TOOL_SCHEMAS.items():
#         provider = schema.get("provider", plat_key)
#         for fn in schema.get("functions", []):
#             fn_name = fn.get("function_name", "").lower()
#             fn_desc = fn.get("description", "").lower()
#             if query_lower in fn_name or query_lower in fn_desc:
#                 matches.append({
#                     "platform": plat_key,
#                     "provider": provider,
#                     "function_name": fn.get("function_name"),
#                     "description": fn.get("description"),
#                     "required_inputs": fn.get("required_inputs", []),
#                     "response_schema": fn.get("response_schema")
#                 })

#     return matches


# Convenience list of all tool functions to bind to LangChain / Gemini models
DYNAMIC_CATALOG_TOOLS = [
    list_available_platforms,
    get_platform_tools,
    # search_tools_by_keyword,
]
