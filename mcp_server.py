import os
import sys
import json
import argparse
from typing import Optional, Dict, Any

# Ensure UTF-8 output encoding across Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from mcp.server import MCPServer
    mcp = MCPServer("Elone-SOP-Ingestion-Engine")
except (ImportError, AttributeError):
    try:
        # pyrefly: ignore [missing-import]
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("Elone-SOP-Ingestion-Engine")
    except Exception:
        from mcp.server.mcpserver import MCPServer
        mcp = MCPServer("Elone-SOP-Ingestion-Engine")

# pyrefly: ignore [missing-import]
from core.jit_converter import (
    convert_raw_sop_to_okf,
    plan_okf_from_raw,
)
# pyrefly: ignore [missing-import]
from core.plan_validator import validate_plan_faithfulness_and_linkage
# pyrefly: ignore [missing-import]
from config.tool_catalog import get_formatted_tools_summary
# pyrefly: ignore [missing-import]
from scheduler import (
    start_sop_ingestion_scheduler,
    run_ingestion_cycle,
    get_scheduler_status,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "knowledge_base", "_uploads")
SOPS_INDEX_PATH = os.path.join(BASE_DIR, "knowledge_base", "sops", "index.md")


def _safe_str(text: str) -> str:
    """Safe ASCII string representation for console output."""
    return str(text).replace("✅", "[SUCCESS]").replace("❌", "[FAILED]").replace("⚠️", "[WARNING]")


def _resolve_sop_path(file_path: str) -> str:
    """Helper: resolves bare filename to knowledge_base/_uploads/ if not found directly."""
    if os.path.isabs(file_path) and os.path.exists(file_path):
        return file_path
    if os.path.exists(file_path):
        return os.path.abspath(file_path)
    
    upload_candidate = os.path.join(UPLOADS_DIR, file_path)
    if os.path.exists(upload_candidate):
        return upload_candidate

    upload_basename_candidate = os.path.join(UPLOADS_DIR, os.path.basename(file_path))
    if os.path.exists(upload_basename_candidate):
        return upload_basename_candidate

    return file_path


@mcp.tool()
def ingest_sop(file_path: str, override_sop_id: Optional[str] = None) -> str:
    """Converts a raw human SOP document (PDF, DOCX, TXT) into an execution-ready OKF Playbook.
    
    Runs multimodal parsing (text + VLM screenshots), 8-Stage CoT with 4 Verification Gates,
    and 2-Layer Validation before committing the verified playbook to knowledge_base/sops/.
    
    Args:
        file_path: Absolute or relative path (or bare filename in knowledge_base/_uploads/).
        override_sop_id: Optional custom SOP ID (e.g. 'SOP-AUTH-001').
    """
    resolved_path = _resolve_sop_path(file_path)
    if not os.path.exists(resolved_path):
        return f"[ERROR]: SOP file not found at '{file_path}' (resolved: '{resolved_path}')."

    try:
        okf_path, frontmatter = convert_raw_sop_to_okf(
            resolved_path,
            override_sop_id=override_sop_id or None
        )
        steps = frontmatter.get("steps", [])
        return (
            f"[SUCCESS] SOP Conversion Succeeded!\n\n"
            f"- SOP ID: `{frontmatter.get('sop_id')}`\n"
            f"- Title: {frontmatter.get('title')}\n"
            f"- Category: `{frontmatter.get('category')}`\n"
            f"- Target OS: `{frontmatter.get('target_os')}`\n"
            f"- Execution Steps: {len(steps)} verified steps\n"
            f"- Playbook Location: `{okf_path}`\n\n"
            f"### Verified Step Summary:\n" +
            "\n".join([
                f"  {s.get('step_number')}. [{s.get('step_type')}] {s.get('sop_step_description')}"
                for s in steps
            ])
        )
    except Exception as e:
        return f"[FAILED] SOP Ingestion Failed: {e}"


@mcp.tool()
def plan_sop(file_path: str) -> str:
    """Read-only Phase 1 conversion: parses the raw SOP and drafts the OKF playbook without writing to disk.
    
    Returns the proposed JSON structure, verification notes, and Layer 1/2 validation status.
    
    Args:
        file_path: Path to the raw SOP document.
    """
    resolved_path = _resolve_sop_path(file_path)
    if not os.path.exists(resolved_path):
        return f"Error: SOP file not found at '{file_path}'."

    try:
        draft = plan_okf_from_raw(resolved_path)
        return json.dumps(draft, indent=2, default=str)
    except Exception as e:
        return f"Error drafting SOP plan: {e}"


@mcp.tool()
def validate_playbook_plan(raw_sop_text: str, steps_json: str) -> str:
    """Evaluates an OKF playbook plan against raw human SOP text using 2-Layer verification.
    
    Layer 1: Deterministic Syntax, Parameter Completeness & Variable Linkage.
    Layer 2: LLM Semantic Faithfulness & Hallucination Inspection.
    
    Args:
        raw_sop_text: Original human SOP document text.
        steps_json: JSON array of proposed OKF playbook steps.
    """
    try:
        steps = json.loads(steps_json)
        if isinstance(steps, dict) and "steps" in steps:
            steps = steps["steps"]
    except Exception as e:
        return f"Invalid steps_json format: {e}"

    is_valid, errors = validate_plan_faithfulness_and_linkage(raw_sop_text, {"steps": steps})
    if is_valid:
        return "[PASSED]: Playbook plan is 100% syntactically valid, variable-linked, and faithful."
    return f"[FAILED] validation with {len(errors)} error(s):\n" + "\n".join([f"- {err}" for err in errors])


