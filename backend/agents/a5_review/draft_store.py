"""
Agent A5: Draft Staging Store
=============================
Frozen Specification: SOP Governance Hub v1.0 (Section 10.1 & 13)
Holds unapproved drafts in-memory or in knowledge_base/_uploads/_drafts/
until human review approval is explicitly confirmed.
Prevents unapproved documents from being written to knowledge_base/sops/.
"""

import os
import json
from typing import Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_DIR = os.getenv("ELONE_KB_DIR")
if not KB_DIR or not os.path.exists(KB_DIR):
    root_kb = os.path.abspath(os.path.join(BASE_DIR, "..", "knowledge_base"))
    if os.path.exists(root_kb):
        KB_DIR = root_kb
    elif os.path.exists(os.path.join(BASE_DIR, "knowledge_base")):
        KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
    else:
        KB_DIR = root_kb
UPLOADS_DIR = os.path.join(KB_DIR, "_uploads")
DRAFTS_DIR = os.path.join(UPLOADS_DIR, "_drafts")
os.makedirs(DRAFTS_DIR, exist_ok=True)


def stage_unapproved_draft(
    sop_id: str,
    draft_data: Dict[str, Any],
    canonical_draft: Dict[str, Any],
    raw_filename: str,
) -> str:
    """Stages unapproved SOP draft in _drafts/ so it is not visible to execution engines."""
    draft_file = os.path.join(DRAFTS_DIR, f"{sop_id}.draft.json")
    payload = {
        "sop_id": sop_id,
        "raw_filename": raw_filename,
        "draft": draft_data,
        "canonical_draft": canonical_draft,
    }
    with open(draft_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return draft_file


def load_staged_draft(sop_id: str) -> Optional[Dict[str, Any]]:
    """Loads a staged unapproved draft for review or editing."""
    draft_file = os.path.join(DRAFTS_DIR, f"{sop_id}.draft.json")
    if not os.path.exists(draft_file):
        return None
    try:
        with open(draft_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def purge_staged_draft(sop_id: str) -> bool:
    """Removes staged draft once published or rejected."""
    draft_file = os.path.join(DRAFTS_DIR, f"{sop_id}.draft.json")
    if os.path.exists(draft_file):
        try:
            os.remove(draft_file)
            return True
        except Exception:
            return False
    return False


def commit_draft_to_playbook(sop_id: str) -> Optional[str]:
    """Commits an approved draft to production OKF playbook and purges the draft."""
    from agents.a2_structuring.okf_builder import write_okf_playbook
    staged = load_staged_draft(sop_id)
    if not staged:
        return None
    draft_data = staged.get("draft", {})
    raw_filename = staged.get("raw_filename", f"{sop_id}.txt")
    playbook_path = write_okf_playbook(draft_data, raw_filename=raw_filename)
    purge_staged_draft(sop_id)
    return playbook_path


__all__ = [
    "stage_unapproved_draft",
    "load_staged_draft",
    "purge_staged_draft",
    "commit_draft_to_playbook",
]
