"""OAuth2 Token Manager with Proactive Refresh Lifecycle.

Manages 15-minute OAuth2 bearer tokens for Hub communications, enforcing:
- Proactive token refresh when remaining TTL <= 180s (3 minutes).
- Fail-closed behavior on refresh or network failure.
- Thread-safe concurrency with double-checked locking.
"""

import time
import threading
from typing import Any, Callable, Dict, Optional


class TokenManagerError(Exception):
    """Base exception for OAuth2 token operations."""
    pass


class TokenRefreshError(TokenManagerError):
    """Raised when token refresh fails or token endpoint returns an error."""
    pass


class TokenExpiredError(TokenManagerError):
    """Raised when token has expired and cannot be refreshed."""
    pass


class OAuth2TokenManager:
    """Manages OAuth2 access token caching and proactive lifecycle renewal."""

    def __init__(
        self,
        token_url: str = "https://hub.internal/oauth/token",
        client_id: str = "sop-execution-engine",
        client_secret: str = "secret-engine-token",
        token_ttl_seconds: int = 900,  # 15 minutes default
        refresh_threshold_seconds: int = 180,  # 3 minutes lead time
        token_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_ttl_seconds = token_ttl_seconds
        self.refresh_threshold_seconds = refresh_threshold_seconds
        self._token_provider = token_provider or self._default_mock_provider

        self._cached_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()
        self.refresh_count: int = 0

    def _default_mock_provider(self) -> Dict[str, Any]:
        """Default token provider simulating standard OAuth2 client credentials grant."""
        return {
            "access_token": f"hub_bearer_{int(time.time())}_{self.client_id}",
            "token_type": "Bearer",
            "expires_in": self.token_ttl_seconds,
        }

    def is_token_expiring(self, lead_time_seconds: Optional[int] = None) -> bool:
        """Return True if token is missing, expired, or expiring within lead_time_seconds."""
        threshold = lead_time_seconds if lead_time_seconds is not None else self.refresh_threshold_seconds
        if not self._cached_token:
            return True
        remaining = self._expires_at - time.time()
        return remaining <= threshold

    def is_token_expired(self) -> bool:
        """Return True if token has strictly expired."""
        return not self._cached_token or time.time() >= self._expires_at

    def get_token(self, force_refresh: bool = False) -> str:
        """Retrieve a valid bearer token, proactively refreshing if near expiration.

        Thread-safe using double-checked locking.
        """
        if not force_refresh and not self.is_token_expiring():
            return self._cached_token  # type: ignore

        with self._lock:
            # Double-check inside lock
            if not force_refresh and not self.is_token_expiring():
                return self._cached_token  # type: ignore

            try:
                payload = self._token_provider()
                token = payload.get("access_token")
                expires_in = payload.get("expires_in", self.token_ttl_seconds)

                if not token:
                    raise TokenRefreshError("OAuth2 provider returned empty or missing access_token")

                self._cached_token = token
                self._expires_at = time.time() + float(expires_in)
                self.refresh_count += 1
                return self._cached_token
            except Exception as e:
                # If cached token is already expired, fail closed immediately
                if self.is_token_expired():
                    self._cached_token = None
                    raise TokenRefreshError(f"OAuth2 token refresh failed and no valid cached token exists: {e}") from e
                # If current token is still valid (in threshold window), re-raise to notify caller
                raise TokenRefreshError(f"Proactive OAuth2 token refresh failed: {e}") from e

    def invalidate(self) -> None:
        """Clear cached token and force renewal on next retrieval."""
        with self._lock:
            self._cached_token = None
            self._expires_at = 0.0

    @property
    def remaining_lifetime(self) -> float:
        """Remaining token lifetime in seconds, or 0.0 if expired."""
        if not self._cached_token:
            return 0.0
        return max(0.0, self._expires_at - time.time())
