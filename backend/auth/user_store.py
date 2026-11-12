"""
Local User Store & Brute-Force Rate Limiter (C2)
================================================
Thread-safe, atomic JSON persistence at knowledge_base/_auth/users.json
(or ELONE_USERS_PATH override), plus sliding-window lockout after repeated
failed password attempts.
"""

import os
import json
import time
import uuid
import datetime
import threading
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Any

from .config import (
    get_users_path,
    get_lockout_policy,
    get_default_tenant,
)
from .models import (
    UserRecord,
    ROLE_AGENT,
    USERNAME_RE,
    validate_roles,
    validate_tenant_id,
    validate_clearance,
    validate_agent_persona_clearance,
    normalize_identity_key,
)
from .passwords import hash_password, verify_password, verify_dummy_password


class AccountExistsError(ValueError):
    """Raised when attempting to create a duplicate username or identity."""


class AccountNotFoundError(KeyError):
    """Raised when target user sub or username does not exist."""


class AuthenticationFailedError(PermissionError):
    """Raised on invalid credentials or disabled account."""


class RateLimitExceededError(PermissionError):
    """Raised when login failures exceed configured brute-force threshold."""

    def __init__(self, retry_after: int):
        super().__init__(f"Too many failed login attempts. Try again in {retry_after} seconds.")
        self.retry_after = max(1, int(retry_after))


