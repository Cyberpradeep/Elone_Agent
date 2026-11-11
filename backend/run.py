"""
SOP Ingestion Pipeline — Standalone CLI Runner
================================================
Use this to test ingestion outside the main FastAPI app.

Usage:
  # Process a single file:
  python run.py --file knowledge_base/_uploads/my_sop.pdf

  # Process a single file with custom SOP ID:
  python run.py --file knowledge_base/_uploads/my_sop.pdf --sop-id SOP-MY-CUSTOM-001

  # Run one scan cycle over all files in _uploads/:
  python run.py --scan

  # Start the background folder watcher (runs forever):
  python run.py --watch

  # Check scheduler status (if watcher is running):
  python run.py --status
"""

import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        description="SOP Ingestion Pipeline — Standalone CLI Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py --file knowledge_base/_uploads/reset_password.pdf
  python run.py --scan
  python run.py --watch
  python run.py --watch --interval 5
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", "-f", type=str, help="Path to a single raw SOP file to convert.")
    group.add_argument("--scan", action="store_true", help="Run one ingestion scan cycle over all files in _uploads/.")
    group.add_argument("--watch", action="store_true", help="Start background folder watcher (runs forever).")
    group.add_argument("--status", action="store_true", help="Print scheduler status.")
    group.add_argument("--models", action="store_true", help="Print currently configured LLM models per agent role.")

    parser.add_argument("--sop-id", type=str, default=None, help="Override the auto-generated SOP ID.")
    parser.add_argument("--interval", type=int, default=None, help="Scan interval in minutes (for --watch mode).")

    args = parser.parse_args()

    if args.models:
        # pyrefly: ignore [missing-import]
        from config.llm_config import print_active_models
        print_active_models()
    elif args.file:
        _process_single_file(args.file, override_sop_id=args.sop_id)
    elif args.scan:
        _run_scan_cycle()
    elif args.watch:
        _start_watcher(interval_minutes=args.interval)
    elif args.status:
        _print_status()


def _governance_block(mode_label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  [GOVERNANCE BLOCKED] {mode_label} DISABLED (C1)")
    print(f"{'='*60}")
    print(
        "  Ungoverned direct ingestion is disabled because it bypasses Agent A3\n"
        "  secret/AST quarantine, Agent A4 verification, Agent A5 dual-custody HITL\n"
        "  review, and Agent A6 publication gates.\n\n"
        "  Use the governed runner instead:\n"
        "    python trace_pipeline.py --file <path>\n"
        "  or submit via Governance Hub API: POST /api/uploads/ingest"
    )
    print(f"{'='*60}\n")
    sys.exit(1)


def _process_single_file(filepath: str, override_sop_id: str = None):
    """Blocked (C1): use trace_pipeline.py or POST /api/uploads/ingest."""
    _governance_block("run.py --file")


def _run_scan_cycle():
    """Blocked (C1): batch ungoverned scan is disabled."""
    _governance_block("run.py --scan")


def _start_watcher(interval_minutes: int = None):
    """Blocked (C1): background ungoverned watcher is disabled."""
    _governance_block("run.py --watch")


def _print_status():
    """Print the scheduler status."""
    # pyrefly: ignore [missing-import]
    from scheduler import get_scheduler_status

    status = get_scheduler_status()
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
