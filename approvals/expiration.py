"""60-Minute Approval TTL Expiration Reaper (Edge Case 30).

Scans active approval requests and transitions overdue requests to EXPIRED,
preventing stale or unattended authorizations from executing.
"""

from datetime import datetime
from typing import List, Optional
from contracts.approval import ApprovalRecord, ApprovalRequest, ApprovalStatusEnum
from approvals.engine import ApprovalManager


def is_request_expired(request: ApprovalRequest, current_time: Optional[datetime] = None) -> bool:
    """Return True if the approval request has exceeded its 60-minute TTL."""
    now = current_time or datetime.utcnow()
    return now > request.expires_at


class ApprovalExpirationReaper:
    """Service that sweeps active approval requests and expires stale authorizations."""

    def __init__(self, manager: ApprovalManager):
        self.manager = manager

    def reap_expired(self, current_time: Optional[datetime] = None) -> List[str]:
        """Sweep all requests; mark expired requests as EXPIRED and return their IDs."""
        now = current_time or datetime.utcnow()
        expired_ids: List[str] = []

        with self.manager._lock:
            for req_id, request in self.manager._requests.items():
                record = self.manager._records.get(req_id)
                if record and record.status == ApprovalStatusEnum.PENDING:
                    if is_request_expired(request, current_time=now):
                        self.manager._records[req_id] = ApprovalRecord(
                            request_id=req_id,
                            status=ApprovalStatusEnum.EXPIRED,
                            approver_ids=list(self.manager._approver_lists.get(req_id, [])),
                            rejection_reason="Approval request TTL expired (60 minutes)",
                            decided_at=now,
                        )
                        expired_ids.append(req_id)

        return expired_ids
