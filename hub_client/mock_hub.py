"""Standalone Offline Mock Governance Hub Service.

Simulates the versioned read-only /api/v1/exec endpoints of Elone_Agent.
Serves cryptographically signed synthetic pilot SOPs with fault injection controls
for testing fail-closed behavior, signature validation, and outage handling.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from contracts.canonical import compute_canonical_hash
from contracts.sop import (
    SOPClassificationEnum,
    SOPReference,
    SOPStatusEnum,
    SignedSOPPayload,
)
from hub_client.crypto import (
    generate_ed25519_keypair,
    sign_canonical_payload,
)


class HubConnectionError(Exception):
    """Raised when the Governance Hub is unreachable."""

    pass


class MockHubService:
    """In-memory Governance Hub test double serving signed pilot SOPs."""

    def __init__(self, key_id: str = "hub-key-2026-v1"):
        self.key_id = key_id
        self._private_key_hex, self._public_key_hex = generate_ed25519_keypair()
        self._outage_mode: bool = False
        self._tamper_mode: bool = False
        self._sops: Dict[str, Dict[str, Any]] = {}
        self._init_pilot_sops()

    def _init_pilot_sops(self) -> None:
        """Seed the mock hub with the 4 pilot synthetic SOPs."""
        # 1. Print Spooler (SOP-WIN-014) - SUCCESS path
        self._register_sop(
            sop_id="SOP-WIN-014",
            version="1.0.0",
            title="Print Spooler Service Recovery Procedure",
            classification=SOPClassificationEnum.INTERNAL,
            tenant_id="tenant-northwind",
            steps=[
                {"step": 1, "title": "Query Spooler Status", "tool": "winrm_jea", "op": "get_service", "params": {"name": "Spooler"}},
                {"step": 2, "title": "Restart Spooler", "tool": "winrm_jea", "op": "restart_service", "params": {"name": "Spooler"}},
            ],
        )

        # 2. DNS Resolution Issue (SOP-NET-006) - SUCCESS path
        self._register_sop(
            sop_id="SOP-NET-006",
            version="1.0.0",
            title="DNS Resolution Remediation Procedure",
            classification=SOPClassificationEnum.INTERNAL,
            tenant_id="tenant-northwind",
            steps=[
                {"step": 1, "title": "Check Resolution", "tool": "winrm_jea", "op": "nslookup", "params": {"target": "gateway.local"}},
                {"step": 2, "title": "Flush DNS Cache", "tool": "winrm_jea", "op": "flush_dns", "params": {}},
            ],
        )

        # 3. SQL Server Down (SOP-DB-021) - NEEDS HUMAN INTERVENTION
        self._register_sop(
            sop_id="SOP-DB-021",
            version="1.0.0",
            title="SQL Production Database Recovery",
            classification=SOPClassificationEnum.RESTRICTED,
            tenant_id="tenant-northwind",
            steps=[
                {"step": 1, "title": "Check DB Status", "tool": "monitoring", "op": "check_sql", "params": {"instance": "PROD-SQL-01"}},
                {"step": 2, "title": "Restart DB Service", "tool": "winrm_jea", "op": "restart_service", "params": {"name": "MSSQLSERVER"}},
            ],
        )

        # 4. Backup Failed (SOP-BKP-003) - FAILED / RETRY EXHAUSTION
        self._register_sop(
            sop_id="SOP-BKP-003",
            version="1.0.0",
            title="Nightly Backup Job Recovery",
            classification=SOPClassificationEnum.CONFIDENTIAL,
            tenant_id="tenant-northwind",
            steps=[
                {"step": 1, "title": "Check Backup Agent", "tool": "backup_api", "op": "agent_health", "params": {}},
                {"step": 2, "title": "Trigger Backup Job", "tool": "backup_api", "op": "run_backup", "params": {"policy": "FullDaily"}},
            ],
        )

    def _register_sop(
        self,
        sop_id: str,
        version: str,
        title: str,
        classification: SOPClassificationEnum,
        tenant_id: str,
        steps: List[Dict[str, Any]],
    ) -> None:
        body_json = {"sop_id": sop_id, "version": version, "title": title, "steps": steps}
        canonical_sha256 = compute_canonical_hash(body_json)
        sig = sign_canonical_payload(self._private_key_hex, body_json)

        sop_ref = SOPReference(
            sop_id=sop_id,
            version=version,
            canonical_hash=canonical_sha256,
            title=title,
            classification=classification,
            tenant_id=tenant_id,
        )

        self._sops[sop_id] = {
            "ref": sop_ref,
            "body_json": body_json,
            "canonical_sha256": canonical_sha256,
            "signature": sig,
            "status": SOPStatusEnum.PUBLISHED,
        }

    # --- Fault Injection Controls ---

    def set_outage(self, active: bool) -> None:
        """Simulate complete Governance Hub network downtime."""
        self._outage_mode = active

    def set_tamper_signature(self, active: bool) -> None:
        """Simulate signature tampering or cryptographic corruption."""
        self._tamper_mode = active

    def deactivate_sop(self, sop_id: str) -> None:
        """Simulate dynamic SOP deactivation."""
        if sop_id in self._sops:
            self._sops[sop_id]["status"] = SOPStatusEnum.DEACTIVATED

    # --- Public API Endpoints (/api/v1/exec) ---

    def get_signing_keys(self) -> Dict[str, Any]:
        """GET /api/v1/exec/signing-keys"""
        if self._outage_mode:
            raise HubConnectionError("Hub service unreachable (HTTP 503)")
        return {
            "keys": [
                {
                    "key_id": self.key_id,
                    "algorithm": "Ed25519",
                    "public_key_hex": self._public_key_hex,
                    "valid_from": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                    "valid_until": (datetime.utcnow() + timedelta(days=365)).isoformat(),
                }
            ]
        }

    def list_sops(self, status: str = "published", tenant_id: str = "tenant-northwind") -> List[Dict[str, Any]]:
        """GET /api/v1/exec/sops?status=published"""
        if self._outage_mode:
            raise HubConnectionError("Hub service unreachable (HTTP 503)")
        results = []
        for sop_id, item in self._sops.items():
            if item["ref"].tenant_id == tenant_id and item["status"].value.lower() == status.lower():
                ref = item["ref"]
                results.append({
                    "sop_id": ref.sop_id,
                    "version": ref.version,
                    "title": ref.title,
                    "classification": ref.classification.value,
                    "canonical_hash": ref.canonical_hash,
                    "status": item["status"].value,
                })
        return results

    def get_sop_version(self, sop_id: str, version: str) -> SignedSOPPayload:
        """GET /api/v1/exec/sops/{id}/versions/{ver}"""
        if self._outage_mode:
            raise HubConnectionError("Hub service unreachable (HTTP 503)")
        if sop_id not in self._sops or self._sops[sop_id]["ref"].version != version:
            raise KeyError(f"SOP '{sop_id}' version '{version}' not found")

        item = self._sops[sop_id]
        sig = "0" * 128 if self._tamper_mode else item["signature"]

        return SignedSOPPayload(
            sop=item["ref"],
            body_json=item["body_json"],
            canonical_sha256=item["canonical_sha256"],
            ed25519_signature=sig,
            key_id=self.key_id,
            status=item["status"],
            signed_at=datetime.utcnow(),
        )

    def get_sop_status(self, sop_id: str) -> Dict[str, Any]:
        """GET /api/v1/exec/sops/{id}/status"""
        if self._outage_mode:
            raise HubConnectionError("Hub service unreachable (HTTP 503)")
        if sop_id not in self._sops:
            raise KeyError(f"SOP '{sop_id}' not found")

        item = self._sops[sop_id]
        return {
            "sop_id": sop_id,
            "version": item["ref"].version,
            "canonical_hash": item["canonical_sha256"],
            "status": item["status"].value,
        }

