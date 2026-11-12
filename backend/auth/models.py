"""
Authentication Models, Lean 4-Role Policy & Claims Validation (C2)
==================================================================
Active Role Set:
  - process_owner     (human, L0-L1 review decisions, upload/ingest, draft edits, publish, delete SOP)
  - security_reviewer (human, L0-L3 review decisions, incidents, logs, telemetry, publish; no delete)
  - admin             (human, full tenant ops, config management, user management, delete SOP; SoD still applies)
  - agent             (downstream machine/service account; retrieval search/stats & published playbooks only)
"""

import re
import sys
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Iterable

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from agents.a6_hub.retrieval_catalog import CLEARANCE_RANKS, PERSONA_DEFAULT_CLEARANCE  # noqa: E402


ROLE_PROCESS_OWNER = "process_owner"
ROLE_SECURITY_REVIEWER = "security_reviewer"
ROLE_ADMIN = "admin"
ROLE_AGENT = "agent"

HUMAN_ROLES = frozenset({
    ROLE_PROCESS_OWNER,
    ROLE_SECURITY_REVIEWER,
    ROLE_ADMIN,
})
ROLE_SET = frozenset({
    ROLE_PROCESS_OWNER,
    ROLE_SECURITY_REVIEWER,
    ROLE_ADMIN,
    ROLE_AGENT,
})

VALID_CLEARANCES = frozenset({"L0", "L1", "L2", "L3"})
TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{1,63}$")


def validate_tenant_id(tenant_id: Any) -> str:
    clean = str(tenant_id or "").strip()
    if not TENANT_ID_RE.fullmatch(clean):
        raise ValueError(
            f"Invalid tenant_id '{tenant_id}'. Must match ^[a-z0-9][a-z0-9_-]{{1,62}}$."
        )
    return clean


def validate_roles(roles: Any) -> List[str]:
    if isinstance(roles, str):
        raw_list = [r.strip().lower() for r in roles.split(",") if r.strip()]
    elif isinstance(roles, Iterable):
        raw_list = [str(r).strip().lower() for r in roles if str(r or "").strip()]
    else:
        raise ValueError("roles must be a list of role strings.")

    normalized: List[str] = []
    seen = set()
    for role in raw_list:
        if role not in ROLE_SET:
            raise ValueError(
                f"Unknown role '{role}'. Allowed roles: {', '.join(sorted(ROLE_SET))}."
            )
        if role not in seen:
            seen.add(role)
            normalized.append(role)

    if not normalized:
        raise ValueError("At least one valid role is required.")
    if ROLE_AGENT in seen and len(normalized) > 1:
        raise ValueError("Role 'agent' cannot coexist with human roles.")
    return normalized


def validate_clearance(clearance: Any) -> str:
    clean = str(clearance or "").strip().upper()
    if clean not in VALID_CLEARANCES:
        raise ValueError(f"Invalid clearance '{clearance}'. Must be one of L0, L1, L2, L3.")
    return clean


def validate_agent_persona_clearance(
    roles: List[str],
    clearance: str,
    agent_persona: Optional[str],
) -> None:
    if ROLE_AGENT in roles and agent_persona:
        default_clr = PERSONA_DEFAULT_CLEARANCE.get(agent_persona)
        if default_clr and CLEARANCE_RANKS[clearance] > CLEARANCE_RANKS[default_clr]:
            raise ValueError(
                f"Clearance '{clearance}' exceeds maximum default '{default_clr}' for persona '{agent_persona}'."
            )


def normalize_identity_key(identity: Any) -> str:
    return str(identity or "").strip().lower()


def compute_capabilities(roles: List[str], clearance: str, actor_type: str) -> Dict[str, bool]:
    is_human = actor_type == "human"
    role_set = set(roles)
    is_admin = is_human and ROLE_ADMIN in role_set
    is_sec = is_human and ROLE_SECURITY_REVIEWER in role_set
    is_po = is_human and ROLE_PROCESS_OWNER in role_set
    any_human = is_human and bool(role_set & HUMAN_ROLES)
    clr_rank = CLEARANCE_RANKS.get(clearance, 0)

    return {
        "can_upload": any_human,
        "can_ingest": any_human,
        "can_edit_draft": any_human,
        "can_publish": any_human,
        "can_review_l0_l1": any_human,
        "can_review_l2_l3": is_human and (is_sec or is_admin) and clr_rank >= CLEARANCE_RANKS["L2"],
        "can_delete_sop": is_human and (is_admin or is_po),
        "can_edit_canonical": is_human and (is_admin or is_po),
        "can_view_logs": is_human and (is_sec or is_admin),
        "can_view_telemetry": is_human and (is_sec or is_admin),
        "can_view_incidents": is_human and (is_sec or is_admin),
        "can_manage_config": is_admin,
        "can_manage_users": is_admin,
        "can_run_security_lab": any_human,
        "can_search_downstream": True,
    }


