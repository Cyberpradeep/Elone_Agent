"""Declarative Risk Rules as Code (Module A7).

Categorizes infrastructure operations into four strict risk tiers:
- Level 1: Read-only diagnostic operations (zero mutation).
- Level 2: Low-risk, reversible mutations.
- Level 3: High-risk mutations (service restarts, process terminations, job triggers).
- Level 4: Critical mutations (database drops, firewall alterations, directory modifications).
"""

import re
from typing import Dict, List, Optional
from pydantic import BaseModel
from contracts.policy import RiskLevelEnum


class OperationRiskRule(BaseModel):
    """Declarative risk rule mapping tool and operation patterns to a baseline risk level."""
    tool_pattern: str
    operation_pattern: str
    base_risk: RiskLevelEnum
    description: str


# Hardcoded declarative rule table
STATIC_OPERATION_RULES: List[OperationRiskRule] = [
    # Level 1 Read-only
    OperationRiskRule(tool_pattern=".*", operation_pattern="^(get|query|read|check|inspect|list|ping|nslookup|status|health).*", base_risk=RiskLevelEnum.LEVEL_1_READONLY, description="Read-only diagnostic inspection"),
    OperationRiskRule(tool_pattern="monitoring", operation_pattern=".*", base_risk=RiskLevelEnum.LEVEL_1_READONLY, description="Monitoring adapter read-only metrics"),

    # Level 2 Low Mutation
    OperationRiskRule(tool_pattern=".*", operation_pattern="^(flush_dns|clear_cache|rotate_log|touch|temp).*", base_risk=RiskLevelEnum.LEVEL_2_LOW_MUTATION, description="Low-risk, benign local state modification"),

    # Level 4 Critical Mutation (Must be checked before Level 3 to catch critical keywords)
    OperationRiskRule(tool_pattern=".*", operation_pattern=".*(drop_database|purge_volume|format_disk|modify_firewall|modify_ad|delete_user|rotate_root).*", base_risk=RiskLevelEnum.LEVEL_4_CRITICAL, description="Critical infrastructure alteration requiring dual approval"),

    # Level 3 High Mutation
    OperationRiskRule(tool_pattern=".*", operation_pattern="^(restart|stop|start|kill|terminate|backup|restore|modify|install|unlock).*", base_risk=RiskLevelEnum.LEVEL_3_HIGH_MUTATION, description="High-risk system modification requiring human approval"),
]


def get_operation_base_risk(tool_name: str, operation: str) -> RiskLevelEnum:
    """Deterministically resolve baseline risk for a tool and operation.

    Checks rules in order:
    1. Critical mutations (Level 4).
    2. Read-only operations (Level 1).
    3. Low-risk mutations (Level 2).
    4. High-risk mutations (Level 3).
    Defaults to Level 3 (High Mutation) if unrecognized, failing safe.
    """
    clean_tool = (tool_name or "").lower().strip()
    clean_op = (operation or "").lower().strip()

    # 1. Critical pattern check first
    for rule in STATIC_OPERATION_RULES:
        if rule.base_risk == RiskLevelEnum.LEVEL_4_CRITICAL:
            if re.match(rule.tool_pattern, clean_tool) and re.match(rule.operation_pattern, clean_op):
                return RiskLevelEnum.LEVEL_4_CRITICAL

    # 2. Read-only check
    for rule in STATIC_OPERATION_RULES:
        if rule.base_risk == RiskLevelEnum.LEVEL_1_READONLY:
            if re.match(rule.tool_pattern, clean_tool) and re.match(rule.operation_pattern, clean_op):
                return RiskLevelEnum.LEVEL_1_READONLY

    # 3. Low-risk mutation check
    for rule in STATIC_OPERATION_RULES:
        if rule.base_risk == RiskLevelEnum.LEVEL_2_LOW_MUTATION:
            if re.match(rule.tool_pattern, clean_tool) and re.match(rule.operation_pattern, clean_op):
                return RiskLevelEnum.LEVEL_2_LOW_MUTATION

    # 4. High-risk mutation check
    for rule in STATIC_OPERATION_RULES:
        if rule.base_risk == RiskLevelEnum.LEVEL_3_HIGH_MUTATION:
            if re.match(rule.tool_pattern, clean_tool) and re.match(rule.operation_pattern, clean_op):
                return RiskLevelEnum.LEVEL_3_HIGH_MUTATION

    # Safe default for any unknown operation: Level 3 High Mutation
    return RiskLevelEnum.LEVEL_3_HIGH_MUTATION
