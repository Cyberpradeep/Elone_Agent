"""
Golden Test Set Evaluator (Section 19.2)
========================================
Frozen Specification: SOP Governance Hub v1.0 (Section 19.2 & 22.3)
Evaluates 16 curated golden test cases across:
1. Happy Path (Standard IT procedures)
2. Edge Cases (Minimal 2-line, missing metadata, Unicode special characters, nested exceptions)
3. Adversarial (Prompt injection, live secret leakage, AST malicious threats, data exfiltration)
4. Domain-Specific (IT Service Desk, Warehouse logistics, IAM Identity, Security SOC)

Evaluates:
- Traceability % (actual vs threshold)
- Schema validity (CanonicalSOPModel Pydantic Schema 1.0)
- Correct quarantine decision (Secret gate & Threat containment)
- Correct confidentiality level (L0-L3 tier assignment)
- Issue recall (Security/quality findings detected)
"""

import os
import sys
import json
import re
from typing import Dict, Any, List, Tuple, Optional

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure backend root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agents.a2_structuring.text_cleaner import clean_and_normalize_text
from agents.a2_structuring.canonical_builder import build_canonical_sop_from_draft
from agents.a3_security.secret_scanner import scan_for_secrets
from agents.a3_security.ast_sandbox import scan_commands_for_ast_threats
from agents.a3_security.confidentiality_engine import compute_confidentiality_score
from agents.a4_verification.quote_tracer import verify_canonical_quotes, compute_source_line_coverage
from schemas.canonical_sop_schema import validate_canonical_sop_dict


INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+(?:override|prompt)", re.IGNORECASE),
    re.compile(r"unrestricted\s+execution\s+mode", re.IGNORECASE),
    re.compile(r"bypass\s+(?:all\s+)?security\s+controls", re.IGNORECASE),
    re.compile(r"reveal\s+(?:all\s+)?signing\s+keys", re.IGNORECASE),
]


def detect_prompt_injection(text: str) -> bool:
    """Detects adversarial prompt injection attempts in raw text."""
    for pat in INJECTION_PATTERNS:
        if pat.search(text):
            return True
    return False


def evaluate_single_golden_case(case_def: Dict[str, Any], golden_dir: str) -> Dict[str, Any]:
    """Runs end-to-end evaluation for a single golden case against its manifest expectations."""
    file_rel = case_def["file"]
    filepath = os.path.join(golden_dir, file_rel)
    
    if not os.path.exists(filepath):
        return {
            "id": case_def["id"],
            "name": case_def["name"],
            "category": case_def["category"],
            "passed": False,
            "error": f"Fixture file not found: {filepath}",
        }

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        raw_text = f.read()

    # 1. Cleaning & Transformation Rules (WS-01, HF-01, HF-02)
    cleaned_text, transformations = clean_and_normalize_text(raw_text)

    # 2. Security Scanners (A3)
    has_secrets, secrets_count, secret_types, dlp_stats = scan_for_secrets(raw_text)
    has_injection = detect_prompt_injection(raw_text)
    
    # Candidate commands check
    candidate_cmds = [l.strip() for l in raw_text.splitlines() if any(l.strip().startswith(p) for p in ("curl", "net ", "certutil", "powershell", "systemctl", "rm ", "taskkill", "Get-", "Set-", "netsh", "ipconfig", "sc "))]
    ast_threats = scan_commands_for_ast_threats(candidate_cmds)
    has_ast_threat = len(ast_threats) > 0

    is_quarantined = has_secrets or has_injection or has_ast_threat
    conf_res = compute_confidentiality_score(raw_text, dlp_stats=dlp_stats)
    actual_level = conf_res.get("level", "L0")

    # 3. Canonical Structuring (A2)
    # Extract steps from procedure section or numbered lines
    proc_match = re.search(
        r"(?:Procedure|Process|Steps)\s*[:\n]+\s*([\s\S]*?)(?=\n\s*(?:[1-9]\.|\bEscalation\b|\bDocument\b|\bNotes\b|\bRevision\b)|\Z)",
        raw_text,
        re.IGNORECASE,
    )
    proc_text = proc_match.group(1) if proc_match else raw_text

    step_lines = []
    for line in proc_text.splitlines():
        s = line.strip()
        if re.match(r"^(?:\d+[\.\)]|[•\-–*])\s+", s):
            clean_s = re.sub(r"^(?:\d+[\.\)]|[•\-–*])\s+", "", s).strip()
            if len(clean_s) > 5 and not clean_s.lower().startswith(("procedure", "purpose", "scope", "preconditions")):
                step_lines.append(clean_s)

    if not step_lines:
        lines = [l.strip() for l in cleaned_text.splitlines() if l.strip()]
        step_lines = [lines[-1]] if lines else ["Execute procedure"]

    mock_steps = []
    for idx, clean_action in enumerate(step_lines, start=1):
        mock_steps.append({
            "step_number": idx,
            "sop_step_description": clean_action,
            "command": clean_action,
            "step_type": "command",
        })

    mock_draft = {
        "frontmatter": {
            "sop_id": case_def["id"],
            "title": case_def["name"],
            "category": "it_ops",
            "description": f"Standard operating procedure for {case_def['name']}",
            "steps": mock_steps,
        }
    }

    canonical_dict = build_canonical_sop_from_draft(
        draft=mock_draft,
        raw_text=cleaned_text,
        tenant_id="tn_eval_golden",
        uploaded_by="evaluator@elverve.ai",
        transformations=transformations,
    )

    # 4. Verification & Validation (A4)
    is_schema_valid, schema_errors, _ = validate_canonical_sop_dict(canonical_dict)
    
    # Traceability calculation
    raw_lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    total_q, verified_q, _ = verify_canonical_quotes(canonical_dict.get("steps", []), raw_lines)
    actual_traceability = (verified_q / total_q) if total_q > 0 else 1.0

    # 5. Evaluate Against Manifest Criteria
    schema_pass = (is_schema_valid == case_def.get("expected_schema_valid", True))
    quarantine_pass = (is_quarantined == case_def.get("expected_quarantine", False))
    level_pass = (actual_level in case_def.get("expected_levels", ["L0", "L1", "L2", "L3"]))
    min_trace = case_def.get("min_traceability", 0.0)
    trace_pass = (actual_traceability >= min_trace)

    # Issue recall pass
    expected_issues = case_def.get("expected_issues", [])
    issue_pass = True
    if "credentials_or_secrets" in expected_issues and not has_secrets:
        issue_pass = False
    if "prompt_injection" in expected_issues and not has_injection:
        issue_pass = False
    if "ast_threat" in expected_issues and not has_ast_threat:
        issue_pass = False

    case_passed = schema_pass and quarantine_pass and level_pass and trace_pass and issue_pass

    return {
        "id": case_def["id"],
        "name": case_def["name"],
        "category": case_def["category"],
        "passed": case_passed,
        "criteria": {
            "schema_valid": {"pass": schema_pass, "actual": is_schema_valid, "errors": schema_errors},
            "quarantine": {"pass": quarantine_pass, "actual": is_quarantined, "expected": case_def.get("expected_quarantine")},
            "level": {"pass": level_pass, "actual": actual_level, "expected": case_def.get("expected_levels")},
            "traceability": {"pass": trace_pass, "actual": round(actual_traceability, 2), "min_required": min_trace},
            "issue_recall": {"pass": issue_pass, "has_secrets": has_secrets, "has_injection": has_injection, "has_threat": has_ast_threat},
        },
        "transformations_count": len(transformations),
    }


