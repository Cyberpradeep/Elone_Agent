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

    parser.add_argument("--sop-id", type=str, default=None, help="Override the auto-generated SOP ID.")
    parser.add_argument("--interval", type=int, default=None, help="Scan interval in minutes (for --watch mode).")

    args = parser.parse_args()

    if args.file:
        _process_single_file(args.file, override_sop_id=args.sop_id)
    elif args.scan:
        _run_scan_cycle()
    elif args.watch:
        _start_watcher(interval_minutes=args.interval)
    elif args.status:
        _print_status()


def _process_single_file(filepath: str, override_sop_id: str = None):
    """Convert a single raw SOP file into an OKF Playbook."""
    from core.jit_converter import convert_raw_sop_to_okf

    if not os.path.exists(filepath):
        print(f"[ERROR] File not found: {filepath}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  SOP Ingestion Pipeline — Single File Processing")
    print(f"{'='*60}")
    print(f"  Input:  {os.path.abspath(filepath)}")
    print(f"{'='*60}\n")

    try:
        okf_path, metadata = convert_raw_sop_to_okf(filepath, override_sop_id=override_sop_id)
        print(f"\n{'='*60}")
        print(f"  INGESTION COMPLETE")
        print(f"{'='*60}")
        print(f"  SOP ID:    {metadata.get('sop_id', 'N/A')}")
        print(f"  Title:     {metadata.get('title', 'N/A')}")
        print(f"  Category:  {metadata.get('category', 'N/A')}")
        print(f"  Output:    {okf_path}")
        print(f"  Entities:  {metadata.get('required_entities', [])}")
        print(f"  Triggers:  {metadata.get('trigger_words', [])}")
        print(f"  Steps:     {len(metadata.get('steps', []))}")
        print(f"{'='*60}\n")

    except Exception as e:
        safe_err = str(e).encode("ascii", "replace").decode("ascii")
        print(f"\n[ERROR] Ingestion failed: {safe_err}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _run_scan_cycle():
    """Run one full ingestion scan cycle."""
    from scheduler import _run_ingestion_cycle

    print(f"\n{'='*60}")
    print(f"  SOP Ingestion Pipeline — Full Scan Cycle")
    print(f"{'='*60}\n")

    summary = _run_ingestion_cycle()
    print(f"\n{'='*60}")
    print(f"  SCAN CYCLE COMPLETE")
    print(f"{'='*60}")
    print(json.dumps(summary, indent=2))
    print(f"{'='*60}\n")


def _start_watcher(interval_minutes: int = None):
    """Start background watcher that runs forever."""
    from scheduler import start_sop_ingestion_scheduler

    interval = interval_minutes or int(os.environ.get("SOP_SCAN_INTERVAL_MINUTES", "10"))

    print(f"\n{'='*60}")
    print(f"  SOP Ingestion Pipeline — Background Watcher")
    print(f"  Scan interval: {interval} minutes")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*60}\n")

    start_sop_ingestion_scheduler(interval_minutes=interval)

    # Keep main thread alive
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SOP Scheduler] Watcher stopped by user.")


def _print_status():
    """Print the scheduler status."""
    from scheduler import get_scheduler_status

    status = get_scheduler_status()
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
