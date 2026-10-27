"""
Agent A6: Downstream Clearance Retrieval Catalog
================================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.6, 14 & 18)
Multi-tenant isolation, L0-L3 clearance hierarchy, instant purge on deactivation,
standard citation stamps ({sop_id}@v{version}#{content_sha256[:10]}).
"""

import os
import json
import re
import datetime
import threading
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field, asdict

CLEARANCE_RANKS: Dict[str, int] = {
    "L0": 0,  # Public
    "L1": 1,  # Internal
    "L2": 2,  # Confidential
    "L3": 3,  # Restricted
}

CLEARANCE_DESCRIPTIONS: Dict[str, str] = {
    "L0": "L0 Public",
    "L1": "L1 Internal",
    "L2": "L2 Confidential",
    "L3": "L3 Restricted",
}

PERSONA_DEFAULT_CLEARANCE: Dict[str, str] = {
    "public_agent": "L0",
    "general_assistant": "L1",
    "service_desk_agent": "L1",
    "it_support_agent": "L1",
    "devops_engineer": "L2",
    "incident_responder": "L2",
    "security_agent": "L3",
    "compliance_auditor": "L3",
    "admin_agent": "L3",
}


def normalize_clearance(level: str) -> str:
    """Normalizes clearance level string to 'L0', 'L1', 'L2', or 'L3'."""
    clean = str(level).strip().upper()
    if clean in CLEARANCE_RANKS:
        return clean
    for prefix in ["L0", "L1", "L2", "L3"]:
        if prefix in clean:
            return prefix
    return "L0"


def format_citation(sop_id: str, version: int, content_sha256: str) -> str:
    """Formats standard downstream citation per Section 17."""
    short_hash = content_sha256[:10] if content_sha256 else "0000000000"
    return f"{sop_id}@v{version}#{short_hash}"


@dataclass
class IndexedSOP:
    """Searchable representation of an approved, published SOP."""
    sop_id: str
    version: int
    tenant_id: str
    title: str
    department: str
    classification_level: str
    classification_score: int
    content_sha256: str
    published_at: str
    purpose: str
    scope: str
    roles: List[str]
    step_actions: List[str]
    step_actors: List[str]
    citation: str
    canonical_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndexedSOP":
        return cls(**data)


@dataclass
class RetrievalResult:
    """Agent retrieval hit containing summary, citation, and operational steps."""
    sop_id: str
    version: int
    title: str
    department: str
    classification_level: str
    citation: str
    purpose: str
    step_count: int
    matched_terms: List[str]
    relevance_score: float
    data: Optional[Dict[str, Any]] = None


@dataclass
class RetrievalAuditRecord:
    """Audit entry for downstream agent query and access decisions."""
    timestamp: str
    tenant_id: str
    agent_id: str
    agent_persona: str
    clearance_level: str
    query: str
    results_count: int
    denied_by_clearance_count: int
    denied_by_tenant_count: int


