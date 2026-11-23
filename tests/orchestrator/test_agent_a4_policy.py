"""Unit and Contract Tests for Agent A4 Declarative Policy & Risk Engine.

Verifies:
- Deterministic operation risk resolution (Level 1 to 4).
- Production environment +1 risk elevation.
- One-Way LLM Advisory rule (LLM can raise risk, never lower deterministic code risk).
- Plan-wide policy evaluation and dual-approver gating for Level 4.
"""

import pytest
from contracts.policy import EnvironmentEnum, RiskLevelEnum
from contracts.plan import ExecutionPlan, ExecutionStep
from contracts.sop import SOPClassificationEnum, SOPReference
from agents.a4_policy.rules import get_operation_base_risk
from agents.a4_policy.engine import PolicyEngine, PlanPolicyEvaluation


@pytest.fixture
def sample_sop_ref():
    """Sample SOPReference fixture."""
    return SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="a" * 64,
        title="Print Spooler Recovery",
        classification=SOPClassificationEnum.INTERNAL,
        tenant_id="tenant-northwind",
    )


def test_base_risk_resolution():
    """Verify deterministic mapping of operations to risk levels."""
    assert get_operation_base_risk("winrm_jea", "get_service") == RiskLevelEnum.LEVEL_1_READONLY
    assert get_operation_base_risk("winrm_jea", "query_service") == RiskLevelEnum.LEVEL_1_READONLY
    assert get_operation_base_risk("monitoring", "agent_health") == RiskLevelEnum.LEVEL_1_READONLY

    assert get_operation_base_risk("winrm_jea", "flush_dns") == RiskLevelEnum.LEVEL_2_LOW_MUTATION
    assert get_operation_base_risk("system", "clear_cache") == RiskLevelEnum.LEVEL_2_LOW_MUTATION

    assert get_operation_base_risk("winrm_jea", "restart_service") == RiskLevelEnum.LEVEL_3_HIGH_MUTATION
    assert get_operation_base_risk("backup_api", "run_backup") == RiskLevelEnum.LEVEL_3_HIGH_MUTATION

    assert get_operation_base_risk("db_tool", "drop_database") == RiskLevelEnum.LEVEL_4_CRITICAL
    assert get_operation_base_risk("net_tool", "modify_firewall") == RiskLevelEnum.LEVEL_4_CRITICAL

    # Unknown operation defaults safely to Level 3
    assert get_operation_base_risk("custom_tool", "unknown_custom_action") == RiskLevelEnum.LEVEL_3_HIGH_MUTATION


def test_prod_environment_elevation_level2_to_level3(sample_sop_ref):
    """Verify that a Level 2 mutation in PROD is elevated to Level 3 (mandating human approval)."""
    step = ExecutionStep(
        step_number=1,
        title="Flush DNS",
        tool_name="winrm_jea",
        operation="flush_dns",
        risk_level=RiskLevelEnum.LEVEL_2_LOW_MUTATION,
    )
    plan = ExecutionPlan.create(issue_id="INC-3001", sop=sample_sop_ref, steps=[step])

    engine = PolicyEngine()

    # In DEV environment -> Remains Level 2, autonomous
    eval_dev = engine.evaluate_plan(plan, environment=EnvironmentEnum.DEV)
    assert eval_dev.overall_risk == RiskLevelEnum.LEVEL_2_LOW_MUTATION
    assert eval_dev.requires_human_approval is False
    assert eval_dev.required_approver_count == 0

    # In PROD environment -> Elevated to Level 3, requires 1 human approver
    eval_prod = engine.evaluate_plan(plan, environment=EnvironmentEnum.PROD)
    assert eval_prod.overall_risk == RiskLevelEnum.LEVEL_3_HIGH_MUTATION
    assert eval_prod.requires_human_approval is True
    assert eval_prod.required_approver_count == 1
    assert eval_prod.evaluated_plan.steps[0].requires_approval is True


