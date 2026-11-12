"""
API Shared Context, Tenant Storage Helpers & Infrastructure Singletons
=======================================================================
Holds shared singletons for OrchestratorLedger, DownstreamRetrievalIndex,
AgentMessageBus, filesystem paths, tenant-isolated upload/manifest/log helpers,
and unified SOP/draft access metadata resolution.
"""

import os
import re
import sys
import json
import glob
import uuid
import hashlib
import datetime
import threading
from typing import Dict, Any, Optional, List, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from orchestrator.ledger import OrchestratorLedger
from orchestrator.bus import AgentBus as AgentMessageBus
from agents.a6_hub.retrieval_catalog import DownstreamRetrievalIndex, normalize_clearance
from auth.config import get_default_tenant
from auth.models import TENANT_ID_RE

KB_DIR = os.getenv("ELONE_KB_DIR")
if not KB_DIR or not os.path.exists(KB_DIR):
    root_kb = os.path.abspath(os.path.join(PROJECT_ROOT, "knowledge_base"))
    if os.path.exists(root_kb):
        KB_DIR = root_kb
    elif os.path.exists(os.path.join(BASE_DIR, "knowledge_base")):
        KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
    else:
        KB_DIR = root_kb

UPLOADS_DIR = os.path.join(KB_DIR, "_uploads")
SOPS_DIR = os.path.join(KB_DIR, "sops")
PATTERNS_DIR = os.path.join(KB_DIR, "patterns")
LOGS_DIR = os.path.join(KB_DIR, "logs", "debug")
AUTH_DIR = os.path.join(KB_DIR, "_auth")
MANIFEST_PATH = os.path.join(UPLOADS_DIR, "_processed_manifest.json")
UPLOAD_OWNERS_PATH = os.path.join(UPLOADS_DIR, "_upload_owners.json")
LOG_OWNERS_PATH = os.path.join(os.path.dirname(LOGS_DIR), "_log_owners.json")
GOVERNANCE_LEDGER_PATH = os.path.join(UPLOADS_DIR, "_governance_ledger.json")
RETRIEVAL_CATALOG_PATH = os.path.join(UPLOADS_DIR, "_retrieval_catalog.json")
DRAFTS_DIR = os.path.join(UPLOADS_DIR, "_drafts")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(SOPS_DIR, exist_ok=True)
os.makedirs(PATTERNS_DIR, exist_ok=True)
os.makedirs(DRAFTS_DIR, exist_ok=True)

_STORAGE_LOCK = threading.RLock()
_SOP_ID_RE = re.compile(r"[A-Za-z0-9_-]+")
_LOG_TENANT_RE = re.compile(r"^\s*Tenant ID:\s*(\S+)", re.MULTILINE | re.IGNORECASE)

governance_ledger = OrchestratorLedger(ledger_path=GOVERNANCE_LEDGER_PATH)
retrieval_index = DownstreamRetrievalIndex(catalog_path=RETRIEVAL_CATALOG_PATH)
agent_bus = AgentMessageBus()


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _atomic_write_json(path: str, payload: Any) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)


def _inside(path: str, root: str) -> bool:
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real == base or real.startswith(base + os.sep)


def _safe_tenant_segment(tenant_id: str) -> str:
    clean = str(tenant_id or "").strip()
    if not TENANT_ID_RE.fullmatch(clean):
        raise ValueError(f"Invalid tenant_id '{tenant_id}'.")
    return clean


def _file_sha256_quick(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Processed Manifest Helpers (Tenant-Scoped + Legacy Attribution)
# ---------------------------------------------------------------------------

def manifest_key(tenant_id: str, safe_name: str) -> str:
    clean_tenant = _safe_tenant_segment(tenant_id)
    clean_name = os.path.basename(str(safe_name or "").strip())
    return f"{clean_tenant}::{clean_name}"


def read_manifest() -> Dict[str, Any]:
    with _STORAGE_LOCK:
        if os.path.exists(MANIFEST_PATH):
            try:
                with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}
            except Exception:
                pass
        return {}


def write_manifest(manifest: Dict[str, Any]) -> None:
    with _STORAGE_LOCK:
        _atomic_write_json(MANIFEST_PATH, manifest)


def get_manifest_entry(
    manifest: Dict[str, Any],
    tenant_id: str,
    safe_name: str,
) -> Tuple[str, Dict[str, Any]]:
    tkey = manifest_key(tenant_id, safe_name)
    if tkey in manifest and isinstance(manifest[tkey], dict):
        return tkey, manifest[tkey]
    clean_name = os.path.basename(str(safe_name or "").strip())
    if tenant_id == get_default_tenant() and clean_name in manifest and isinstance(manifest[clean_name], dict):
        return clean_name, manifest[clean_name]
    return tkey, {}


