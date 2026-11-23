"""Immutable Execution Plan Endpoints (Module A10 & PR-15).

Enforces:
- Rule 3: No endpoint may edit an approved SOP, binding, or plan (strictly read-only).
- Edge Case 22: Tenant isolation on plan retrieval.
- Authenticated retrieval requiring valid JWT.
"""

import threading
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException

from api.auth import AuthenticatedUser, get_current_user, verify_tenant_access
from contracts.plan import ExecutionPlan

router = APIRouter(prefix="/plans", tags=["plans"])


class PlanRegistry:
    """Thread-safe in-memory plan registry for execution orchestrator."""

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register_plan(
        self,
        issue_id: str,
        plan: ExecutionPlan,
        tenant_id: str,
        requester_id: str,
    ) -> None:
        """Register an immutable execution plan bound to an issue and tenant."""
        with self._lock:
            self._store[issue_id] = {
                "plan": plan,
                "tenant_id": tenant_id,
                "requester_id": requester_id,
            }

    def get_entry(self, issue_id: str) -> Optional[Dict[str, Any]]:
        """Fetch plan registration entry by issue ID."""
        with self._lock:
            return self._store.get(issue_id)

    def clear(self) -> None:
        """Clear all registered plans (used in testing)."""
        with self._lock:
            self._store.clear()


GLOBAL_PLAN_REGISTRY = PlanRegistry()


@router.get("/{issue_id}")
async def get_execution_plan(
    issue_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve an immutable execution plan with canonical hash and steps."""
    entry = GLOBAL_PLAN_REGISTRY.get_entry(issue_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"PLAN_NOT_FOUND: No execution plan found for issue '{issue_id}'",
        )

    verify_tenant_access(current_user, entry["tenant_id"])
    plan: ExecutionPlan = entry["plan"]
    return plan.model_dump(mode="json")
