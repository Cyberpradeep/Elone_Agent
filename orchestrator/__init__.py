"""Orchestrator package for SOP Execution Engine (Module A4)."""

from orchestrator.checkpointer import (
    SqliteCheckpointer,
    PostgresCheckpointer,
    get_checkpointer,
)
from orchestrator.state_graph import (
    ExecutionModeEnum,
    EngineState,
    create_orchestrator_graph,
)
from orchestrator.stubs import (
    MockExecutorWorker,
    MockVerifierWorker,
)
from orchestrator.kill_switch import (
    KillSwitch,
    GLOBAL_KILL_SWITCH,
)
from orchestrator.pre_step_guard import (
    PreStepGuardResult,
    verify_pre_step_guard,
)
from orchestrator.lifecycle import (
    reset_issue,
    cancel_execution,
    package_human_handover,
)
from orchestrator.budgets import (
    RunBudget,
    BudgetTracker,
    execute_with_timeout,
)

__all__ = [
    "SqliteCheckpointer",
    "PostgresCheckpointer",
    "get_checkpointer",
    "ExecutionModeEnum",
    "EngineState",
    "create_orchestrator_graph",
    "MockExecutorWorker",
    "MockVerifierWorker",
    "KillSwitch",
    "GLOBAL_KILL_SWITCH",
    "PreStepGuardResult",
    "verify_pre_step_guard",
    "reset_issue",
    "cancel_execution",
    "package_human_handover",
    "RunBudget",
    "BudgetTracker",
    "execute_with_timeout",
]
