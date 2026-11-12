"""
Elone Authentication & Authorization Package (C2)
=================================================
Exports public models, config helpers, token handlers, and user store singletons.
"""

from .config import (
    AuthConfigurationError,
    get_auth_mode,
    get_jwt_secret,
    get_default_tenant,
    is_cookie_secure,
    parse_allowed_origins,
)
from .models import (
    ROLE_PROCESS_OWNER,
    ROLE_SECURITY_REVIEWER,
    ROLE_ADMIN,
    ROLE_AGENT,
    HUMAN_ROLES,
    ROLE_SET,
    AuthPrincipal,
    UserRecord,
    compute_capabilities,
    validate_roles,
    validate_tenant_id,
    validate_clearance,
)
from .passwords import hash_password, verify_password
from .tokens import (
    TokenValidationError,
    revocation_store,
    create_access_token,
    decode_local_token,
    decode_oidc_token,
    decode_access_token,
)
from .user_store import (
    AccountExistsError,
    AccountNotFoundError,
    AuthenticationFailedError,
    RateLimitExceededError,
    login_rate_limiter,
    user_store,
)
from .dependencies import (
    AuthAccessError,
    bearer_scheme,
    authenticate_request,
    get_current_principal,
    require_roles,
    require_human,
    csrf_protect,
    enforce_tenant_access,
    enforce_clearance_access,
    enforce_review_task_eligibility,
    log_auth_event,
)

__all__ = [
    "AuthConfigurationError",
    "get_auth_mode",
    "get_jwt_secret",
    "get_default_tenant",
    "is_cookie_secure",
    "parse_allowed_origins",
    "ROLE_PROCESS_OWNER",
    "ROLE_SECURITY_REVIEWER",
    "ROLE_ADMIN",
    "ROLE_AGENT",
    "HUMAN_ROLES",
    "ROLE_SET",
    "AuthPrincipal",
    "UserRecord",
    "compute_capabilities",
    "validate_roles",
    "validate_tenant_id",
    "validate_clearance",
    "hash_password",
    "verify_password",
    "TokenValidationError",
    "revocation_store",
    "create_access_token",
    "decode_local_token",
    "decode_oidc_token",
    "decode_access_token",
    "AccountExistsError",
    "AccountNotFoundError",
    "AuthenticationFailedError",
    "RateLimitExceededError",
    "login_rate_limiter",
    "user_store",
]
