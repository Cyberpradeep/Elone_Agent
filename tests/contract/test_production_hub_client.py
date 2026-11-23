"""Tests for Production Hub Client and OAuth2 Token Lifecycle.

Verifies:
- 15-minute OAuth2 token lifecycle with proactive refresh (lead time <= 180s).
- Thread-safe token acquisition.
- Fail-closed behavior on refresh failure or Hub unavailability.
- Mutual TLS and Bearer authentication header creation.
- Ed25519 canonical signature validation on retrieved SOPs.
- Pre-step mutation guard status re-checking (Rule 5 & Edge Case 4).
- Tenant isolation and 403 forbidden rejection.
"""

import time
import threading
from datetime import datetime
import pytest

from contracts.canonical import compute_canonical_hash
from contracts.sop import SOPClassificationEnum, SOPReference, SOPStatusEnum
from hub_client.crypto import (
    generate_ed25519_keypair,
    sign_canonical_payload,
    CryptographicVerificationError,
)
from hub_client.token_manager import (
    OAuth2TokenManager,
    TokenRefreshError,
)
from hub_client.client import (
    HubClient,
    HubAuthenticationError,
    HubAuthorizationError,
    HubClientError,
    HubUnreachableError,
    SOPNotFoundError,
)
from orchestrator.pre_step_guard import verify_pre_step_guard


# --- OAuth2TokenManager Tests ---

def test_oauth2_token_caching_and_reuse():
    """Verify that valid tokens are cached and not repeatedly re-requested."""
    call_count = 0

    def mock_provider():
        nonlocal call_count
        call_count += 1
        return {"access_token": f"token_{call_count}", "expires_in": 900}

    manager = OAuth2TokenManager(token_provider=mock_provider)
    assert manager.is_token_expiring() is True

    t1 = manager.get_token()
    assert t1 == "token_1"
    assert call_count == 1
    assert manager.is_token_expiring() is False

    # Second call must reuse cached token
    t2 = manager.get_token()
    assert t2 == "token_1"
    assert call_count == 1


def test_oauth2_proactive_refresh_threshold():
    """Verify that remaining TTL <= 180s triggers proactive token refresh."""
    call_count = 0

    def mock_provider():
        nonlocal call_count
        call_count += 1
        # First token has only 100 seconds of lifetime left (within 180s threshold)
        expires_in = 100 if call_count == 1 else 900
        return {"access_token": f"token_{call_count}", "expires_in": expires_in}

    manager = OAuth2TokenManager(refresh_threshold_seconds=180, token_provider=mock_provider)
    t1 = manager.get_token()
    assert t1 == "token_1"
    assert call_count == 1

    # Remaining lifetime is <= 180s, so next get_token() must proactively refresh
    assert manager.is_token_expiring() is True
    t2 = manager.get_token()
    assert t2 == "token_2"
    assert call_count == 2
    assert manager.is_token_expiring() is False


def test_oauth2_force_refresh_and_invalidate():
    """Verify force_refresh and invalidate bypass cache."""
    call_count = 0

    def mock_provider():
        nonlocal call_count
        call_count += 1
        return {"access_token": f"token_{call_count}", "expires_in": 900}

    manager = OAuth2TokenManager(token_provider=mock_provider)
    manager.get_token()
    assert call_count == 1

    # Force refresh
    t_forced = manager.get_token(force_refresh=True)
    assert t_forced == "token_2"
    assert call_count == 2

    # Invalidate cache
    manager.invalidate()
    assert manager.remaining_lifetime == 0.0
    t_after_invalid = manager.get_token()
    assert t_after_invalid == "token_3"
    assert call_count == 3


def test_oauth2_refresh_failure_fails_closed():
    """Verify that token provider errors fail closed and raise TokenRefreshError."""
    def failing_provider():
        raise ConnectionResetError("OAuth2 auth server connection dropped")

    manager = OAuth2TokenManager(token_provider=failing_provider)
    with pytest.raises(TokenRefreshError, match="OAuth2 token refresh failed"):
        manager.get_token()


def test_oauth2_concurrent_thread_safety():
    """Verify that multiple threads requesting tokens safely share one refresh."""
    call_count = 0
    lock = threading.Lock()

    def slow_provider():
        nonlocal call_count
        with lock:
            call_count += 1
        time.sleep(0.05)
        return {"access_token": "concurrent_shared_token", "expires_in": 900}

    manager = OAuth2TokenManager(token_provider=slow_provider)
    results = []

    def worker():
        token = manager.get_token()
        results.append(token)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 8
    assert all(r == "concurrent_shared_token" for r in results)
    assert call_count == 1  # Only one refresh operation executed


# --- HubClient Contract Tests ---

@pytest.fixture
def test_hub_keys():
    """Generate Ed25519 keypair for Hub fixtures."""
    priv, pub = generate_ed25519_keypair()
    return priv, pub


