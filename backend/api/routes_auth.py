"""
Authentication & Tenant User Provisioning API Route Handlers (C2)
================================================================
Provides:
  - POST /api/auth/login            (public, brute-force rate-limited, sets HttpOnly + CSRF cookies)
  - POST /api/auth/logout           (revokes JWT jti + clears session cookies)
  - GET  /api/auth/me               (returns current verified principal + capabilities)
  - GET  /api/auth/users            (admin only, tenant-scoped)
  - POST /api/auth/users            (admin only, tenant-scoped)
  - PATCH /api/auth/users/{sub}     (admin only, tenant-scoped)
  - POST /api/auth/users/{sub}/token (admin only, issues scoped service token for agent accounts)
"""

import secrets
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from auth.config import is_cookie_secure
from auth.models import ROLE_AGENT, ROLE_ADMIN, ROLE_SET
from auth.tokens import create_access_token, revocation_store
from auth.user_store import (
    AccountExistsError,
    AccountNotFoundError,
    AuthenticationFailedError,
    RateLimitExceededError,
    user_store,
)
from auth.dependencies import (
    authenticate_request,
    enforce_tenant_access,
    get_client_ip,
    log_auth_event,
)


async def api_auth_login(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    client_ip = get_client_ip(request)

    if not username or not password:
        return JSONResponse(
            {"error": "Username and password are required.", "error_code": "missing_credentials"},
            status_code=400,
        )

    try:
        rec = user_store.authenticate(username, password, client_ip=client_ip)
    except RateLimitExceededError as e:
        log_auth_event(
            "login_lockout",
            identity=username,
            client_ip=client_ip,
            path=str(request.url.path),
            status="denied",
            detail=f"retry_after={e.retry_after}",
        )
        return JSONResponse(
            {"error": str(e), "error_code": "rate_limited", "retry_after": e.retry_after},
            status_code=429,
            headers={"Retry-After": str(e.retry_after)},
        )
    except AuthenticationFailedError as e:
        log_auth_event(
            "login_failure",
            identity=username,
            client_ip=client_ip,
            path=str(request.url.path),
            status="denied",
            detail=str(e),
        )
        return JSONResponse(
            {"error": str(e), "error_code": "invalid_credentials"},
            status_code=401,
        )

    token, jti, expires_in = create_access_token(rec)
    csrf_token = secrets.token_urlsafe(24)
    principal = rec.to_principal(jti=jti, auth_method="cookie")

    log_auth_event(
        "login_success",
        identity=principal.identity,
        sub=principal.sub,
        roles=principal.roles,
        tenant_id=principal.tenant_id,
        clearance=principal.clearance,
        actor_type=principal.actor_type,
        client_ip=client_ip,
        path=str(request.url.path),
        status="ok",
    )

    resp = JSONResponse({
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "csrf_token": csrf_token,
        "user": principal.to_public_dict(),
    })

    cookie_secure = is_cookie_secure()
    resp.set_cookie(
        key="elone_session",
        value=token,
        max_age=expires_in,
        path="/api",
        httponly=True,
        samesite="lax",
        secure=cookie_secure,
    )
    resp.set_cookie(
        key="elone_csrf",
        value=csrf_token,
        max_age=expires_in,
        path="/",
        httponly=False,
        samesite="lax",
        secure=cookie_secure,
    )
    return resp


async def api_auth_logout(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=ROLE_SET,
        human_only=False,
        check_csrf=True,
    )
    if principal.jti:
        revocation_store.revoke(principal.jti, principal.exp)

    log_auth_event(
        "logout",
        identity=principal.identity,
        sub=principal.sub,
        roles=principal.roles,
        tenant_id=principal.tenant_id,
        clearance=principal.clearance,
        actor_type=principal.actor_type,
        client_ip=get_client_ip(request),
        path=str(request.url.path),
        status="ok",
    )

    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie(key="elone_session", path="/api")
    resp.delete_cookie(key="elone_csrf", path="/")
    return resp


async def api_auth_me(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=ROLE_SET,
        human_only=False,
        check_csrf=False,
    )
    return JSONResponse({
        "user": principal.to_public_dict(),
        "capabilities": principal.capabilities,
    })


async def api_auth_list_users(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_ADMIN,),
        human_only=True,
        check_csrf=False,
    )
    users = user_store.list_users(tenant_id=principal.tenant_id)
    return JSONResponse({
        "users": [u.to_public_dict() for u in users],
        "total": len(users),
        "tenant_id": principal.tenant_id,
    })


async def api_auth_create_user(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_ADMIN,),
        human_only=True,
        check_csrf=True,
    )
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body."}, status_code=400)

    if "tenant_id" in body and body["tenant_id"] is not None:
        if str(body["tenant_id"]).strip() != principal.tenant_id:
            return JSONResponse(
                {"error": "Access denied: Admins may only create accounts in their own tenant.", "error_code": "tenant_isolation"},
                status_code=403,
            )

    try:
        rec = user_store.create_user(
            username=str(body.get("username") or "").strip(),
            password=body.get("password"),
            roles=body.get("roles") or body.get("role"),
            tenant_id=principal.tenant_id,
            clearance=body.get("clearance") or "L1",
            identity=body.get("identity"),
            display_name=body.get("display_name"),
            agent_id=body.get("agent_id"),
            agent_persona=body.get("agent_persona"),
            disabled=bool(body.get("disabled", False)),
        )
    except AccountExistsError as e:
        return JSONResponse({"error": str(e), "error_code": "account_exists"}, status_code=409)
    except ValueError as e:
        return JSONResponse({"error": str(e), "error_code": "validation_error"}, status_code=400)

    log_auth_event(
        "user_created",
        identity=principal.identity,
        sub=principal.sub,
        roles=principal.roles,
        tenant_id=principal.tenant_id,
        clearance=principal.clearance,
        actor_type=principal.actor_type,
        client_ip=get_client_ip(request),
        path=str(request.url.path),
        status="ok",
        detail=f"created_sub={rec.sub},roles={','.join(rec.roles)}",
    )
    return JSONResponse({"status": "created", "user": rec.to_public_dict()}, status_code=201)


