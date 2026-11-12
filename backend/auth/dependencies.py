"""
FastAPI Authentication, CSRF, RBAC, Tenant & Clearance Dependencies (C2)
========================================================================
Extracts credentials strictly from Authorization Bearer header or HttpOnly session cookie,
verifies tokens via decode_access_token, enforces double-submit CSRF on cookie mutations,
enforces Lean 4-role RBAC + human-only checks + tenant + clearance boundaries, and emits
structured audit events to knowledge_base/_auth/auth_events.jsonl.
"""

import os
import json
import hmac
import datetime
import threading
from typing import Optional, Iterable, Dict, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agents.a6_hub.retrieval_catalog import normalize_clearance
from .config import get_auth_audit_log_path
from .models import (
    AuthPrincipal,
    HUMAN_ROLES,
    ROLE_ADMIN,
    ROLE_PROCESS_OWNER,
    ROLE_SECURITY_REVIEWER,
    ROLE_SET,
)
from .tokens import TokenValidationError, decode_access_token
from .user_store import user_store


_AUDIT_LOCK = threading.RLock()
bearer_scheme = HTTPBearer(auto_error=False)


class AuthAccessError(Exception):
    """HTTP-mapped authentication/authorization failure returning {"error", "error_code"}."""

    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.message = str(message)
        self.error_code = str(error_code)
        self.headers = dict(headers or {})


def get_client_ip(request: Request) -> str:
    try:
        if request.client and request.client.host:
            return str(request.client.host)
    except Exception:
        pass
    return "127.0.0.1"


