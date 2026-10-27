"""
Governance Lifecycle Models, State Constants, and Domain Exceptions
===================================================================
Frozen Specification: SOP Governance Hub v1.0 (Sections 8, 9, 10, 13)
"""

import uuid
import datetime
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

# ---------------------------------------------------------------------------
# 1. State Machine Definitions (Section 8)
# ---------------------------------------------------------------------------

STATE_RECEIVED = "received"
STATE_EXTRACTING = "extracting"
STATE_SCANNING = "scanning"
STATE_STRUCTURING = "structuring"
STATE_ASSESSING = "assessing"
STATE_CORRECTING = "correcting"
STATE_AWAITING_REVIEW = "awaiting_review"
STATE_CHANGES_REQUESTED = "changes_requested"
STATE_APPROVED = "approved"
STATE_PUBLISHED = "published"
STATE_DEACTIVATED = "deactivated"
STATE_ARCHIVED = "archived"
STATE_SOFT_DELETED = "soft_deleted"

# Terminal states: Retries must create a new job
STATE_QUARANTINED = "quarantined"
STATE_REJECTED = "rejected"
STATE_DUPLICATE = "duplicate"
STATE_FAILED = "failed"
STATE_BLOCKED = "blocked"

ALL_STATES: Set[str] = {
    STATE_RECEIVED,
    STATE_EXTRACTING,
    STATE_SCANNING,
    STATE_STRUCTURING,
    STATE_ASSESSING,
    STATE_CORRECTING,
    STATE_AWAITING_REVIEW,
    STATE_CHANGES_REQUESTED,
    STATE_APPROVED,
    STATE_PUBLISHED,
    STATE_DEACTIVATED,
    STATE_ARCHIVED,
    STATE_SOFT_DELETED,
    STATE_QUARANTINED,
    STATE_REJECTED,
    STATE_DUPLICATE,
    STATE_FAILED,
    STATE_BLOCKED,
}

TERMINAL_STATES: Set[str] = {
    STATE_QUARANTINED,
    STATE_REJECTED,
    STATE_DUPLICATE,
    STATE_FAILED,
    STATE_BLOCKED,
}

# Deterministic transition table per Section 8 of the frozen specification
ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    STATE_RECEIVED: {STATE_EXTRACTING, STATE_REJECTED, STATE_DUPLICATE, STATE_FAILED, STATE_BLOCKED},
    STATE_EXTRACTING: {STATE_SCANNING, STATE_REJECTED, STATE_FAILED, STATE_BLOCKED},
    STATE_SCANNING: {STATE_STRUCTURING, STATE_QUARANTINED, STATE_FAILED, STATE_BLOCKED},
    STATE_STRUCTURING: {STATE_ASSESSING, STATE_FAILED, STATE_BLOCKED},
    STATE_ASSESSING: {STATE_CORRECTING, STATE_AWAITING_REVIEW, STATE_FAILED, STATE_BLOCKED},
    STATE_CORRECTING: {STATE_ASSESSING, STATE_FAILED, STATE_BLOCKED},
    STATE_AWAITING_REVIEW: {STATE_APPROVED, STATE_CHANGES_REQUESTED, STATE_AWAITING_REVIEW, STATE_STRUCTURING},
    STATE_CHANGES_REQUESTED: {STATE_STRUCTURING, STATE_AWAITING_REVIEW},
    STATE_APPROVED: {STATE_PUBLISHED, STATE_AWAITING_REVIEW},
    STATE_PUBLISHED: {STATE_DEACTIVATED, STATE_ARCHIVED, STATE_SOFT_DELETED},
    STATE_DEACTIVATED: {STATE_PUBLISHED, STATE_ARCHIVED, STATE_SOFT_DELETED},
    STATE_ARCHIVED: {STATE_SOFT_DELETED},
    STATE_SOFT_DELETED: {STATE_DEACTIVATED},
    # Terminal states allow no outward transitions
    STATE_QUARANTINED: set(),
    STATE_REJECTED: set(),
    STATE_DUPLICATE: set(),
    STATE_FAILED: set(),
    STATE_BLOCKED: set(),
}


# ---------------------------------------------------------------------------
# 2. Domain Exceptions (Appendix B Error Codes)
# ---------------------------------------------------------------------------

