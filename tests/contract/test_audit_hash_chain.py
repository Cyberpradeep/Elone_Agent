"""Tests for Hash-Chained Audit Event Contracts and Cryptographic Verification."""

from contracts.audit import AuditEvent, AuditEventTypeEnum, GENESIS_HASH


def test_audit_event_chain_creation_and_integrity():
    """Verify that sequential audit events form an immutable cryptographic chain."""
    # Step 1: Genesis event (Issue received)
    evt1 = AuditEvent.create(
        sequence_number=1,
        event_id="EVT-10000001",
        event_type=AuditEventTypeEnum.ISSUE_RECEIVED,
        issue_id="INC-2041",
        tenant_id="tenant-northwind",
        actor="system",
        payload={"raw_ticket": "Print spooler failure"},
        previous_event_hash=GENESIS_HASH,
    )
    assert evt1.previous_event_hash == GENESIS_HASH
    assert evt1.verify_integrity() is True

    # Step 2: Second event (Plan generated)
    evt2 = AuditEvent.create(
        sequence_number=2,
        event_id="EVT-10000002",
        event_type=AuditEventTypeEnum.PLAN_GENERATED,
        issue_id="INC-2041",
        tenant_id="tenant-northwind",
        actor="planner_agent",
        payload={"steps_count": 3, "plan_hash": "a" * 64},
        previous_event_hash=evt1.event_hash,
    )
    assert evt2.previous_event_hash == evt1.event_hash
    assert evt2.verify_integrity() is True

    # Step 3: Third event (Approval requested)
    evt3 = AuditEvent.create(
        sequence_number=3,
        event_id="EVT-10000003",
        event_type=AuditEventTypeEnum.APPROVAL_REQUESTED,
        issue_id="INC-2041",
        tenant_id="tenant-northwind",
        actor="policy_engine",
        payload={"risk_level": 3, "required_approver": "ops_lead"},
        previous_event_hash=evt2.event_hash,
    )
    assert evt3.previous_event_hash == evt2.event_hash
    assert evt3.verify_integrity() is True


def test_audit_event_tamper_detection():
    """Verify that tampering with an event's hash or payload breaks verification."""
    evt = AuditEvent.create(
        sequence_number=1,
        event_id="EVT-20000001",
        event_type=AuditEventTypeEnum.STEP_STARTED,
        issue_id="INC-2042",
        tenant_id="tenant-01",
        actor="orchestrator",
        payload={"step": 1, "tool": "winrm_jea"},
        previous_event_hash=GENESIS_HASH,
    )
    assert evt.verify_integrity() is True

    # Construct a forged event with tampered payload but the original hash
    tampered_evt = AuditEvent(
        sequence_number=evt.sequence_number,
        event_id=evt.event_id,
        event_type=evt.event_type,
        issue_id=evt.issue_id,
        tenant_id=evt.tenant_id,
        actor=evt.actor,
        payload={"step": 1, "tool": "malicious_injected_tool"},  # Tampered
        previous_event_hash=evt.previous_event_hash,
        event_hash=evt.event_hash,  # Original hash no longer matches
        timestamp=evt.timestamp,
    )
    assert tampered_evt.verify_integrity() is False

