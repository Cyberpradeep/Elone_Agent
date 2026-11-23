"""Authenticated Approvals Management Endpoints (Module A10 & PR-15).

Enforces:
- Rule 1: Approver identity and clearance strictly derived from verified JWT.
- Rule 2: Server-side validation (separation of duties, hash check, dual approvers).
- Edge Case 29: Self-approval forbidden (HTTP 403).
- Edge Case 30: 60-minute TTL expiry (HTTP 410).
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.auth import AuthenticatedUser, get_current_user, verify_tenant_access
from api.routes_plans import GLOBAL_PLAN_REGISTRY
from approvals.engine import (
    ApprovalError,
    ApprovalExpiredError,
    ApprovalManager,
    SelfApprovalForbiddenError,
)
from contracts.plan import ExecutionPlan

router = APIRouter(prefix="/plans", tags=["approvals"])
GLOBAL_APPROVAL_MANAGER = ApprovalManager()


class ApprovalSubmissionBody(BaseModel):
    """Schema for operator approval submission."""

    model_config = ConfigDict(extra="forbid")

    plan_hash: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    comments: Optional[str] = None


class RejectionSubmissionBody(BaseModel):
    """Schema for operator rejection submission."""

    model_config = ConfigDict(extra="forbid")

    plan_hash: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(..., min_length=3)


def _get_or_create_request(plan: ExecutionPlan, requester_id: str):
    """Resolve active approval request for plan or create new one."""
    with GLOBAL_APPROVAL_MANAGER._lock:
        for r_id, req in GLOBAL_APPROVAL_MANAGER._requests.items():
            if req.plan_hash == plan.plan_hash:
                return req
    return GLOBAL_APPROVAL_MANAGER.create_request(plan=plan, requester_id=requester_id)


@router.post("/{issue_id}/approve")
async def approve_execution_plan(
    issue_id: str,
    body: ApprovalSubmissionBody,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Approve an execution plan, enforcing separation of duties and dual approvers."""
    entry = GLOBAL_PLAN_REGISTRY.get_entry(issue_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"PLAN_NOT_FOUND: No execution plan found for issue '{issue_id}'",
        )

    verify_tenant_access(current_user, entry["tenant_id"])
    plan: ExecutionPlan = entry["plan"]

    if body.plan_hash != plan.plan_hash:
        raise HTTPException(
            status_code=409,
            detail=f"PLAN_HASH_MISMATCH: Provided plan_hash does not match active plan for '{issue_id}'",
        )

    req = _get_or_create_request(plan, entry["requester_id"])

    if current_user.clearance < req.risk_level:
        raise HTTPException(
            status_code=403,
            detail=f"INSUFFICIENT_CLEARANCE: Risk level {req.risk_level} requires clearance >= {req.risk_level}",
        )

    try:
        record = GLOBAL_APPROVAL_MANAGER.submit_approval(
            request_id=req.request_id,
            approver_id=current_user.user_id,
        )
        return {
            "issue_id": issue_id,
            "plan_hash": plan.plan_hash,
            "approval_record": record.model_dump(mode="json"),
            "is_authorized": record.status.value == "APPROVED",
        }
    except SelfApprovalForbiddenError:
        raise HTTPException(
            status_code=403,
            detail=f"SELF_APPROVAL_FORBIDDEN: Requester '{req.requester_id}' cannot approve their own plan",
        )
    except ApprovalExpiredError:
        raise HTTPException(
            status_code=410,
            detail=f"APPROVAL_EXPIRED: Approval request '{req.request_id}' has expired (60m TTL)",
        )
    except ApprovalError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{issue_id}/reject")
async def reject_execution_plan(
    issue_id: str,
    body: RejectionSubmissionBody,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Reject an execution plan, permanently halting execution."""
    entry = GLOBAL_PLAN_REGISTRY.get_entry(issue_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"PLAN_NOT_FOUND: No execution plan found for issue '{issue_id}'",
        )

    verify_tenant_access(current_user, entry["tenant_id"])
    plan: ExecutionPlan = entry["plan"]

    if body.plan_hash != plan.plan_hash:
        raise HTTPException(
            status_code=409,
            detail="PLAN_HASH_MISMATCH: Provided plan_hash does not match active plan",
        )

    req = _get_or_create_request(plan, entry["requester_id"])
    record = GLOBAL_APPROVAL_MANAGER.reject_request(
        request_id=req.request_id,
        rejecter_id=current_user.user_id,
        reason=body.reason,
    )
    return {
        "issue_id": issue_id,
        "plan_hash": plan.plan_hash,
        "approval_record": record.model_dump(mode="json"),
        "is_authorized": False,
    }


@router.get("/{issue_id}/approvals")
async def get_plan_approvals(
    issue_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Fetch active approval request and decision record for an execution plan."""
    entry = GLOBAL_PLAN_REGISTRY.get_entry(issue_id)
    if not entry:
        raise HTTPException(status_code=404, detail="PLAN_NOT_FOUND")

    verify_tenant_access(current_user, entry["tenant_id"])
    plan: ExecutionPlan = entry["plan"]
    req = _get_or_create_request(plan, entry["requester_id"])
    record = GLOBAL_APPROVAL_MANAGER.get_record(req.request_id)

    return {
        "issue_id": issue_id,
        "plan_hash": plan.plan_hash,
        "request": req.model_dump(mode="json"),
        "record": record.model_dump(mode="json") if record else None,
        "is_authorized": GLOBAL_APPROVAL_MANAGER.is_execution_authorized(plan.plan_hash),
    }
