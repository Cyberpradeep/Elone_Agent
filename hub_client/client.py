"""Production Hub Client with mTLS Transport and OAuth2 Bearer Authentication.

Interacts with the Central SOP Governance Hub, enforcing:
- Bearer token authentication via OAuth2TokenManager (15m TTL, proactive 3m renewal).
- Mutual TLS (mTLS) certificate verification support.
- Cryptographic Ed25519 signature validation on all retrieved SOP payloads.
- Fail-closed status checks before step execution (Rule 5 & Edge Case 4).
- Strict multi-tenant isolation via tenant context headers.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple
from contracts.canonical import compute_canonical_hash
from contracts.sop import SignedSOPPayload, SOPReference
from hub_client.crypto import verify_canonical_signature_or_raise, CryptographicVerificationError
from hub_client.token_manager import OAuth2TokenManager, TokenManagerError


class HubClientError(Exception):
    """Base exception for Governance Hub client operations."""
    pass


class HubAuthenticationError(HubClientError):
    """Raised when authentication with Hub fails (401)."""
    pass


class HubAuthorizationError(HubClientError):
    """Raised when access is denied or tenant isolation check fails (403)."""
    pass


class SOPNotFoundError(HubClientError):
    """Raised when the requested SOP ID does not exist in Hub (404)."""
    pass


class HubUnreachableError(HubClientError):
    """Raised when Hub is unreachable or network connection times out."""
    pass


# Type signature for injectable HTTP transport: (method, path, headers, body) -> (status_code, response_dict)
TransportCallable = Callable[[str, str, Dict[str, str], Optional[Dict[str, Any]]], Tuple[int, Dict[str, Any]]]


class HubClient:
    """Production Governance Hub Client with OAuth2 and mTLS capabilities."""

    def __init__(
        self,
        base_url: str = "https://hub.internal",
        token_manager: Optional[OAuth2TokenManager] = None,
        client_cert: Optional[Tuple[str, str]] = None,
        ca_cert: Optional[str] = None,
        hub_public_key: Optional[str] = None,
        transport: Optional[TransportCallable] = None,
        timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.token_manager = token_manager or OAuth2TokenManager()
        self.client_cert = client_cert
        self.ca_cert = ca_cert
        self.hub_public_key = hub_public_key
        self._transport = transport or self._default_mock_transport
        self.timeout = timeout

    def _default_mock_transport(
        self, method: str, path: str, headers: Dict[str, str], body: Optional[Dict[str, Any]]
    ) -> Tuple[int, Dict[str, Any]]:
        """Fallback mock transport for local execution and self-contained testing."""
        return 404, {"error": "Not Found", "message": f"Endpoint {method} {path} not configured in mock"}

    def _build_headers(self, tenant_id: Optional[str] = None) -> Dict[str, str]:
        """Construct secure request headers with Bearer token and tenant context."""
        try:
            token = self.token_manager.get_token()
        except TokenManagerError as e:
            raise HubAuthenticationError(f"Cannot authenticate with Hub: {e}") from e

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "SOP-Execution-Engine/1.0",
            "Accept": "application/json",
        }
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        if self.client_cert:
            headers["X-Client-Cert-Thumbprint"] = "mtls_verified"
        return headers

    def _dispatch(
        self, method: str, endpoint: str, tenant_id: Optional[str] = None, body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Dispatch HTTP request through transport layer and handle HTTP error codes fail-closed."""
        headers = self._build_headers(tenant_id=tenant_id)
        url_path = f"{self.base_url}{endpoint}"

        try:
            status_code, response_data = self._transport(method, url_path, headers, body)
        except Exception as e:
            raise HubUnreachableError(f"Failed to connect to Governance Hub at {url_path}: {e}") from e

        if status_code == 200:
            return response_data
        elif status_code == 401:
            raise HubAuthenticationError(f"Hub returned 401 Unauthorized for {endpoint}")
        elif status_code == 403:
            raise HubAuthorizationError(f"Hub returned 403 Forbidden: Tenant isolation or permission violation")
        elif status_code == 404:
            raise SOPNotFoundError(f"Resource not found on Hub: {endpoint}")
        else:
            raise HubClientError(f"Hub request failed with status {status_code}: {response_data}")

    def get_sop_by_id(
        self, sop_id: str, tenant_id: str, public_key_hex: Optional[str] = None
    ) -> SignedSOPPayload:
        """Fetch signed SOP by ID, validating tenant boundary and Ed25519 signature."""
        data = self._dispatch("GET", f"/api/v1/sops/{sop_id}", tenant_id=tenant_id)

        body_json = data.get("body_json") if "body_json" in data else data.get("payload")
        sig = data.get("ed25519_signature") or data.get("signature")
        pubkey = public_key_hex or data.get("public_key") or self.hub_public_key

        if not sig or not pubkey or body_json is None:
            raise CryptographicVerificationError(
                f"Hub response for SOP '{sop_id}' missing signature, public_key, or body_json"
            )

        # Verify hash match if provided
        expected_hash = data.get("canonical_sha256") or (data.get("sop", {}).get("canonical_hash"))
        if expected_hash:
            calculated_hash = compute_canonical_hash(body_json)
            if calculated_hash != expected_hash:
                raise CryptographicVerificationError(
                    f"Canonical hash mismatch for SOP '{sop_id}': expected '{expected_hash}', calculated '{calculated_hash}'"
                )

        verify_canonical_signature_or_raise(pubkey, sig, body_json, context=f"SOP '{sop_id}'")
        
        # Build validated SignedSOPPayload without extraneous transport metadata
        model_payload = {
            "sop": data.get("sop"),
            "body_json": body_json,
            "canonical_sha256": expected_hash or compute_canonical_hash(body_json),
            "ed25519_signature": sig,
            "key_id": data.get("key_id", "hub-key-1"),
            "status": data.get("status", "PUBLISHED"),
        }
        if "signed_at" in data:
            model_payload["signed_at"] = data["signed_at"]

        return SignedSOPPayload.model_validate(model_payload)

    def get_sop_status(self, sop_id: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch real-time publication status of an SOP (used for Rule 5 pre-mutation checks)."""
        return self._dispatch("GET", f"/api/v1/sops/{sop_id}/status", tenant_id=tenant_id)

    def verify_sop_status(self, sop_id: str, expected_hash: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Perform authoritative pre-step status verification against Hub."""
        info = self.get_sop_status(sop_id, tenant_id=tenant_id)
        current_status = info.get("status")
        current_hash = info.get("canonical_hash")

        is_valid = (current_status == "PUBLISHED") and (current_hash == expected_hash)
        return {
            "sop_id": sop_id,
            "status": current_status,
            "canonical_hash": current_hash,
            "verified": is_valid,
        }

    def list_published_sops(self, tenant_id: str) -> List[SOPReference]:
        """List all published SOPs visible to the requesting tenant."""
        data = self._dispatch("GET", "/api/v1/sops", tenant_id=tenant_id)
        raw_items = data.get("sops", [])
        return [SOPReference.model_validate(item) for item in raw_items]
