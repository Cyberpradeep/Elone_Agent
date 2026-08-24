"""Centralized Gateway for Knowledge Base & Standalone Ingestion Engine.

Single unified import gateway for:
1. Knowledge Base Catalog & Playbook Loaders
2. Tool Platform Schemas & Discovery (from elone_sop)
3. JIT Converter & Validation Pipeline (from elone_sop)
4. Memory & Learned Pattern Loggers
"""

# ---------------------------------------------------------------------------
# 1. Knowledge Base Playbook & Catalog Loaders
# ---------------------------------------------------------------------------
from okf_engine.loader import (
    load_okf_concept,
    parse_sops_catalog_index,
    get_active_intent_category_map_from_okf,
    load_reflection_rulebook,
    load_device_profile,
    KB_DIR,
    SOPS_DIR,
    PATTERNS_DIR,
    HOSTS_DIR,
    LOGS_DIR,
)

# ---------------------------------------------------------------------------
# 2. Tool Platform Schemas & Discovery (Single Source of Truth)
# ---------------------------------------------------------------------------
from shared.tool_catalog import (
    TOOL_CATALOG,
    PROVIDER_NAMES,
    PROVIDERS,
    get_tool_names,
    get_function_names,
    get_required_inputs,
)

# ---------------------------------------------------------------------------
# 3. Standalone SOP Ingestion & Compilation Pipeline (elone_sop)
# ---------------------------------------------------------------------------
# pyrefly: ignore [missing-import]
from elone_sop import (
    convert_raw_sop_to_okf,
    plan_okf_from_raw,
    write_okf_playbook,
    validate_plan_faithfulness_and_linkage,
    extract_ordered_sop_content,
    extract_full_text,
    find_platform_schema,
    get_all_valid_platform_names,
    DETAILED_TOOL_SCHEMAS,
    PLATFORM_SUMMARIES,
    SOLANDRA_SCHEMA,
    EMAIL_SCHEMA,
    AUTH0_SCHEMA,
    AIRRETAILER_SCHEMA,
    MOCK_SCHEMA,
)

# ---------------------------------------------------------------------------
# 4. Memory & Pattern Loggers
# ---------------------------------------------------------------------------
from okf_engine.memory_logger import (
    append_reflection_rule,
    write_episodic_log,
    update_device_profile,
    ReflectionRule,
)

__all__ = [
    # KB Loaders
    "load_okf_concept",
    "parse_sops_catalog_index",
    "get_active_intent_category_map_from_okf",
    "load_reflection_rulebook",
    "load_device_profile",
    "KB_DIR",
    "SOPS_DIR",
    "PATTERNS_DIR",
    "HOSTS_DIR",
    "LOGS_DIR",
    # Tools & Schemas
    "TOOL_CATALOG",
    "PROVIDER_NAMES",
    "PROVIDERS",
    "get_tool_names",
    "get_function_names",
    "get_required_inputs",
    "find_platform_schema",
    "get_all_valid_platform_names",
    "DETAILED_TOOL_SCHEMAS",
    "PLATFORM_SUMMARIES",
    "SOLANDRA_SCHEMA",
    "EMAIL_SCHEMA",
    "AUTH0_SCHEMA",
    "AIRRETAILER_SCHEMA",
    "MOCK_SCHEMA",
    # Ingestion & Translation
    "convert_raw_sop_to_okf",
    "plan_okf_from_raw",
    "write_okf_playbook",
    "validate_plan_faithfulness_and_linkage",
    "extract_ordered_sop_content",
    "extract_full_text",
    # Memory Loggers
    "append_reflection_rule",
    "write_episodic_log",
    "update_device_profile",
    "ReflectionRule",
]
