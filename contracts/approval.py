"""Governance Approvals & Separation of Duties Contract Models.

Enforces strict separation of duties (requester cannot approve), role limits,
dual-approver mandates for Level 4 critical mutations, and 60-minute TTL expiration.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApprovalStatusEnum(str, Enum):
    """Lifecycle statuses for an approval request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class ApprovalRequest(BaseModel):
    """Immutable request for human operator sign-off, cryptographically tied to plan_hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str = Field(..., pattern=r"^REQ-[a-f0-9]{8}$")
    plan_hash: str = Field(..., pattern=r"^[a-f0-9]{64}$", description="Hash of the exact plan being approved")
    step_numbers: List[int] = Field(..., min_length=1)
    risk_level: int = Field(..., ge=1, le=4)
    requester_id: str = Field(..., min_length=3, description="User or agent who requested the run")
    required_clearance: str = Field(default="INTERNAL")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(
        default_factory=lambda: datetime.utcnow() + timedelta(minutes=60),
        description="60-minute TTL expiry",
    )


class ApprovalRecord(BaseModel):
    """Immutable record of an approval decision made by one or more authorized approvers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str = Field(..., pattern=r"^REQ-[a-f0-9]{8}$")
    status: ApprovalStatusEnum
    approver_ids: List[str] = Field(default_factory=list)
    rejection_reason: Optional[str] = None
    decided_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_approver_uniqueness(self) -> "ApprovalRecord":
        """Ensure approvers are distinct individuals (no duplicate sign-offs)."""
        if self.status == ApprovalStatusEnum.APPROVED:
            if not self.approver_ids:
                raise ValueError("Approval record must include at least one approver ID when approved.")
            if len(self.approver_ids) != len(set(self.approver_ids)):
                raise ValueError("Approver IDs must be distinct; one person cannot act as multiple approvers.")
        return self


def validate_approval_governance(
    request: ApprovalRequest,
    record: ApprovalRecord,
    current_time: Optional[datetime] = None,
) -> None:
    """Authoritative validation of separation of duties, expiry, and approval quotas."""
    now = current_time or datetime.utcnow()

    # Rule 1: 60-Minute Expiry Check
    if now > request.expires_at:
        raise ValueError(f"Approval request {request.request_id} expired at {request.expires_at.isoformat()}")

    if record.status != ApprovalStatusEnum.APPROVED:
        return

    # Rule 2: Strict Separation of Duties (Requester cannot approve their own request)
    if request.requester_id in record.approver_ids:
        raise ValueError(
            f"Separation of duties violation: Requester '{request.requester_id}' cannot approve their own plan."
        )

    # Rule 3: Level 4 Critical Mutations require at least two distinct approvers
    if request.risk_level == 4 and len(record.approver_ids) < 2:
        raise ValueError(
            f"Level 4 critical risk requires at least 2 distinct approvers; received {len(record.approver_ids)}."
        )

    # Rule 4: Level 3 High Mutations require at least one approver
    if request.risk_level == 3 and len(record.approver_ids) < 1:
        raise ValueError("Level 3 high risk requires at least 1 approver.")
