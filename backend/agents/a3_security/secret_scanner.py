"""
Agent A3: Secret Scanner & Terminal Quarantine Protocol
=======================================================
Frozen Specification: SOP Governance Hub v1.0 (Section 10)
- Gate 2: Deterministic credential scanning (passwords, api_keys, private_keys)
- Terminal Quarantine: Immediate execution halt, file content purged, 0 AI calls made
- Generates INC-xxxxxx incident ticket
"""

from typing import Dict, Any, Tuple, List
from utils.security import redact_sensitive_dlp
from schemas.governance_models import generate_incident_id, QuarantineIncident


def scan_for_secrets(raw_text: str) -> Tuple[bool, int, List[str], Dict[str, Any]]:
    """Scans extracted raw text for credentials and secrets.
    Returns (has_secrets, secrets_count, secret_types, dlp_stats).
    """
    _, dlp_stats = redact_sensitive_dlp(raw_text)
    secret_types = [k for k, v in dlp_stats.items() if v > 0 and k in ("passwords", "api_keys", "private_keys")]
    secrets_count = sum(dlp_stats.get(k, 0) for k in ("passwords", "api_keys", "private_keys"))
    return len(secret_types) > 0, secrets_count, secret_types, dlp_stats


def create_quarantine_incident(
    job_id: str,
    sop_id: str,
    content_sha256: str,
    secrets_count: int,
    secret_types: List[str],
) -> QuarantineIncident:
    """Emits an official INC-xxxxxx incident ticket for terminal quarantine."""
    return QuarantineIncident(
        incident_id=generate_incident_id(),
        sop_id=sop_id,
        job_id=job_id,
        content_sha256=content_sha256,
        secrets_count=secrets_count,
        secret_types=secret_types,
        purged=True,
    )