def test_hub_client_get_sop_by_id_success(test_hub_keys):
    """Verify HubClient retrieves and cryptographically validates a signed SOP."""
    priv_hex, pub_hex = test_hub_keys
    sop_body = {
        "sop_id": "SOP-WIN-014",
        "version": "1.0.0",
        "title": "Print Spooler Recovery",
        "steps": [{"step": 1, "tool": "winrm_jea", "op": "restart_service"}],
    }
    canonical_hash = compute_canonical_hash(sop_body)
    sig_hex = sign_canonical_payload(priv_hex, sop_body)

    sop_ref_data = {
        "sop_id": "SOP-WIN-014",
        "version": "1.0.0",
        "canonical_hash": canonical_hash,
        "title": "Print Spooler Recovery",
        "classification": "INTERNAL",
        "tenant_id": "tenant-northwind",
    }

    mock_response = {
        "sop": sop_ref_data,
        "body_json": sop_body,
        "canonical_sha256": canonical_hash,
        "ed25519_signature": sig_hex,
        "key_id": "hub-key-1",
        "status": "PUBLISHED",
        "signed_at": datetime.utcnow().isoformat(),
        "public_key": pub_hex,
    }

    captured_headers = {}

    def mock_transport(method, url, headers, body):
        nonlocal captured_headers
        captured_headers = headers
        if "/api/v1/sops/SOP-WIN-014" in url:
            return 200, mock_response
        return 404, {"error": "Not Found"}

    client = HubClient(
        client_cert=("client.crt", "client.key"),
        hub_public_key=pub_hex,
        transport=mock_transport,
    )

    payload = client.get_sop_by_id("SOP-WIN-014", tenant_id="tenant-northwind")
    assert payload.sop.sop_id == "SOP-WIN-014"
    assert payload.canonical_sha256 == canonical_hash
    assert payload.ed25519_signature == sig_hex

    # Verify security headers
    assert "Bearer" in captured_headers["Authorization"]
    assert captured_headers["X-Tenant-ID"] == "tenant-northwind"
    assert captured_headers["X-Client-Cert-Thumbprint"] == "mtls_verified"


def test_hub_client_tampered_sop_raises_verification_error(test_hub_keys):
    """Verify that tampering with SOP body causes verification to fail closed."""
    priv_hex, pub_hex = test_hub_keys
    sop_body = {"sop_id": "SOP-WIN-014", "action": "legitimate_restart"}
    sig_hex = sign_canonical_payload(priv_hex, sop_body)
    canonical_hash = compute_canonical_hash(sop_body)

    # Tampered body returned by compromised or MITM Hub
    tampered_body = {"sop_id": "SOP-WIN-014", "action": "malicious_command"}

    mock_response = {
        "sop": {
            "sop_id": "SOP-WIN-014",
            "version": "1.0.0",
            "canonical_hash": canonical_hash,
            "title": "Print Spooler Recovery",
            "classification": "INTERNAL",
            "tenant_id": "tenant-northwind",
        },
        "body_json": tampered_body,
        "canonical_sha256": canonical_hash,
        "ed25519_signature": sig_hex,
        "key_id": "hub-key-1",
        "status": "PUBLISHED",
        "signed_at": datetime.utcnow().isoformat(),
        "public_key": pub_hex,
    }

    def mock_transport(method, url, headers, body):
        return 200, mock_response

    client = HubClient(hub_public_key=pub_hex, transport=mock_transport)

    with pytest.raises(CryptographicVerificationError, match="Canonical hash mismatch|INVALID_SIGNATURE"):
        client.get_sop_by_id("SOP-WIN-014", tenant_id="tenant-northwind")


def test_hub_client_status_recheck_and_pre_step_guard():
    """Verify Hub status re-check integration with orchestrator pre_step_guard (Rule 5 & Edge Case 4)."""
    expected_hash = "a" * 64

    def mock_transport(method, url, headers, body):
        if "/api/v1/sops/SOP-WIN-014/status" in url:
            return 200, {
                "sop_id": "SOP-WIN-014",
                "canonical_hash": expected_hash,
                "status": "PUBLISHED",
            }
        return 404, {}

    client = HubClient(transport=mock_transport)

    # 1. Authoritative client verify_sop_status
    status_info = client.verify_sop_status("SOP-WIN-014", expected_hash=expected_hash)
    assert status_info["verified"] is True
    assert status_info["status"] == "PUBLISHED"

    # 2. Seamless integration with verify_pre_step_guard
    guard_res = verify_pre_step_guard("SOP-WIN-014", expected_canonical_hash=expected_hash, hub_service=client)
    assert guard_res.passed is True


def test_hub_client_deactivated_sop_fails_guard():
    """Verify that an SOP marked DEACTIVATED on Hub fails pre-step guard."""
    def mock_transport(method, url, headers, body):
        return 200, {
            "sop_id": "SOP-WIN-014",
            "canonical_hash": "a" * 64,
            "status": "DEACTIVATED",
        }

    client = HubClient(transport=mock_transport)
    guard_res = verify_pre_step_guard("SOP-WIN-014", expected_canonical_hash="a" * 64, hub_service=client)
    assert guard_res.passed is False
    assert "DEACTIVATED" in guard_res.reason


def test_hub_client_tenant_isolation_forbidden_403():
    """Verify cross-tenant access returns 403 and raises HubAuthorizationError."""
    def mock_transport(method, url, headers, body):
        if headers.get("X-Tenant-ID") != "tenant-correct":
            return 403, {"error": "Cross-tenant access forbidden"}
        return 200, {}

    client = HubClient(transport=mock_transport)
    with pytest.raises(HubAuthorizationError, match="403 Forbidden"):
        client.get_sop_status("SOP-WIN-014", tenant_id="tenant-wrong")


def test_hub_client_unreachable_fail_closed():
    """Verify connection timeout/failure raises HubUnreachableError."""
    def failing_transport(method, url, headers, body):
        raise TimeoutError("Connection to Hub timed out after 10000ms")

    client = HubClient(transport=failing_transport)
    with pytest.raises(HubUnreachableError, match="Failed to connect to Governance Hub"):
        client.get_sop_status("SOP-WIN-014")
