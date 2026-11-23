"""Governance Hub Client and Cryptography Infrastructure.

Provides Ed25519 cryptographic signing and verification utilities,
OAuth2 token lifecycle management, the production HubClient, and
the offline MockHubService for local development and failure drills.
"""

from hub_client.crypto import (
    generate_ed25519_keypair,
    sign_canonical_payload,
    verify_canonical_signature,
    verify_canonical_signature_or_raise,
    CryptographicVerificationError,
)
from hub_client.token_manager import (
    OAuth2TokenManager,
    TokenManagerError,
    TokenRefreshError,
    TokenExpiredError,
)
from hub_client.client import (
    HubClient,
    HubClientError,
    HubAuthenticationError,
    HubAuthorizationError,
    SOPNotFoundError,
    HubUnreachableError,
)
from hub_client.mock_hub import (
    MockHubService,
    HubConnectionError,
)

__all__ = [
    "generate_ed25519_keypair",
    "sign_canonical_payload",
    "verify_canonical_signature",
    "verify_canonical_signature_or_raise",
    "CryptographicVerificationError",
    "OAuth2TokenManager",
    "TokenManagerError",
    "TokenRefreshError",
    "TokenExpiredError",
    "HubClient",
    "HubClientError",
    "HubAuthenticationError",
    "HubAuthorizationError",
    "SOPNotFoundError",
    "HubUnreachableError",
    "MockHubService",
    "HubConnectionError",
]
