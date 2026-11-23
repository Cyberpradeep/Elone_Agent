"""Deterministic Execution Plan & Step-to-Tool Binding Contracts.

Ensures that execution plans are strictly composed of pre-approved bindings
with deterministic parameter resolution and canonical SHA-256 plan hashing.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from contracts.canonical import compute_canonical_hash
from contracts.policy import RiskLevelEnum
from contracts.sop import SOPReference


class ParameterSourceEnum(str, Enum):
    """Allowed origins for command parameters (preventing prompt hallucination)."""

    TICKET_ENTITY = "TICKET_ENTITY"  # Extracted entity from ticket (e.g. hostname)
    CMDB_LOOKUP = "CMDB_LOOKUP"  # Resolved from CMDB asset inventory
    SOP_CONSTANT = "SOP_CONSTANT"  # Hardcoded approved constant in SOP definition
    PREVIOUS_STEP_OUTPUT = "PREVIOUS_STEP_OUTPUT"  # Captured output from prior step


class ParameterBinding(BaseModel):
    """Mapping of a tool input parameter to an authoritative data source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    param_name: str = Field(..., min_length=1)
    source: ParameterSourceEnum
    source_key: str = Field(..., min_length=1)
    static_value: Optional[str] = None
    is_secret: bool = False


class StepBinding(BaseModel):
    """Pre-approved mapping between an SOP step and an executable tool invocation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sop_id: str = Field(..., pattern=r"^SOP-[A-Z]{2,4}-\d{3}$")
    sop_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    step_number: int = Field(..., ge=1)
    tool_name: str = Field(..., min_length=2)
    operation: str = Field(..., min_length=2)
    parameter_bindings: List[ParameterBinding] = Field(default_factory=list)
    process_owner_approver: str = Field(..., min_length=3)
    security_reviewer_approver: str = Field(..., min_length=3)
    binding_hash: str = Field(..., pattern=r"^[a-f0-9]{64}$")


class ExecutionStep(BaseModel):
    """An individual actionable step within an execution plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step_number: int = Field(..., ge=1)
    title: str = Field(..., min_length=3)
    tool_name: str = Field(..., min_length=2)
    operation: str = Field(..., min_length=2)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevelEnum = RiskLevelEnum.LEVEL_1_READONLY
    rollback_step: Optional[Dict[str, Any]] = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    requires_approval: bool = False


class ExecutionPlan(BaseModel):
    """Immutable, canonically hashed execution plan bound to an exact SOP version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: str = Field(..., pattern=r"^INC-\d{4,8}$")
    sop: SOPReference
    steps: List[ExecutionStep] = Field(..., min_length=1)
    plan_hash: str = Field(
        ...,
        pattern=r"^[a-f0-9]{64}$",
        description="Canonical SHA-256 hash of all steps. Approvals bind to this hash.",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def create(
        cls,
        issue_id: str,
        sop: SOPReference,
        steps: List[ExecutionStep],
        created_at: Optional[datetime] = None,
    ) -> "ExecutionPlan":
        """Factory constructor that automatically computes the canonical plan hash."""
        steps_data = [s.model_dump(mode="json") for s in steps]
        h = compute_canonical_hash(steps_data)
        return cls(
            issue_id=issue_id,
            sop=sop,
            steps=steps,
            plan_hash=h,
            created_at=created_at or datetime.utcnow(),
        )