@mcp.tool()
def list_knowledge_base_playbooks() -> str:
    """Returns the master catalog index of all active OKF Playbooks currently stored in the knowledge base."""
    if not os.path.exists(SOPS_INDEX_PATH):
        return "Knowledge base index not found."
    with open(SOPS_INDEX_PATH, "r", encoding="utf-8") as f:
        return f.read()


@mcp.tool()
def read_playbook(sop_id: str) -> str:
    """Retrieves the full OKF Playbook markdown and YAML frontmatter by SOP ID or filename.
    
    Args:
        sop_id: The SOP ID (e.g. 'SOP-SOL-PWD-RESET-L1-002') or category path.
    """
    sops_root = os.path.join(BASE_DIR, "knowledge_base", "sops")
    clean_id = str(sop_id).strip()
    if not clean_id.endswith(".md"):
        clean_id += ".md"

    # Search for playbook in knowledge_base/sops/ subdirectories
    for root, _, files in os.walk(sops_root):
        for file in files:
            if file.lower() == clean_id.lower() or os.path.splitext(file)[0].lower() == os.path.splitext(clean_id)[0].lower():
                full_path = os.path.join(root, file)
                with open(full_path, "r", encoding="utf-8") as f:
                    return f.read()

    return f"Playbook '{sop_id}' not found in knowledge base."


@mcp.tool()
def get_registered_tool_catalog() -> str:
    """Returns the dynamic summary of all registered IT tool platforms available for agent step binding."""
    return get_formatted_tools_summary()


@mcp.tool()
def scan_uploads_now() -> str:
    """Triggers an immediate scan of knowledge_base/_uploads/ for new or modified SOP files without waiting for the scheduler interval.
    
    Converts and commits any unprocessed SOP files to knowledge_base/sops/.
    """
    summary = run_ingestion_cycle()
    return json.dumps(summary, indent=2, default=str)


@mcp.tool()
def get_ingestion_scheduler_status() -> str:
    """Returns the real-time background scheduler state (running status, scan interval, last/next run times, and run summaries)."""
    return json.dumps(get_scheduler_status(), indent=2, default=str)


# ---------------------------------------------------------------------------
# CLI Test Harness
# ---------------------------------------------------------------------------

def _run_cli_test_harness(test_file: Optional[str] = None):
    """Verifies all MCP tools locally without requiring an external MCP client."""
    print("\n" + "=" * 65)
    print("  ELONE SOP INGESTION — MCP SERVER CLI TEST HARNESS")
    print("=" * 65)

    print("\n[MCP Test 1/5] Testing tool: 'get_registered_tool_catalog'...")
    catalog_summary = get_registered_tool_catalog()
    print(f"  [PASS] Retrieved catalog summary ({len(catalog_summary)} chars).")

    print("\n[MCP Test 2/5] Testing tool: 'list_knowledge_base_playbooks'...")
    index_md = list_knowledge_base_playbooks()
    print(f"  [PASS] Retrieved catalog index ({len(index_md)} chars).")

    print("\n[MCP Test 3/5] Testing tool: 'validate_playbook_plan' (deterministic check)...")
    dummy_sop = "Step 1: Check IP using ipconfig."
    dummy_steps = json.dumps([
        {
            "step_number": 1,
            "sop_step_description": "Check IP",
            "step_type": "command",
            "command": "ipconfig",
            "shell": "powershell",
            "timeout_seconds": 30
        }
    ])
    val_res = validate_playbook_plan(dummy_sop, dummy_steps)
    print(f"  Result: {_safe_str(val_res)}")
    assert "PASSED" in val_res, "Validation failed!"
    print("  [PASS] validate_playbook_plan executed cleanly.")

    print("\n[MCP Test 4/5] Testing tool: 'get_ingestion_scheduler_status'...")
    sched_status = get_ingestion_scheduler_status()
    print(f"  Result: {sched_status}")
    print("  [PASS] get_ingestion_scheduler_status executed cleanly.")

    target_sop = test_file or "sample_account_unlock.txt"
    print(f"\n[MCP Test 5/5] Testing tool: 'ingest_sop' with file '{target_sop}'...")
    ingest_res = ingest_sop(target_sop)
    print("\n" + "-" * 55)
    print(_safe_str(ingest_res))
    print("-" * 55)
    assert "Succeeded" in ingest_res or "SUCCESS" in ingest_res, "Ingestion failed!"
    print("  [PASS] ingest_sop executed cleanly.")

    print("\n" + "=" * 65)
    print("  ALL MCP TOOLS VERIFIED SUCCESSFULLY!")
    print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Elone SOP Ingestion MCP Server")
    parser.add_argument("--test", action="store_true", help="Run local CLI test harness verifying all MCP tools.")
    parser.add_argument("--file", "-f", type=str, default=None, help="Target SOP file for test conversion in --test mode.")
    args, unknown = parser.parse_known_args()

    # Automatically start background SOP uploads directory watcher
    start_sop_ingestion_scheduler()

    if args.test:
        _run_cli_test_harness(test_file=args.file)
    else:
        # Default: Run standard stdio FastMCP server
        mcp.run()


if __name__ == "__main__":
    main()
