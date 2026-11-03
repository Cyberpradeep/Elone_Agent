"""
Elone Agent — Modular FastAPI & REST API Routers
================================================
Combines ingestion, playbooks, governance, and telemetry routers.
"""

from api.routes_ingestion import ingestion_routes, ingestion_router
from api.routes_playbooks import playbook_routes, playbook_router
from api.routes_governance import governance_routes, governance_router
from api.routes_telemetry import telemetry_routes, telemetry_router

all_routers = [
    telemetry_router,
    playbook_router,
    ingestion_router,
    governance_router,
]

all_routes = (
    telemetry_routes +
    playbook_routes +
    ingestion_routes +
    governance_routes
)

__all__ = [
    "ingestion_router",
    "playbook_router",
    "governance_router",
    "telemetry_router",
    "all_routers",
    "ingestion_routes",
    "playbook_routes",
    "governance_routes",
    "telemetry_routes",
    "all_routes",
]