class LoginRateLimiter:
    """Sliding-window brute-force limiter keyed by (client_ip, username)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._failures: Dict[Tuple[str, str], List[float]] = defaultdict(list)

    def _prune_locked(self, key: Tuple[str, str], now: float, window: int) -> List[float]:
        cutoff = now - window
        kept = [ts for ts in self._failures.get(key, []) if ts >= cutoff]
        if kept:
            self._failures[key] = kept
        else:
            self._failures.pop(key, None)
        return kept

    def check_allowed(self, client_ip: str, username: str) -> None:
        max_attempts, window = get_lockout_policy()
        key = (str(client_ip or "127.0.0.1"), str(username or "").strip().lower())
        now = time.time()
        with self._lock:
            kept = self._prune_locked(key, now, window)
            if len(kept) >= max_attempts:
                oldest = kept[0]
                retry_after = max(1, int((oldest + window) - now) + 1)
                raise RateLimitExceededError(retry_after=retry_after)

    def record_failure(self, client_ip: str, username: str) -> None:
        _, window = get_lockout_policy()
        key = (str(client_ip or "127.0.0.1"), str(username or "").strip().lower())
        now = time.time()
        with self._lock:
            kept = self._prune_locked(key, now, window)
            kept.append(now)
            self._failures[key] = kept

    def clear(self, client_ip: str, username: str) -> None:
        key = (str(client_ip or "127.0.0.1"), str(username or "").strip().lower())
        with self._lock:
            self._failures.pop(key, None)

    def reset_all_for_tests(self) -> None:
        with self._lock:
            self._failures.clear()


login_rate_limiter = LoginRateLimiter()


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class UserStore:
    """Thread-safe JSON-backed user and downstream service-account repository."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache_path: Optional[str] = None
        self._cache_mtime_ns: Optional[int] = None
        self._users: Dict[str, UserRecord] = {}

    def _load_locked(self, path: str) -> Dict[str, UserRecord]:
        if not os.path.exists(path):
            self._cache_path = path
            self._cache_mtime_ns = None
            self._users = {}
            return self._users
        stat = os.stat(path)
        mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
        if self._cache_path == path and self._cache_mtime_ns == mtime_ns:
            return self._users
        if os.path.getsize(path) == 0:
            self._users = {}
        else:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            records = raw.get("users", raw) if isinstance(raw, dict) else []
            loaded: Dict[str, UserRecord] = {}
            if isinstance(records, list):
                for item in records:
                    rec = UserRecord.from_dict(item)
                    loaded[rec.sub] = rec
            elif isinstance(records, dict):
                for k, item in records.items():
                    rec = UserRecord.from_dict(item)
                    loaded[rec.sub] = rec
            self._users = loaded
        self._cache_path = path
        self._cache_mtime_ns = mtime_ns
        return self._users

    def _save_locked(self, path: str, users: Dict[str, UserRecord]) -> None:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
        payload = {
            "schema_version": "1.0",
            "updated_at": _utc_now(),
            "users": [u.to_dict() for u in users.values()],
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, path)
        self._users = users
        self._cache_path = path
        try:
            st = os.stat(path)
            self._cache_mtime_ns = getattr(st, "st_mtime_ns", None)
        except Exception:
            self._cache_mtime_ns = None

    def list_users(self, tenant_id: Optional[str] = None) -> List[UserRecord]:
        path = get_users_path()
        with self._lock:
            users = self._load_locked(path)
            recs = list(users.values())
            if tenant_id is not None:
                recs = [r for r in recs if r.tenant_id == tenant_id]
            return recs

    def get_by_sub(self, sub: str) -> Optional[UserRecord]:
        path = get_users_path()
        with self._lock:
            users = self._load_locked(path)
            return users.get(str(sub or "").strip())

    def get_by_username(self, username: str) -> Optional[UserRecord]:
        clean = str(username or "").strip().lower()
        if not clean:
            return None
        path = get_users_path()
        with self._lock:
            users = self._load_locked(path)
            for rec in users.values():
                if rec.username.lower() == clean or rec.identity.lower() == clean:
                    return rec
            return None

    def create_user(
        self,
        *,
        username: str,
        password: Optional[str],
        roles: Any,
        tenant_id: Optional[str] = None,
        clearance: str = "L1",
        identity: Optional[str] = None,
        display_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_persona: Optional[str] = None,
        disabled: bool = False,
        min_password_length: int = 8,
    ) -> UserRecord:
        clean_username = str(username or "").strip().lower()
        if not USERNAME_RE.fullmatch(clean_username):
            raise ValueError(
                "Invalid username. Use 2-64 alphanumeric, '.', '_', '-', or '@' characters."
            )
        clean_identity = str(identity or clean_username).strip()
        if not clean_identity:
            raise ValueError("User identity cannot be empty.")

        clean_roles = validate_roles(roles)
        clean_tenant = validate_tenant_id(tenant_id or get_default_tenant())
        clean_clearance = validate_clearance(clearance)
        actor_type = "agent" if ROLE_AGENT in clean_roles else "human"
        clean_agent_id = str(agent_id).strip() if agent_id else (f"agent_{clean_username}" if actor_type == "agent" else None)
        clean_persona = str(agent_persona).strip() if agent_persona else None
        validate_agent_persona_clearance(clean_roles, clean_clearance, clean_persona)

        if actor_type == "human" and not password:
            raise ValueError("Password is required for human user accounts.")
        if password is not None:
            if len(password) < min_password_length:
                raise ValueError(f"Password must be at least {min_password_length} characters.")
            pw_hash = hash_password(password)
        else:
            pw_hash = None

        now = _utc_now()
        path = get_users_path()
        with self._lock:
            users = dict(self._load_locked(path))
            for existing in users.values():
                if existing.username.lower() == clean_username:
                    raise AccountExistsError(f"Username '{clean_username}' already exists.")
                if normalize_identity_key(existing.identity) == normalize_identity_key(clean_identity):
                    raise AccountExistsError(f"Identity '{clean_identity}' already exists.")

            sub = f"usr_{uuid.uuid4().hex[:12]}"
            rec = UserRecord(
                sub=sub,
                username=clean_username,
                identity=clean_identity,
                display_name=str(display_name or clean_identity).strip(),
                password_hash=pw_hash,
                roles=clean_roles,
                tenant_id=clean_tenant,
                clearance=clean_clearance,
                actor_type=actor_type,
                agent_id=clean_agent_id,
                agent_persona=clean_persona,
                disabled=bool(disabled),
                created_at=now,
                updated_at=now,
                last_login_at=None,
            )
            users[sub] = rec
            self._save_locked(path, users)
            return rec

    def update_user(
        self,
        sub: str,
        *,
        roles: Any = None,
        clearance: Optional[str] = None,
        display_name: Optional[str] = None,
        disabled: Optional[bool] = None,
        password: Optional[str] = None,
        agent_persona: Optional[str] = None,
        min_password_length: int = 8,
    ) -> UserRecord:
        path = get_users_path()
        with self._lock:
            users = dict(self._load_locked(path))
            rec = users.get(sub)
            if not rec:
                raise AccountNotFoundError(f"User '{sub}' not found.")

            new_roles = validate_roles(roles) if roles is not None else list(rec.roles)
            new_actor = "agent" if ROLE_AGENT in new_roles else "human"
            new_clearance = validate_clearance(clearance) if clearance is not None else rec.clearance
            new_persona = rec.agent_persona if agent_persona is None else (str(agent_persona).strip() or None)
            validate_agent_persona_clearance(new_roles, new_clearance, new_persona)

            if password is not None:
                if len(password) < min_password_length:
                    raise ValueError(f"Password must be at least {min_password_length} characters.")
                rec.password_hash = hash_password(password)
            if new_actor == "human" and not rec.password_hash:
                raise ValueError("Password is required when enabling or switching to a human role.")

            rec.roles = new_roles
            rec.actor_type = new_actor
            rec.clearance = new_clearance
            rec.agent_persona = new_persona
            if display_name is not None:
                rec.display_name = str(display_name).strip() or rec.identity
            if disabled is not None:
                rec.disabled = bool(disabled)
            rec.updated_at = _utc_now()
            users[sub] = rec
            self._save_locked(path, users)
            return rec

    def authenticate(self, username: str, password: str, client_ip: str = "127.0.0.1") -> UserRecord:
        clean_user = str(username or "").strip().lower()
        login_rate_limiter.check_allowed(client_ip, clean_user)

        rec = self.get_by_username(clean_user)
        if rec is None or not rec.password_hash:
            verify_dummy_password(password)
            login_rate_limiter.record_failure(client_ip, clean_user)
            raise AuthenticationFailedError("Invalid username or password.")

        ok = verify_password(password, rec.password_hash)
        if not ok or rec.disabled:
            login_rate_limiter.record_failure(client_ip, clean_user)
            if rec.disabled and ok:
                raise AuthenticationFailedError("Account is disabled. Contact an administrator.")
            raise AuthenticationFailedError("Invalid username or password.")

        login_rate_limiter.clear(client_ip, clean_user)
        path = get_users_path()
        with self._lock:
            users = dict(self._load_locked(path))
            stored = users.get(rec.sub)
            if stored:
                stored.last_login_at = _utc_now()
                users[rec.sub] = stored
                self._save_locked(path, users)
                return stored
        return rec


user_store = UserStore()

__all__ = [
    "AccountExistsError",
    "AccountNotFoundError",
    "AuthenticationFailedError",
    "RateLimitExceededError",
    "LoginRateLimiter",
    "login_rate_limiter",
    "UserStore",
    "user_store",
]

