"""
Elone Agent — SOP Governance Hub Backend API Bridge
=====================================================
Lightweight ASGI bridge server providing RESTful endpoints for the
SOP Governance Hub frontend dashboard and downstream agents.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from starlette.applications import Starlette
from starlette.staticfiles import StaticFiles
from starlette.routing import Mount
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

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
from api import all_routes

# Static Files Setup
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
static_routes = []
if os.path.exists(FRONTEND_DIR):
    static_routes.append(Mount("/", app=StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend"))

# Starlette Application
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

app = Starlette(
    debug=True,
    routes=all_routes + static_routes,
    middleware=middleware,
)


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("  Elone Agent — SOP Governance Hub API Server")
    print("  Serving Dashboard at: http://127.0.0.1:8000")
    print("  REST API Endpoints:   http://127.0.0.1:8000/api/overview")
    print("=" * 60 + "\n")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
