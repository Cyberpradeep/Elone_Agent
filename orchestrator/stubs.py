"""Contract Worker Stubs for Chezhian's Track B Subsystems.

Provides offline mock execution and verification workers that adhere strictly to
the shared contracts in contracts/plan.py, enabling isolated testing of Module A4.
"""

from typing import Any, Dict, Optional
from contracts.plan import ExecutionStep


class MockExecutorWorker:
    """Mock worker stub for Chezhian's Module A5 (execution engine)."""

    def __init__(self, default_exit_code: int = 0, default_stdout: str = "Mock execution completed successfully"):
        self.default_exit_code = default_exit_code
        self.default_stdout = default_stdout
        self.invocations: list[Dict[str, Any]] = []

    def execute_step(
        self, step: ExecutionStep, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Simulate deterministic execution of an approved step."""
        invocation = {
            "step_number": step.step_number,
            "tool_name": step.tool_name,
            "operation": step.operation,
            "parameters": step.parameters,
            "risk_level": step.risk_level.value if hasattr(step.risk_level, "value") else step.risk_level,
            "context": context or {},
        }
        self.invocations.append(invocation)
        return {
            "step_number": step.step_number,
            "tool_name": step.tool_name,
            "operation": step.operation,
            "exit_code": self.default_exit_code,
            "stdout": self.default_stdout,
            "stderr": "",
            "success": self.default_exit_code == 0,
        }


class MockVerifierWorker:
    """Mock worker stub for Chezhian's Module A6 (verification engine)."""

    def __init__(self, default_passed: bool = True, default_message: str = "Verification succeeded"):
        self.default_passed = default_passed
        self.default_message = default_message
        self.invocations: list[Dict[str, Any]] = []

    def verify_step(
        self, step_number: int, expected: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Simulate deterministic verification of a post-execution system state."""
        invocation = {
            "step_number": step_number,
            "expected": expected or {},
        }
        self.invocations.append(invocation)
        return {
            "step_number": step_number,
            "passed": self.default_passed,
            "message": self.default_message,
            "evidence": {"status": "HEALTHY", "verified": self.default_passed},
        }
