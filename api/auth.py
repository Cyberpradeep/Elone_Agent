"""Authenticated API Guard & JWT Token Management (Module A10 & PR-15).

Enforces:
- Rule 1: Identity, tenant, role and clearance come only from verified JWT.
- Zero Anonymous Access: Missing or invalid token yields HTTP 401.
- Tenant Isolation (Edge Case 22): Prevents cross-tenant data leakage.
"""

from datetime import datetime, timedelta
import os
import time
from typing import List, Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pydantic import BaseModel, ConfigDict, Field

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "elone-pilot-jwt-insecure-secret-key-32b")
JWT_ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    """User identity extracted exclusively from verified cryptographically signed JWT."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str = Field(..., min_length=2)
    tenant_id: str = Field(..., min_length=2)
    roles: List[str] = Field(default_factory=list)
    clearance: int = Field(default=1, ge=1, le=4)


def create_access_token(
    user: AuthenticatedUser,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Issue a signed JWT access token for authentication and authorization."""
    now = int(time.time())
    delta_sec = int(expires_delta.total_seconds()) if expires_delta else 3600
    exp = now + delta_sec
    payload = {
        "sub": user.user_id,
        "tenant_id": user.tenant_id,
        "roles": user.roles,
        "clearance": user.clearance,
        "iat": now,
        "exp": exp,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> AuthenticatedUser:
    """Validate and decode a signed JWT token, extracting AuthenticatedUser."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return AuthenticatedUser(
            user_id=payload["sub"],
            tenant_id=payload["tenant_id"],
            roles=payload.get("roles", []),
            clearance=payload.get("clearance", 1),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="EXPIRED_TOKEN")
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """FastAPI dependency: Extract verified user identity or fail closed with 401."""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="MISSING_TOKEN")
    return decode_access_token(credentials.credentials)


def require_clearance(min_level: int):
    """Factory dependency: Enforce user has sufficient clearance for risk tier."""

    async def _clearance_check(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if user.clearance < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"INSUFFICIENT_CLEARANCE: Required {min_level}, user has {user.clearance}",
            )
        return user

    return _clearance_check


def verify_tenant_access(user: AuthenticatedUser, resource_tenant_id: str) -> None:
    """Enforce strict multi-tenant boundary (Edge Case 22)."""
    if user.tenant_id != resource_tenant_id:
        raise HTTPException(
            status_code=403,
            detail=f"CROSS_TENANT_ACCESS_FORBIDDEN: User tenant '{user.tenant_id}' cannot access resource for '{resource_tenant_id}'",
        )
