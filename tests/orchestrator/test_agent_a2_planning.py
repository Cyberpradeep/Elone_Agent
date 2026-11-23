"""Unit and Contract Tests for Agent A2 Deterministic Planning Subsystem.

Verifies:
- Edge Case 27: Unapproved step-to-tool binding halts planning with security error.
- Two-Person approval rule enforcement (process owner != security reviewer).
- Tampered binding hash rejection.
- Edge Case 28: Parameter provenance violation rejects plan (zero LLM hallucinations).
- Deterministic canonical RFC 8785 plan hashing.
- Contract validation against contracts.plan.ExecutionPlan.
"""

from datetime import datetime
import pytest

from contracts.canonical import compute_canonical_hash
from contracts.issue import Issue, IssuePriorityEnum, IssueSourceEnum
from contracts.plan import (
    ExecutionPlan,
    ParameterBinding,
    ParameterSourceEnum,
    StepBinding,
)
from contracts.policy import RiskLevelEnum
from contracts.sop import SOPClassificationEnum, SOPReference, SignedSOPPayload, SOPStatusEnum
from agents.a2_planning.bindings import (
    BindingRegistry,
    UnapprovedStepBindingError,
    compute_binding_hash,
)
from agents.a2_planning.provenance import (
    resolve_step_parameters,
    ParameterProvenanceViolationError,
)
from agents.a2_planning.planner import (
    DeterministicPlanner,
)


@pytest.fixture
def sample_issue():
    """Valid sample Issue model with resolved host entities."""
    return Issue(
        issue_id="INC-2041",
        tenant_id="tenant-northwind",
        source=IssueSourceEnum.MANUAL,
        raw_text="The print spooler service is stopped on DESKTOP-O9HENH2.",
        customer_email="pradeepnaveen930@gmail.com",
        priority=IssuePriorityEnum.P3_MEDIUM,
        entities={"hostname": "DESKTOP-O9HENH2", "emp_id": "EL-002"},
    )


@pytest.fixture
def signed_spooler_sop():
    """Valid signed SOP payload for Print Spooler recovery (SOP-WIN-014)."""
    body = {
        "sop_id": "SOP-WIN-014",
        "version": "1.0.0",
        "title": "Print Spooler Recovery",
        "steps": [
            {"step": 1, "title": "Inspect Spooler Status", "tool": "winrm_jea", "op": "get_service"},
            {"step": 2, "title": "Restart Spooler Service", "tool": "winrm_jea", "op": "restart_service"},
        ],
    }
    canonical_hash = compute_canonical_hash(body)
    sop_ref = SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash=canonical_hash,
        title="Print Spooler Recovery",
        classification=SOPClassificationEnum.INTERNAL,
        tenant_id="tenant-northwind",
    )
    return SignedSOPPayload(
        sop=sop_ref,
        body_json=body,
        canonical_sha256=canonical_hash,
        ed25519_signature="0" * 128,
        key_id="hub-key-1",
        status=SOPStatusEnum.PUBLISHED,
        signed_at=datetime.utcnow(),
    )


# --- Step-to-Tool Binding Registry Tests ---

def test_unapproved_step_binding_rejected(sample_issue, signed_spooler_sop):
    """Edge Case 27: Calling planner with an unapproved step binding halts planning."""
    # Empty registry with zero registered bindings
    empty_registry = BindingRegistry(register_defaults=False)
    planner = DeterministicPlanner(registry=empty_registry)

    with pytest.raises(UnapprovedStepBindingError, match="Edge Case 27: Unapproved step binding"):
        planner.build_plan(sample_issue, signed_spooler_sop)


def test_tampered_binding_hash_rejected():
    """Verify that a binding with a mismatched hash is rejected upon registration."""
    params = [
        ParameterBinding(
            param_name="name",
            source=ParameterSourceEnum.SOP_CONSTANT,
            source_key="name",
            static_value="Spooler",
        )
    ]
    tampered_binding = StepBinding(
        sop_id="SOP-WIN-014",
        sop_version="1.0.0",
        step_number=1,
        tool_name="winrm_jea",
        operation="get_service",
        parameter_bindings=params,
        process_owner_approver="lead_ops@northwind.com",
        security_reviewer_approver="sec_reviewer@northwind.com",
        binding_hash="0" * 64,  # Fraudulent hash
    )
    registry = BindingRegistry(register_defaults=False)
    with pytest.raises(UnapprovedStepBindingError, match="Binding hash mismatch"):
        registry.register(tampered_binding)


def test_two_person_approval_rule_enforced():
    """Verify that process owner cannot self-approve as security reviewer."""
    params = []
    same_approver = "operator@northwind.com"
    h = compute_binding_hash(
        "SOP-WIN-014", "1.0.0", 1, "winrm_jea", "get_service", params, same_approver, same_approver
    )
    self_approved_binding = StepBinding(
        sop_id="SOP-WIN-014",
        sop_version="1.0.0",
        step_number=1,
        tool_name="winrm_jea",
        operation="get_service",
        parameter_bindings=params,
        process_owner_approver=same_approver,
        security_reviewer_approver=same_approver,
        binding_hash=h,
    )
    registry = BindingRegistry(register_defaults=False)
    with pytest.raises(UnapprovedStepBindingError, match="Two-person rule violation"):
        registry.register(self_approved_binding)


