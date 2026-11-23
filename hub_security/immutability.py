"""Fix N1: Published SOP & Playbook Immutability Guard.

Enforces strict write-protection on all published procedures. Once an SOP
is marked PUBLISHED, its steps, bindings, and metadata cannot be altered.
Any change requires publishing a new SemVer draft version.
"""

from typing import Any, Dict, Optional
from contracts.canonical import compute_canonical_hash


class ImmutableSOPError(Exception):
    """Raised when an attempt is made to mutate an already published SOP."""

    pass


def check_sop_immutability(existing_sop: Optional[Dict[str, Any]], new_sop: Dict[str, Any]) -> None:
    """Enforce that published SOPs cannot have their content or bindings modified.

    - If no existing SOP is found: allowed (new SOP draft).
    - If existing SOP is in DRAFT: allowed (updates to in-progress drafts permitted).
    - If existing SOP is PUBLISHED:
        - If canonical content hash matches: allowed as idempotent save.
        - If canonical content hash differs: raises ImmutableSOPError.
    """
    if not existing_sop:
        return

    existing_status = str(existing_sop.get("status", "")).upper()
    if existing_status != "PUBLISHED":
        # Drafts or pending reviews can be edited prior to final publication
        return

    sop_id = existing_sop.get("sop_id", "UNKNOWN")
    version = existing_sop.get("version", "UNKNOWN")

    # Compute canonical hashes of the procedure bodies
    existing_body = existing_sop.get("body_json") or existing_sop.get("steps") or existing_sop
    new_body = new_sop.get("body_json") or new_sop.get("steps") or new_sop

    existing_hash = existing_sop.get("canonical_hash") or compute_canonical_hash(existing_body)
    new_hash = compute_canonical_hash(new_body)

    if existing_hash != new_hash:
        raise ImmutableSOPError(
            f"SOP_IMMUTABLE_ERROR: Cannot modify published SOP '{sop_id}' version '{version}'. "
            f"Published procedures are strictly immutable. To introduce changes, you must publish "
            f"a new SemVer draft version."
        )


def validate_semver_progression(current_version: str, next_version: str) -> bool:
    """Validate that a proposed new version represents a valid forward SemVer progression."""
    try:
        curr_parts = [int(p) for p in current_version.split(".")]
        next_parts = [int(p) for p in next_version.split(".")]
        if len(curr_parts) != 3 or len(next_parts) != 3:
            return False
        return tuple(next_parts) > tuple(curr_parts)
    except (ValueError, AttributeError):
        return False
