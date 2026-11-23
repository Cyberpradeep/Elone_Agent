"""Tests for Authoritative State Transitions and Validation Graph."""

import pytest
from contracts.state import (
    EngineStateEnum,
    VALID_TRANSITIONS,
    is_valid_transition,
    validate_transition_or_raise,
)


def test_valid_forward_pipeline_transitions():
    """Verify standard happy-path lifecycle transitions."""
    assert is_valid_transition(EngineStateEnum.RECEIVED, EngineStateEnum.TRIAGED)
    assert is_valid_transition(EngineStateEnum.TRIAGED, EngineStateEnum.PLANNED)
    assert is_valid_transition(EngineStateEnum.PLANNED, EngineStateEnum.POLICY_EVALUATED)
    assert is_valid_transition(EngineStateEnum.POLICY_EVALUATED, EngineStateEnum.AWAITING_APPROVAL)
    assert is_valid_transition(EngineStateEnum.AWAITING_APPROVAL, EngineStateEnum.EXECUTING)
    assert is_valid_transition(EngineStateEnum.EXECUTING, EngineStateEnum.VERIFYING)
    assert is_valid_transition(EngineStateEnum.VERIFYING, EngineStateEnum.COMPLETED)


def test_autonomous_policy_transition():
    """Verify that Level 1-2 policy allows transitioning directly to EXECUTING."""
    assert is_valid_transition(EngineStateEnum.POLICY_EVALUATED, EngineStateEnum.EXECUTING)


def test_illegal_transitions_rejected():
    """Verify that bypassing phases or transitioning from completed states raises ValueError."""
    # Bypassing planning directly to execution
    assert not is_valid_transition(EngineStateEnum.RECEIVED, EngineStateEnum.EXECUTING)
    with pytest.raises(ValueError, match="Illegal state transition"):
        validate_transition_or_raise(EngineStateEnum.RECEIVED, EngineStateEnum.EXECUTING)

    # Outbound transitions from COMPLETED
    assert not is_valid_transition(EngineStateEnum.COMPLETED, EngineStateEnum.RECEIVED)
    with pytest.raises(ValueError, match="Illegal state transition"):
        validate_transition_or_raise(EngineStateEnum.COMPLETED, EngineStateEnum.EXECUTING)


def test_kill_switch_accessible_from_active_states():
    """Verify that the emergency Kill Switch can interrupt any active pre-mutation state."""
    active_states = [
        EngineStateEnum.RECEIVED,
        EngineStateEnum.TRIAGED,
        EngineStateEnum.PLANNED,
        EngineStateEnum.POLICY_EVALUATED,
        EngineStateEnum.AWAITING_APPROVAL,
        EngineStateEnum.EXECUTING,
        EngineStateEnum.VERIFYING,
    ]
    for state in active_states:
        assert is_valid_transition(state, EngineStateEnum.STOPPED_KILL_SWITCH)


def test_security_blocked_accessible_from_active_states():
    """Verify that Security Guard can block any active intake, planning, or execution state."""
    guard_states = [
        EngineStateEnum.RECEIVED,
        EngineStateEnum.TRIAGED,
        EngineStateEnum.PLANNED,
        EngineStateEnum.POLICY_EVALUATED,
        EngineStateEnum.AWAITING_APPROVAL,
        EngineStateEnum.EXECUTING,
    ]
    for state in guard_states:
        assert is_valid_transition(state, EngineStateEnum.STOPPED_SECURITY_BLOCKED)

