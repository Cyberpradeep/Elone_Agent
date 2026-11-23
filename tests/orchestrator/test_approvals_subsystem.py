"""Unit and Contract Tests for Approvals Management Subsystem (Module A8).

Verifies:
- Edge Case 29: Separation of duties blocks self-approval (SELF_APPROVAL_FORBIDDEN).
- Dual approver mandate for Level 4 Critical Mutations.
- Level 3 single approver completion.
- Edge Case 30: 60-minute approval TTL expiry.
- Automatic expiration reaper sweeps.
- Rejection lifecycle and authorization queries.
"""

from datetime import datetime, timedelta
import pytest

from contracts.approval import ApprovalStatusEnum
from contracts.policy import RiskLevelEnum
from contracts.plan import ExecutionPlan, ExecutionStep
from contracts.sop import SOPClassificationEnum, SOPReference
from approvals.engine import (
    ApprovalManager,
    ApprovalError,
    SelfApprovalForbiddenError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
)
from approvals.expiration import ApprovalExpirationReaper, is_request_expired


@pytest.fixture
def sop_ref():
    return SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="a" * 64,
        title="Print Spooler Recovery",
        classification=SOPClassificationEnum.INTERNAL,
        tenant_id="tenant-northwind",
    )


@pytest.fixture
def level3_plan(sop_ref):
    """Plan containing Level 3 High Mutation step."""
    step = ExecutionStep(
        step_number=1,
        title="Restart Spooler",
        tool_name="winrm_jea",
        operation="restart_service",
        risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
        requires_approval=True,
    )
    return ExecutionPlan.create(issue_id="INC-4001", sop=sop_ref, steps=[step])


@pytest.fixture
def level4_plan(sop_ref):
    """Plan containing Level 4 Critical Mutation step."""
    step = ExecutionStep(
        step_number=1,
        title="Drop Database",
        tool_name="db_tool",
        operation="drop_database",
        risk_level=RiskLevelEnum.LEVEL_4_CRITICAL,
        requires_approval=True,
    )
    return ExecutionPlan.create(issue_id="INC-4002", sop=sop_ref, steps=[step])


# --- Separation of Duties (Edge Case 29) ---

def test_self_approval_forbidden(level3_plan):
    """Edge Case 29: Requester attempting to approve their own request raises SELF_APPROVAL_FORBIDDEN."""
    manager = ApprovalManager()
    requester = "requester_bob@northwind.com"

    req = manager.create_request(level3_plan, requester_id=requester)
    assert req.requester_id == requester

    # Requester Bob attempts to approve his own execution request
    with pytest.raises(SelfApprovalForbiddenError, match="SELF_APPROVAL_FORBIDDEN"):
        manager.submit_approval(req.request_id, approver_id=requester)

    # Execution remains unauthorized
    assert manager.is_execution_authorized(level3_plan.plan_hash) is False


# --- Approval Quotas: Level 3 (1 Approver) & Level 4 (2 Approvers) ---

def test_level3_single_approval_success(level3_plan):
    """Verify single distinct approver authorizes Level 3 mutation."""
    manager = ApprovalManager()
    req = manager.create_request(level3_plan, requester_id="requester_bob@northwind.com")

    # Independent operator signs off
    record = manager.submit_approval(req.request_id, approver_id="operator_alice@northwind.com")

    assert record.status == ApprovalStatusEnum.APPROVED
    assert record.approver_ids == ["operator_alice@northwind.com"]
    assert record.decided_at is not None
    assert manager.is_execution_authorized(level3_plan.plan_hash) is True


