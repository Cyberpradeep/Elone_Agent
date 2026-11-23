"""Cryptographic Governance Hub SOP Reference and Payload Contracts.

Enforces cryptographic integrity, SemVer versioning, tenant isolation,
and security classification for all SOPs fetched from the Governance Hub.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict
from pydantic import BaseModel, ConfigDict, Field


class SOPClassificationEnum(str, Enum):
    """Security classification levels for SOPs."""

    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class SOPStatusEnum(str, Enum):
    """Authoritative lifecycle status of an SOP in the Governance Hub."""

    PUBLISHED = "PUBLISHED"
    DEACTIVATED = "DEACTIVATED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class SOPReference(BaseModel):
    """Immutable reference to an approved, versioned SOP."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sop_id: str = Field(
        ...,
        pattern=r"^SOP-[A-Z]{3,4}-\d{3}$",
        description="Canonical SOP identifier, e.g. SOP-WIN-014, SOP-NET-006",
    )
    version: str = Field(
        ...,
        pattern=r"^\d+\.\d+\.\d+$",
        description="SemVer release string, e.g. 1.0.0",
    )
    canonical_hash: str = Field(
        ...,
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 hash of the canonical SOP JSON body",
    )
    title: str = Field(..., min_length=3, max_length=200)
    classification: SOPClassificationEnum = SOPClassificationEnum.INTERNAL
    tenant_id: str = Field(..., min_length=3, max_length=64)


class SignedSOPPayload(BaseModel):
    """Full signed payload returned by Governance Hub /api/v1/exec/sops endpoints."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sop: SOPReference
    body_json: Dict[str, Any] = Field(..., description="Canonical SOP step definitions and metadata")
    canonical_sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    ed25519_signature: str = Field(
        ...,
        min_length=64,
        max_length=128,
        description="Hex or Base64 encoded Ed25519 signature from Hub private key",
    )
    key_id: str = Field(..., min_length=3, max_length=64, description="Hub public key ID")
    status: SOPStatusEnum = SOPStatusEnum.PUBLISHED
    signed_at: datetime = Field(default_factory=datetime.utcnow)

