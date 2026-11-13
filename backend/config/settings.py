"""
Dynamic Pipeline Settings & Configuration Manager
=================================================
Centralized management for dynamically configurable settings:
  - File input size limit (10MB - 50MB+)
  - Images allowed per document (10 - 15+ images)
  - Document page limits (10 - 20+ pages)
  - Dynamic LLM provider & model mappings
  - Daily quota circuit-breakers & governance thresholds

Precedence Order:
  1. Environment Variables in .env (e.g., MAX_FILE_SIZE_MB, MAX_IMAGES_PER_SOP)
  2. Configuration File: backend/config/pipeline_config.json
  3. Safe Hardcoded Defaults
"""

import logging

_log = logging.getLogger(__name__)

import os
import json
import threading
from typing import Dict, Any, List, Set, Optional
from dotenv import load_dotenv

_CONFIG_LOCK = threading.RLock()
_AUDIT_LOCK = threading.RLock()

load_dotenv()

try:
    from utils.pipeline_logger import log_warning, log_error
except ImportError:
    try:
        from backend.utils.pipeline_logger import log_warning, log_error
    except ImportError:
        def log_warning(tag, msg): print(f"[{tag} Warning] {msg}")
        def log_error(tag, msg): print(f"[{tag} Error] {msg}")

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(CONFIG_DIR, "pipeline_config.json")
SETTINGS_JSON_PATH = os.path.join(CONFIG_DIR, "settings.json")

# Default fallback dictionary
_DEFAULT_CONFIG: Dict[str, Any] = {
    "file_upload": {
        "max_file_size_mb": 50.0,
        "max_page_count": 10,
        "max_text_lines": 600,
        "max_text_words": 5000,
        "max_table_rows": 600,
        "upload_chunk_bytes": 65536,
        "max_uncompressed_zip_mb": 50.0,
        "max_zip_compression_ratio": 20.0,
        "allowed_extensions": [".pdf", ".docx", ".csv", ".xls", ".xlsx", ".md", ".txt"],
    },
    "images": {
        "max_images_per_sop": 15,
        "max_image_dimension": 4096,
        "target_image_dimension": 1024,
        "allowed_extensions": [".png", ".jpg", ".jpeg", ".webp", ".gif"],
    },
    "llm_models": {
        "execution_planning": {
            "provider": "mistral",
            "model": "codestral-latest",
            "temperature": 0.0,
            "fallbacks": [
                {"provider": "groq", "model": "qwen/qwen3.8-27b"},
            ],
        },
        "planning_validation": {
            "provider": "mistral",
            "model": "codestral-latest",
            "temperature": 0.0,
            "fallbacks": [
                {"provider": "groq", "model": "qwen/qwen3.8-27b"},
            ],
        },
        "vlm_image_analysis": {
            "provider": "nvidia",
            "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            "temperature": 0.2,
            "timeout": 150,
            "fallbacks": [
                {"provider": "openrouter", "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"},
                {"provider": "nvidia", "model": "meta/llama-3.2-11b-vision-instruct"},
            ],
        },
    },
    # Output-token cap per provider. Providers not listed use their own default.
    "llm_limits": {
        "max_output_tokens": {"groq": 2048, "zai": 2048, "nvidia": 4096},
    },
    "governance": {
        "min_passing_score": 80.0,
        "max_daily_calls": 200,
        "unlimited_daily_calls": False,
        "max_calls_per_job": 25,
        "llm_timeout_seconds": 120,
        "llm_max_retries": 2,
        "sop_scan_interval_minutes": 10,
        "max_agent_calls_per_job": 30,
    },
    "link_scraper": {
        "max_output_chars": 4000,
        "max_redirect_hops": 3,
        "timeout_seconds": 10,
    },
    "cost": {
        "usd_to_inr_rate": 87.0,
    },
    "execution_mode": "auto",
}


