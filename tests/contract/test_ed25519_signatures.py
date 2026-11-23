"""Tests for Asymmetric Ed25519 Cryptographic Signing and Verification."""

import pytest
from hub_client.crypto import (
    generate_ed25519_keypair,
    sign_canonical_payload,
    verify_canonical_signature,
    verify_canonical_signature_or_raise,
    CryptographicVerificationError,
)


def test_ed25519_keypair_generation():
    """Verify clean generation of 64-char hex Ed25519 raw keys."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    assert len(priv_hex) == 64
    assert len(pub_hex) == 64
    assert priv_hex != pub_hex


def test_sign_and_verify_valid_canonical_payload():
    """Verify that a signed canonical dictionary passes verification."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    sop_data = {
        "sop_id": "SOP-WIN-014",
        "title": "Print Spooler Recovery",
        "steps": [{"step": 1, "action": "restart_service"}],
    }

    sig_hex = sign_canonical_payload(priv_hex, sop_data)
    assert len(sig_hex) == 128  # 64-byte Ed25519 signature in hex

    # Verification must succeed
    assert verify_canonical_signature(pub_hex, sig_hex, sop_data) is True
    # Or-raise variant must not raise
    verify_canonical_signature_or_raise(pub_hex, sig_hex, sop_data)


def test_tampered_payload_fails_signature_verification():
    """Verify that any modification to payload data causes verification to fail closed."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    sop_data = {"sop_id": "SOP-WIN-014", "command": "Restart-Service Spooler"}

    sig_hex = sign_canonical_payload(priv_hex, sop_data)

    # Tamper with the payload
    tampered_data = {"sop_id": "SOP-WIN-014", "command": "Restart-Service Malicious"}

    assert verify_canonical_signature(pub_hex, sig_hex, tampered_data) is False
    with pytest.raises(CryptographicVerificationError, match="INVALID_SIGNATURE"):
        verify_canonical_signature_or_raise(pub_hex, sig_hex, tampered_data)


def test_unauthorized_key_fails_verification():
    """Verify that a signature verified against a different public key fails."""
    priv_hex1, _ = generate_ed25519_keypair()
    _, pub_hex2 = generate_ed25519_keypair()

    data = {"sop_id": "SOP-NET-006"}
    sig_hex = sign_canonical_payload(priv_hex1, data)

    # Verify using key 2 (not the signer)
    assert verify_canonical_signature(pub_hex2, sig_hex, data) is False
    with pytest.raises(CryptographicVerificationError):
        verify_canonical_signature_or_raise(pub_hex2, sig_hex, data)