def log_auth_event(
    event: str,
    *,
    identity: Optional[str] = None,
    sub: Optional[str] = None,
    roles: Optional[Iterable[str]] = None,
    tenant_id: Optional[str] = None,
    clearance: Optional[str] = None,
    actor_type: Optional[str] = None,
    client_ip: Optional[str] = None,
    path: Optional[str] = None,
    status: str = "ok",
    detail: Optional[str] = None,
) -> None:
    """Appends an append-only JSONL security event (never records secrets or JWTs)."""
    record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "event": str(event),
        "status": str(status),
        "identity": identity,
        "sub": sub,
        "roles": list(roles) if roles is not None else None,
        "tenant_id": tenant_id,
        "clearance": clearance,
        "actor_type": actor_type,
        "client_ip": client_ip,
        "path": path,
        "detail": detail,
    }
    log_path = get_auth_audit_log_path()
    try:
        with _AUDIT_LOCK:
            os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def extract_token_from_request(request: Request) -> tuple[str, str]:
    """Returns (raw_token, auth_method) where auth_method is 'bearer' or 'cookie'."""
    auth_header = request.headers.get("authorization")
    if auth_header is not None and auth_header.strip():
        parts = auth_header.strip().split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
            raise AuthAccessError(
                401,
                "Invalid Authorization header. Expected 'Bearer <token>'.",
                "token_invalid",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return parts[1].strip(), "bearer"

    cookie_token = request.cookies.get("elone_session")
    if cookie_token and cookie_token.strip():
        return cookie_token.strip(), "cookie"

    raise AuthAccessError(
        401,
        "Authentication required. Sign in or provide a valid Bearer token.",
        "auth_required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def csrf_protect(request: Request, principal: AuthPrincipal) -> None:
    """Enforces double-submit CSRF token validation on cookie-authenticated mutations."""
    if principal.auth_method != "cookie":
        return
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    csrf_cookie = str(request.cookies.get("elone_csrf") or "").strip()
    csrf_header = str(request.headers.get("x-csrf-token") or "").strip()
    if len(csrf_cookie) < 8 or len(csrf_header) < 8 or not hmac.compare_digest(csrf_cookie, csrf_header):
        log_auth_event(
            "access_denied",
            identity=principal.identity,
            sub=principal.sub,
            roles=principal.roles,
            tenant_id=principal.tenant_id,
            clearance=principal.clearance,
            actor_type=principal.actor_type,
            client_ip=get_client_ip(request),
            path=str(request.url.path),
            status="denied",
            detail="csrf_invalid",
        )
        raise AuthAccessError(
            403,
            "CSRF protection error: missing or mismatched X-CSRF-Token header.",
            "csrf_invalid",
        )


def authenticate_request(
    request: Request,
    *,
    allowed_roles: Optional[Iterable[str]] = None,
    human_only: bool = False,
    check_csrf: bool = True,
) -> AuthPrincipal:
    """Authenticates and authorizes the incoming request strictly from token claims."""
    raw_token, auth_method = extract_token_from_request(request)
    try:
        principal = decode_access_token(raw_token, auth_method=auth_method)
    except TokenValidationError as e:
        raise AuthAccessError(
            401,
            e.message,
            e.error_code,
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    # Immediate local account disablement enforcement
    stored_user = user_store.get_by_sub(principal.sub)
    if stored_user is not None and stored_user.disabled:
        raise AuthAccessError(
            401,
            "Account has been disabled.",
            "account_disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if check_csrf:
        csrf_protect(request, principal)

    if human_only and not principal.is_human:
        log_auth_event(
            "access_denied",
            identity=principal.identity,
            sub=principal.sub,
            roles=principal.roles,
            tenant_id=principal.tenant_id,
            clearance=principal.clearance,
            actor_type=principal.actor_type,
            client_ip=get_client_ip(request),
            path=str(request.url.path),
            status="denied",
            detail="not_human",
        )
        raise AuthAccessError(
            403,
            "Only human operator accounts may perform this action.",
            "not_human",
        )

    if allowed_roles is not None:
        role_tuple = tuple(sorted({str(r).strip().lower() for r in allowed_roles}))
        if not principal.has_any_role(role_tuple):
            log_auth_event(
                "access_denied",
                identity=principal.identity,
                sub=principal.sub,
                roles=principal.roles,
                tenant_id=principal.tenant_id,
                clearance=principal.clearance,
                actor_type=principal.actor_type,
                client_ip=get_client_ip(request),
                path=str(request.url.path),
                status="denied",
                detail=f"insufficient_role:requires={','.join(role_tuple)}",
            )
            raise AuthAccessError(
                403,
                f"Access denied: requires one of role(s) [{', '.join(role_tuple)}].",
                "insufficient_role",
            )

    try:
        request.state.principal = principal
    except Exception:
        pass
    return principal


def get_current_principal(
    request: Request,
    _cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthPrincipal:
    return authenticate_request(request, allowed_roles=ROLE_SET, human_only=False, check_csrf=True)


def require_roles(*roles: str, human_only: bool = True, check_csrf: bool = True):
    allowed = tuple(roles) if roles else tuple(HUMAN_ROLES)

    def _dependency(
        request: Request,
        _cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    ) -> AuthPrincipal:
        return authenticate_request(
            request,
            allowed_roles=allowed,
            human_only=human_only,
            check_csrf=check_csrf,
        )

    return _dependency


def require_human(
    request: Request,
    _cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthPrincipal:
    return authenticate_request(
        request,
        allowed_roles=HUMAN_ROLES,
        human_only=True,
        check_csrf=True,
    )


def enforce_tenant_access(
    principal: AuthPrincipal,
    resource_tenant_id: Optional[str],
    *,
    request: Optional[Request] = None,
) -> None:
    clean_res = str(resource_tenant_id or "").strip()
    if not clean_res or clean_res != principal.tenant_id:
        log_auth_event(
            "access_denied",
            identity=principal.identity,
            sub=principal.sub,
            roles=principal.roles,
            tenant_id=principal.tenant_id,
            clearance=principal.clearance,
            actor_type=principal.actor_type,
            client_ip=get_client_ip(request) if request else None,
            path=str(request.url.path) if request else None,
            status="denied",
            detail=f"tenant_isolation:resource_tenant={clean_res}",
        )
        raise AuthAccessError(
            403,
            "Access denied: Tenant isolation policy violation.",
            "tenant_isolation",
        )


def enforce_clearance_access(
    principal: AuthPrincipal,
    required_tier: Optional[str],
    *,
    request: Optional[Request] = None,
) -> None:
    tier = normalize_clearance(required_tier or "L1")
    if not principal.can_access_tier(tier):
        log_auth_event(
            "access_denied",
            identity=principal.identity,
            sub=principal.sub,
            roles=principal.roles,
            tenant_id=principal.tenant_id,
            clearance=principal.clearance,
            actor_type=principal.actor_type,
            client_ip=get_client_ip(request) if request else None,
            path=str(request.url.path) if request else None,
            status="denied",
            detail=f"insufficient_clearance:required={tier}",
        )
        raise AuthAccessError(
            403,
            f"Access denied: Insufficient clearance. Resource requires {tier}, caller has {principal.clearance}.",
            "insufficient_clearance",
        )


def enforce_review_task_eligibility(
    principal: AuthPrincipal,
    task: Optional[Dict[str, Any]],
    sop_tier: str,
    *,
    request: Optional[Request] = None,
) -> None:
    """Enforces human actor, clearance >= sop_tier, and strict Option A Security Reviewer role gate."""
    if not principal.is_human:
        raise AuthAccessError(
            403,
            "Approval rejected: Only human reviewers may record decisions.",
            "not_human",
        )

    enforce_clearance_access(principal, sop_tier, request=request)

    if not principal.has_role(ROLE_SECURITY_REVIEWER):
        log_auth_event(
            "access_denied",
            identity=principal.identity,
            sub=principal.sub,
            roles=principal.roles,
            tenant_id=principal.tenant_id,
            clearance=principal.clearance,
            actor_type=principal.actor_type,
            client_ip=get_client_ip(request) if request else None,
            path=str(request.url.path) if request else None,
            status="denied",
            detail="role_gate:requires=security_reviewer",
        )
        raise AuthAccessError(
            403,
            "Access denied: Review decisions require the 'security_reviewer' role.",
            "insufficient_role",
        )


__all__ = [
    "AuthAccessError",
    "bearer_scheme",
    "get_client_ip",
    "log_auth_event",
    "extract_token_from_request",
    "csrf_protect",
    "authenticate_request",
    "get_current_principal",
    "require_roles",
    "require_human",
    "enforce_tenant_access",
    "enforce_clearance_access",
    "enforce_review_task_eligibility",
]