class DownstreamRetrievalIndex:
    """Secure in-memory and persistent retrieval index enforcing clearance gates."""

    def __init__(self, catalog_path: Optional[str] = None):
        self.catalog_path = catalog_path
        self._index: Dict[str, IndexedSOP] = {}
        self._audit_log: List[RetrievalAuditRecord] = []
        self._lock = threading.RLock()
        if self.catalog_path and os.path.exists(self.catalog_path):
            self.load()

    def index_published_sop(self, canonical_sop: Dict[str, Any]) -> IndexedSOP:
        """Indexes an approved SOP upon publication (Section 17)."""
        with self._lock:
            lifecycle = canonical_sop.get("lifecycle", {})
            state = lifecycle.get("state", "").lower()
            if state != "published":
                raise ValueError(
                    f"Only published SOPs can be added to the downstream retrieval index. Document is in state '{state}'."
                )

            sop_id = canonical_sop.get("sop_id", "")
            if not sop_id:
                raise ValueError("Canonical SOP missing 'sop_id'.")

            tenant_id = canonical_sop.get("tenant_id", "default_tenant")
            version = canonical_sop.get("version", 1)
            title = canonical_sop.get("title", "")
            
            dept_field = canonical_sop.get("department", {})
            department = dept_field.get("value", "") if isinstance(dept_field, dict) else str(dept_field or "")

            classif = canonical_sop.get("classification", {})
            level = normalize_clearance(classif.get("level", "L1"))
            score = int(classif.get("score", 25))

            source = canonical_sop.get("source", {})
            sha256 = source.get("sha256", "")
            if not sha256 and lifecycle.get("approvals"):
                sha256 = lifecycle["approvals"][-1].get("content_sha256", "")

            citation = format_citation(sop_id, version, sha256)

            purpose_data = canonical_sop.get("purpose")
            purpose = purpose_data.get("text", "") if isinstance(purpose_data, dict) else ""
            scope_data = canonical_sop.get("scope")
            scope = scope_data.get("text", "") if isinstance(scope_data, dict) else ""

            roles = [r.get("role", "") for r in canonical_sop.get("roles", []) if isinstance(r, dict)]
            steps = canonical_sop.get("steps", [])
            step_actions = [s.get("action", "") for s in steps if isinstance(s, dict)]
            step_actors = [s.get("actor", "") for s in steps if isinstance(s, dict)]

            entry = IndexedSOP(
                sop_id=sop_id,
                version=version,
                tenant_id=tenant_id,
                title=title,
                department=department,
                classification_level=level,
                classification_score=score,
                content_sha256=sha256,
                published_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                purpose=purpose,
                scope=scope,
                roles=roles,
                step_actions=step_actions,
                step_actors=step_actors,
                citation=citation,
                canonical_data=canonical_sop,
            )

            self._index[sop_id] = entry
            self._save_unlocked()
            return entry

    # Aliases
    index = index_published_sop
    index_sop = index_published_sop

    def purge_sop(self, sop_id: str, reason: str = "deactivated") -> bool:
        """Immediately removes an SOP from downstream retrieval upon deactivation/archival."""
        with self._lock:
            if sop_id in self._index:
                del self._index[sop_id]
                self._save_unlocked()
                return True
            return False

    def search(
        self,
        query: str,
        tenant_id: str,
        clearance_level: str,
        agent_id: str = "agent_unknown",
        agent_persona: Optional[str] = None,
        department: Optional[str] = None,
        limit: int = 10,
        include_full_content: bool = False,
    ) -> List[RetrievalResult]:
        """Queries the retrieval index with strict clearance and tenant enforcement."""
        with self._lock:
            agent_level = normalize_clearance(clearance_level)
            agent_rank = CLEARANCE_RANKS[agent_level]
            query_tokens = set(re.findall(r"\b\w{3,}\b", query.lower()))

            matched_results: List[RetrievalResult] = []
            denied_clearance_count = 0
            denied_tenant_count = 0

            for entry in self._index.values():
                if entry.tenant_id != tenant_id:
                    denied_tenant_count += 1
                    continue

                sop_rank = CLEARANCE_RANKS.get(entry.classification_level, 0)
                if sop_rank > agent_rank:
                    denied_clearance_count += 1
                    continue

                if department and entry.department and entry.department.lower() != department.lower():
                    continue

                searchable_text = f"{entry.title} {entry.purpose} {entry.scope} {' '.join(entry.step_actions)} {entry.department}".lower()
                matched_terms = [tok for tok in query_tokens if tok in searchable_text]

                relevance = 0.0
                if query.strip():
                    if not matched_terms:
                        continue
                    relevance = len(matched_terms) / len(query_tokens) if query_tokens else 1.0
                    if any(tok in entry.title.lower() for tok in query_tokens):
                        relevance += 0.5
                else:
                    relevance = 1.0

                if agent_persona:
                    clean_persona = agent_persona.lower().replace("_", " ")
                    if any(clean_persona in r.lower() for r in entry.roles):
                        relevance += 0.3
                    if any(clean_persona in a.lower() for a in entry.step_actors):
                        relevance += 0.2

                matched_results.append(
                    RetrievalResult(
                        sop_id=entry.sop_id,
                        version=entry.version,
                        title=entry.title,
                        department=entry.department,
                        classification_level=entry.classification_level,
                        citation=entry.citation,
                        purpose=entry.purpose,
                        step_count=len(entry.step_actions),
                        matched_terms=matched_terms,
                        relevance_score=round(relevance, 3),
                        data=entry.canonical_data if include_full_content else None,
                    )
                )

            matched_results.sort(key=lambda x: x.relevance_score, reverse=True)
            final_results = matched_results[:limit]

            self._audit_log.append(
                RetrievalAuditRecord(
                    timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    agent_persona=agent_persona or "unspecified",
                    clearance_level=agent_level,
                    query=query,
                    results_count=len(final_results),
                    denied_by_clearance_count=denied_clearance_count,
                    denied_by_tenant_count=denied_tenant_count,
                )
            )

            return final_results

    def get_by_id(
        self,
        sop_id: str,
        tenant_id: str,
        clearance_level: str,
        agent_id: str = "agent_unknown",
    ) -> Tuple[Optional[IndexedSOP], Optional[str]]:
        """Direct retrieval by SOP ID with clearance check."""
        with self._lock:
            entry = self._index.get(sop_id)
            if not entry:
                return None, f"SOP '{sop_id}' not found in published catalog."

            if entry.tenant_id != tenant_id:
                return None, "Access denied: Tenant isolation policy violation."

            agent_level = normalize_clearance(clearance_level)
            agent_rank = CLEARANCE_RANKS[agent_level]
            sop_rank = CLEARANCE_RANKS.get(entry.classification_level, 0)

            if sop_rank > agent_rank:
                return None, f"Access denied: Insufficient clearance. SOP requires {entry.classification_level}, agent has {agent_level}."

            return entry, None

    def get_stats(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Returns live statistics of published SOPs per clearance tier."""
        with self._lock:
            entries = [e for e in self._index.values() if tenant_id is None or e.tenant_id == tenant_id]
            tier_counts = {"L0": 0, "L1": 0, "L2": 0, "L3": 0}
            for e in entries:
                tier_counts[e.classification_level] = tier_counts.get(e.classification_level, 0) + 1

            return {
                "total_published": len(entries),
                "by_tier": tier_counts,
                "audit_queries_count": len(self._audit_log),
            }

    def get_audit_trail(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return [asdict(r) for r in self._audit_log[-limit:]]

    def _save_unlocked(self):
        if not self.catalog_path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.catalog_path)), exist_ok=True)
        tmp_path = f"{self.catalog_path}.tmp"
        data = {k: v.to_dict() for k, v in self._index.items()}
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, self.catalog_path)

    def save(self):
        with self._lock:
            self._save_unlocked()

    def load(self):
        with self._lock:
            if not self.catalog_path or not os.path.exists(self.catalog_path):
                return
            if os.path.getsize(self.catalog_path) == 0:
                self._index = {}
                return
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._index = {k: IndexedSOP.from_dict(v) for k, v in data.items()}


__all__ = [
    "DownstreamRetrievalIndex",
    "IndexedSOP",
    "RetrievalResult",
    "RetrievalAuditRecord",
    "normalize_clearance",
    "format_citation",
    "CLEARANCE_RANKS",
    "CLEARANCE_DESCRIPTIONS",
    "PERSONA_DEFAULT_CLEARANCE",
]
