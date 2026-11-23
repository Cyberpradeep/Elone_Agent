"""Authoritative Engine Lifecycle & State Transition Graph.

Reflects the exact 1-to-1 mapping with the Execution Engine Console UI state strip.
Every run is guaranteed to be in exactly one known state with no hidden states.
"""

from enum import Enum
from typing import Dict, Set


class EngineStateEnum(str, Enum):
    """The authoritative execution lifecycle states and terminal stop states."""

    # Active Pipeline States
    RECEIVED = "RECEIVED"
    TRIAGED = "TRIAGED"
    PLANNED = "PLANNED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"

    # Terminal Stop & Escalation States
    STOPPED_KILL_SWITCH = "STOPPED_KILL_SWITCH"
    STOPPED_SECURITY_BLOCKED = "STOPPED_SECURITY_BLOCKED"
    STOPPED_REJECTED = "STOPPED_REJECTED"
    STOPPED_BUDGET_EXCEEDED = "STOPPED_BUDGET_EXCEEDED"
    NEEDS_HUMAN = "NEEDS_HUMAN"


# Authoritative state transition graph
VALID_TRANSITIONS: Dict[EngineStateEnum, Set[EngineStateEnum]] = {
    EngineStateEnum.RECEIVED: {
        EngineStateEnum.TRIAGED,
        EngineStateEnum.STOPPED_SECURITY_BLOCKED,
        EngineStateEnum.STOPPED_KILL_SWITCH,
    },
    EngineStateEnum.TRIAGED: {
        EngineStateEnum.PLANNED,
        EngineStateEnum.NEEDS_HUMAN,
        EngineStateEnum.STOPPED_SECURITY_BLOCKED,
        EngineStateEnum.STOPPED_KILL_SWITCH,
    },
    EngineStateEnum.PLANNED: {
        EngineStateEnum.POLICY_EVALUATED,
        EngineStateEnum.NEEDS_HUMAN,
        EngineStateEnum.STOPPED_KILL_SWITCH,
        EngineStateEnum.STOPPED_SECURITY_BLOCKED,
    },
    EngineStateEnum.POLICY_EVALUATED: {
        EngineStateEnum.AWAITING_APPROVAL,
        EngineStateEnum.EXECUTING,
        EngineStateEnum.STOPPED_KILL_SWITCH,
        EngineStateEnum.STOPPED_SECURITY_BLOCKED,
        EngineStateEnum.STOPPED_BUDGET_EXCEEDED,
    },
    EngineStateEnum.AWAITING_APPROVAL: {
        EngineStateEnum.EXECUTING,
        EngineStateEnum.STOPPED_REJECTED,
        EngineStateEnum.STOPPED_KILL_SWITCH,
        EngineStateEnum.STOPPED_SECURITY_BLOCKED,
        EngineStateEnum.STOPPED_BUDGET_EXCEEDED,
    },
    EngineStateEnum.EXECUTING: {
        EngineStateEnum.VERIFYING,
        EngineStateEnum.STOPPED_KILL_SWITCH,
        EngineStateEnum.STOPPED_SECURITY_BLOCKED,
        EngineStateEnum.STOPPED_BUDGET_EXCEEDED,
        EngineStateEnum.NEEDS_HUMAN,
    },
    EngineStateEnum.VERIFYING: {
        EngineStateEnum.EXECUTING,  # Loop to next step
        EngineStateEnum.COMPLETED,  # All steps finished and verified
        EngineStateEnum.NEEDS_HUMAN,  # Verification failed / retries exhausted
        EngineStateEnum.STOPPED_KILL_SWITCH,
        EngineStateEnum.STOPPED_BUDGET_EXCEEDED,
    },
    # Terminal stop states have zero outbound transitions
    EngineStateEnum.COMPLETED: set(),
    EngineStateEnum.STOPPED_KILL_SWITCH: set(),
    EngineStateEnum.STOPPED_SECURITY_BLOCKED: set(),
    EngineStateEnum.STOPPED_REJECTED: set(),
    EngineStateEnum.STOPPED_BUDGET_EXCEEDED: set(),
    EngineStateEnum.NEEDS_HUMAN: set(),
}


def is_valid_transition(current: EngineStateEnum, target: EngineStateEnum) -> bool:
    """Check whether a transition between two engine states is permitted."""
    allowed = VALID_TRANSITIONS.get(current, set())
    return target in allowed


def validate_transition_or_raise(current: EngineStateEnum, target: EngineStateEnum) -> None:
    """Validate a transition and raise a ValueError if illegal."""
    if not is_valid_transition(current, target):
        raise ValueError(
            f"Illegal state transition from {current.value} to {target.value}. "
            f"Permitted targets: {[s.value for s in VALID_TRANSITIONS.get(current, set())]}"
        )

