"""Governance Hub Client and Cryptography Infrastructure.

Provides Ed25519 cryptographic signing and verification utilities,
and the offline MockHubService for local development and failure drills.
"""

from hub_client.crypto import (
    generate_ed25519_keypair,
    sign_canonical_payload,
    verify_canonical_signature,
    verify_canonical_signature_or_raise,
    CryptographicVerificationError,
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
    "MockHubService",
    "HubConnectionError",
]
