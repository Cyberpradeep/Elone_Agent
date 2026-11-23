"""Tests for Cryptographic SOP Reference and Signed Payload Contracts."""

import pytest
from pydantic import ValidationError
from contracts.sop import (
    SOPClassificationEnum,
    SOPReference,
    SOPStatusEnum,
    SignedSOPPayload,
)


def test_valid_sop_reference():
    """Verify clean instantiation of an approved SOP reference."""
    sop = SOPReference(
        sop_id="SOP-WIN-014",
        version="1.2.0",
        canonical_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        title="Print Spooler Service Recovery Procedure",
        classification=SOPClassificationEnum.INTERNAL,
        tenant_id="tenant-northwind",
    )
    assert sop.sop_id == "SOP-WIN-014"
    assert sop.version == "1.2.0"
    assert sop.classification == SOPClassificationEnum.INTERNAL


def test_invalid_sop_id_pattern():
    """Verify that non-canonical SOP ID patterns fail validation."""
    with pytest.raises(ValidationError):
        SOPReference(
            sop_id="INVALID_SOP_ID",  # Must match ^SOP-[A-Z]{3,4}-\d{3}$
            version="1.0.0",
            canonical_hash="a" * 64,
            title="Invalid SOP",
            tenant_id="tenant-01",
        )


def test_signed_sop_payload():
    """Verify instantiation and signature fields of SignedSOPPayload."""
    sop_ref = SOPReference(
        sop_id="SOP-NET-006",
        version="2.0.1",
        canonical_hash="b" * 64,
        title="DNS Resolution Issue Remediation",
        classification=SOPClassificationEnum.CONFIDENTIAL,
        tenant_id="tenant-northwind",
    )
    payload = SignedSOPPayload(
        sop=sop_ref,
        body_json={"steps": [{"step": 1, "action": "flush_dns"}]},
        canonical_sha256="b" * 64,
        ed25519_signature="c" * 64,
        key_id="hub-key-2026-v1",
        status=SOPStatusEnum.PUBLISHED,
    )
    assert payload.status == SOPStatusEnum.PUBLISHED
    assert payload.key_id == "hub-key-2026-v1"

