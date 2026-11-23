"""Tests for Policy Rules Engine and Risk Evaluation Contracts."""

from contracts.policy import (
    EnvironmentEnum,
    RiskLevelEnum,
    evaluate_step_risk,
)


def test_level_1_readonly_in_test_is_autonomous():
    """Verify that Level 1 read-only checks execute autonomously without approvals."""
    decision = evaluate_step_risk(
        step_number=1,
        base_risk=RiskLevelEnum.LEVEL_1_READONLY,
        environment=EnvironmentEnum.TEST,
    )
    assert decision.evaluated_risk == RiskLevelEnum.LEVEL_1_READONLY
    assert decision.requires_approval is False
    assert decision.required_approver_count == 0


def test_production_environment_elevates_risk_by_one():
    """Verify that running in PROD automatically elevates Level 2 to Level 3."""
    decision = evaluate_step_risk(
        step_number=2,
        base_risk=RiskLevelEnum.LEVEL_2_LOW_MUTATION,
        environment=EnvironmentEnum.PROD,
    )
    assert decision.evaluated_risk == RiskLevelEnum.LEVEL_3_HIGH_MUTATION
    assert decision.requires_approval is True
    assert decision.required_approver_count == 1
    assert "Production environment +1 elevation applied" in decision.policy_reason


def test_llm_advisory_cannot_lower_risk():
    """Verify that an LLM advisory attempting to lower risk is strictly ignored."""
    decision = evaluate_step_risk(
        step_number=3,
        base_risk=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
        environment=EnvironmentEnum.TEST,
        llm_advisory_risk=RiskLevelEnum.LEVEL_1_READONLY,  # LLM tries to downplay risk
    )
    # Evaluated risk must remain Level 3
    assert decision.evaluated_risk == RiskLevelEnum.LEVEL_3_HIGH_MUTATION
    assert decision.llm_advisory_elevation is False


def test_llm_advisory_can_elevate_risk():
    """Verify that an LLM advisory detecting subtle production hazard elevates risk."""
    decision = evaluate_step_risk(
        step_number=4,
        base_risk=RiskLevelEnum.LEVEL_2_LOW_MUTATION,
        environment=EnvironmentEnum.TEST,
        llm_advisory_risk=RiskLevelEnum.LEVEL_4_CRITICAL,  # LLM spots critical blast radius
    )
    assert decision.evaluated_risk == RiskLevelEnum.LEVEL_4_CRITICAL
    assert decision.requires_approval is True
    assert decision.required_approver_count == 2
    assert decision.llm_advisory_elevation is True


def test_level_4_critical_requires_dual_approvers():
    """Verify that Level 4 critical mutations mandate 2 distinct approvers."""
    decision = evaluate_step_risk(
        step_number=5,
        base_risk=RiskLevelEnum.LEVEL_4_CRITICAL,
        environment=EnvironmentEnum.PROD,
    )
    assert decision.evaluated_risk == RiskLevelEnum.LEVEL_4_CRITICAL
    assert decision.requires_approval is True
    assert decision.required_approver_count == 2

