"""
Elone Agent — Modular REST API Routers
======================================
Combines ingestion, playbooks, governance, and telemetry routers.
"""

from api.routes_ingestion import ingestion_routes
from api.routes_playbooks import playbook_routes
from api.routes_governance import governance_routes
from api.routes_telemetry import telemetry_routes

all_routes = (
    telemetry_routes +
    playbook_routes +
    ingestion_routes +
    governance_routes
)

__all__ = [
    "ingestion_routes",
    "playbook_routes",
    "governance_routes",
    "telemetry_routes",
    "all_routes",
]