class PipelineSettings:
    """Thread-safe dynamic configuration reader and updater."""

    def __init__(self, config_path: str = SETTINGS_JSON_PATH):
        self._config_path = config_path if os.path.exists(config_path) else CONFIG_FILE_PATH
        self._cached_config: Dict[str, Any] = {}
        self.reload()

    def reload(self) -> Dict[str, Any]:
        """Reload configuration from disk and overlay environment variable overrides."""
        cfg = json.loads(json.dumps(_DEFAULT_CONFIG))

        # Check settings.json first, then pipeline_config.json
        candidate_paths = [SETTINGS_JSON_PATH, CONFIG_FILE_PATH]
        loaded_file = False
        for cpath in candidate_paths:
            if os.path.exists(cpath):
                try:
                    with open(cpath, "r", encoding="utf-8") as f:
                        file_data = json.load(f)
                        # Deep merge file data over defaults
                        for section, values in file_data.items():
                            if section.startswith("_"):
                                continue
                            if isinstance(values, dict) and section in cfg:
                                cfg[section].update(values)
                            else:
                                cfg[section] = values
                    self._config_path = cpath
                    loaded_file = True
                    break
                except Exception as e:
                    log_warning("Config", f"Could not parse '{cpath}': {e}. Trying fallback.")

        # Snapshot of file+defaults BEFORE env overrides, so save() never persists env values.
        self._file_config = json.loads(json.dumps(cfg))

        # Overlay Environment Variable Overrides (Highest Precedence)
        if os.environ.get("MAX_FILE_SIZE_MB"):
            try:
                cfg["file_upload"]["max_file_size_mb"] = float(os.environ["MAX_FILE_SIZE_MB"])
            except ValueError as _exc:
                _log.debug("reload: value could not be parsed, keeping default (%s: %s)", type(_exc).__name__, _exc)

        if os.environ.get("MAX_PAGE_COUNT"):
            try:
                cfg["file_upload"]["max_page_count"] = int(os.environ["MAX_PAGE_COUNT"])
            except ValueError as _exc:
                _log.debug("reload: value could not be parsed, keeping default (%s: %s)", type(_exc).__name__, _exc)

        if os.environ.get("MAX_IMAGES_PER_SOP"):
            try:
                cfg["images"]["max_images_per_sop"] = int(os.environ["MAX_IMAGES_PER_SOP"])
            except ValueError as _exc:
                _log.debug("reload: value could not be parsed, keeping default (%s: %s)", type(_exc).__name__, _exc)

        if os.environ.get("PLANNING_PROVIDER"):
            cfg["llm_models"]["execution_planning"]["provider"] = os.environ["PLANNING_PROVIDER"].lower()
        if os.environ.get("PLANNING_MODEL"):
            cfg["llm_models"]["execution_planning"]["model"] = os.environ["PLANNING_MODEL"]

        if os.environ.get("VALIDATION_PROVIDER"):
            cfg["llm_models"]["planning_validation"]["provider"] = os.environ["VALIDATION_PROVIDER"].lower()
        if os.environ.get("VALIDATION_MODEL"):
            cfg["llm_models"]["planning_validation"]["model"] = os.environ["VALIDATION_MODEL"]

        if os.environ.get("VLM_PROVIDER"):
            cfg["llm_models"]["vlm_image_analysis"]["provider"] = os.environ["VLM_PROVIDER"].lower()
        if os.environ.get("VLM_MODEL"):
            cfg["llm_models"]["vlm_image_analysis"]["model"] = os.environ["VLM_MODEL"]

        if os.environ.get("GROQ_MODEL"):
            for role_cfg in cfg["llm_models"].values():
                if not isinstance(role_cfg, dict):
                    continue
                for fb in role_cfg.get("fallbacks") or []:
                    if isinstance(fb, dict) and str(fb.get("provider", "")).lower() == "groq":
                        fb["model"] = os.environ["GROQ_MODEL"]

        if os.environ.get("UNLIMITED_DAILY_CALLS", "").strip().lower() in ("1", "true", "yes"):
            cfg["governance"]["unlimited_daily_calls"] = True
            cfg["governance"]["max_daily_calls"] = 0

        if os.environ.get("MAX_DAILY_CALLS"):
            try:
                val = int(os.environ["MAX_DAILY_CALLS"])
                cfg["governance"]["max_daily_calls"] = val
                if val <= 0:
                    cfg["governance"]["unlimited_daily_calls"] = True
            except ValueError as _exc:
                _log.debug("reload: value could not be parsed, keeping default (%s: %s)", type(_exc).__name__, _exc)

        if os.environ.get("EXECUTION_MODE"):
            cfg["execution_mode"] = os.environ["EXECUTION_MODE"].strip().lower()

        with _CONFIG_LOCK:
            self._cached_config = cfg
        # Hand the active model map to llm_config (also drops cached LLM clients).
        # Fails harmlessly while llm_config is still mid-import; it then pulls the
        # map itself at the end of its own import.
        try:
            import config.llm_config as _llm_config
            _llm_config.apply_llm_models(cfg.get("llm_models", {}))
        except Exception as _exc:
            _log.debug("reload: model map not applied yet (import still in progress) (%s: %s)", type(_exc).__name__, _exc)
        return self._cached_config

    def get_all(self) -> Dict[str, Any]:
        """Returns the full active configuration dictionary."""
        return self._cached_config

    def save(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Applies dynamic updates and persists them to settings.json and pipeline_config.json."""
        with _CONFIG_LOCK:
            base = json.loads(json.dumps(getattr(self, "_file_config", None) or self._cached_config))
            for section, values in updates.items():
                if section in base and isinstance(values, dict):
                    base[section].update(values)
                else:
                    base[section] = values

            for p in (SETTINGS_JSON_PATH, CONFIG_FILE_PATH):
                try:
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump(base, f, indent=2)
                except Exception as e:
                    log_error("Config", f"Failed to write config to '{p}': {e}")

            # Re-apply env overrides on top of freshly saved file values and clear cached LLM clients.
            return self.reload()

    # --- Property Helpers ---
    @property
    def max_file_size_mb(self) -> float:
        return float(self._cached_config.get("file_upload", {}).get("max_file_size_mb", 50.0))

    @property
    def max_file_size_bytes(self) -> int:
        return int(self.max_file_size_mb * 1024 * 1024)

    @property
    def max_page_count(self) -> int:
        return int(self._cached_config.get("file_upload", {}).get("max_page_count", 10))

    @property
    def max_text_lines(self) -> int:
        return int(self._cached_config.get("file_upload", {}).get("max_text_lines", 600))

    @property
    def max_text_words(self) -> int:
        return int(self._cached_config.get("file_upload", {}).get("max_text_words", 5000))

    @property
    def max_table_rows(self) -> int:
        return int(self._cached_config.get("file_upload", {}).get("max_table_rows", 600))

    @property
    def allowed_file_extensions(self) -> Set[str]:
        return set(self._cached_config.get("file_upload", {}).get("allowed_extensions", []))

    @property
    def max_images_per_sop(self) -> int:
        return int(self._cached_config.get("images", {}).get("max_images_per_sop", 15))

    @property
    def max_image_dimension(self) -> int:
        return int(self._cached_config.get("images", {}).get("max_image_dimension", 4096))

    @property
    def target_image_dimension(self) -> int:
        return int(self._cached_config.get("images", {}).get("target_image_dimension", 1024))

    @property
    def allowed_image_extensions(self) -> Set[str]:
        return set(self._cached_config.get("images", {}).get("allowed_extensions", []))

    @property
    def llm_models(self) -> Dict[str, Any]:
        return self._cached_config.get("llm_models", {})

    @property
    def is_unlimited_daily_calls(self) -> bool:
        gov = self._cached_config.get("governance", {})
        if gov.get("unlimited_daily_calls") is True:
            return True
        max_c = gov.get("max_daily_calls", 0)
        return max_c in (0, -1, "unlimited", "infinite", None)

    @property
    def max_daily_calls(self) -> int:
        if self.is_unlimited_daily_calls:
            return 0
        return int(self._cached_config.get("governance", {}).get("max_daily_calls", 0))

    @property
    def max_calls_per_job(self) -> int:
        return max(1, int(self._cached_config.get("governance", {}).get("max_calls_per_job", 25)))

    @property
    def llm_timeout_seconds(self) -> float:
        return float(self._cached_config.get("governance", {}).get("llm_timeout_seconds", 120))

    @property
    def llm_max_retries(self) -> int:
        return int(self._cached_config.get("governance", {}).get("llm_max_retries", 2))

    @property
    def min_passing_score(self) -> float:
        return float(self._cached_config.get("governance", {}).get("min_passing_score", 80.0))

    @property
    def upload_chunk_bytes(self) -> int:
        return max(4096, int(self._cached_config.get("file_upload", {}).get("upload_chunk_bytes", 65536)))

    @property
    def max_uncompressed_zip_bytes(self) -> int:
        return int(float(self._cached_config.get("file_upload", {}).get("max_uncompressed_zip_mb", 50.0)) * 1024 * 1024)

    @property
    def max_zip_compression_ratio(self) -> float:
        return float(self._cached_config.get("file_upload", {}).get("max_zip_compression_ratio", 20.0))

    @property
    def max_agent_calls_per_job(self) -> int:
        return max(1, int(self._cached_config.get("governance", {}).get("max_agent_calls_per_job", 30)))

    @property
    def scrape_max_output_chars(self) -> int:
        return int(self._cached_config.get("link_scraper", {}).get("max_output_chars", 4000))

    @property
    def scrape_max_redirect_hops(self) -> int:
        return int(self._cached_config.get("link_scraper", {}).get("max_redirect_hops", 3))

    @property
    def scrape_timeout_seconds(self) -> float:
        return float(self._cached_config.get("link_scraper", {}).get("timeout_seconds", 10))

    @property
    def usd_to_inr_rate(self) -> float:
        return float(self._cached_config.get("cost", {}).get("usd_to_inr_rate", 87.0))

    def max_output_tokens(self, provider: str, default: Optional[int] = None) -> Optional[int]:
        caps = self._cached_config.get("llm_limits", {}).get("max_output_tokens", {}) or {}
        val = caps.get(str(provider).lower())
        return int(val) if val else default

    @property
    def execution_mode(self) -> str:
        return str(self._cached_config.get("execution_mode", "auto")).strip().lower()


# ---------------------------------------------------------------------------
# /api/config hardening (H1): allowlist + schema validation + audit trail
# ---------------------------------------------------------------------------
# Only these keys can be changed through the API. Anything else is rejected.
# Deliberately NOT editable via API: governance.unlimited_daily_calls, llm_models
# providers/models, allowed_extensions (change those in settings.json / env).
_NUM = (int, float)
_EDITABLE_SCHEMA: Dict[str, Dict[str, tuple]] = {
    "file_upload": {
        "max_file_size_mb": (_NUM, 1, 100),
        "max_page_count": (int, 1, 200),
        "max_text_lines": (int, 1, 5000),
        "max_text_words": (int, 1, 50000),
        "max_table_rows": (int, 1, 5000),
    },
    "images": {
        "max_images_per_sop": (int, 0, 50),
        "max_image_dimension": (int, 64, 8192),
        "target_image_dimension": (int, 64, 4096),
    },
    "governance": {
        "min_passing_score": (_NUM, 50, 100),
        "max_daily_calls": (int, 1, 5000),
        "max_calls_per_job": (int, 1, 100),
        "llm_timeout_seconds": (_NUM, 5, 600),
        "llm_max_retries": (int, 0, 5),
        "sop_scan_interval_minutes": (int, 1, 1440),
    },
}


def validate_config_updates(updates: Any) -> "tuple[Dict[str, Dict[str, Any]], List[str]]":
    """Returns (clean_updates, errors). Rejects unknown sections/keys, wrong types and out-of-range values."""
    errors: List[str] = []
    clean: Dict[str, Dict[str, Any]] = {}
    if not isinstance(updates, dict) or not updates:
        return {}, ["Body must be a non-empty JSON object."]
    for section, values in updates.items():
        if section not in _EDITABLE_SCHEMA:
            errors.append(f"Section '{section}' is not editable via API.")
            continue
        if not isinstance(values, dict):
            errors.append(f"Section '{section}' must be an object.")
            continue
        for key, val in values.items():
            rule = _EDITABLE_SCHEMA[section].get(key)
            if rule is None:
                errors.append(f"'{section}.{key}' is not editable via API.")
                continue
            types, lo, hi = rule
            if isinstance(val, bool) or not isinstance(val, types):
                errors.append(f"'{section}.{key}' has the wrong type.")
            elif not (lo <= val <= hi):
                errors.append(f"'{section}.{key}' must be between {lo} and {hi}.")
            else:
                clean.setdefault(section, {})[key] = val
    if errors:
        return {}, errors
    return clean, []


def _resolve_kb_dir() -> str:
    env_kb = os.getenv("ELONE_KB_DIR", "").strip()
    if env_kb:
        return os.path.abspath(env_kb)
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.dirname(backend_dir)
    root_kb = os.path.abspath(os.path.join(project_root, "knowledge_base"))
    local_kb = os.path.abspath(os.path.join(backend_dir, "knowledge_base"))
    if os.path.exists(root_kb) or not os.path.exists(local_kb):
        return root_kb
    return local_kb


def audit_config_change(actor: str, source_ip: str, before: Dict[str, Any], clean: Dict[str, Dict[str, Any]], outcome: str) -> None:
    """Appends one JSON line per config change attempt to <KB_DIR>/logs/config_audit.jsonl."""
    import datetime
    try:
        log_dir = os.path.join(_resolve_kb_dir(), "logs")
        diff = {
            f"{s}.{k}": {"old": before.get(s, {}).get(k), "new": v}
            for s, vals in clean.items() for k, v in vals.items()
        }
        entry = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "actor": actor,
            "ip": source_ip,
            "outcome": outcome,
            "changes": diff,
        }
        with _AUDIT_LOCK:
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, "config_audit.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
    except Exception as e:
        log_error("Config", f"Could not write config audit entry: {e}")


# Global singleton instance
settings = PipelineSettings()

# Exported helper accessor functions for clean, decoupled consumption
def get_settings() -> PipelineSettings:
    return settings

def get_execution_mode() -> str:
    return settings.execution_mode

def is_unlimited_daily_calls() -> bool:
    return settings.is_unlimited_daily_calls

def get_max_daily_calls() -> int:
    return settings.max_daily_calls

def get_max_file_size_mb() -> float:
    return settings.max_file_size_mb

def get_max_file_size_bytes() -> int:
    return settings.max_file_size_bytes

def get_max_page_count() -> int:
    return settings.max_page_count

def get_max_images_per_sop() -> int:
    return settings.max_images_per_sop

def get_max_image_dimension() -> int:
    return settings.max_image_dimension

def get_target_image_dimension() -> int:
    return settings.target_image_dimension

def get_allowed_extensions() -> Set[str]:
    return settings.allowed_file_extensions

def reload_settings() -> Dict[str, Any]:
    return settings.reload()

def update_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    return settings.save(updates)

