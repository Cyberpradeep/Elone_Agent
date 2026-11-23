"""Tamper-Evident Hash-Chained Audit Event Contracts.

Every state transition, approval, and execution step writes an immutable
audit event chained to its predecessor with SHA-256 cryptographic verification.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict
from pydantic import BaseModel, ConfigDict, Field
from contracts.canonical import compute_canonical_hash

GENESIS_HASH = "0" * 64


class AuditEventTypeEnum(str, Enum):
    """Authoritative event types for the tamper-evident audit log."""

    ISSUE_RECEIVED = "ISSUE_RECEIVED"
    PLAN_GENERATED = "PLAN_GENERATED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    STEP_STARTED = "STEP_STARTED"
    TOOL_INVOKED = "TOOL_INVOKED"
    STEP_VERIFIED = "STEP_VERIFIED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_STOPPED = "RUN_STOPPED"


class AuditEvent(BaseModel):
    """An immutable, cryptographically chained audit log entry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence_number: int = Field(..., ge=1, description="1-based strictly monotonic counter")
    event_id: str = Field(..., pattern=r"^EVT-[a-f0-9]{8,16}$", description="Unique event identifier")
    event_type: AuditEventTypeEnum
    issue_id: str = Field(..., pattern=r"^INC-\d{4,8}$")
    tenant_id: str = Field(..., min_length=3, max_length=64)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor: str = Field(..., description="Identity of agent or user who triggered this event")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event-specific metadata")
    previous_event_hash: str = Field(..., pattern=r"^[a-f0-9]{64}$", description="Parent event hash")
    event_hash: str = Field(..., pattern=r"^[a-f0-9]{64}$", description="Self hash of canonical fields")

    @classmethod
    def create(
        cls,
        sequence_number: int,
        event_id: str,
        event_type: AuditEventTypeEnum,
        issue_id: str,
        tenant_id: str,
        actor: str,
        payload: Dict[str, Any],
        previous_event_hash: str = GENESIS_HASH,
        timestamp: datetime = None,
    ) -> "AuditEvent":
        """Factory constructor that automatically computes the canonical event hash."""
        ts = timestamp or datetime.utcnow()
        hash_payload = {
            "seq": sequence_number,
            "id": event_id,
            "type": event_type.value,
            "issue": issue_id,
            "tenant": tenant_id,
            "actor": actor,
            "payload": payload,
            "prev": previous_event_hash,
            "ts": ts.isoformat(),
        }
        computed_hash = compute_canonical_hash(hash_payload)
        return cls(
            sequence_number=sequence_number,
            event_id=event_id,
            event_type=event_type,
            issue_id=issue_id,
            tenant_id=tenant_id,
            actor=actor,
            payload=payload,
            previous_event_hash=previous_event_hash,
            event_hash=computed_hash,
            timestamp=ts,
        )

    def verify_integrity(self) -> bool:
        """Recompute canonical hash locally and verify it matches event_hash."""
        hash_payload = {
            "seq": self.sequence_number,
            "id": self.event_id,
            "type": self.event_type.value,
            "issue": self.issue_id,
            "tenant": self.tenant_id,
            "actor": self.actor,
            "payload": self.payload,
            "prev": self.previous_event_hash,
            "ts": self.timestamp.isoformat(),
        }
        return compute_canonical_hash(hash_payload) == self.event_hash

