"""Approvals Management Subsystem (Module A8).

Provides:
- ApprovalManager: Tracks requests and enforces separation of duties (Edge Case 29).
- Dual approver enforcement for Level 4 critical mutations.
- ApprovalExpirationReaper: Sweeps requests and expires stale authorizations (Edge Case 30).
"""

from approvals.engine import (
    ApprovalManager,
    ApprovalError,
    SelfApprovalForbiddenError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
)
from approvals.expiration import (
    ApprovalExpirationReaper,
    is_request_expired,
)

__all__ = [
    "ApprovalManager",
    "ApprovalError",
    "SelfApprovalForbiddenError",
    "ApprovalExpiredError",
    "ApprovalNotFoundError",
    "ApprovalExpirationReaper",
    "is_request_expired",
]
