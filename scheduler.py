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
import threading
import time
from typing import Optional

from core.jit_converter import convert_raw_sop_to_okf


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
UPLOADS_DIR = os.path.join(KB_DIR, "_uploads")
MANIFEST_PATH = os.path.join(UPLOADS_DIR, "_processed_manifest.json")

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".doc", ".txt", ".xlsx", ".xls", ".pptx")

# Configurable via .env; falls back to 10 minutes.
DEFAULT_INTERVAL_MINUTES = int(os.environ.get("SOP_SCAN_INTERVAL_MINUTES", "10"))

# Module-level state exposed to the status endpoint.
_scheduler_state = {
    "running": False,
    "interval_minutes": DEFAULT_INTERVAL_MINUTES,
    "last_run_at": None,
    "next_run_at": None,
    "last_run_summary": None,
    "total_runs": 0,
}
_scheduler_lock = threading.Lock()


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
            print(f"[SOP Scheduler] Warning: could not read manifest, starting fresh ({e})")
    return {}


def _save_manifest(manifest: dict):
    """Persist the manifest back to disk."""
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Core scan & convert cycle
# ---------------------------------------------------------------------------

def _run_ingestion_cycle():
    """One full scan-and-convert pass over the uploads folder."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)

    raw_files = [
        f for f in os.listdir(UPLOADS_DIR)
        if os.path.isfile(os.path.join(UPLOADS_DIR, f))
        and f.lower().endswith(SUPPORTED_EXTENSIONS)
        and not f.startswith("_")  # skip manifest and other internal files
    ]

    if not raw_files:
        print("[SOP Scheduler] No raw SOP files found in _uploads/. Nothing to process.")
        return {"processed": 0, "skipped": 0, "failed": 0, "details": []}

    manifest = _load_manifest()
    processed = 0
    skipped = 0
    failed = 0
    details = []

    for filename in sorted(raw_files):
        filepath = os.path.join(UPLOADS_DIR, filename)
        file_mtime = os.path.getmtime(filepath)

        # Check manifest: skip if already processed and file hasn't changed.
        existing = manifest.get(filename)
        if existing and existing.get("status") == "success" and existing.get("mtime") == file_mtime:
            skipped += 1
            continue

        # Also skip if previously failed AND file hasn't been modified since.
        if existing and existing.get("status") == "failed" and existing.get("mtime") == file_mtime:
            skipped += 1
            continue

        # New or modified file → convert.
        print(f"\n[SOP Scheduler] Processing: {filename} ...")
        try:
            okf_path, metadata = convert_raw_sop_to_okf(filepath)
            sop_id = metadata.get("sop_id", "UNKNOWN")
            print(f"[SOP Scheduler] Successfully converted '{filename}' -> {os.path.basename(okf_path)} (SOP ID: {sop_id})")

            manifest[filename] = {
                "status": "success",
                "mtime": file_mtime,
                "sop_id": sop_id,
                "okf_path": okf_path,
                "converted_at": datetime.datetime.now().isoformat(),
            }
            processed += 1
            details.append({"file": filename, "status": "success", "sop_id": sop_id})

        except Exception as err:
            print(f"[SOP Scheduler] Failed to convert '{filename}': {err}")
            manifest[filename] = {
                "status": "failed",
                "mtime": file_mtime,
                "error": str(err),
                "failed_at": datetime.datetime.now().isoformat(),
            }
            failed += 1
            details.append({"file": filename, "status": "failed", "error": str(err)})

    _save_manifest(manifest)

    summary = {"processed": processed, "skipped": skipped, "failed": failed, "details": details}
    print(f"[SOP Scheduler] Cycle complete — Processed: {processed}, Skipped: {skipped}, Failed: {failed}")
    return summary


# ---------------------------------------------------------------------------
# Background scheduler thread
# ---------------------------------------------------------------------------

def _scheduler_loop(interval_minutes: int):
    """Runs forever on a daemon thread, calling _run_ingestion_cycle every N minutes."""
    interval_seconds = interval_minutes * 60

    # Run the first cycle immediately on startup so any pending files are
    # processed without waiting for the first interval to elapse.
    print(f"[SOP Scheduler] Running initial ingestion cycle on startup...")
    try:
        summary = _run_ingestion_cycle()
        with _scheduler_lock:
            _scheduler_state["last_run_at"] = datetime.datetime.now().isoformat()
            _scheduler_state["last_run_summary"] = summary
            _scheduler_state["total_runs"] += 1
    except Exception as e:
        print(f"[SOP Scheduler] Error during initial cycle: {e}")

    while True:
        next_run = datetime.datetime.now() + datetime.timedelta(seconds=interval_seconds)
        with _scheduler_lock:
            _scheduler_state["next_run_at"] = next_run.isoformat()

        time.sleep(interval_seconds)

        print(f"\n[SOP Scheduler] Scheduled cycle triggered at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            summary = _run_ingestion_cycle()
            with _scheduler_lock:
                _scheduler_state["last_run_at"] = datetime.datetime.now().isoformat()
                _scheduler_state["last_run_summary"] = summary
                _scheduler_state["total_runs"] += 1
        except Exception as e:
            print(f"[SOP Scheduler] Error during scheduled cycle: {e}")


def start_sop_ingestion_scheduler(interval_minutes: Optional[int] = None):
    """Start the SOP ingestion scheduler as a background daemon thread.

    Safe to call multiple times — only the first call starts the thread.
    """
    interval = interval_minutes or DEFAULT_INTERVAL_MINUTES

    with _scheduler_lock:
        if _scheduler_state["running"]:
            print("[SOP Scheduler] Already running. Ignoring duplicate start request.")
            return
        _scheduler_state["running"] = True
        _scheduler_state["interval_minutes"] = interval

    print(f"[SOP Scheduler] Starting background worker. Scanning every {interval} minutes.")
    print(f"[SOP Scheduler] Watching folder: {UPLOADS_DIR}")

    thread = threading.Thread(
        target=_scheduler_loop,
        args=(interval,),
        daemon=True,
        name="sop-ingestion-scheduler",
    )
    thread.start()


def get_scheduler_status() -> dict:
    """Returns the current scheduler state for the status API endpoint."""
    with _scheduler_lock:
        return dict(_scheduler_state)