async def api_auth_update_user(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_ADMIN,),
        human_only=True,
        check_csrf=True,
    )
    sub = str(request.path_params.get("sub") or "").strip()
    target = user_store.get_by_sub(sub)
    if not target:
        return JSONResponse({"error": f"User '{sub}' not found."}, status_code=404)

    enforce_tenant_access(principal, target.tenant_id, request=request)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body."}, status_code=400)

    if "tenant_id" in body and body["tenant_id"] is not None:
        if str(body["tenant_id"]).strip() != principal.tenant_id:
            return JSONResponse(
                {"error": "Access denied: Cannot move account across tenants.", "error_code": "tenant_isolation"},
                status_code=403,
            )

    if target.sub == principal.sub:
        if body.get("disabled") is True:
            return JSONResponse(
                {"error": "Admins cannot disable their own active account.", "error_code": "self_lockout_prevented"},
                status_code=400,
            )
        if "roles" in body or "role" in body:
            proposed = body.get("roles") or body.get("role")
            proposed_set = {str(r).strip().lower() for r in ([proposed] if isinstance(proposed, str) else (proposed or []))}
            if ROLE_ADMIN not in proposed_set:
                return JSONResponse(
                    {"error": "Admins cannot remove their own 'admin' role.", "error_code": "self_lockout_prevented"},
                    status_code=400,
                )

    try:
        updated = user_store.update_user(
            sub,
            roles=body.get("roles") if "roles" in body else body.get("role"),
            clearance=body.get("clearance"),
            display_name=body.get("display_name"),
            disabled=body.get("disabled"),
            password=body.get("password"),
            agent_persona=body.get("agent_persona"),
        )
    except AccountNotFoundError:
        return JSONResponse({"error": f"User '{sub}' not found."}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e), "error_code": "validation_error"}, status_code=400)

    log_auth_event(
        "user_updated",
        identity=principal.identity,
        sub=principal.sub,
        roles=principal.roles,
        tenant_id=principal.tenant_id,
        clearance=principal.clearance,
        actor_type=principal.actor_type,
        client_ip=get_client_ip(request),
        path=str(request.url.path),
        status="ok",
        detail=f"updated_sub={updated.sub},disabled={updated.disabled}",
    )
    return JSONResponse({"status": "updated", "user": updated.to_public_dict()})


async def api_auth_issue_agent_token(request: Request):
    principal = authenticate_request(
        request,
        allowed_roles=(ROLE_ADMIN,),
        human_only=True,
        check_csrf=True,
    )
    sub = str(request.path_params.get("sub") or "").strip()
    target = user_store.get_by_sub(sub)
    if not target:
        return JSONResponse({"error": f"Account '{sub}' not found."}, status_code=404)

    enforce_tenant_access(principal, target.tenant_id, request=request)
    if target.disabled:
        return JSONResponse({"error": "Cannot issue token for a disabled account.", "error_code": "account_disabled"}, status_code=400)
    if ROLE_AGENT not in target.roles:
        return JSONResponse({"error": "Service tokens may only be minted for accounts with role 'agent'.", "error_code": "validation_error"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    ttl_minutes = body.get("ttl_minutes")
    ttl_seconds = max(60, int(ttl_minutes) * 60) if ttl_minutes is not None else None
    token, jti, expires_in = create_access_token(target, ttl_seconds=ttl_seconds)

    log_auth_event(
        "agent_token_issued",
        identity=principal.identity,
        sub=principal.sub,
        roles=principal.roles,
        tenant_id=principal.tenant_id,
        clearance=principal.clearance,
        actor_type=principal.actor_type,
        client_ip=get_client_ip(request),
        path=str(request.url.path),
        status="ok",
        detail=f"target_sub={target.sub},jti={jti}",
    )
    return JSONResponse({
        "token_type": "bearer",
        "access_token": token,
        "jti": jti,
        "expires_in": expires_in,
        "user": target.to_public_dict(),
    })


auth_router = APIRouter(tags=["Authentication & Access Control"])
auth_router.add_api_route("/api/auth/login", api_auth_login, methods=["POST"], summary="Authenticate & Establish Session")
auth_router.add_api_route("/api/auth/logout", api_auth_logout, methods=["POST"], summary="Revoke Token & Clear Session Cookies")
auth_router.add_api_route("/api/auth/me", api_auth_me, methods=["GET"], summary="Inspect Current Verified Principal & Capabilities")
auth_router.add_api_route("/api/auth/users", api_auth_list_users, methods=["GET"], summary="List Tenant Users (Admin Only)")
auth_router.add_api_route("/api/auth/users", api_auth_create_user, methods=["POST"], summary="Create Tenant User or Service Account (Admin Only)")
auth_router.add_api_route("/api/auth/users/{sub}", api_auth_update_user, methods=["PATCH"], summary="Update Tenant User / Service Account (Admin Only)")
auth_router.add_api_route("/api/auth/users/{sub}/token", api_auth_issue_agent_token, methods=["POST"], summary="Issue Bounded Service Token for Agent Account (Admin Only)")

auth_routes = list(auth_router.routes)

