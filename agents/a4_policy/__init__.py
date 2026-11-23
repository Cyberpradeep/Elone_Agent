"""Agent A4: Declarative Policy & Risk Engine (Module A7).

Provides:
- Declarative operation-to-risk rules mapping.
- Automatic PROD environment +1 risk elevation.
- One-Way LLM Advisory rule enforcement (can only raise risk).
- Plan-wide policy evaluation and approval requirements aggregation.
"""

from agents.a4_policy.rules import (
    OperationRiskRule,
    STATIC_OPERATION_RULES,
    get_operation_base_risk,
)
from agents.a4_policy.engine import (
    PolicyEngine,
    PlanPolicyEvaluation,
)

__all__ = [
    "OperationRiskRule",
    "STATIC_OPERATION_RULES",
    "get_operation_base_risk",
    "PolicyEngine",
    "PlanPolicyEvaluation",
]
