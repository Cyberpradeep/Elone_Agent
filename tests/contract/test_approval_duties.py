"""Tests for Separation of Duties and Approval Governance Contracts."""

from datetime import datetime, timedelta
import pytest
from contracts.approval import (
    ApprovalRecord,
    ApprovalRequest,
    ApprovalStatusEnum,
    validate_approval_governance,
)


def _sample_request(risk_level: int = 3, requester: str = "operator@northwind.com"):
    return ApprovalRequest(
        request_id="REQ-12345678",
        plan_hash="a" * 64,
        step_numbers=[1],
        risk_level=risk_level,
        requester_id=requester,
    )


def test_valid_approval_workflow():
    """Verify that an independent authorized operator can approve a Level 3 request."""
    req = _sample_request(risk_level=3, requester="operator@northwind.com")
    rec = ApprovalRecord(
        request_id=req.request_id,
        status=ApprovalStatusEnum.APPROVED,
        approver_ids=["lead_ops@northwind.com"],
        decided_at=datetime.utcnow(),
    )
    # Should complete without error
    validate_approval_governance(req, rec)


def test_self_approval_strictly_forbidden():
    """Verify that the ticket requester cannot approve their own plan."""
    req = _sample_request(risk_level=3, requester="operator@northwind.com")
    rec = ApprovalRecord(
        request_id=req.request_id,
        status=ApprovalStatusEnum.APPROVED,
        approver_ids=["operator@northwind.com"],  # Self-approval
        decided_at=datetime.utcnow(),
    )
    with pytest.raises(ValueError, match="Separation of duties violation"):
        validate_approval_governance(req, rec)


def test_level_4_requires_two_distinct_approvers():
    """Verify that Level 4 critical mutations require at least 2 distinct approvers."""
    req = _sample_request(risk_level=4, requester="operator@northwind.com")

    # Only 1 approver provided
    rec_single = ApprovalRecord(
        request_id=req.request_id,
        status=ApprovalStatusEnum.APPROVED,
        approver_ids=["lead_ops@northwind.com"],
        decided_at=datetime.utcnow(),
    )
    with pytest.raises(ValueError, match="Level 4 critical risk requires at least 2 distinct approvers"):
        validate_approval_governance(req, rec_single)

    # 2 duplicate approvers (same identity) rejected by Pydantic validator
    with pytest.raises(ValueError, match="Approver IDs must be distinct"):
        ApprovalRecord(
            request_id=req.request_id,
            status=ApprovalStatusEnum.APPROVED,
            approver_ids=["lead_ops@northwind.com", "lead_ops@northwind.com"],
            decided_at=datetime.utcnow(),
        )

    # 2 distinct approvers succeeds
    rec_dual = ApprovalRecord(
        request_id=req.request_id,
        status=ApprovalStatusEnum.APPROVED,
        approver_ids=["lead_ops@northwind.com", "sec_director@northwind.com"],
        decided_at=datetime.utcnow(),
    )
    validate_approval_governance(req, rec_dual)


def test_expired_approval_request_rejected():
    """Verify that an approval attempt after the 60-minute TTL expires raises ValueError."""
    req = _sample_request(risk_level=3, requester="operator@northwind.com")
    rec = ApprovalRecord(
        request_id=req.request_id,
        status=ApprovalStatusEnum.APPROVED,
        approver_ids=["lead_ops@northwind.com"],
        decided_at=datetime.utcnow(),
    )
    # Simulate time 65 minutes later
    simulated_future_time = req.created_at + timedelta(minutes=65)
    with pytest.raises(ValueError, match="expired"):
        validate_approval_governance(req, rec, current_time=simulated_future_time)

