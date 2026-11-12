"""
JWT Issuing/Verification, OIDC Adapter & Persistent Revocation Store (C2)
=======================================================================
Supports:
  - Local HS256 JWTs with strict iss/aud/exp/sub/jti validation
  - External OIDC/SSO RS256/ES256 tokens via cached JWKS (PyJWKClient)
  - Hybrid mode (OIDC humans + local service-account JWTs)
  - Thread-safe, persistent jti revocation store (_auth/revoked_tokens.json)
"""

import os
import json
import time
import uuid
import hmac
import hashlib
import threading
from typing import Optional, Dict, Any, Tuple

import jwt

from .config import (
    get_auth_mode,
    get_jwt_secret,
    get_jwt_issuer,
    get_jwt_audience,
    get_token_ttl_seconds,
    get_agent_token_ttl_seconds,
    get_revoked_tokens_path,
    get_oidc_settings,
    AuthConfigurationError,
)
from .models import AuthPrincipal, ROLE_AGENT


class TokenValidationError(Exception):
    """Raised when a session cookie or Bearer token is missing, malformed, expired, or revoked."""

    def __init__(self, message: str, error_code: str = "token_invalid"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class RevocationStore:
    """Persistent, thread-safe JWT ID (jti) revocation store."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache_path: Optional[str] = None
        self._cache_mtime_ns: Optional[int] = None
        self._entries: Dict[str, int] = {}

    def _load_locked(self, path: str) -> Dict[str, int]:
        if not os.path.exists(path):
            self._cache_path = path
            self._cache_mtime_ns = None
            self._entries = {}
            return self._entries
        try:
            stat = os.stat(path)
            mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
            if self._cache_path == path and self._cache_mtime_ns == mtime_ns:
                return self._entries
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f) if os.path.getsize(path) > 0 else {}
            if not isinstance(raw, dict):
                raw = {}
            now = int(time.time())
            self._entries = {
                str(k): int(v)
                for k, v in raw.items()
                if isinstance(v, (int, float)) and int(v) >= now
            }
            self._cache_path = path
            self._cache_mtime_ns = mtime_ns
        except Exception:
            self._entries = {}
        return self._entries

    def _save_locked(self, path: str, entries: Dict[str, int]) -> None:
        now = int(time.time())
        pruned = {k: int(v) for k, v in entries.items() if int(v) >= now}
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(pruned, f, indent=2)
        os.replace(tmp, path)
        self._entries = pruned
        self._cache_path = path
        try:
            st = os.stat(path)
            self._cache_mtime_ns = getattr(st, "st_mtime_ns", None)
        except Exception:
            self._cache_mtime_ns = None

    def revoke(self, jti: str, exp: Optional[int] = None) -> None:
        clean_jti = str(jti or "").strip()
        if not clean_jti:
            return
        exp_ts = int(exp) if exp else int(time.time()) + 86400
        path = get_revoked_tokens_path()
        with self._lock:
            entries = dict(self._load_locked(path))
            entries[clean_jti] = max(exp_ts, int(time.time()) + 60)
            self._save_locked(path, entries)

    def is_revoked(self, jti: str) -> bool:
        clean_jti = str(jti or "").strip()
        if not clean_jti:
            return False
        path = get_revoked_tokens_path()
        with self._lock:
            entries = self._load_locked(path)
            exp_ts = entries.get(clean_jti)
            return exp_ts is not None and exp_ts >= int(time.time())


revocation_store = RevocationStore()

_JWKS_CLIENTS: Dict[str, Any] = {}
_JWKS_LOCK = threading.RLock()


def _get_jwk_client(jwks_url: str):
    with _JWKS_LOCK:
        client = _JWKS_CLIENTS.get(jwks_url)
        if client is None:
            client = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300)
            _JWKS_CLIENTS[jwks_url] = client
        return client


def create_access_token(
    subject_or_principal: Any,
    ttl_seconds: Optional[int] = None,
    secret: Optional[str] = None,
) -> Tuple[str, str, int]:
    """Mints a signed HS256 JWT and returns (token_str, jti, expires_in_seconds)."""
    principal = (
        subject_or_principal
        if isinstance(subject_or_principal, AuthPrincipal)
        else subject_or_principal.to_principal()
    )
    is_agent = ROLE_AGENT in principal.roles
    ttl = int(
        ttl_seconds
        if ttl_seconds is not None
        else (get_agent_token_ttl_seconds() if is_agent else get_token_ttl_seconds())
    )
    ttl = max(1, ttl)
    now = int(time.time())
    exp = now + ttl
    jti = f"tok_{uuid.uuid4().hex}"

    payload = {
        "sub": principal.sub,
        "identity": principal.identity,
        "display_name": principal.display_name,
        "roles": list(principal.roles),
        "tenant_id": principal.tenant_id,
        "clearance": principal.clearance,
        "actor_type": principal.actor_type,
        "agent_id": principal.agent_id,
        "agent_persona": principal.agent_persona,
        "jti": jti,
        "iss": get_jwt_issuer(),
        "aud": get_jwt_audience(),
        "iat": now,
        "exp": exp,
    }
    signing_key = secret or get_jwt_secret()
    token = jwt.encode(payload, signing_key, algorithm="HS256")
    return token, jti, ttl


def _principal_from_claims(
    claims: Dict[str, Any],
    *,
    auth_method: str,
    jti_fallback: str = "",
) -> AuthPrincipal:
    jti = str(claims.get("jti") or jti_fallback).strip()
    if jti and revocation_store.is_revoked(jti):
        raise TokenValidationError("Session or token has been revoked.", error_code="token_revoked")
    try:
        return AuthPrincipal(
            sub=claims.get("sub"),
            identity=claims.get("identity"),
            display_name=claims.get("display_name") or claims.get("identity"),
            roles=claims.get("roles"),
            tenant_id=claims.get("tenant_id"),
            clearance=claims.get("clearance"),
            actor_type=claims.get("actor_type") or "",
            agent_id=claims.get("agent_id"),
            agent_persona=claims.get("agent_persona"),
            jti=jti,
            exp=claims.get("exp"),
            auth_method=auth_method,
        )
    except ValueError as e:
        raise TokenValidationError(f"Invalid token claims: {e}", error_code="token_claims_invalid") from e


def decode_local_token(
    token: str,
    *,
    auth_method: str = "bearer",
    secret: Optional[str] = None,
) -> AuthPrincipal:
    signing_key = secret or get_jwt_secret()
    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["HS256"],
            issuer=get_jwt_issuer(),
            audience=get_jwt_audience(),
            options={"require": ["exp", "iat", "sub", "jti", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise TokenValidationError("Token has expired.", error_code="token_expired") from e
    except jwt.PyJWTError as e:
        raise TokenValidationError(f"Invalid authentication token: {e}", error_code="token_invalid") from e

    return _principal_from_claims(claims, auth_method=auth_method)


def _map_oidc_claims(raw_claims: Dict[str, Any], settings: Dict[str, Optional[str]]) -> Dict[str, Any]:
    id_key = settings["identity_claim"] or "email"
    roles_key = settings["roles_claim"] or "roles"
    tenant_key = settings["tenant_claim"] or "tenant_id"
    clearance_key = settings["clearance_claim"] or "clearance"

    identity = (
        raw_claims.get(id_key)
        or raw_claims.get("email")
        or raw_claims.get("preferred_username")
        or raw_claims.get("upn")
        or raw_claims.get("sub")
    )
    raw_roles = raw_claims.get(roles_key)
    if raw_roles is None:
        raw_roles = raw_claims.get("groups") or []
    if isinstance(raw_roles, str):
        raw_roles = [raw_roles]
    elif not isinstance(raw_roles, list):
        raw_roles = list(raw_roles)

    role_map_raw = settings.get("role_map_json")
    if role_map_raw:
        try:
            role_map = json.loads(role_map_raw)
        except Exception as e:
            raise AuthConfigurationError(f"Invalid ELONE_OIDC_ROLE_MAP JSON: {e}") from e
        mapped_roles = [role_map.get(r, r) for r in raw_roles]
    else:
        mapped_roles = list(raw_roles)

    return {
        "sub": raw_claims.get("sub"),
        "identity": identity,
        "display_name": raw_claims.get("name") or identity,
        "roles": mapped_roles,
        "tenant_id": raw_claims.get(tenant_key),
        "clearance": raw_claims.get(clearance_key, "L1"),
        "actor_type": "human",
        "jti": raw_claims.get("jti"),
        "exp": raw_claims.get("exp"),
    }


def decode_oidc_token(
    token: str,
    *,
    auth_method: str = "bearer",
    jwk_client: Any = None,
) -> AuthPrincipal:
    settings = get_oidc_settings()
    jwks_url = settings["jwks_url"]
    issuer = settings["issuer"]
    audience = settings["audience"] or get_jwt_audience()
    if (not jwks_url and jwk_client is None) or not issuer:
        raise AuthConfigurationError(
            "OIDC authentication enabled but ELONE_OIDC_JWKS_URL or ELONE_OIDC_ISSUER is unset."
        )
    client = jwk_client or _get_jwk_client(jwks_url)
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        raw_claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384"],
            issuer=issuer,
            audience=audience,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise TokenValidationError("OIDC token has expired.", error_code="token_expired") from e
    except jwt.PyJWTError as e:
        raise TokenValidationError(f"Invalid OIDC token: {e}", error_code="token_invalid") from e

    mapped = _map_oidc_claims(raw_claims, settings)
    token_digest = f"oidc_{hashlib.sha256(token.encode('utf-8')).hexdigest()[:32]}"
    return _principal_from_claims(mapped, auth_method=auth_method, jti_fallback=token_digest)


def decode_access_token(token: str, *, auth_method: str = "bearer") -> AuthPrincipal:
    if not token or not str(token).strip():
        raise TokenValidationError("Authentication token is missing.", error_code="token_missing")
    clean = str(token).strip()
    mode = get_auth_mode()
    if mode == "local":
        return decode_local_token(clean, auth_method=auth_method)
    if mode == "oidc":
        return decode_oidc_token(clean, auth_method=auth_method)

    # hybrid: inspect unverified issuer ONLY to pick local vs OIDC verifier (still cryptographically verified!)
    try:
        unverified = jwt.decode(clean, options={"verify_signature": False})
    except jwt.PyJWTError as e:
        raise TokenValidationError(f"Malformed token: {e}", error_code="token_invalid") from e
    iss = str(unverified.get("iss") or "").strip()
    if hmac.compare_digest(iss, get_jwt_issuer()):
        return decode_local_token(clean, auth_method=auth_method)
    return decode_oidc_token(clean, auth_method=auth_method)


__all__ = [
    "TokenValidationError",
    "RevocationStore",
    "revocation_store",
    "create_access_token",
    "decode_local_token",
    "decode_oidc_token",
    "decode_access_token",
]

