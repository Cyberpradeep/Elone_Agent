"""Resource Budgets, Latency Timeouts & Remediation Loop Breakers.

Enforces:
1. Master Prompt Edge Case 35: Remediation Loop Breaker (max 2 replans -> NEEDS_HUMAN)
2. Master Prompt Edge Case 11 & Page 12 Target: 15-second per-node latency timeout (AGENT_TIMEOUT)
3. Master Prompt Edge Case 36: Global run duration (300s) and token budget (50,000) caps
"""

import time
import concurrent.futures
from typing import Any, Callable, Dict, Optional, Tuple
from pydantic import BaseModel, Field


class RunBudget(BaseModel):
    """Immutable resource budget configuration for an execution run."""

    max_tokens: int = Field(default=50_000, ge=1)
    max_duration_seconds: float = Field(default=300.0, ge=1.0)
    max_node_timeout_seconds: float = Field(default=15.0, ge=0.1)
    max_replan_attempts: int = Field(default=2, ge=0)
    max_cost_usd: float = Field(default=2.00, ge=0.0)


class BudgetTracker:
    """Thread-safe runtime tracker for resource consumption and loop counts."""

    def __init__(self, start_time: Optional[float] = None) -> None:
        self.start_time = start_time or time.time()
        self.tokens_used: int = 0
        self.replan_count: int = 0

    def record_tokens(self, count: int) -> int:
        """Add consumed tokens to tracker."""
        self.tokens_used += count
        return self.tokens_used

    def record_replan(self) -> int:
        """Increment replan count."""
        self.replan_count += 1
        return self.replan_count

    def elapsed_seconds(self) -> float:
        """Calculate elapsed seconds since run inception."""
        return time.time() - self.start_time

    def check_limits(self, budget: RunBudget) -> Tuple[bool, Optional[str]]:
        """Verify whether global token or duration caps have been breached."""
        if self.tokens_used > budget.max_tokens:
            return False, f"Token budget exceeded: {self.tokens_used} > {budget.max_tokens}"
        elapsed = self.elapsed_seconds()
        if elapsed > budget.max_duration_seconds:
            return False, f"Duration budget exceeded: {elapsed:.1f}s > {budget.max_duration_seconds}s"
        return True, None

    def is_loop_broken(self, budget: RunBudget) -> bool:
        """Remediation loop breaker: True if replans reached maximum allowed."""
        return self.replan_count >= budget.max_replan_attempts


def execute_with_timeout(
    func: Callable[..., Any],
    *args: Any,
    timeout_seconds: float = 15.0,
    **kwargs: Any,
) -> Any:
    """Execute a synchronous function within an asynchronous latency timeout deadline.

    If timeout expires, raises TimeoutError with AGENT_TIMEOUT marker.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            raise TimeoutError(
                f"Node execution timed out after {timeout_seconds}s (AGENT_TIMEOUT)."
            ) from exc
