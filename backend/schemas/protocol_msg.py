"""
Agent Communication Protocol msg/1.0 Schemas & Models
=====================================================
Frozen Specification: SOP Governance Hub v1.0 (Sections 6 & 7)
"""

import uuid
import json
import hashlib
import datetime
from typing import Dict, List, Set, Optional, Tuple, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

# ---------------------------------------------------------------------------
# 1. Routing Matrix & Permissions Configuration (Sections 5 & 7)
# ---------------------------------------------------------------------------

AGENT_ROLES: Set[str] = {"orchestrator", "A1", "A2", "A3", "A4", "A5", "A6"}

# The 12 explicitly permitted routing edges (Section 7)
ALLOWED_ROUTES: Set[Tuple[str, str]] = {
    ("orchestrator", "A1"),  # New upload; linked file attached
    ("orchestrator", "A3"),  # Secret gate after extraction
    ("A1", "A2"),            # Extraction -> cleaning
    ("A2", "A4"),            # Cleaning -> verification
    ("A2", "A3"),            # Cleaning -> security assessment
    ("A3", "A4"),            # Security findings -> verification (when relevant)
    ("A4", "A2"),            # Correction request (max 1 per revision)
    ("orchestrator", "A5"),  # Human intervention, review task
    ("A5", "A2"),            # Approved change request -> re-structure
    ("A5", "A6"),            # Only after an approval is recorded
    ("orchestrator", "A4"),  # Deterministic re-verification after human edit
    ("orchestrator", "A6"),  # Lifecycle request by an authorized user
}

# Artifact Read & Write Permissions per Agent (Section 5)
ARTIFACT_PERMISSIONS: Dict[str, Dict[str, Set[str]]] = {
    "A1": {
        "reads": {"upload", "linked_file"},
        "writes": {"extracted"},
    },
    "A2": {
        "reads": {"extracted", "quality_report", "review_decision"},
        "writes": {"cleaned", "canonical_draft"},
    },
    "A3": {
        "reads": {"extracted", "cleaned", "security_findings"},
        "writes": {"security_findings", "confidentiality_assessment"},
    },
    "A4": {
        "reads": {"cleaned", "canonical_draft", "security_findings"},
        "writes": {"quality_report"},
    },
    "A5": {
        "reads": {"canonical_draft", "quality_report", "confidentiality_assessment"},
        "writes": {"review_task", "review_decision"},
    },
    "A6": {
        "reads": {"review_decision", "canonical_draft"},
        "writes": {"publication_record"},
    },
    "orchestrator": {
        "reads": {
            "upload", "linked_file", "extracted", "cleaned", "canonical_draft",
            "security_findings", "confidentiality_assessment", "quality_report",
            "review_task", "review_decision", "publication_record"
        },
        "writes": {
            "upload", "linked_file", "extracted", "cleaned", "canonical_draft",
            "security_findings", "confidentiality_assessment", "quality_report",
            "review_task", "review_decision", "publication_record"
        },
    },
}


# ---------------------------------------------------------------------------
# 2. Domain Exceptions (Appendix B Error Codes)
# ---------------------------------------------------------------------------

class AgentProtocolError(Exception):
    """Base exception for msg/1.0 protocol violations."""
    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class RouteNotAllowedError(AgentProtocolError):
    """Raised when an unapproved routing path is attempted (Section 7)."""
    def __init__(self, sender: str, recipient: str):
        msg = f"Route not allowed: '{sender}' -> '{recipient}' is not permitted by the routing matrix."
        super().__init__(msg, error_code="route_not_allowed")
        self.sender = sender
        self.recipient = recipient


class MalformedMessageError(AgentProtocolError):
    """Raised when task or result message fails structural schema validation (Section 6.3)."""
    def __init__(self, message: str, error_code: str = "malformed_output"):
        super().__init__(message, error_code=error_code)


class TenantMismatchError(AgentProtocolError):
    """Raised when message or artifact tenant violates tenant isolation."""
    def __init__(self, expected: str, found: str):
        super().__init__(f"Tenant mismatch: expected '{expected}', found '{found}'.", error_code="tenant_mismatch")


class ArtifactAccessDeniedError(AgentProtocolError):
    """Raised when an agent attempts to read or write an unauthorized artifact type."""
    def __init__(self, agent: str, operation: str, artifact_type: str):
        msg = f"Artifact access denied: Agent '{agent}' may not {operation} artifact of type '{artifact_type}'."
        super().__init__(msg, error_code="artifact_access_denied")


# ---------------------------------------------------------------------------
# 3. Artifact Data Model
# ---------------------------------------------------------------------------

class Artifact(BaseModel):
    """Tenant-isolated, citable data artifact passed by reference (Section 6 & Appendix A)."""
    model_config = ConfigDict(extra="ignore")

    artifact_id: str
    tenant_id: str
    artifact_type: str
    created_by: str
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    content_sha256: str
    data: Any  # Dict or text payload

    @classmethod
    def create(cls, tenant_id: str, artifact_type: str, created_by: str, data: Any) -> "Artifact":
        raw = json.dumps(data, sort_keys=True) if isinstance(data, (dict, list)) else str(data)
        sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        artifact_id = f"art-{uuid.uuid4().hex[:8]}"
        return cls(
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            artifact_type=artifact_type,
            created_by=created_by,
            content_sha256=sha256,
            data=data,
        )


# ---------------------------------------------------------------------------
# 4. Task Message Model (Section 6.1)
# ---------------------------------------------------------------------------

class TaskMessage(BaseModel):
    """Structured task dispatch message under msg/1.0 specification (Section 6.1)."""
    model_config = ConfigDict(extra="ignore")

    task_id: str = Field(default_factory=lambda: f"tsk-{uuid.uuid4().hex[:8]}")
    correlation_id: str = Field(..., description="Job-wide trace ID")
    tenant_id: str
    sop_id: str
    source_version_id: str  # e.g. "SOP-1042@v1"
    source_content_hash: str
    sender: str
    recipient: str
    task_type: str  # extract, secret_gate, clean_and_structure, assess, verify, etc.
    schema_version: Literal["msg/1.0"] = "msg/1.0"
    input_artifact_references: List[str] = Field(default_factory=list)
    requested_operation: Dict[str, Any] = Field(default_factory=dict)
    policy_context_reference: str = "policy/v1.0"
    timeout_ms: int = 180000
    idempotency_key: str  # job:task:version:revision:loop

    @model_validator(mode="after")
    def validate_task_contract(self) -> "TaskMessage":
        # 1. Route validation
        route = (self.sender, self.recipient)
        if route not in ALLOWED_ROUTES:
            raise RouteNotAllowedError(self.sender, self.recipient)
        return self


# ---------------------------------------------------------------------------
# 5. Result Message Model (Section 6.2)
# ---------------------------------------------------------------------------

class ResultMessage(BaseModel):
    """Structured agent response message under msg/1.0 specification (Section 6.2)."""
    model_config = ConfigDict(extra="ignore")

    task_id: str
    correlation_id: str
    agent_id: str
    status: Literal["success", "partial_success", "needs_review", "blocked", "failed", "retryable_failure"]
    output_artifact_reference: Optional[str] = None
    structured_findings: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = None
    source_evidence_references: List[str] = Field(default_factory=list)
    unresolved_issues: List[Dict[str, Any]] = Field(default_factory=list)
    retryable: bool = False
    error_code: Optional[str] = None
    processing_metrics: Dict[str, Any] = Field(default_factory=dict)
