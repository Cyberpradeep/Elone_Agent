"""Authoritative Policy Evaluation & Risk Rules as Code.

Enforces deterministic risk categorization (Level 1-4), mandatory production
environment risk elevation (+1), and the one-way LLM advisory rule.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class RiskLevelEnum(int, Enum):
    """The four risk tiers defining autonomous execution vs. approval gating."""

    LEVEL_1_READONLY = 1  # Read-only diagnostics (ping, tasklist, query)
    LEVEL_2_LOW_MUTATION = 2  # Low-risk mutations (flushdns, harmless cache clear)
    LEVEL_3_HIGH_MUTATION = 3  # High-risk mutations (restart service, kill process)
    LEVEL_4_CRITICAL = 4  # Critical mutations (DB drop, firewall/AD modify)


class EnvironmentEnum(str, Enum):
    """Deployment environment tiers."""

    DEV = "DEV"
    TEST = "TEST"
    STAGING = "STAGING"
    PROD = "PROD"


class PolicyDecision(BaseModel):
    """Immutable evaluation decision for a single execution step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step_number: int = Field(..., ge=1)
    base_risk: RiskLevelEnum
    evaluated_risk: RiskLevelEnum
    is_prod: bool
    requires_approval: bool
    required_approver_count: int = Field(default=0, ge=0, le=2)
    llm_advisory_elevation: bool = False
    policy_reason: str


def evaluate_step_risk(
    step_number: int,
    base_risk: RiskLevelEnum,
    environment: EnvironmentEnum,
    llm_advisory_risk: Optional[RiskLevelEnum] = None,
    base_reason: str = "Standard rule evaluation",
) -> PolicyDecision:
    """Authoritative risk decision function enforcing enterprise safety rules."""
    is_prod = environment == EnvironmentEnum.PROD
    current_risk_val = int(base_risk.value)

    # Rule 1: Production environment automatically adds +1 risk elevation
    if is_prod and current_risk_val < 4:
        current_risk_val += 1
        base_reason += " | Production environment +1 elevation applied"

    llm_elevated = False
    # Rule 2: LLM advisory is one-way only; it may raise risk, never lower it
    if llm_advisory_risk is not None:
        advisory_val = int(llm_advisory_risk.value)
        if advisory_val > current_risk_val:
            current_risk_val = advisory_val
            llm_elevated = True
            base_reason += f" | LLM advisory raised risk to Level {current_risk_val}"

    evaluated_risk = RiskLevelEnum(current_risk_val)

    # Rule 3: Level 1 and 2 run autonomously under policy; Level 3 and 4 require approval
    requires_approval = evaluated_risk >= RiskLevelEnum.LEVEL_3_HIGH_MUTATION

    # Rule 4: Level 4 strictly requires two approvers; Level 3 requires one
    if evaluated_risk == RiskLevelEnum.LEVEL_4_CRITICAL:
        required_approver_count = 2
    elif evaluated_risk == RiskLevelEnum.LEVEL_3_HIGH_MUTATION:
        required_approver_count = 1
    else:
        required_approver_count = 0

    return PolicyDecision(
        step_number=step_number,
        base_risk=base_risk,
        evaluated_risk=evaluated_risk,
        is_prod=is_prod,
        requires_approval=requires_approval,
        required_approver_count=required_approver_count,
        llm_advisory_elevation=llm_elevated,
        policy_reason=base_reason,
    )

