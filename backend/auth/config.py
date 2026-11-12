"""
Authentication & Authorization Configuration (C2)
===============================================
Centralized, fail-closed loader for JWT secrets, CORS origin allowlists,
token TTLs, brute-force lockout limits, auth storage paths, and OIDC settings.
"""

import os
import sys
import secrets
from typing import List, Dict, Tuple, Optional


class AuthConfigurationError(RuntimeError):
    """Raised when required authentication or CORS configuration is missing or insecure."""


_DEV_EPHEMERAL_SECRET: Optional[str] = None
_DEV_WARNING_EMITTED = False

DEFAULT_ALLOWED_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000"
VALID_AUTH_MODES = frozenset({"local", "oidc", "hybrid"})


def get_auth_mode() -> str:
    mode = os.getenv("ELONE_AUTH_MODE", "local").strip().lower() or "local"
    if mode not in VALID_AUTH_MODES:
        raise AuthConfigurationError(
            f"Invalid ELONE_AUTH_MODE '{mode}'. Must be one of: {', '.join(sorted(VALID_AUTH_MODES))}."
        )
    return mode


def get_jwt_secret() -> str:
    """Fail-closed JWT HMAC secret loader matching utils.security.get_playbook_signing_key().

    Requires ELONE_JWT_SECRET unless ELONE_ALLOW_INSECURE_DEV_KEY == '1' is set explicitly
    for local development or automated unit tests (uses an ephemeral per-process secret).
    """
    global _DEV_EPHEMERAL_SECRET, _DEV_WARNING_EMITTED
    secret = os.getenv("ELONE_JWT_SECRET")
    if secret and secret.strip():
        clean = secret.strip()
        if len(clean) < 16:
            raise AuthConfigurationError(
                "ELONE_JWT_SECRET must be at least 16 characters (32+ bytes recommended)."
            )
        return clean

    if os.getenv("ELONE_ALLOW_INSECURE_DEV_KEY") == "1":
        if _DEV_EPHEMERAL_SECRET is None:
            _DEV_EPHEMERAL_SECRET = secrets.token_urlsafe(48)
        if not _DEV_WARNING_EMITTED:
            _DEV_WARNING_EMITTED = True
            print(
                "[AUTH WARNING] ELONE_JWT_SECRET is unset; using ephemeral process secret "
                "(ELONE_ALLOW_INSECURE_DEV_KEY=1). Do not use in production.",
                file=sys.stderr,
            )
        return _DEV_EPHEMERAL_SECRET

    raise AuthConfigurationError(
        "Authentication configuration missing: 'ELONE_JWT_SECRET' environment variable must be set. "
        "For local testing only, set 'ELONE_ALLOW_INSECURE_DEV_KEY=1'."
    )


def reset_dev_ephemeral_secret_for_tests() -> None:
    """Testing helper only: resets cached ephemeral dev secret."""
    global _DEV_EPHEMERAL_SECRET, _DEV_WARNING_EMITTED
    _DEV_EPHEMERAL_SECRET = None
    _DEV_WARNING_EMITTED = False


def get_jwt_issuer() -> str:
    return os.getenv("ELONE_JWT_ISSUER", "elone-governance-hub").strip() or "elone-governance-hub"


def get_jwt_audience() -> str:
    return os.getenv("ELONE_JWT_AUDIENCE", "elone-api").strip() or "elone-api"


def get_token_ttl_seconds() -> int:
    raw = os.getenv("ELONE_TOKEN_TTL_MINUTES", "30").strip()
    try:
        mins = max(1, int(raw))
    except ValueError:
        mins = 30
    return mins * 60


def get_agent_token_ttl_seconds() -> int:
    raw = os.getenv("ELONE_AGENT_TOKEN_TTL_MINUTES", "480").strip()
    try:
        mins = max(1, int(raw))
    except ValueError:
        mins = 480
    return mins * 60


def get_default_tenant() -> str:
    return os.getenv("ELONE_DEFAULT_TENANT", "tn_northwind").strip() or "tn_northwind"


def is_cookie_secure() -> bool:
    return os.getenv("ELONE_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes"}