# --- Parameter Provenance Tests ---

def test_parameter_provenance_violation_rejected(signed_spooler_sop):
    """Edge Case 28: Missing ticket entity causes provenance check to fail closed."""
    # Issue with missing hostname entity
    issue_missing_host = Issue(
        issue_id="INC-2042",
        tenant_id="tenant-northwind",
        source=IssueSourceEnum.MANUAL,
        raw_text="The print spooler is stuck on unknown machine.",
        customer_email="user@northwind.com",
        priority=IssuePriorityEnum.P3_MEDIUM,
        entities={},  # Missing hostname
    )
    planner = DeterministicPlanner()  # Uses pilot bindings requiring hostname

    with pytest.raises(ParameterProvenanceViolationError, match="Provenance violation: Required ticket entity 'hostname'"):
        planner.build_plan(issue_missing_host, signed_spooler_sop)


def test_provenance_resolves_constants_and_cmdb():
    """Verify that SOP_CONSTANT and CMDB_LOOKUP resolve correctly."""
    b_params = [
        ParameterBinding(
            param_name="service_name",
            source=ParameterSourceEnum.SOP_CONSTANT,
            source_key="service_name",
            static_value="MSSQLSERVER",
        ),
        ParameterBinding(
            param_name="db_host",
            source=ParameterSourceEnum.CMDB_LOOKUP,
            source_key="db_server_ip",
        ),
    ]
    h = compute_binding_hash(
        "SOP-DB-021", "1.0.0", 1, "winrm_jea", "restart_service", b_params, "dba_lead@corp.com", "sec_lead@corp.com"
    )
    binding = StepBinding(
        sop_id="SOP-DB-021",
        sop_version="1.0.0",
        step_number=1,
        tool_name="winrm_jea",
        operation="restart_service",
        parameter_bindings=b_params,
        process_owner_approver="dba_lead@corp.com",
        security_reviewer_approver="sec_lead@corp.com",
        binding_hash=h,
    )

    cmdb = {"db_server_ip": "10.0.10.45"}
    resolved = resolve_step_parameters(binding, entities={}, cmdb_context=cmdb)
    assert resolved["service_name"] == "MSSQLSERVER"
    assert resolved["db_host"] == "10.0.10.45"


# --- Deterministic Plan Hashing & Construction Tests ---

def test_deterministic_plan_creation_success(sample_issue, signed_spooler_sop):
    """Verify clean construction of ExecutionPlan with pre-approved bindings."""
    planner = DeterministicPlanner()
    plan = planner.build_plan(sample_issue, signed_spooler_sop)

    assert isinstance(plan, ExecutionPlan)
    assert plan.issue_id == "INC-2041"
    assert plan.sop.sop_id == "SOP-WIN-014"
    assert len(plan.steps) == 2

    # Step 1: Read-only query
    s1 = plan.steps[0]
    assert s1.step_number == 1
    assert s1.tool_name == "winrm_jea"
    assert s1.operation == "get_service"
    assert s1.parameters == {"name": "Spooler", "target_host": "DESKTOP-O9HENH2"}
    assert s1.risk_level == RiskLevelEnum.LEVEL_1_READONLY
    assert s1.requires_approval is False

    # Step 2: High mutation restart
    s2 = plan.steps[1]
    assert s2.step_number == 2
    assert s2.operation == "restart_service"
    assert s2.parameters == {"name": "Spooler", "target_host": "DESKTOP-O9HENH2"}
    assert s2.risk_level == RiskLevelEnum.LEVEL_3_HIGH_MUTATION
    assert s2.requires_approval is True

    # Plan hash must be a valid 64-char hex string
    assert len(plan.plan_hash) == 64


def test_plan_hash_determinism_across_runs(sample_issue, signed_spooler_sop):
    """Verify that multiple planning runs on identical inputs produce identical plan hashes."""
    planner = DeterministicPlanner()
    plan_run1 = planner.build_plan(sample_issue, signed_spooler_sop)
    plan_run2 = planner.build_plan(sample_issue, signed_spooler_sop)

    assert plan_run1.plan_hash == plan_run2.plan_hash


def test_empty_sop_steps_rejected(sample_issue):
    """Verify that SOP with zero steps raises ValueError."""
    empty_body = {"sop_id": "SOP-WIN-014", "version": "1.0.0", "steps": []}
    sop_ref = SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="0" * 64,
        title="Empty SOP",
        tenant_id="tenant-northwind",
    )
    empty_sop = SignedSOPPayload(
        sop=sop_ref,
        body_json=empty_body,
        canonical_sha256="0" * 64,
        ed25519_signature="0" * 128,
        key_id="hub-key-1",
        status=SOPStatusEnum.PUBLISHED,
        signed_at=datetime.utcnow(),
    )
    planner = DeterministicPlanner()
    with pytest.raises(ValueError, match="contains zero execution steps"):
        planner.build_plan(sample_issue, empty_sop)
