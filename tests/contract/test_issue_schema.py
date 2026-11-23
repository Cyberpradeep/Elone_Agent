"""Tests for Issue Contract Schema Validation and Immutability."""

import pytest
from pydantic import ValidationError
from contracts.issue import Issue, IssuePriorityEnum, IssueSourceEnum


def test_valid_issue_creation():
    """Verify clean instantiation of a standard incident issue."""
    issue = Issue(
        issue_id="INC-2041",
        tenant_id="tenant-northwind",
        source=IssueSourceEnum.MANUAL,
        raw_text="Print spooler service is halted on host PRN-SRV-01.",
        customer_email="operator@northwind.com",
        priority=IssuePriorityEnum.P2_HIGH,
        entities={"hostname": "PRN-SRV-01", "service": "Spooler"},
    )
    assert issue.issue_id == "INC-2041"
    assert issue.tenant_id == "tenant-northwind"
    assert issue.entities["hostname"] == "PRN-SRV-01"


def test_invalid_issue_id_format():
    """Verify that malformed issue IDs fail validation."""
    with pytest.raises(ValidationError):
        Issue(
            issue_id="TICKET-999",  # Must match ^INC-\d{4,8}$
            tenant_id="tenant-01",
            raw_text="Valid issue body text.",
            customer_email="admin@test.com",
        )


def test_invalid_customer_email():
    """Verify that malformed email addresses fail validation."""
    with pytest.raises(ValidationError):
        Issue(
            issue_id="INC-2042",
            tenant_id="tenant-01",
            raw_text="Valid issue body text.",
            customer_email="not-an-email",
        )


def test_issue_immutability():
    """Verify that frozen=True prevents modifying fields after creation."""
    issue = Issue(
        issue_id="INC-2043",
        tenant_id="tenant-01",
        raw_text="SQL service is unresponsive.",
        customer_email="dba@test.com",
    )
    with pytest.raises(ValidationError):
        issue.tenant_id = "tenant-other"  # Modifying frozen model must raise error


def test_issue_extra_fields_forbidden():
    """Verify that extra='forbid' prevents injecting unexpected fields."""
    with pytest.raises(ValidationError):
        Issue(
            issue_id="INC-2044",
            tenant_id="tenant-01",
            raw_text="Antivirus alert.",
            customer_email="sec@test.com",
            unauthorized_injection_field="payload",
        )