@dataclass
class AuthPrincipal:
    """Verified identity, roles, tenant, and clearance derived strictly from a token."""
    sub: str
    identity: str
    display_name: str
    roles: List[str]
    tenant_id: str
    clearance: str
    actor_type: str
    agent_id: Optional[str] = None
    agent_persona: Optional[str] = None
    jti: str = ""
    exp: Optional[int] = None
    auth_method: str = "bearer"

    def __post_init__(self) -> None:
        self.sub = str(self.sub or "").strip()
        self.identity = str(self.identity or "").strip()
        if not self.sub or not self.identity:
            raise ValueError("Principal requires non-empty 'sub' and 'identity'.")
        self.display_name = str(self.display_name or self.identity).strip()
        self.roles = validate_roles(self.roles)
        self.tenant_id = validate_tenant_id(self.tenant_id)
        self.clearance = validate_clearance(self.clearance)
        expected_actor = "agent" if ROLE_AGENT in self.roles else "human"
        if str(self.actor_type or "").strip().lower() not in {"", expected_actor}:
            raise ValueError(
                f"actor_type '{self.actor_type}' conflicts with roles {self.roles} (expected '{expected_actor}')."
            )
        self.actor_type = expected_actor
        self.agent_id = str(self.agent_id).strip() if self.agent_id else None
        self.agent_persona = str(self.agent_persona).strip() if self.agent_persona else None
        validate_agent_persona_clearance(self.roles, self.clearance, self.agent_persona)

    @property
    def is_human(self) -> bool:
        return self.actor_type == "human"

    @property
    def capabilities(self) -> Dict[str, bool]:
        return compute_capabilities(self.roles, self.clearance, self.actor_type)

    def has_role(self, role: str) -> bool:
        return str(role or "").strip().lower() in self.roles

    def has_any_role(self, allowed: Iterable[str]) -> bool:
        allowed_set = {str(r).strip().lower() for r in allowed}
        return bool(set(self.roles) & allowed_set)

    def clearance_rank(self) -> int:
        return CLEARANCE_RANKS[self.clearance]

    def can_access_tier(self, sop_tier: str) -> bool:
        tier = str(sop_tier or "L1").strip().upper()
        if tier not in CLEARANCE_RANKS:
            return False
        return CLEARANCE_RANKS[tier] <= self.clearance_rank()

    def ledger_delete_role(self) -> Optional[str]:
        if not self.is_human:
            return None
        if ROLE_ADMIN in self.roles:
            return "admin"
        if ROLE_PROCESS_OWNER in self.roles:
            return "owner"
        return None

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "sub": self.sub,
            "identity": self.identity,
            "display_name": self.display_name,
            "roles": list(self.roles),
            "tenant_id": self.tenant_id,
            "clearance": self.clearance,
            "actor_type": self.actor_type,
            "agent_id": self.agent_id,
            "agent_persona": self.agent_persona,
            "capabilities": self.capabilities,
        }


@dataclass
class UserRecord:
    """Persisted local user or downstream agent service account."""
    sub: str
    username: str
    identity: str
    display_name: str
    password_hash: Optional[str]
    roles: List[str]
    tenant_id: str
    clearance: str
    actor_type: str
    agent_id: Optional[str] = None
    agent_persona: Optional[str] = None
    disabled: bool = False
    created_at: str = ""
    updated_at: str = ""
    last_login_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "sub": self.sub,
            "username": self.username,
            "identity": self.identity,
            "display_name": self.display_name,
            "roles": list(self.roles),
            "tenant_id": self.tenant_id,
            "clearance": self.clearance,
            "actor_type": self.actor_type,
            "agent_id": self.agent_id,
            "agent_persona": self.agent_persona,
            "disabled": bool(self.disabled),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_login_at": self.last_login_at,
            "capabilities": compute_capabilities(self.roles, self.clearance, self.actor_type),
        }

    def to_principal(self, jti: str = "", exp: Optional[int] = None, auth_method: str = "bearer") -> AuthPrincipal:
        return AuthPrincipal(
            sub=self.sub,
            identity=self.identity,
            display_name=self.display_name,
            roles=list(self.roles),
            tenant_id=self.tenant_id,
            clearance=self.clearance,
            actor_type=self.actor_type,
            agent_id=self.agent_id,
            agent_persona=self.agent_persona,
            jti=jti,
            exp=exp,
            auth_method=auth_method,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserRecord":
        return cls(**data)


__all__ = [
    "ROLE_PROCESS_OWNER",
    "ROLE_SECURITY_REVIEWER",
    "ROLE_ADMIN",
    "ROLE_AGENT",
    "HUMAN_ROLES",
    "ROLE_SET",
    "VALID_CLEARANCES",
    "TENANT_ID_RE",
    "USERNAME_RE",
    "validate_tenant_id",
    "validate_roles",
    "validate_clearance",
    "validate_agent_persona_clearance",
    "normalize_identity_key",
    "compute_capabilities",
    "AuthPrincipal",
    "UserRecord",
]

