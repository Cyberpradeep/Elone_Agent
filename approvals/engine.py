"""Approvals Management & Separation of Duties Engine (Module A8).

Enforces:
- Separation of Duties (Edge Case 29: SELF_APPROVAL_FORBIDDEN).
- Dual Approver Requirement for Level 4 Critical Mutations.
- Plan Hash Cryptographic Binding (Approval is tied strictly to plan_hash).
- 60-Minute TTL Expiration (Edge Case 30).
"""

from datetime import datetime, timedelta
import threading
import uuid
from typing import Dict, List, Optional, Tuple

from contracts.approval import (
    ApprovalRecord,
    ApprovalRequest,
    ApprovalStatusEnum,
    validate_approval_governance,
)
from contracts.plan import ExecutionPlan


class ApprovalError(Exception):
    """Base exception for approval subsystem errors."""
    pass


class SelfApprovalForbiddenError(ApprovalError):
    """Raised when a ticket requester attempts to self-approve execution (Edge Case 29)."""
    pass


class ApprovalExpiredError(ApprovalError):
    """Raised when an approval is attempted after the 60-minute TTL has expired (Edge Case 30)."""
    pass


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval request ID is not found."""
    pass


class ApprovalManager:
    """Thread-safe lifecycle manager for enterprise execution approvals."""

    def __init__(self):
        self._requests: Dict[str, ApprovalRequest] = {}
        self._records: Dict[str, ApprovalRecord] = {}
        self._approver_lists: Dict[str, List[str]] = {}
        self._lock = threading.Lock()

    def create_request(
        self,
        plan: ExecutionPlan,
        requester_id: str,
        required_clearance: str = "INTERNAL",
        ttl_minutes: int = 60,
    ) -> ApprovalRequest:
        """Create a new approval request tied to plan_hash and execution steps."""
        with self._lock:
            req_id = f"REQ-{uuid.uuid4().hex[:8]}"
            steps_needing_approval = [s.step_number for s in plan.steps if s.requires_approval]
            if not steps_needing_approval:
                steps_needing_approval = [s.step_number for s in plan.steps]

            max_risk = max((int(s.risk_level.value) if hasattr(s.risk_level, "value") else int(s.risk_level)) for s in plan.steps)

            now = datetime.utcnow()
            request = ApprovalRequest(
                request_id=req_id,
                plan_hash=plan.plan_hash,
                step_numbers=steps_needing_approval,
                risk_level=max_risk,
                requester_id=requester_id,
                required_clearance=required_clearance,
                created_at=now,
                expires_at=now + timedelta(minutes=ttl_minutes),
            )
            self._requests[req_id] = request
            self._approver_lists[req_id] = []
            self._records[req_id] = ApprovalRecord(
                request_id=req_id,
                status=ApprovalStatusEnum.PENDING,
                approver_ids=[],
            )
            return request

    def submit_approval(
        self,
        request_id: str,
        approver_id: str,
        current_time: Optional[datetime] = None,
    ) -> ApprovalRecord:
        """Submit an approval decision by an authorized operator.

        Enforces separation of duties and dual-approver requirements.
        """
        now = current_time or datetime.utcnow()

        with self._lock:
            if request_id not in self._requests:
                raise ApprovalNotFoundError(f"Approval request '{request_id}' not found")

            request = self._requests[request_id]
            record = self._records[request_id]

            # 1. 60-Minute TTL Expiry Check (Edge Case 30)
            if now > request.expires_at or record.status == ApprovalStatusEnum.EXPIRED:
                self._records[request_id] = ApprovalRecord(
                    request_id=request_id,
                    status=ApprovalStatusEnum.EXPIRED,
                    approver_ids=self._approver_lists[request_id],
                    rejection_reason="Approval request TTL expired (60 minutes)",
                    decided_at=now,
                )
                raise ApprovalExpiredError(
                    f"Approval request '{request_id}' expired at {request.expires_at.isoformat()} (Edge Case 30)"
                )

            # 2. Separation of Duties Check (Edge Case 29: SELF_APPROVAL_FORBIDDEN)
            if approver_id == request.requester_id:
                raise SelfApprovalForbiddenError(
                    f"SELF_APPROVAL_FORBIDDEN: Requester '{request.requester_id}' cannot approve their own "
                    f"execution plan for request '{request_id}' (Edge Case 29)"
                )

            # 3. Check for Duplicate Approver
            current_approvers = self._approver_lists[request_id]
            if approver_id in current_approvers:
                raise ApprovalError(f"Approver '{approver_id}' has already approved request '{request_id}'")

            current_approvers.append(approver_id)

            # 4. Determine Approval Quota
            needed_approvers = 2 if request.risk_level == 4 else 1

            if len(current_approvers) >= needed_approvers:
                new_status = ApprovalStatusEnum.APPROVED
                decided_time = now
            else:
                new_status = ApprovalStatusEnum.PENDING
                decided_time = None

            updated_record = ApprovalRecord(
                request_id=request_id,
                status=new_status,
                approver_ids=list(current_approvers),
                decided_at=decided_time,
            )

            # Validate against governance rules
            if new_status == ApprovalStatusEnum.APPROVED:
                validate_approval_governance(request, updated_record, current_time=now)

            self._records[request_id] = updated_record
            return updated_record

    def reject_request(
        self,
        request_id: str,
        rejecter_id: str,
        reason: str,
        current_time: Optional[datetime] = None,
    ) -> ApprovalRecord:
        """Reject an approval request, permanently halting execution."""
        now = current_time or datetime.utcnow()
        with self._lock:
            if request_id not in self._requests:
                raise ApprovalNotFoundError(f"Approval request '{request_id}' not found")

            record = ApprovalRecord(
                request_id=request_id,
                status=ApprovalStatusEnum.REJECTED,
                approver_ids=[rejecter_id],
                rejection_reason=reason,
                decided_at=now,
            )
            self._records[request_id] = record
            return record

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Fetch request by ID."""
        with self._lock:
            return self._requests.get(request_id)

    def get_record(self, request_id: str) -> Optional[ApprovalRecord]:
        """Fetch current decision record by request ID."""
        with self._lock:
            return self._records.get(request_id)

    def is_execution_authorized(self, plan_hash: str) -> bool:
        """Check if an active, approved ApprovalRecord exists for this exact plan_hash."""
        with self._lock:
            for req_id, req in self._requests.items():
                if req.plan_hash == plan_hash:
                    rec = self._records.get(req_id)
                    if rec and rec.status == ApprovalStatusEnum.APPROVED:
                        return True
            return False
