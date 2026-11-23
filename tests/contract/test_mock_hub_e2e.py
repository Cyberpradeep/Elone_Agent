"""End-to-End Tests for Mock Hub Service, Cryptographic Pipeline & Fault Drills."""

import pytest
from contracts.canonical import compute_canonical_hash
from contracts.sop import SOPStatusEnum
from hub_client.crypto import (
    verify_canonical_signature,
    verify_canonical_signature_or_raise,
    CryptographicVerificationError,
)
from hub_client.mock_hub import (
    MockHubService,
    HubConnectionError,
)


def test_mock_hub_e2e_signature_and_hash_verification():
    """Verify that Mock Hub delivers valid signed pilot SOPs that pass local verification."""
    hub = MockHubService()

    # 1. Fetch public keys
    keys_resp = hub.get_signing_keys()
    assert len(keys_resp["keys"]) >= 1
    hub_pub_key = keys_resp["keys"][0]["public_key_hex"]

    # 2. Fetch published Print Spooler SOP (SOP-WIN-014)
    sop_payload = hub.get_sop_version("SOP-WIN-014", "1.0.0")
    assert sop_payload.status == SOPStatusEnum.PUBLISHED
    assert sop_payload.sop.sop_id == "SOP-WIN-014"

    # 3. Verify canonical SHA-256 hash locally
    computed_local_hash = compute_canonical_hash(sop_payload.body_json)
    assert computed_local_hash == sop_payload.canonical_sha256
    assert computed_local_hash == sop_payload.sop.canonical_hash

    # 4. Verify Ed25519 signature locally using Hub public key
    assert verify_canonical_signature(
        hub_pub_key,
        sop_payload.ed25519_signature,
        sop_payload.body_json,
    ) is True
    verify_canonical_signature_or_raise(
        hub_pub_key,
        sop_payload.ed25519_signature,
        sop_payload.body_json,
    )


def test_mock_hub_outage_drill_fails_closed():
    """Verify that when the Hub goes down, requests raise HubConnectionError (fail-closed)."""
    hub = MockHubService()
    hub.set_outage(True)

    with pytest.raises(HubConnectionError, match="unreachable"):
        hub.get_signing_keys()

    with pytest.raises(HubConnectionError, match="unreachable"):
        hub.list_sops()

    with pytest.raises(HubConnectionError, match="unreachable"):
        hub.get_sop_version("SOP-WIN-014", "1.0.0")


def test_mock_hub_tamper_drill_fails_verification():
    """Verify that tampered signatures from the Hub are rejected locally."""
    hub = MockHubService()
    keys_resp = hub.get_signing_keys()
    hub_pub_key = keys_resp["keys"][0]["public_key_hex"]

    # Enable tamper mode (corrupts signature)
    hub.set_tamper_signature(True)
    sop_payload = hub.get_sop_version("SOP-WIN-014", "1.0.0")

    assert verify_canonical_signature(
        hub_pub_key,
        sop_payload.ed25519_signature,
        sop_payload.body_json,
    ) is False
    with pytest.raises(CryptographicVerificationError):
        verify_canonical_signature_or_raise(
            hub_pub_key,
            sop_payload.ed25519_signature,
            sop_payload.body_json,
        )


def test_mock_hub_deactivation_drill():
    """Verify that deactivating an SOP reflects in status checks before state changes."""
    hub = MockHubService()

    # Pre-check: active
    status_before = hub.get_sop_status("SOP-WIN-014")
    assert status_before["status"] == "PUBLISHED"

    # Simulate revocation webhook / Hub deactivation
    hub.deactivate_sop("SOP-WIN-014")

    # Post-check: deactivated
    status_after = hub.get_sop_status("SOP-WIN-014")
    assert status_after["status"] == "DEACTIVATED"
