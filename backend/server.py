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

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from auth.config import parse_allowed_origins
from auth.dependencies import AuthAccessError

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

# Validate CORS origins fail-closed at startup (never permits '*' with allow_credentials=True)
ALLOWED_ORIGINS = parse_allowed_origins()

# FastAPI Application
app = FastAPI(
    title="Elone Agent — SOP Governance Hub API",
    description=(
        "Enterprise Multi-Agent Standard Operating Procedure Governance Engine.\n\n"
        "Features:\n"
        "- Authenticated Lean 4-Role RBAC & Tenant/Clearance Enforcement (C2)\n"
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


@app.exception_handler(AuthAccessError)
async def _auth_access_error_handler(_request: Request, exc: AuthAccessError):
    return JSONResponse(
        {"error": exc.message, "error_code": exc.error_code},
        status_code=exc.status_code,
        headers=exc.headers or None,
    )


# Explicit CORS Lockdown (no wildcard origins/methods/headers with credentials)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    max_age=600,
)

# Register API Routers
for router in all_routers:
    app.include_router(router)


def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    components = schema.setdefault("components", {})
    schemes = components.setdefault("securitySchemes", {})
    schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    public_paths = {"/api/health", "/api/auth/login"}
    for path, methods in (schema.get("paths") or {}).items():
        if path in public_paths:
            continue
        for op in (methods or {}).values():
            if isinstance(op, dict):
                op.setdefault("security", [{"BearerAuth": []}])
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _custom_openapi

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
