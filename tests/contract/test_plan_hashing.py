"""Tests for Deterministic Execution Plan Hashing and Bindings."""

from contracts.policy import RiskLevelEnum
from contracts.sop import SOPClassificationEnum, SOPReference
from contracts.plan import (
    ExecutionPlan,
    ExecutionStep,
    ParameterBinding,
    ParameterSourceEnum,
    StepBinding,
)


def _sample_sop():
    return SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="a" * 64,
        title="Print Spooler Recovery",
        classification=SOPClassificationEnum.INTERNAL,
        tenant_id="tenant-01",
    )


def test_plan_hash_determinism_and_stability():
    """Verify that identical steps produce identical plan_hash digests."""
    sop = _sample_sop()
    steps = [
        ExecutionStep(
            step_number=1,
            title="Inspect Spooler Status",
            tool_name="winrm_jea",
            operation="get_service",
            parameters={"name": "Spooler"},
            risk_level=RiskLevelEnum.LEVEL_1_READONLY,
        ),
        ExecutionStep(
            step_number=2,
            title="Restart Spooler Service",
            tool_name="winrm_jea",
            operation="restart_service",
            parameters={"name": "Spooler"},
            risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
            requires_approval=True,
        ),
    ]

    plan1 = ExecutionPlan.create(issue_id="INC-2041", sop=sop, steps=steps)
    plan2 = ExecutionPlan.create(issue_id="INC-2041", sop=sop, steps=steps)

    assert plan1.plan_hash == plan2.plan_hash
    assert len(plan1.plan_hash) == 64


def test_parameter_tampering_alters_plan_hash():
    """Verify that altering any parameter value changes the cryptographic plan hash."""
    sop = _sample_sop()
    step_orig = ExecutionStep(
        step_number=1,
        title="Query Service",
        tool_name="winrm_jea",
        operation="get_service",
        parameters={"service": "Spooler"},
    )
    step_tampered = ExecutionStep(
        step_number=1,
        title="Query Service",
        tool_name="winrm_jea",
        operation="get_service",
        parameters={"service": "MaliciousService"},
    )

    plan_orig = ExecutionPlan.create(issue_id="INC-2041", sop=sop, steps=[step_orig])
    plan_tampered = ExecutionPlan.create(issue_id="INC-2041", sop=sop, steps=[step_tampered])

    assert plan_orig.plan_hash != plan_tampered.plan_hash


def test_step_binding_contract():
    """Verify clean instantiation of pre-approved step bindings."""
    binding = StepBinding(
        sop_id="SOP-WIN-014",
        sop_version="1.0.0",
        step_number=1,
        tool_name="winrm_jea",
        operation="restart_service",
        parameter_bindings=[
            ParameterBinding(
                param_name="target_host",
                source=ParameterSourceEnum.TICKET_ENTITY,
                source_key="hostname",
            )
        ],
        process_owner_approver="lead_ops@northwind.com",
        security_reviewer_approver="sec_audit@northwind.com",
        binding_hash="f" * 64,
    )
    assert binding.tool_name == "winrm_jea"
    assert binding.parameter_bindings[0].source == ParameterSourceEnum.TICKET_ENTITY

