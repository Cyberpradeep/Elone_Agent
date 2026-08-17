import argparse
import datetime
import os
import sys
import re

# Custom Tee stream to simultaneously write to stdout and log file
class DualLogger:
    def __init__(self, filepath, stream):
        self.terminal = stream
        self.log_file = open(filepath, "w", encoding="utf-8")

    def write(self, message):
        try:
            self.terminal.write(message)
            self.terminal.flush()
        except Exception:
            pass
        try:
            self.log_file.write(message)
            self.log_file.flush()
        except Exception:
            pass

    def flush(self):
        try:
            self.terminal.flush()
        except Exception:
            pass
        try:
            self.log_file.flush()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="SOP Ingestion Debug Runner — Captures full internal reasoning traces to file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        required=True,
        help="Path to the raw SOP file to test (e.g. knowledge_base/_uploads/sop_software_application_unblock_request_ifeo.pdf)"
    )
    parser.add_argument(
        "--sop-id",
        type=str,
        default=None,
        help="Optional override for the generated SOP ID."
    )

    args = parser.parse_args()

    target_path = args.file
    # If not found directly, check inside knowledge_base/_uploads/
    if not os.path.exists(target_path):
        uploads_candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_base", "_uploads", args.file)
        if os.path.exists(uploads_candidate):
            target_path = uploads_candidate
        else:
            print(f"[ERROR] Target SOP file not found: {args.file}")
            print(f"        Checked: {os.path.abspath(args.file)}")
            print(f"        Checked: {uploads_candidate}")
            sys.exit(1)

    # 1. Setup Debug Log Directory & Filepath
    base_dir = os.path.dirname(os.path.abspath(__file__))
    debug_logs_dir = os.path.join(base_dir, "knowledge_base", "logs", "debug")
    os.makedirs(debug_logs_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    raw_name = os.path.splitext(os.path.basename(target_path))[0]
    clean_slug = re.sub(r"[^A-Za-z0-9_]+", "_", raw_name).strip("_")
    log_filename = f"{timestamp}_{clean_slug}_full_debug.log"
    log_filepath = os.path.join(debug_logs_dir, log_filename)

    # 2. Redirect stdout and stderr to DualLogger
    sys.stdout = DualLogger(log_filepath, sys.__stdout__)
    sys.stderr = DualLogger(log_filepath, sys.__stderr__)

    print("=" * 70)
    print("  SOP INGESTION FULL INTERNAL REASONING DEBUG RUNNER")
    print("=" * 70)
    print(f"  Input SOP File:  {os.path.abspath(target_path)}")
    print(f"  Debug Log File:  {log_filepath}")
    print(f"  Execution Time:  {datetime.datetime.now().isoformat()}")
    print("=" * 70 + "\n")

    # 3. Enable LangChain Full Debug Tracing
    try:
        from langchain_core.globals import set_debug, set_verbose
        set_debug(True)
        set_verbose(True)
        print("[DEBUG RUNNER] LangChain full internal debug tracing ENABLED.\n")
    except ImportError:
        print("[DEBUG RUNNER] Warning: langchain_core.globals not found. Running with standard output.\n")

    # 4. Execute Ingestion Pipeline
    try:
        from core.jit_converter import convert_raw_sop_to_okf
        okf_path, metadata = convert_raw_sop_to_okf(target_path, override_sop_id=args.sop_id)

        print("\n" + "=" * 70)
        print("  INGESTION & VALIDATION COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print(f"  Generated Playbook: {okf_path}")
        print(f"  SOP ID:             {metadata.get('sop_id', 'N/A')}")
        print(f"  Category:           {metadata.get('category', 'N/A')}")
        print(f"  Required Entities:  {metadata.get('required_entities', [])}")
        print(f"  Total Steps:        {len(metadata.get('steps', []))}")
        print(f"  Complete Log Saved: {log_filepath}")
        print("=" * 70 + "\n")

    except Exception as e:
        print("\n" + "=" * 70)
        print(f"  [ERROR] Ingestion Failed: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        print(f"\n  Full error trace saved to: {log_filepath}")
        sys.exit(1)


if __name__ == "__main__":
    main()
