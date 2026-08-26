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
    parser.add_argument(
        "--images-only", "-i",
        action="store_true",
        help="Run ONLY the image extraction and VLM description report generation without downstream JIT conversion."
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
    kb_dir = os.getenv("ELONE_KB_DIR", os.path.join(base_dir, "knowledge_base"))
    debug_logs_dir = os.path.join(kb_dir, "logs", "debug")
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

    # 4. Start Per-Execution Session Tracker
    # pyrefly: ignore [missing-import]
    from gemini_monitor.monitor import start_execution_session
    sop_basename = os.path.basename(target_path)
    session_id = start_execution_session(sop_filename=sop_basename)
    print(f"[DEBUG RUNNER] Execution session started: {session_id}\n")

    # 5. Execute Pipeline
    try:
        if args.images_only:
            print("=" * 70)
            print("  SOP IMAGE EXTRACTION & VLM ANALYSIS MODE (Images Only)")
            print("=" * 70)
            # pyrefly: ignore [missing-import]
            from core.document_parser import extract_ordered_sop_content
            # pyrefly: ignore [missing-import]
            from core.vlm_inspector import analyze_and_save_image

            sop_slug = os.path.splitext(os.path.basename(target_path))[0].upper()[:20]
            parser_type, segments = extract_ordered_sop_content(target_path)
            image_segments = [s for s in segments if s.get("type") == "image"]
            print(f"  Document parsed using '{parser_type}' engine.")
            print(f"  Found {len(image_segments)} embedded image(s) in document.\n")

            if not image_segments:
                print("  [INFO] No embedded images found in this document.")
            else:
                for idx, img_seg in enumerate(image_segments, start=1):
                    label = img_seg.get("label", f"Image {idx}")
                    mime = img_seg.get("mime_type", "image/png")
                    size_kb = len(img_seg["bytes"]) / 1024.0
                    print(f"--- [Image {idx}/{len(image_segments)}] {label} ({mime}, {size_kb:.1f} KB) ---")
                    report_text, img_ref = analyze_and_save_image(
                        img_seg["bytes"], mime, label, sop_slug, idx
                    )
                    print(f"\n[VLM Output Report]:\n{report_text}\n")
                    print(f"  Confidence:  {img_ref.get('confidence_score')} ({img_ref.get('confidence_level')})")
                    print(f"  Reason:      {img_ref.get('confidence_reason')}")
                    print(f"  Report Log:  {img_ref.get('file_path')}\n")

            try:
                # pyrefly: ignore [missing-import]
                from gemini_monitor.monitor import print_daily_usage_banner
                print_daily_usage_banner()
            except Exception:
                pass
            return

        # pyrefly: ignore [missing-import]
        from core.jit_converter import convert_raw_sop_to_okf
        okf_path, metadata = convert_raw_sop_to_okf(target_path, override_sop_id=args.sop_id)

        print("\n" + "=" * 70)
        print("  INGESTION & VALIDATION COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print(f"  Generated Playbook: {okf_path}")
        print(f"  SOP ID:             {metadata.get('sop_id', 'N/A')}")
        print(f"  Category:           {metadata.get('category', 'N/A')}")
        print(f"  Confidence:         {metadata.get('confidence_score', 'N/A')} ({metadata.get('confidence_level', 'N/A')})")
        if metadata.get('confidence_reason'):
            print(f"  Confidence Reason:  {metadata.get('confidence_reason')}")
        print(f"  Required Entities:  {metadata.get('required_entities', [])}")
        print(f"  Total Steps:        {len(metadata.get('steps', []))}")
        print(f"  Complete Log Saved: {log_filepath}")
        print("=" * 70 + "\n")

        # Print Per-Execution Session Summary (THIS RUN ONLY)
        try:
            # pyrefly: ignore [missing-import]
            from gemini_monitor.monitor import print_execution_session_banner, end_execution_session
            session_summary = end_execution_session()
            print_execution_session_banner(session_summary)
        except Exception:
            pass

        # Print Gemini & Vision Monitor Daily Usage Report
        try:
            # pyrefly: ignore [missing-import]
            from gemini_monitor.monitor import print_daily_usage_banner
            print_daily_usage_banner()
        except Exception:
            pass

    except Exception as e:
        # pyrefly: ignore [missing-import]
        from core.input_validator import SOPInputValidationError

        print("\n" + "=" * 70)
        if isinstance(e, SOPInputValidationError):
            print("  [SECURITY / VALIDATION REJECTION] INGESTION BLOCKED")
            print("=" * 70)
            print(f"  Source File:  {e.filename}")
            print(f"  Status:       REJECTED (Pre-Ingestion Gate)")
            print(f"  Reason:       {e.reason}")
            if e.metadata:
                ext = e.metadata.get('extension')
                size_mb = e.metadata.get('size_mb')
                pages = e.metadata.get('page_count')
                if ext:
                    print(f"  Detected Ext: {ext}")
                if size_mb is not None:
                    print(f"  File Size:    {size_mb} MB (Max allowed: 10.0 MB)")
                if pages is not None:
                    print(f"  Page Count:   {pages} pages (Max allowed: 10 pages)")
            print("=" * 70)
            print(f"\n  [Audit Note] Pipeline halted before parsing/LLM execution. Zero tokens consumed.")
            print(f"  Security log: {log_filepath}\n")
        elif isinstance(e, ValueError):
            print("  [INGESTION VALIDATION ERROR]")
            print("=" * 70)
            print(f"  Reason: {e}")
            print("=" * 70)
            print(f"\n  Full details saved to: {log_filepath}\n")
        else:
            print(f"  [UNEXPECTED PIPELINE ERROR]: {e}")
            print("=" * 70)
            import traceback
            traceback.print_exc()
            print(f"\n  Full crash traceback saved to: {log_filepath}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
