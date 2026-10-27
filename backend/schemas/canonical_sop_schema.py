"""
Canonical SOP JSON Schema 1.0 (Section 16)
===========================================
Defines the authoritative Pydantic V2 data model for Canonical SOP documents:
- Preserves full provenance, line-numbered source citations, and verbatim quotes.
- Enforces strict 1..N continuous step numbering without gaps.
- Validates exception linking against valid step indices.
- Captures deterministic confidentiality and quality scoring profiles.
- Validates structural integrity for Publication Gate 2.
"""

from typing import List, Dict, Any, Optional, Literal, Tuple
from pydantic import BaseModel, Field, model_validator, ConfigDict


class MetadataFieldModel(BaseModel):
    """Structured metadata field with source provenance (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    status: Literal["present", "missing", "unknown", "not_applicable"] = "missing"
    value: Optional[str] = None
    source_lines: Optional[List[int]] = None


class SourceCitationModel(BaseModel):
    """Text block bounded by line numbers with verbatim quotes (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    text: str = Field(..., description="Normalized procedure or description text")
    source_lines: List[int] = Field(default_factory=list, description="[start_line, end_line]")
    quote: Optional[str] = Field(None, description="5-25 word verbatim quote from source")
    verified: bool = Field(False, description="Whether verbatim quote was verified within +/- 1 line")


class DocumentSourceModel(BaseModel):
    """Source file ingestion metadata (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    filename: str
    sha256: str
    size: int
    detected_type: str
    pages: int = 1
    extracted_lines: int = 0
    ocr: bool = False


class RoleModel(BaseModel):
    """Role definition involved in SOP execution (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    role: str
    responsibility: str
    source_lines: List[int] = Field(default_factory=list)


class CanonicalStepModel(BaseModel):
    """Single operational step in Canonical SOP JSON (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    n: int = Field(..., description="1-indexed step number, strictly continuous")
    action: str = Field(..., description="Actionable verb phrase")
    input: Optional[str] = Field(None, description="Input parameters or entity identifiers")
    expected_outcome: Optional[str] = Field(None, description="Expected operational result")
    warning: Optional[str] = Field(None, description="Cautionary note or pitfall")
    actor: Literal["agent", "user", "hybrid"] = "agent"
    requires_approval: bool = False
    risk: Literal["low", "medium", "high"] = "low"
    source_lines: List[int] = Field(default_factory=list, description="Source lines [start, end]")
    quote: str = Field(..., description="5-25 word verbatim quote from source")
    verified: bool = False


class ExceptionModel(BaseModel):
    """Exception recovery path bound to a specific step (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    condition: str
    action: str
    escalate_to: Optional[str] = None
    related_step: int = Field(..., description="Target step number this exception attaches to")
    source_lines: List[int] = Field(default_factory=list)
    quote: Optional[str] = None


class ReferenceModel(BaseModel):
    """Hyperlinks, attachments, or cross-SOP references (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    kind: Literal["url", "sop", "image", "attachment"]
    target: str
    label: Optional[str] = None


class MediaModel(BaseModel):
    """Embedded image or video frame summary (Section 13 & 16)."""
    model_config = ConfigDict(extra="ignore")

    label: str
    description: str
    source_line: int


class IssueModel(BaseModel):
    """Quality or security issue detected by an agent (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    id: str
    type: str  # suspicious_instruction, contradiction, missing_step, unsupported_claim, etc.
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    detail: str
    proposed_correction: Optional[str] = None
    source_lines: List[int] = Field(default_factory=list)
    agent: str
    status: Literal["open", "resolved"] = "open"
    resolution: Optional[str] = None
    resolved_by: Optional[str] = None


class ClassificationModel(BaseModel):
    """Confidentiality profile computed by policy engine (Section 11 & 16)."""
    model_config = ConfigDict(extra="ignore")

    level: Literal["L0", "L1", "L2", "L3"] = "L0"
    score: int = 5
    evidence_categories: List[str] = Field(default_factory=list)
    rule_level: str = "L0"
    ai_suggested_level: str = "L0"
    rationale: Optional[str] = None
    confirmed: bool = False
    confirmed_by: Optional[str] = None
    override_reason: Optional[str] = None


class QualityModel(BaseModel):
    """Quality indicators computed by verification engine (Section 12 & 16)."""
    model_config = ConfigDict(extra="ignore")

    completeness: float = 0.0
    traceability: float = 0.0
    schema_valid: bool = False
    blocking_issues_count: int = 0
    quality_score: float = 0.0
    status: Literal["Ready", "Needs attention", "Failed checks", "Quarantined"] = "Needs attention"


class TransformationModel(BaseModel):
    """Cleaned header/footer or whitespace transformation log (Section 7.2 & 16)."""
    model_config = ConfigDict(extra="ignore")

    cleaning_rule_id: str
    type: str
    detail: str
    original_line: Optional[str] = None


class LifecycleApprovalRecord(BaseModel):
    """Audit record of a human approval bound to version and content hash (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    by: str
    at: str
    version: int
    content_sha256: str


class LifecycleModel(BaseModel):
    """Lifecycle tracking metadata (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    state: str = "received"
    uploaded_by: str
    created_at: str
    approvals: List[LifecycleApprovalRecord] = Field(default_factory=list)


class ProvenanceModel(BaseModel):
    """Agent pipeline provenance (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    producing_agent: str = "A2_structuring"
    provider: str = "elverve_ai"
    generated_at: str


# ---------------------------------------------------------------------------
# Canonical SOP Document Model (Schema 1.0)
# ---------------------------------------------------------------------------

class CanonicalSOPModel(BaseModel):
    """Authoritative Canonical SOP JSON Schema 1.0 document model (Section 16)."""
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    sop_id: str
    version: int = 1
    tenant_id: str

    title: str
    title_lines: List[int] = Field(default_factory=list)
    metadata_lines: List[int] = Field(default_factory=list)

    department: MetadataFieldModel = Field(default_factory=MetadataFieldModel)
    owner: MetadataFieldModel = Field(default_factory=MetadataFieldModel)
    version_label: MetadataFieldModel = Field(default_factory=MetadataFieldModel)
    review_date: MetadataFieldModel = Field(default_factory=MetadataFieldModel)

    source: DocumentSourceModel
    purpose: Optional[SourceCitationModel] = None
    scope: Optional[SourceCitationModel] = None

    preconditions: List[SourceCitationModel] = Field(default_factory=list)
    roles: List[RoleModel] = Field(default_factory=list)
    steps: List[CanonicalStepModel] = Field(default_factory=list)
    exceptions: List[ExceptionModel] = Field(default_factory=list)

    notes: List[SourceCitationModel] = Field(default_factory=list)
    references: List[ReferenceModel] = Field(default_factory=list)
    media: List[MediaModel] = Field(default_factory=list)
    issues: List[IssueModel] = Field(default_factory=list)

    classification: ClassificationModel = Field(default_factory=ClassificationModel)
    quality: QualityModel = Field(default_factory=QualityModel)
    transformations: List[TransformationModel] = Field(default_factory=list)
    lifecycle: LifecycleModel
    provenance: ProvenanceModel

    @model_validator(mode="after")
    def validate_step_sequence_and_exceptions(self) -> "CanonicalSOPModel":
        """Enforces continuous 1..N step numbering and validates exception links."""
        # 1. Check steps 1..N without gaps (Section 16)
        if self.steps:
            for idx, step in enumerate(self.steps, start=1):
                if step.n != idx:
                    raise ValueError(
                        f"Step numbering violation: Expected step n={idx}, but found n={step.n}. Steps must be continuous 1..N without gaps."
                    )

        # 2. Check that all exceptions link to an existing step (Section 16)
        valid_step_numbers = {s.n for s in self.steps}
        for exc in self.exceptions:
            if exc.related_step not in valid_step_numbers:
                raise ValueError(
                    f"Exception linkage error: Exception '{exc.condition[:30]}...' references related_step={exc.related_step}, which does not exist in steps list {sorted(valid_step_numbers)}."
                )

        return self


# ---------------------------------------------------------------------------
# Validation Helper for Gate 2
# ---------------------------------------------------------------------------

def validate_canonical_sop_dict(data: Dict[str, Any]) -> Tuple[bool, List[str], Optional[CanonicalSOPModel]]:
    """Validates raw dictionary against Canonical SOP JSON Schema 1.0.
    Returns:
        (is_valid: bool, errors: List[str], model: Optional[CanonicalSOPModel])
    """
    try:
        model = CanonicalSOPModel.model_validate(data)
        return True, [], model
    except Exception as e:
        # Extract clear human-readable error messages
        errors: List[str] = []
        if hasattr(e, "errors"):
            for err in e.errors():
                loc = ".".join(str(p) for p in err.get("loc", []))
                msg = err.get("msg", "Validation error")
                errors.append(f"{loc}: {msg}" if loc else msg)
        else:
            errors.append(str(e))
        return False, errors, None
