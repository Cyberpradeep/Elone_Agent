"""Security Tests for Fix N1: Published SOP & Playbook Immutability."""

import pytest
from hub_security.immutability import (
    ImmutableSOPError,
    check_sop_immutability,
    validate_semver_progression,
)


def test_draft_sop_can_be_updated():
    """Verify that in-progress drafts can be edited prior to publication."""
    draft_existing = {
        "sop_id": "SOP-WIN-014",
        "version": "1.0.0",
        "status": "DRAFT",
        "steps": [{"step": 1, "action": "check_spooler"}],
    }
    draft_new = {
        "sop_id": "SOP-WIN-014",
        "version": "1.0.0",
        "status": "DRAFT",
        "steps": [
            {"step": 1, "action": "check_spooler"},
            {"step": 2, "action": "restart_spooler"},
        ],
    }
    # Editing a draft must not raise error
    check_sop_immutability(draft_existing, draft_new)


def test_published_sop_idempotent_resave_allowed():
    """Verify that submitting identical published content is accepted idempotently."""
    published_existing = {
        "sop_id": "SOP-WIN-014",
        "version": "1.0.0",
        "status": "PUBLISHED",
        "steps": [{"step": 1, "action": "check_spooler"}],
    }
    published_same = {
        "sop_id": "SOP-WIN-014",
        "version": "1.0.0",
        "status": "PUBLISHED",
        "steps": [{"step": 1, "action": "check_spooler"}],
    }
    check_sop_immutability(published_existing, published_same)


def test_modifying_published_sop_raises_immutablesoperror():
    """Verify that attempting to modify steps in an approved SOP raises ImmutableSOPError."""
    published_existing = {
        "sop_id": "SOP-WIN-014",
        "version": "1.0.0",
        "status": "PUBLISHED",
        "steps": [{"step": 1, "action": "check_spooler"}],
    }
    published_modified = {
        "sop_id": "SOP-WIN-014",
        "version": "1.0.0",
        "status": "PUBLISHED",
        "steps": [{"step": 1, "action": "malicious_injected_action"}],
    }
    with pytest.raises(ImmutableSOPError, match="SOP_IMMUTABLE_ERROR"):
        check_sop_immutability(published_existing, published_modified)


def test_semver_progression_validation():
    """Verify that SemVer versions advance strictly forward."""
    assert validate_semver_progression("1.0.0", "1.0.1") is True
    assert validate_semver_progression("1.0.0", "1.1.0") is True
    assert validate_semver_progression("1.0.0", "2.0.0") is True

    # Same version or downgrade fails
    assert validate_semver_progression("1.1.0", "1.1.0") is False
    assert validate_semver_progression("1.2.0", "1.1.0") is False
    assert validate_semver_progression("1.0.0", "invalid_ver") is False
