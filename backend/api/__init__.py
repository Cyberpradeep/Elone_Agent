"""
Elone Agent — Modular FastAPI & REST API Routers
================================================
Combines auth, ingestion, playbooks, governance, and telemetry routers.
"""

from api.routes_auth import auth_routes, auth_router
from api.routes_ingestion import ingestion_routes, ingestion_router
from api.routes_playbooks import playbook_routes, playbook_router
from api.routes_governance import governance_routes, governance_router
from api.routes_telemetry import telemetry_routes, telemetry_router

all_routers = [
    auth_router,
    telemetry_router,
    playbook_router,
    ingestion_router,
    governance_router,
]

all_routes = (
    auth_routes +
    telemetry_routes +
    playbook_routes +
    ingestion_routes +
    governance_routes
)

__all__ = [
    "auth_router",
    "ingestion_router",
    "playbook_router",
    "governance_router",
    "telemetry_router",
    "all_routers",
    "auth_routes",
    "ingestion_routes",
    "playbook_routes",
    "governance_routes",
    "telemetry_routes",
    "all_routes",
]
