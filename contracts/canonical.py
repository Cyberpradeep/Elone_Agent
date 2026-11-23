"""RFC 8785 Canonical JSON and Deterministic SHA-256 Hashing Utilities.

Used across the SOP Execution Engine for immutable hashing of plans,
audit event chains, and cryptographic signature payloads.
"""

import hashlib
import json
from datetime import datetime
from typing import Any


def _json_default(obj: Any) -> Any:
    """Normalize non-standard types for canonical JSON output."""
    if isinstance(obj, datetime):
        # RFC 3339 / ISO 8601 UTC representation with Z suffix if timezone-aware or clean ISO
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        # Pydantic v2 model support
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        # Pydantic v1 fallback support
        return obj.dict()
    if isinstance(obj, set):
        return sorted(list(obj))
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def to_canonical_json(data: Any) -> str:
    """Serializes dictionaries or Pydantic models to deterministic RFC 8785 JSON.

    Guarantees:
    - Keys sorted lexicographically at every level.
    - No whitespace between separators (',', ':').
    - Unicode characters preserved (ensure_ascii=False).
    - Normalized datetime ISO-8601 representation.
    """
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


def compute_canonical_hash(data: Any) -> str:
    """Returns the lowercase 64-character SHA-256 digest of canonical JSON."""
    canonical_str = to_canonical_json(data)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