def parse_allowed_origins(raw_origins: Optional[str] = None) -> List[str]:
    """Parses ELONE_ALLOWED_ORIGINS and rejects wildcard '*' when credentials are enabled."""
    raw = os.getenv("ELONE_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS) if raw_origins is None else raw_origins
    origins: List[str] = []
    seen = set()
    for part in str(raw or "").split(","):
        cleaned = part.strip().rstrip("/")
        if not cleaned:
            continue
        if cleaned == "*":
            raise AuthConfigurationError(
                "CORS configuration error: ELONE_ALLOWED_ORIGINS cannot contain '*' while allow_credentials=True."
            )
        if cleaned not in seen:
            seen.add(cleaned)
            origins.append(cleaned)
    if not origins:
        raise AuthConfigurationError(
            "CORS configuration error: ELONE_ALLOWED_ORIGINS must specify at least one explicit origin."
        )
    return origins


def get_lockout_policy() -> Tuple[int, int]:
    """Returns (max_failures, window_seconds), defaulting to (5, 300)."""
    try:
        max_attempts = max(1, int(os.getenv("ELONE_LOGIN_MAX_ATTEMPTS", "5").strip()))
    except ValueError:
        max_attempts = 5
    try:
        window_seconds = max(10, int(os.getenv("ELONE_LOGIN_WINDOW_SECONDS", "300").strip()))
    except ValueError:
        window_seconds = 300
    return max_attempts, window_seconds


def get_auth_dir(kb_dir: Optional[str] = None) -> str:
    override = os.getenv("ELONE_AUTH_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    base = kb_dir or os.getenv("ELONE_KB_DIR", "").strip()
    if not base:
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_root = os.path.dirname(backend_dir)
        base = os.path.abspath(os.path.join(project_root, "knowledge_base"))
    return os.path.join(base, "_auth")


def get_users_path(kb_dir: Optional[str] = None) -> str:
    override = os.getenv("ELONE_USERS_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(get_auth_dir(kb_dir), "users.json")


def get_revoked_tokens_path(kb_dir: Optional[str] = None) -> str:
    override = os.getenv("ELONE_REVOKED_TOKENS_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(get_auth_dir(kb_dir), "revoked_tokens.json")


def get_auth_audit_log_path(kb_dir: Optional[str] = None) -> str:
    override = os.getenv("ELONE_AUTH_AUDIT_LOG_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(get_auth_dir(kb_dir), "auth_events.jsonl")


def get_oidc_settings() -> Dict[str, Optional[str]]:
    return {
        "jwks_url": os.getenv("ELONE_OIDC_JWKS_URL", "").strip() or None,
        "issuer": os.getenv("ELONE_OIDC_ISSUER", "").strip() or None,
        "audience": os.getenv("ELONE_OIDC_AUDIENCE", "").strip() or None,
        "identity_claim": os.getenv("ELONE_OIDC_IDENTITY_CLAIM", "email").strip() or "email",
        "roles_claim": os.getenv("ELONE_OIDC_ROLES_CLAIM", "roles").strip() or "roles",
        "tenant_claim": os.getenv("ELONE_OIDC_TENANT_CLAIM", "tenant_id").strip() or "tenant_id",
        "clearance_claim": os.getenv("ELONE_OIDC_CLEARANCE_CLAIM", "clearance").strip() or "clearance",
        "role_map_json": os.getenv("ELONE_OIDC_ROLE_MAP", "").strip() or None,
    }


__all__ = [
    "AuthConfigurationError",
    "DEFAULT_ALLOWED_ORIGINS",
    "VALID_AUTH_MODES",
    "get_auth_mode",
    "get_jwt_secret",
    "reset_dev_ephemeral_secret_for_tests",
    "get_jwt_issuer",
    "get_jwt_audience",
    "get_token_ttl_seconds",
    "get_agent_token_ttl_seconds",
    "get_default_tenant",
    "is_cookie_secure",
    "parse_allowed_origins",
    "get_lockout_policy",
    "get_auth_dir",
    "get_users_path",
    "get_revoked_tokens_path",
    "get_auth_audit_log_path",
    "get_oidc_settings",
]