def run_golden_set_evaluation(manifest_path: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
    """Evaluates the entire Golden Test Set and prints a structured evaluation report."""
    if not manifest_path:
        manifest_path = os.path.join(os.path.dirname(__file__), "golden_set", "manifest.json")

    golden_dir = os.path.dirname(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    cases = manifest.get("cases", [])
    results = []

    print("\n" + "=" * 80)
    print("SOP GOVERNANCE HUB v1.0 — GOLDEN SET EVALUATION BENCHMARK (§19.2)")
    print("=" * 80)
    print(f"{'ID':<10} | {'Category':<15} | {'Schema':<7} | {'Quarantine':<10} | {'Level':<6} | {'Trace %':<8} | {'Status'}")
    print("-" * 80)

    category_stats: Dict[str, Dict[str, int]] = {}

    for c in cases:
        cat = c.get("category", "general")
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "passed": 0}
        category_stats[cat]["total"] += 1

        res = evaluate_single_golden_case(c, golden_dir)
        results.append(res)

        if res["passed"]:
            category_stats[cat]["passed"] += 1

        crit = res.get("criteria", {})
        sch_str = "PASS" if crit.get("schema_valid", {}).get("pass") else "FAIL"
        quar_str = "QUAR" if crit.get("quarantine", {}).get("actual") else "CLEAN"
        lvl_str = str(crit.get("level", {}).get("actual", "L0"))
        trace_str = f"{crit.get('traceability', {}).get('actual', 0.0) * 100:.0f}%"
        status_str = "PASS" if res["passed"] else "FAIL"

        print(f"{res['id']:<10} | {res['category']:<15} | {sch_str:<7} | {quar_str:<10} | {lvl_str:<6} | {trace_str:<8} | {status_str}")

    print("=" * 80)

    total_cases = len(results)
    passed_cases = sum(1 for r in results if r["passed"])
    overall_pass_rate = (passed_cases / total_cases * 100) if total_cases > 0 else 0.0

    print(f"\nOVERALL RESULTS: {passed_cases}/{total_cases} Passed ({overall_pass_rate:.1f}%)")
    print("\nCategory Breakdown:")
    for cat, stats in category_stats.items():
        rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0.0
        print(f"  - {cat:<16}: {stats['passed']}/{stats['total']} ({rate:.1f}%)")

    all_passed = (passed_cases == total_cases)
    return all_passed, {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "pass_rate_pct": overall_pass_rate,
        "category_breakdown": category_stats,
        "results": results,
    }


if __name__ == "__main__":
    success, report = run_golden_set_evaluation()
    sys.exit(0 if success else 1)