def test_level4_critical_mutation_dual_approval(level4_plan):
    """Verify Level 4 requires two distinct approvers."""
    manager = ApprovalManager()
    req = manager.create_request(level4_plan, requester_id="requester_bob@northwind.com")
    assert req.risk_level == 4

    # 1. First approver signs off -> Must remain PENDING (awaiting second approver)
    record1 = manager.submit_approval(req.request_id, approver_id="lead_ops@northwind.com")
    assert record1.status == ApprovalStatusEnum.PENDING
    assert record1.approver_ids == ["lead_ops@northwind.com"]
    assert manager.is_execution_authorized(level4_plan.plan_hash) is False

    # 2. Second distinct approver signs off -> Transitions to APPROVED
    record2 = manager.submit_approval(req.request_id, approver_id="sec_admin@northwind.com")
    assert record2.status == ApprovalStatusEnum.APPROVED
    assert record2.approver_ids == ["lead_ops@northwind.com", "sec_admin@northwind.com"]
    assert manager.is_execution_authorized(level4_plan.plan_hash) is True


def test_level4_same_approver_twice_rejected(level4_plan):
    """Verify that one person cannot satisfy both approval slots on Level 4."""
    manager = ApprovalManager()
    req = manager.create_request(level4_plan, requester_id="requester_bob@northwind.com")

    # First approval succeeds
    manager.submit_approval(req.request_id, approver_id="lead_ops@northwind.com")

    # Same person attempts second approval
    with pytest.raises(ApprovalError, match="has already approved"):
        manager.submit_approval(req.request_id, approver_id="lead_ops@northwind.com")


# --- 60-Minute TTL Expiry (Edge Case 30) ---

def test_approval_ttl_expiry_rejected(level3_plan):
    """Edge Case 30: Approval submitted after 60-minute TTL raises ApprovalExpiredError."""
    manager = ApprovalManager()
    now = datetime.utcnow()
    req = manager.create_request(level3_plan, requester_id="requester_bob@northwind.com", ttl_minutes=60)

    # Time travels 65 minutes into the future
    future_time = now + timedelta(minutes=65)
    assert is_request_expired(req, current_time=future_time) is True

    # Attempt approval on expired request
    with pytest.raises(ApprovalExpiredError, match="expired at"):
        manager.submit_approval(req.request_id, approver_id="operator_alice@northwind.com", current_time=future_time)

    rec = manager.get_record(req.request_id)
    assert rec.status == ApprovalStatusEnum.EXPIRED
    assert manager.is_execution_authorized(level3_plan.plan_hash) is False


def test_approval_reaper_sweeps_expired_requests(level3_plan):
    """Verify that expiration reaper automatically transitions expired requests to EXPIRED."""
    manager = ApprovalManager()
    now = datetime.utcnow()

    # Request 1: expires in 60 minutes
    req1 = manager.create_request(level3_plan, requester_id="bob@northwind.com", ttl_minutes=60)
    # Request 2: expired 10 minutes ago
    req2 = manager.create_request(level3_plan, requester_id="alice@northwind.com", ttl_minutes=10)

    reaper = ApprovalExpirationReaper(manager)
    # Advance time by 30 minutes: req2 is expired, req1 is still valid
    sweep_time = now + timedelta(minutes=30)
    reaped = reaper.reap_expired(current_time=sweep_time)

    assert req2.request_id in reaped
    assert req1.request_id not in reaped

    assert manager.get_record(req2.request_id).status == ApprovalStatusEnum.EXPIRED
    assert manager.get_record(req1.request_id).status == ApprovalStatusEnum.PENDING


# --- Rejection Lifecycle ---

def test_operator_rejection(level3_plan):
    """Verify operator rejection transitions request to REJECTED and halts execution."""
    manager = ApprovalManager()
    req = manager.create_request(level3_plan, requester_id="requester_bob@northwind.com")

    rec = manager.reject_request(
        req.request_id,
        rejecter_id="duty_manager@northwind.com",
        reason="Maintenance window expired",
    )
    assert rec.status == ApprovalStatusEnum.REJECTED
    assert rec.rejection_reason == "Maintenance window expired"
    assert manager.is_execution_authorized(level3_plan.plan_hash) is False