def set_manifest_entry(
    manifest: Dict[str, Any],
    tenant_id: str,
    safe_name: str,
    entry: Dict[str, Any],
) -> str:
    tkey = manifest_key(tenant_id, safe_name)
    clean_name = os.path.basename(str(safe_name or "").strip())
    manifest[tkey] = entry
    if tenant_id == get_default_tenant() and clean_name in manifest:
        del manifest[clean_name]
    return tkey


def del_manifest_entry(
    manifest: Dict[str, Any],
    tenant_id: str,
    safe_name: str,
) -> bool:
    removed = False
    tkey = manifest_key(tenant_id, safe_name)
    clean_name = os.path.basename(str(safe_name or "").strip())
    if tkey in manifest:
        del manifest[tkey]
        removed = True
    if tenant_id == get_default_tenant() and clean_name in manifest:
        del manifest[clean_name]
        removed = True
    return removed


def filter_manifest_for_tenant(manifest: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    prefix = f"{_safe_tenant_segment(tenant_id)}::"
    is_default = tenant_id == get_default_tenant()
    scoped: Dict[str, Any] = {}
    for k, v in (manifest or {}).items():
        if not isinstance(v, dict):
            continue
        if "::" in k:
            if k.startswith(prefix):
                scoped[k] = v
        elif is_default:
            scoped[k] = v
    return scoped


# ---------------------------------------------------------------------------
# Tenant-Scoped Upload Storage & Ownership Helpers
# ---------------------------------------------------------------------------

def tenant_uploads_dir(tenant_id: str) -> str:
    return os.path.join(UPLOADS_DIR, _safe_tenant_segment(tenant_id))


def read_upload_owners() -> Dict[str, Any]:
    with _STORAGE_LOCK:
        if os.path.exists(UPLOAD_OWNERS_PATH):
            try:
                with open(UPLOAD_OWNERS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}
            except Exception:
                pass
        return {}


def record_upload_owner(
    tenant_id: str,
    safe_name: str,
    uploaded_by: str,
    sha256: Optional[str] = None,
) -> Dict[str, Any]:
    clean_tenant = _safe_tenant_segment(tenant_id)
    clean_name = os.path.basename(str(safe_name or "").strip())
    rec = {
        "tenant_id": clean_tenant,
        "filename": clean_name,
        "uploaded_by": str(uploaded_by or "").strip(),
        "sha256": sha256,
        "uploaded_at": _utc_now_iso(),
    }
    key = f"{clean_tenant}/{clean_name}"
    with _STORAGE_LOCK:
        owners = read_upload_owners()
        owners[key] = rec
        _atomic_write_json(UPLOAD_OWNERS_PATH, owners)
    return rec


def get_upload_owner(tenant_id: str, safe_name: str) -> Optional[Dict[str, Any]]:
    clean_tenant = _safe_tenant_segment(tenant_id)
    clean_name = os.path.basename(str(safe_name or "").strip())
    owners = read_upload_owners()
    entry = owners.get(f"{clean_tenant}/{clean_name}")
    if isinstance(entry, dict):
        return entry
    if clean_tenant == get_default_tenant():
        legacy = owners.get(clean_name)
        if isinstance(legacy, dict) and legacy.get("tenant_id", clean_tenant) == clean_tenant:
            return legacy
    return None


def _legacy_flat_upload_owner_tenant(safe_name: str, flat_path: str) -> Optional[str]:
    owners = read_upload_owners()
    legacy_rec = owners.get(safe_name)
    if isinstance(legacy_rec, dict) and legacy_rec.get("tenant_id"):
        return str(legacy_rec["tenant_id"])

    file_sha = _file_sha256_quick(flat_path)
    if file_sha:
        matching_jobs = [
            j for j in list(governance_ledger._jobs.values())
            if j.content_sha256 == file_sha
        ]
        if matching_jobs:
            matching_jobs.sort(key=lambda j: (j.updated_at or j.created_at or ""), reverse=True)
            return matching_jobs[0].tenant_id

    if os.path.exists(DRAFTS_DIR):
        for df_name in os.listdir(DRAFTS_DIR):
            if not df_name.endswith(".draft.json"):
                continue
            df_path = os.path.join(DRAFTS_DIR, df_name)
            try:
                with open(df_path, "r", encoding="utf-8") as f:
                    d_data = json.load(f)
                if d_data.get("raw_filename") == safe_name:
                    c_tenant = (d_data.get("canonical_draft") or {}).get("tenant_id")
                    if c_tenant:
                        return str(c_tenant)
            except Exception:
                continue
    return None


def resolve_tenant_upload(tenant_id: str, safe_name: str) -> Optional[str]:
    clean_tenant = _safe_tenant_segment(tenant_id)
    clean_name = os.path.basename(str(safe_name or "").strip())
    if not clean_name or clean_name.startswith("_") or clean_name in {".", ".."}:
        return None

    t_dir = tenant_uploads_dir(clean_tenant)
    scoped_path = os.path.join(t_dir, clean_name)
    if _inside(scoped_path, t_dir) and os.path.isfile(scoped_path):
        return scoped_path

    legacy_path = os.path.join(UPLOADS_DIR, clean_name)
    if _inside(legacy_path, UPLOADS_DIR) and os.path.isfile(legacy_path):
        owner_tenant = _legacy_flat_upload_owner_tenant(clean_name, legacy_path)
        if owner_tenant is not None:
            return legacy_path if owner_tenant == clean_tenant else None
        if clean_tenant == get_default_tenant():
            return legacy_path
    return None


def list_tenant_uploads(tenant_id: str) -> List[Tuple[str, str]]:
    clean_tenant = _safe_tenant_segment(tenant_id)
    items: Dict[str, str] = {}
    t_dir = tenant_uploads_dir(clean_tenant)
    if os.path.exists(t_dir):
        for name in sorted(os.listdir(t_dir)):
            if name.startswith("_"):
                continue
            full_path = os.path.join(t_dir, name)
            if _inside(full_path, t_dir) and os.path.isfile(full_path):
                items[name] = full_path

    if os.path.exists(UPLOADS_DIR):
        for name in sorted(os.listdir(UPLOADS_DIR)):
            if name.startswith("_") or name in items:
                continue
            full_path = os.path.join(UPLOADS_DIR, name)
            if os.path.isfile(full_path):
                resolved = resolve_tenant_upload(clean_tenant, name)
                if resolved and os.path.realpath(resolved) == os.path.realpath(full_path):
                    items[name] = full_path

    return sorted(items.items(), key=lambda kv: kv[0])


# ---------------------------------------------------------------------------
# Log Tenant Attribution Helpers
# ---------------------------------------------------------------------------

def read_log_owners() -> Dict[str, str]:
    with _STORAGE_LOCK:
        if os.path.exists(LOG_OWNERS_PATH):
            try:
                with open(LOG_OWNERS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
            except Exception:
                pass
        return {}


def record_log_owner(filename: str, tenant_id: str) -> None:
    clean_name = os.path.basename(str(filename or "").strip())
    clean_tenant = _safe_tenant_segment(tenant_id)
    if not clean_name:
        return
    with _STORAGE_LOCK:
        owners = read_log_owners()
        owners[clean_name] = clean_tenant
        _atomic_write_json(LOG_OWNERS_PATH, owners)


def get_log_owner(filename: str, resolved_path: Optional[str] = None) -> str:
    clean_name = os.path.basename(str(filename or "").strip())
    owners = read_log_owners()
    if clean_name in owners:
        return owners[clean_name]
    if resolved_path and os.path.isfile(resolved_path):
        try:
            with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                header = f.read(2048)
            match = _LOG_TENANT_RE.search(header)
            if match:
                return match.group(1).strip()
        except OSError:
            pass
    return get_default_tenant()


# ---------------------------------------------------------------------------
# Unified SOP & Draft Access Metadata Resolvers
# ---------------------------------------------------------------------------

def _build_canonical_meta_map() -> Dict[str, Dict[str, Any]]:
    meta_map: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(SOPS_DIR):
        return meta_map
    for path in glob.glob(os.path.join(SOPS_DIR, "**", "*.canonical.json"), recursive=True):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            stem = os.path.basename(path)[: -len(".canonical.json")]
            sid = str(cdata.get("sop_id") or stem).strip()
            src = cdata.get("source") or {}
            classif = cdata.get("classification") or {}
            lifecycle = cdata.get("lifecycle") or {}
            rec = {
                "sop_id": sid,
                "tenant_id": cdata.get("tenant_id"),
                "classification_level": normalize_clearance(classif.get("level", "L1")),
                "state": str(lifecycle.get("state") or "published").lower(),
                "source_sha256": src.get("file_sha256") or src.get("sha256"),
                "path": path,
            }
            if sid:
                meta_map[sid.lower()] = rec
            if stem:
                meta_map.setdefault(stem.lower(), rec)
        except Exception:
            continue
    return meta_map


def _find_job_for_sop(sop_id: str, preferred_states: Optional[set] = None):
    clean = str(sop_id or "").strip().lower()
    matches = [j for j in list(governance_ledger._jobs.values()) if str(j.sop_id or "").lower() == clean]
    if not matches:
        return None
    if preferred_states:
        pref = [j for j in matches if j.current_state in preferred_states]
        if pref:
            pref.sort(key=lambda j: (j.updated_at or j.created_at or ""), reverse=True)
            return pref[0]
    priority = {
        "published": 5,
        "approved": 4,
        "awaiting_review": 4,
        "changes_requested": 3,
        "assessing": 2,
        "structuring": 2,
        "scanning": 2,
        "extracting": 2,
        "received": 2,
    }
    matches.sort(
        key=lambda j: (priority.get(j.current_state, 0), j.updated_at or j.created_at or ""),
        reverse=True,
    )
    return matches[0]


def resolve_sop_access_meta(
    sop_id: str,
    canonical_map: Optional[Dict[str, Dict[str, Any]]] = None,
    frontmatter: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolves canonical tenant_id, clearance level, and lifecycle state for a published SOP."""
    clean_id = str(sop_id or "").replace(".md", "").strip()
    key = clean_id.lower()
    default_tenant = get_default_tenant()

    canon_entry = (canonical_map or _build_canonical_meta_map()).get(key)
    idx_entry = retrieval_index._index.get(clean_id)
    if idx_entry is None:
        for k, val in list(retrieval_index._index.items()):
            if k.lower() == key:
                idx_entry = val
                break
    job = _find_job_for_sop(clean_id)

    tenant_id = None
    clearance_level = None
    state = None
    source_sha256 = None

    if canon_entry:
        tenant_id = canon_entry.get("tenant_id") or tenant_id
        clearance_level = canon_entry.get("classification_level") or clearance_level
        state = canon_entry.get("state") or state
        source_sha256 = canon_entry.get("source_sha256") or source_sha256

    if idx_entry:
        if not tenant_id or tenant_id == "default_tenant":
            if idx_entry.tenant_id and idx_entry.tenant_id != "default_tenant":
                tenant_id = idx_entry.tenant_id
        if not clearance_level:
            clearance_level = idx_entry.classification_level
        state = state or "published"
        source_sha256 = source_sha256 or idx_entry.content_sha256

    if job:
        if not tenant_id or tenant_id == "default_tenant":
            tenant_id = job.tenant_id
        state = state or job.current_state
        source_sha256 = source_sha256 or job.content_sha256

    if frontmatter and isinstance(frontmatter, dict):
        if not tenant_id or tenant_id == "default_tenant":
            fm_tenant = frontmatter.get("tenant_id")
            if fm_tenant:
                tenant_id = fm_tenant
        if not clearance_level and frontmatter.get("classification_level"):
            clearance_level = normalize_clearance(frontmatter["classification_level"])

    if not tenant_id or tenant_id == "default_tenant":
        tenant_id = default_tenant
    if not clearance_level:
        clearance_level = "L1"
    else:
        clearance_level = normalize_clearance(clearance_level)

    return {
        "sop_id": clean_id,
        "tenant_id": str(tenant_id),
        "classification_level": clearance_level,
        "state": str(state or "published").lower(),
        "source_sha256": source_sha256,
    }


def read_draft_file(sop_id: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    clean_id = str(sop_id or "").strip()
    if not _SOP_ID_RE.fullmatch(clean_id):
        return None, None
    path = os.path.join(DRAFTS_DIR, f"{clean_id}.draft.json")
    if not _inside(path, DRAFTS_DIR) or not os.path.isfile(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return path, json.load(f)
    except Exception:
        return None, None


def resolve_draft_access_meta(
    sop_id: str,
    draft_data: Optional[Dict[str, Any]] = None,
    job: Any = None,
) -> Dict[str, Any]:
    clean_id = str(sop_id or "").strip()
    if draft_data is None:
        _, draft_data = read_draft_file(clean_id)
    if job is None:
        job = _find_job_for_sop(clean_id)

    canon = (draft_data or {}).get("canonical_draft") or {}
    classif = canon.get("classification") or {}
    lifecycle = canon.get("lifecycle") or {}

    tenant_id = canon.get("tenant_id") or (job.tenant_id if job else None) or get_default_tenant()
    if tenant_id == "default_tenant":
        tenant_id = (job.tenant_id if job else None) or get_default_tenant()

    raw_level = classif.get("level")
    if not raw_level and job and isinstance(job.approval_decision, dict):
        pass
    clearance_level = normalize_clearance(raw_level or "L1")

    return {
        "sop_id": clean_id,
        "tenant_id": str(tenant_id),
        "classification_level": clearance_level,
        "uploaded_by": lifecycle.get("uploaded_by") or (job.uploaded_by if job else None),
        "last_editor": (draft_data or {}).get("last_editor") or lifecycle.get("last_editor"),
        "state": job.current_state if job else None,
    }


def parse_yaml_frontmatter(content: str):
    import yaml
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1])
                return fm or {}, parts[2].strip()
            except Exception:
                pass
    return {}, content.strip()
