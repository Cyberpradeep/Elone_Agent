"""
Elone Agent DeepEval Benchmark Suite Runner
============================================
Runs all evaluation suites and generates an executive benchmark summary.

Usage:
    python backend/tests/deepeval/run_deepeval_suite.py
    or
    pytest backend/tests/deepeval -v
"""

import os
import sys
import time
import pytest

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EVAL_SUITES = [
    {
        "file": "test_eval_faithfulness.py",
        "agent": "Agent A2 (Structuring)",
        "metric": "Faithfulness & Hallucination Rate",
        "description": "Verifies OKF steps faithfully represent human SOP text",
    },
    {
        "file": "test_eval_command_safety.py",
        "agent": "Agent A2/A3 (Execution Safety)",
        "metric": "Diagnostic-First & Blast Radius GEval",
        "description": "Evaluates PowerShell/shell quoting, diagnostics, LOLBin rejection",
    },
    {
        "file": "test_eval_tool_correctness.py",
        "agent": "Agent A2 (Tool Calling)",
        "metric": "Tool Catalog Schema & Parameter GEval",
        "description": "Evaluates platform tool mappings against registered catalog",
    },
    {
        "file": "test_eval_adversarial_defense.py",
        "agent": "Agent A3 (Security Gatekeeper)",
        "metric": "Prompt Injection & Secret Leakage GEval",
        "description": "Tests resistance against jailbreaks, exfiltration, key theft",
    },
    {
        "file": "test_eval_confidentiality_tiering.py",
        "agent": "Agent A3 (Classification)",
        "metric": "L0-L3 Sensitivity Floor GEval",
        "description": "Evaluates clearance tiering accuracy and floor constraints",
    },
    {
        "file": "test_eval_retrieval_relevancy.py",
        "agent": "Agent A6 (Downstream Catalog)",
        "metric": "Contextual Relevancy & Tenant Isolation",
        "description": "Evaluates clearance boundaries and cross-tenant segregation",
    },
]


def run_deepeval_suite():
    print("\n" + "=" * 92, flush=True)
    print("        ELONE AGENT — PRODUCTION DEEPEVAL EVALUATION BENCHMARK SUITE", flush=True)
    print("=" * 92, flush=True)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"Framework: DeepEval 4.x + Pytest", flush=True)
    print(f"Directory: {os.path.dirname(os.path.abspath(__file__))}", flush=True)
    print("-" * 92, flush=True)
    print(f"{'#':<3} | {'Evaluation Target':<28} | {'Metric Evaluated':<36} | {'Status'}", flush=True)
    print("-" * 92, flush=True)

    suite_dir = os.path.dirname(os.path.abspath(__file__))

    total = len(EVAL_SUITES)
    passed = 0
    failed = 0
    start_time = time.time()

    for idx, suite in enumerate(EVAL_SUITES, start=1):
        test_file = os.path.join(suite_dir, suite["file"])
        # Run in-process with pytest
        ret_code = pytest.main([test_file, "-q", "--tb=no"])
        is_pass = (ret_code == pytest.ExitCode.OK)

        if is_pass:
            status_badge = "[ PASS ]"
            passed += 1
        else:
            status_badge = "[ FAIL ]"
            failed += 1

        print(f"{idx:<3} | {suite['agent']:<28} | {suite['metric']:<36} | {status_badge}", flush=True)

    duration = time.time() - start_time
    print("=" * 92, flush=True)
    pass_pct = (passed / total * 100) if total > 0 else 0.0
    print(f"\nOVERALL SUMMARY: {passed}/{total} Suites Passed ({pass_pct:.1f}%) in {duration:.2f}s", flush=True)
    if failed == 0:
        print("[SUCCESS] All AI Agent evaluation gates passed enterprise compliance thresholds.", flush=True)
    else:
        print(f"[WARNING] {failed} evaluation suite(s) flagged compliance or accuracy issues.", flush=True)

    print("=" * 92 + "\n", flush=True)
    return (failed == 0)


if __name__ == "__main__":
    success = run_deepeval_suite()
    sys.exit(0 if success else 1)

