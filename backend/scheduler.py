"""
Scheduled SOP Ingestion Worker — Standalone Version
=====================================================
Extracted from ingestion_pipe/scheduler.py in the main app.

Polls ``knowledge_base/_uploads/`` on a configurable interval (default 10 min)
and converts any new or modified raw SOP files into OKF Playbooks using the
JIT converter + plan validator.

Processed files are tracked via a JSON manifest so they are not re-processed
unless their modification time changes (i.e. the user re-uploads a fixed
version).
"""

import datetime
import json
import os
import sys
import threading
import time
from typing import Optional

# pyrefly: ignore [missing-import]
from agents.a1_ingestion import ALLOWED_EXTENSIONS


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
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
MANIFEST_PATH = os.path.join(UPLOADS_DIR, "_processed_manifest.json")

SUPPORTED_EXTENSIONS = tuple(ALLOWED_EXTENSIONS)

# Configurable via .env; falls back to 10 minutes.
DEFAULT_INTERVAL_MINUTES = int(os.environ.get("SOP_SCAN_INTERVAL_MINUTES", "10"))

# Module-level state exposed to the status endpoint.
_scheduler_state = {
    "running": False,
    "disabled": True,
    "disabled_reason": (
        "Disabled (C1): background directory scanning bypassed Agent A3-A6 governance "
        "and HITL review. Use governed single-file ingestion via POST /api/uploads/ingest."
    ),
    "interval_minutes": DEFAULT_INTERVAL_MINUTES,
    "last_run_at": None,
    "next_run_at": None,
    "last_run_summary": None,
    "total_runs": 0,
}
_scheduler_lock = threading.Lock()


def _log(msg: str):
    """Writes scheduler log messages safely to stderr so stdio MCP transport is not corrupted."""
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def _load_manifest() -> dict:
    """Load the processed-files manifest from disk."""
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            _log(f"[SOP Scheduler] Warning: could not read manifest, starting fresh ({e})")
    return {}


def _save_manifest(manifest: dict):
    """Persist the manifest back to disk."""
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Core scan & convert cycle
# ---------------------------------------------------------------------------

def run_ingestion_cycle() -> dict:
    """Blocked (C1): ungoverned batch scan-and-commit cycle is disabled pending A1-A6 queue wiring."""
    msg = (
        "Ungoverned scheduler ingestion cycle is disabled (C1) because it bypassed "
        "Agent A3 secret/AST quarantine, Agent A4 verification, Agent A5 dual-custody "
        "HITL review, and Agent A6 publication gates. Use POST /api/uploads/ingest or trace_pipeline.py."
    )
    _log(f"[SOP Scheduler] [GOVERNANCE BLOCKED] {msg}")
    raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# Background scheduler thread
# ---------------------------------------------------------------------------

def _scheduler_loop(interval_minutes: int):
    """Runs forever on a daemon thread, calling run_ingestion_cycle every N minutes."""
    interval_seconds = interval_minutes * 60

    # Run the first cycle immediately on startup so any pending files are processed.
    _log(f"[SOP Scheduler] Running initial ingestion cycle on startup...")
    try:
        summary = run_ingestion_cycle()
        with _scheduler_lock:
            _scheduler_state["last_run_at"] = datetime.datetime.now().isoformat()
            _scheduler_state["last_run_summary"] = summary
            _scheduler_state["total_runs"] += 1
    except Exception as e:
        _log(f"[SOP Scheduler] Error during initial cycle: {e}")

    while True:
        next_run = datetime.datetime.now() + datetime.timedelta(seconds=interval_seconds)
        with _scheduler_lock:
            _scheduler_state["next_run_at"] = next_run.isoformat()

        time.sleep(interval_seconds)

        _log(f"\n[SOP Scheduler] Scheduled cycle triggered at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            summary = run_ingestion_cycle()
            with _scheduler_lock:
                _scheduler_state["last_run_at"] = datetime.datetime.now().isoformat()
                _scheduler_state["last_run_summary"] = summary
                _scheduler_state["total_runs"] += 1
        except Exception as e:
            _log(f"[SOP Scheduler] Error during scheduled cycle: {e}")


def start_sop_ingestion_scheduler(interval_minutes: Optional[int] = None):
    """Disabled (C1): refuses to start an ungoverned background watcher thread."""
    with _scheduler_lock:
        _scheduler_state["running"] = False
        _scheduler_state["disabled"] = True
        status = dict(_scheduler_state)
    _log(f"[SOP Scheduler] [GOVERNANCE BLOCKED] {status['disabled_reason']}")
    return status


def get_scheduler_status() -> dict:
    """Returns the current scheduler state for the status API endpoint."""
    with _scheduler_lock:
        return dict(_scheduler_state)
