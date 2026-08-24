from typing import Dict, List, Any, Optional
import re

# pyrefly: ignore [missing-import]
from tools.platforms.solandra import SOLANDRA_SCHEMA
# pyrefly: ignore [missing-import]
from tools.platforms.auth0 import AUTH0_SCHEMA
# pyrefly: ignore [missing-import]
from tools.platforms.email import EMAIL_SCHEMA
# pyrefly: ignore [missing-import]
from tools.platforms.airretailer import AIRRETAILER_SCHEMA
# pyrefly: ignore [missing-import]
from tools.platforms.mock import MOCK_SCHEMA

# ---------------------------------------------------------------------------
# Master Detailed Platform Tool Schemas
# ---------------------------------------------------------------------------
DETAILED_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "solandra": SOLANDRA_SCHEMA,
    "auth0": AUTH0_SCHEMA,
    "email": EMAIL_SCHEMA,
    "airretailer": AIRRETAILER_SCHEMA,
    "mock": MOCK_SCHEMA,
}

# ---------------------------------------------------------------------------
# Dynamically Derived Lightweight Summaries for LLM Prompts
# ---------------------------------------------------------------------------
PLATFORM_SUMMARIES: List[Dict[str, str]] = [
    {
        "platform": schema["platform"],
        "description": schema["description"]
    }
    for schema in DETAILED_TOOL_SCHEMAS.values()
]


def _normalize_name(name: str) -> str:
    """Normalizes string for fuzzy alias matching."""
    if not name:
        return ""
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", str(name).lower())
    return " ".join(clean.split())


def find_platform_schema(platform_name: str) -> Optional[Dict[str, Any]]:
    """Universal alias-aware platform schema resolver.

    Matches by:
    1. Exact canonical dictionary key (e.g. 'solandra', 'auth0', 'email')
    2. Exact platform name in schema
    3. Declared aliases list (e.g. 'coreid', 'coreid admin console', 'solandra group')
    4. Normalized / fuzzy name matching
    """
    if not platform_name:
        return None

    raw_key = str(platform_name).lower().strip()
    norm_key = _normalize_name(raw_key)

    # 1. Exact key match
    if raw_key in DETAILED_TOOL_SCHEMAS:
        return DETAILED_TOOL_SCHEMAS[raw_key]

    # 2. Check each schema's platform and declared aliases
    for plat_key, schema in DETAILED_TOOL_SCHEMAS.items():
        schema_plat = schema.get("platform", "").lower().strip()
        if raw_key == schema_plat or norm_key == _normalize_name(schema_plat):
            return schema

        aliases = schema.get("aliases", [])
        for alias in aliases:
            clean_alias = str(alias).lower().strip()
            if raw_key == clean_alias or norm_key == _normalize_name(clean_alias):
                return schema

    # 3. Substring / partial match on canonical keys
    for plat_key, schema in DETAILED_TOOL_SCHEMAS.items():
        if plat_key in raw_key or raw_key in plat_key:
            return schema

    return None


def get_all_valid_platform_names() -> List[str]:
    """Returns all recognized canonical platform names and aliases."""
    names = set(DETAILED_TOOL_SCHEMAS.keys())
    for schema in DETAILED_TOOL_SCHEMAS.values():
        if "platform" in schema:
            names.add(schema["platform"])
        for alias in schema.get("aliases", []):
            names.add(alias)
    return sorted(list(names))
