"""
Elone Agent — SOP Governance Hub FastAPI Server
================================================
Production-ready FastAPI ASGI server providing RESTful endpoints for the
SOP Governance Hub frontend dashboard, interactive OpenAPI docs (/docs),
and downstream agent catalog retrieval.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Shared Context & Services
from api.context import (
    governance_ledger,
    retrieval_index,
    agent_bus,
    KB_DIR,
    UPLOADS_DIR,
    SOPS_DIR,
    PATTERNS_DIR,
    LOGS_DIR,
    DRAFTS_DIR,
    read_manifest,
    parse_yaml_frontmatter,
)

# Route Controllers
from api import all_routers, all_routes

# FastAPI Application
app = FastAPI(
    title="Elone Agent — SOP Governance Hub API",
    description=(
        "Enterprise Multi-Agent Standard Operating Procedure Governance Engine.\n\n"
        "Features:\n"
        "- 14-State Lifecycle Machine & Separation of Duties (SoD)\n"
        "- Dual-Custody HITL (Human-in-the-Loop) Review Gate\n"
        "- Automated Secret Scanning, DLP & AST Threat Quarantine Gate\n"
        "- Verbatim Quote Traceability & Source Line Completeness Verification\n"
        "- Downstream Multi-Tenant Clearance Catalog Retrieval (L0-L3)\n"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
for router in all_routers:
    app.include_router(router)

# Mount Frontend Dashboard Static Assets
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 70)
    print("  Elone Agent — SOP Governance Hub FastAPI Server")
    print("  Interactive Swagger Docs: http://127.0.0.1:8000/docs")
    print("  Interactive ReDoc:        http://127.0.0.1:8000/redoc")
    print("  Serving Web Dashboard at: http://127.0.0.1:8000")
    print("  REST API Health Check:    http://127.0.0.1:8000/api/health")
    print("=" * 70 + "\n")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