class GovernanceError(Exception):
    """Base exception for governance pipeline violations."""
    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class IllegalTransitionError(GovernanceError):
    """Raised when an invalid state transition is attempted."""
    def __init__(self, current_state: str, attempted_state: str):
        allowed = sorted(list(ALLOWED_TRANSITIONS.get(current_state, set())))
        msg = f"Illegal transition from '{current_state}' to '{attempted_state}'. Allowed next states: {allowed}"
        super().__init__(msg, error_code="illegal_transition")
        self.current_state = current_state
        self.attempted_state = attempted_state


class SeparationOfDutiesViolation(GovernanceError):
    """Raised when uploader/editor attempts to approve their own document."""
    def __init__(self, message: str):
        super().__init__(message, error_code="separation_of_duties")


class NotHumanActorError(GovernanceError):
    """Raised when an automated agent attempts to make an approval decision."""
    def __init__(self, message: str = "Only human actors may record review decisions."):
        super().__init__(message, error_code="not_human")


class GateFailureError(GovernanceError):
    """Raised when publication gates fail during approval or publishing."""
    def __init__(self, message: str, failure_reasons: List[str]):
        super().__init__(f"{message}: {'; '.join(failure_reasons)}", error_code="gates_failed")
        self.failure_reasons = failure_reasons


class StaleApprovalError(GovernanceError):
    """Raised when content hash or version has changed since approval."""
    def __init__(self, message: str):
        super().__init__(message, error_code="stale_approval")


class NotApprovedError(GovernanceError):
    """Raised when an unapproved SOP is requested to publish."""
    def __init__(self, message: str = "SOP must be in 'approved' state with an active approval decision to publish."):
        super().__init__(message, error_code="not_approved")


# ---------------------------------------------------------------------------
# 3. Data Entities
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def generate_incident_id() -> str:
    """Emits INC-xxxxxx identifier for security quarantine incidents."""
    return f"INC-{uuid.uuid4().hex[:6].upper()}"


def generate_review_task_id() -> str:
    """Emits RT-xxxxxx identifier for human review tasks."""
    return f"RT-{uuid.uuid4().hex[:6].upper()}"


@dataclass
class QuarantineIncident:
    """Incident record emitted when live credentials trigger quarantine (Section 10)."""
    incident_id: str
    sop_id: str
    job_id: str
    content_sha256: str
    secrets_count: int
    secret_types: List[str]
    timestamp: str = field(default_factory=_utc_now_iso)
    purged: bool = True
    description: str = "Live credentials detected during scanning. File content isolated and quarantined."


@dataclass
class ReviewTask:
    """Human review task created by Agent A5 upon entering awaiting_review (Section 5.5)."""
    task_id: str
    sop_id: str
    job_id: str
    version: int
    content_sha256: str
    assigned_role: str  # "Process owner" or "Security reviewer"
    due_date: str
    uploaded_by: str
    status: str = "pending"  # "pending", "approved", "changes_requested", "rejected"
    created_at: str = field(default_factory=_utc_now_iso)
    completed_at: Optional[str] = None
    reviewer: Optional[str] = None
    notes: Optional[str] = None

    def is_overdue(self, as_of: Optional[datetime.datetime] = None) -> bool:
        """Returns True if the task is pending past its due date."""
        if self.status != "pending":
            return False
        ref = as_of or datetime.datetime.now(datetime.timezone.utc)
        try:
            due_dt = datetime.datetime.fromisoformat(self.due_date)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=datetime.timezone.utc)
            return ref > due_dt
        except Exception:
            return False


@dataclass
class ReviewDecision:
    """Immutable record of a human review decision (Section 5.5)."""
    decision: str  # "approve", "changes_requested", "reject"
    reviewer: str
    actor_type: str  # Must be "human"
    sop_id: str
    version: int
    content_sha256: str
    timestamp: str = field(default_factory=_utc_now_iso)
    notes: Optional[str] = None
    route: Optional[str] = None


@dataclass
class PublicationGateResult:
    """Result of deterministic publication checklist evaluation (Section 9.1)."""
    passed: bool
    gates: Dict[str, Dict[str, Any]]
    failure_reasons: List[str]


@dataclass
class JobRecord:
    """Complete lifecycle state of a single document ingestion job."""
    job_id: str
    sop_id: str
    tenant_id: str
    version: int
    content_sha256: str
    uploaded_by: str
    current_state: str = STATE_RECEIVED
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    history: List[Dict[str, Any]] = field(default_factory=list)
    incident: Optional[Dict[str, Any]] = None
    review_task: Optional[Dict[str, Any]] = None
    approval_decision: Optional[Dict[str, Any]] = None
    gate_results: Optional[Dict[str, Any]] = None
    purged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobRecord":
        return cls(**data)