def test_prod_environment_elevation_level3_to_level4(sample_sop_ref):
    """Verify that a Level 3 mutation in PROD is elevated to Level 4 (mandating dual approvers)."""
    step = ExecutionStep(
        step_number=1,
        title="Restart Spooler",
        tool_name="winrm_jea",
        operation="restart_service",
        risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
    )
    plan = ExecutionPlan.create(issue_id="INC-3002", sop=sample_sop_ref, steps=[step])

    engine = PolicyEngine()
    eval_prod = engine.evaluate_plan(plan, environment=EnvironmentEnum.PROD)

    assert eval_prod.overall_risk == RiskLevelEnum.LEVEL_4_CRITICAL
    assert eval_prod.requires_human_approval is True
    assert eval_prod.required_approver_count == 2
    assert eval_prod.step_decisions[0].required_approver_count == 2


def test_one_way_llm_advisory_cannot_lower_risk(sample_sop_ref):
    """Rule 3: LLM advisory risk can never lower deterministic code risk."""
    step = ExecutionStep(
        step_number=1,
        title="Restart Spooler Service",
        tool_name="winrm_jea",
        operation="restart_service",
        risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
    )
    plan = ExecutionPlan.create(issue_id="INC-3003", sop=sample_sop_ref, steps=[step])

    engine = PolicyEngine()
    # Malicious or hallucinated LLM advising Level 1 (Read-only) for a service restart
    llm_advisory = {1: RiskLevelEnum.LEVEL_1_READONLY}

    eval_result = engine.evaluate_plan(plan, environment=EnvironmentEnum.DEV, llm_advisories=llm_advisory)

    # Risk must remain Level 3; LLM reduction attempt ignored
    assert eval_result.overall_risk == RiskLevelEnum.LEVEL_3_HIGH_MUTATION
    assert eval_result.step_decisions[0].evaluated_risk == RiskLevelEnum.LEVEL_3_HIGH_MUTATION
    assert eval_result.step_decisions[0].llm_advisory_elevation is False
    assert eval_result.requires_human_approval is True


def test_one_way_llm_advisory_can_raise_risk(sample_sop_ref):
    """Rule 3: LLM advisory risk can elevate risk when suspicious context is detected."""
    step = ExecutionStep(
        step_number=1,
        title="Flush DNS",
        tool_name="winrm_jea",
        operation="flush_dns",
        risk_level=RiskLevelEnum.LEVEL_2_LOW_MUTATION,
    )
    plan = ExecutionPlan.create(issue_id="INC-3004", sop=sample_sop_ref, steps=[step])

    engine = PolicyEngine()
    # LLM detects suspicious environment context and elevates to Level 4
    llm_advisory = {1: RiskLevelEnum.LEVEL_4_CRITICAL}

    eval_result = engine.evaluate_plan(plan, environment=EnvironmentEnum.DEV, llm_advisories=llm_advisory)

    # Risk must be elevated to Level 4
    assert eval_result.overall_risk == RiskLevelEnum.LEVEL_4_CRITICAL
    assert eval_result.step_decisions[0].evaluated_risk == RiskLevelEnum.LEVEL_4_CRITICAL
    assert eval_result.step_decisions[0].llm_advisory_elevation is True
    assert eval_result.requires_human_approval is True
    assert eval_result.required_approver_count == 2


def test_multi_step_plan_policy_evaluation(sample_sop_ref):
    """Verify plan-wide aggregation of highest risk and approver counts."""
    steps = [
        ExecutionStep(
            step_number=1,
            title="Inspect Spooler Status",
            tool_name="winrm_jea",
            operation="get_service",
            risk_level=RiskLevelEnum.LEVEL_1_READONLY,
        ),
        ExecutionStep(
            step_number=2,
            title="Restart Spooler",
            tool_name="winrm_jea",
            operation="restart_service",
            risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
        ),
    ]
    plan = ExecutionPlan.create(issue_id="INC-3005", sop=sample_sop_ref, steps=steps)

    engine = PolicyEngine()
    eval_result = engine.evaluate_plan(plan, environment=EnvironmentEnum.DEV)

    # Highest step is Level 3
    assert eval_result.overall_risk == RiskLevelEnum.LEVEL_3_HIGH_MUTATION
    assert eval_result.requires_human_approval is True
    assert eval_result.required_approver_count == 1
    assert len(eval_result.step_decisions) == 2
    assert eval_result.step_decisions[0].evaluated_risk == RiskLevelEnum.LEVEL_1_READONLY
    assert eval_result.step_decisions[1].evaluated_risk == RiskLevelEnum.LEVEL_3_HIGH_MUTATION
