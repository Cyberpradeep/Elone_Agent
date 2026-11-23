"""SOP Execution Engine Shared Contracts Package.

The single source of truth for state models, issue definitions,
governance references, deterministic plans, policy evaluation,
approvals, and cryptographic audit hashing.
"""

from contracts.canonical import compute_canonical_hash, to_canonical_json
from contracts.state import (
    EngineStateEnum,
    VALID_TRANSITIONS,
    is_valid_transition,
    validate_transition_or_raise,
)
from contracts.issue import (
    Issue,
    IssuePriorityEnum,
    IssueSourceEnum,
)
from contracts.audit import (
    AuditEvent,
    AuditEventTypeEnum,
    GENESIS_HASH,
)
from contracts.sop import (
    SOPClassificationEnum,
    SOPReference,
    SOPStatusEnum,
    SignedSOPPayload,
)
from contracts.policy import (
    EnvironmentEnum,
    PolicyDecision,
    RiskLevelEnum,
    evaluate_step_risk,
)
from contracts.plan import (
    ExecutionPlan,
    ExecutionStep,
    ParameterBinding,
    ParameterSourceEnum,
    StepBinding,
)
from contracts.approval import (
    ApprovalRecord,
    ApprovalRequest,
    ApprovalStatusEnum,
    validate_approval_governance,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # Canonical
    "to_canonical_json",
    "compute_canonical_hash",
    # State
    "EngineStateEnum",
    "VALID_TRANSITIONS",
    "is_valid_transition",
    "validate_transition_or_raise",
    # Issue
    "Issue",
    "IssuePriorityEnum",
    "IssueSourceEnum",
    # Audit
    "AuditEvent",
    "AuditEventTypeEnum",
    "GENESIS_HASH",
    # SOP
    "SOPClassificationEnum",
    "SOPReference",
    "SOPStatusEnum",
    "SignedSOPPayload",
    # Policy
    "EnvironmentEnum",
    "PolicyDecision",
    "RiskLevelEnum",
    "evaluate_step_risk",
    # Plan
    "ExecutionPlan",
    "ExecutionStep",
    "ParameterBinding",
    "ParameterSourceEnum",
    "StepBinding",
    # Approval
    "ApprovalRecord",
    "ApprovalRequest",
    "ApprovalStatusEnum",
    "validate_approval_governance",
]
