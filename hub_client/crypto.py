"""Ed25519 Asymmetric Cryptographic Signing & Verification Engine.

Replaces shared-secret HMAC with asymmetric public-key cryptography.
The Governance Hub holds the private key to sign published procedures;
the Execution Engine holds only the public key to verify integrity.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature
from contracts.canonical import to_canonical_json


class CryptographicVerificationError(Exception):
    """Raised when signature verification or cryptographic checks fail."""

    pass


def generate_ed25519_keypair() -> Tuple[str, str]:
    """Generates a new Ed25519 keypair.

    Returns (private_key_hex, public_key_hex).
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    return priv_bytes.hex(), pub_bytes.hex()


def sign_canonical_payload(private_key_hex: str, data: Any) -> str:
    """Signs the canonical JSON serialization of data using an Ed25519 private key.

    Returns the signature formatted as a lowercase hex string.
    """
    private_key_bytes = bytes.fromhex(private_key_hex)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)

    canonical_bytes = to_canonical_json(data).encode("utf-8")
    signature = private_key.sign(canonical_bytes)
    return signature.hex()


def verify_canonical_signature(public_key_hex: str, signature_hex: str, data: Any) -> bool:
    """Verifies that signature_hex was created by the holder of public_key_hex for data.

    Returns True if valid, False if signature or formatting is invalid.
    """
    try:
        public_key_bytes = bytes.fromhex(public_key_hex)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        signature_bytes = bytes.fromhex(signature_hex)
        canonical_bytes = to_canonical_json(data).encode("utf-8")

        public_key.verify(signature_bytes, canonical_bytes)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def verify_canonical_signature_or_raise(
    public_key_hex: str,
    signature_hex: str,
    data: Any,
    context: str = "SOP Payload",
) -> None:
    """Verifies canonical signature and raises CryptographicVerificationError if invalid."""
    if not verify_canonical_signature(public_key_hex, signature_hex, data):
        raise CryptographicVerificationError(
            f"INVALID_SIGNATURE: Cryptographic verification failed for {context}. "
            f"The payload has been tampered with or was signed by an unauthorized key."
        )
