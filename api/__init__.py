"""Execution Engine API Package (Module A10 & PR-15).

Provides versioned, authenticated endpoints for plan inspection and approval governance.
"""

from fastapi import APIRouter, FastAPI
from api.auth import AuthenticatedUser, create_access_token, get_current_user
from api.routes_plans import GLOBAL_PLAN_REGISTRY, router as plans_router
from api.routes_approvals import GLOBAL_APPROVAL_MANAGER, router as approvals_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(plans_router)
api_v1_router.include_router(approvals_router)


def create_api_app() -> FastAPI:
    """Create a standalone FastAPI test application mounting versioned API routes."""
    app = FastAPI(title="SOP Execution Engine API", version="1.0.0")
    app.include_router(api_v1_router)
    return app


__all__ = [
    "api_v1_router",
    "create_api_app",
    "AuthenticatedUser",
    "create_access_token",
    "get_current_user",
    "GLOBAL_PLAN_REGISTRY",
    "GLOBAL_APPROVAL_MANAGER",
]
