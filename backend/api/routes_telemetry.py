"""
Telemetry & Diagnostics API Route Handlers
==========================================
Handles multi-model token telemetry, daily quotas, log inspection, and security testing.
"""

import os
import glob
import re
import datetime
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from api.context import (
    UPLOADS_DIR,
    SOPS_DIR,
    LOGS_DIR,
    read_manifest,
)
from scheduler import get_scheduler_status
from gemini_monitor.monitor import get_today_usage, get_daily_max_calls, _load_usage_data
from config.tool_catalog import TOOL_CATALOG
from config.llm_config import ROLE_PROVIDER_MAP
from utils.security import redact_sensitive_dlp, clean_unicode_and_zero_width
from agents.a4_verification.plan_validator import MALICIOUS_COMMAND_PATTERNS as AST_MALICIOUS_PATTERNS


async def api_health(request):
    return JSONResponse({
        "status": "healthy",
        "service": "Elone SOP Governance Hub API Bridge",
        "timestamp": datetime.datetime.now().isoformat()
    })


async def api_overview(request):
    """Aggregate dashboard metrics across all pipeline components."""
    manifest = read_manifest()
    total_manifest = len(manifest)
    success_manifest = sum(1 for v in manifest.values() if v.get("status") == "success")
    failed_manifest = sum(1 for v in manifest.values() if v.get("status") == "failed")

    upload_files = [f for f in os.listdir(UPLOADS_DIR) if not f.startswith("_")] if os.path.exists(UPLOADS_DIR) else []
    playbook_files = glob.glob(os.path.join(SOPS_DIR, "**", "*.md"), recursive=True)
    total_playbooks = len([p for p in playbook_files if os.path.basename(p).lower() != "index.md"])

    today_usage = get_today_usage()
    sched_state = get_scheduler_status()

    total_tools = len(TOOL_CATALOG)
    total_functions = sum(len(p.get("functions", [])) for p in TOOL_CATALOG)

    gates = [
        {
            "gate_id": 1,
            "phase": "Intake & Pre-Validation",
            "name": "Deterministic File & Size Whitelist",
            "module": "core/input_validator.py",
            "status": "active",
            "rules": [
                "Extension allowlist (.pdf, .docx, .csv, .xls, .xlsx, .md, .txt)",
                "Magic-byte executable detection (MZ, ELF, Mach-O)",
                "Hard size limit <= 10MB",
                "Max page limit <= 10 pages"
            ]
        },
        {
            "gate_id": 2,
            "phase": "Intake & Pre-Validation",
            "name": "DLP Secret Redaction & Zero-Width Cleansing",
            "module": "core/security.py",
            "status": "active",
            "rules": [
                "Redacts passwords, API keys, private keys",
                "Strips Unicode zero-width invisibility characters",
                "High-entropy credential pattern detection"
            ]
        },
        {
            "gate_id": 3,
            "phase": "Phase 1: MarkItDown Engine & Optical OCR",
            "name": "VLM Vision Security & OCR",
            "module": "core/vlm_inspector.py",
            "status": "active",
            "rules": [
                "Pixel bomb cap max 4096px",
                "Downscale to 1024px JPEG anti-bloat",
                "NVIDIA Vision OCR UI element label extraction",
                "Max 5 images per document quota"
            ]
        },
        {
            "gate_id": 4,
            "phase": "Phase 2: Document-Order Extraction & Splicing",
            "name": "SSRF & Web Quarantine",
            "module": "core/link_scraper.py",
            "status": "active",
            "rules": [
                "Blocks AWS metadata 169.254.169.254",
                "Blocks RFC1918 private subnets",
                "Max 4KB markdown cache disk quarantine",
                "Untrusted link isolation"
            ]
        },
        {
            "gate_id": 5,
            "phase": "Phase 3: JIT Converter Agent & Reasoning",
            "name": "Prompt Sandboxing & 6-Stage Command CoT",
            "module": "core/jit_converter.py",
            "status": "active",
            "rules": [
                "<untrusted_document_payload> XML delimiter sandboxing",
                "Closing tag breakout escaping",
                "6-Stage Command CoT reasoning mandate",
                "Diagnostic-first command sequencing (Test-Connection, reg query)"
            ]
        },
        {
            "gate_id": 6,
            "phase": "Phase 4: Dual-Layer Plan Validation",
            "name": "AST Blacklist Scan & LLM Faithfulness Audit",
            "module": "core/plan_validator.py",
            "status": "active",
            "rules": [
                "Layer 1: Deterministic AST & Blacklist Scan (<1ms)",
                "Bans LOLBins (certutil, bitsadmin, mshta)",
                "Bans Encoded PowerShell (-enc, -encodedcommand)",
                "Bans Backdoor User Creation (net user /add)",
                "Enforces double-quotes on variables (\"{entities.*}\")",
                "Layer 2: Mistral Small LLM Faithfulness & Injection Audit (>= 0.85)",
                "Auto-retry controller up to 3 attempts with surgical feedback"
            ]
        },
        {
            "gate_id": 7,
            "phase": "Phase 5: Cryptographic Integrity & Storage",
            "name": "Storage Sandbox & HMAC-SHA256 Digital Stamp",
            "module": "core/security.py",
            "status": "active",
            "rules": [
                "Alphanumeric whitelist slugging (re.sub r'[^A-Za-z0-9_-]')",
                "HMAC-SHA256 digital stamp signature embedding",
                "Post-approval disk tamper detection",
                "Auto-initialization of Reflection Rulebook in knowledge_base/patterns/"
            ]
        }
    ]

    return JSONResponse({
        "stats": {
            "total_playbooks": total_playbooks,
            "total_uploads": len(upload_files),
            "manifest_total": total_manifest,
            "manifest_success": success_manifest,
            "manifest_failed": failed_manifest,
            "success_rate": round((success_manifest / total_manifest * 100), 1) if total_manifest > 0 else 100.0,
            "total_tools": total_tools,
            "total_functions": total_functions,
        },
        "telemetry": {
            "date": today_usage.get("date"),
            "total_calls": today_usage.get("total_calls", 0),
            "max_daily_calls": today_usage.get("max_daily_calls", get_daily_max_calls()),
            "calls_remaining": today_usage.get("calls_remaining", 0),
            "gemini_calls": today_usage.get("gemini_calls", 0),
            "mistral_calls": today_usage.get("mistral_calls", 0),
            "nvidia_vision_calls": today_usage.get("nvidia_vision_calls", 0),
            "total_tokens": today_usage.get("total_tokens", 0),
            "total_cost_usd": today_usage.get("total_cost_usd", 0.0),
            "total_cost_inr": today_usage.get("total_cost_inr", 0.0),
        },
        "scheduler": sched_state,
        "models": ROLE_PROVIDER_MAP,
        "gates": gates
    })


async def api_get_scheduler(request):
    status = get_scheduler_status()
    return JSONResponse(status)


async def api_get_tools(request):
    return JSONResponse({
        "platforms": TOOL_CATALOG,
        "count": len(TOOL_CATALOG),
        "total_functions": sum(len(p.get("functions", [])) for p in TOOL_CATALOG)
    })


async def api_get_telemetry(request):
    usage_data = _load_usage_data()
    today_usage = get_today_usage()

    return JSONResponse({
        "today": today_usage,
        "history": usage_data,
        "max_daily_calls": get_daily_max_calls()
    })


async def api_list_logs(request):
    logs = []
    if os.path.exists(LOGS_DIR):
        for name in sorted(os.listdir(LOGS_DIR), reverse=True):
            if name.endswith(".log"):
                path = os.path.join(LOGS_DIR, name)
                stat = os.stat(path)
                logs.append({
                    "filename": name,
                    "size_bytes": stat.st_size,
                    "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
    return JSONResponse({"logs": logs, "total": len(logs)})


async def api_get_log(request):
    filename = request.path_params.get("filename", "").strip()
    safe_name = os.path.basename(filename)
    path = os.path.join(LOGS_DIR, safe_name)

    if not os.path.exists(path) or not safe_name.endswith(".log"):
        return JSONResponse({"error": f"Log file '{filename}' not found"}, status_code=404)

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return Response(content, media_type="text/plain")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_test_security(request):
    """Interactive endpoint to test security filters (DLP, AST, Zero-width)."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    payload = body.get("payload", "")
    test_type = body.get("type", "all")

    results = {"input": payload}

    if test_type in ("all", "dlp"):
        masked, dlp_stats = redact_sensitive_dlp(payload)
        had_redactions = masked != payload
        redactions = []
        if dlp_stats.get("passwords", 0) > 0 or "[DLP_REDACTED_PASSWORD]" in masked:
            redactions.append("Password Detected & Redacted")
        if dlp_stats.get("api_keys", 0) > 0 or "[DLP_REDACTED_API_KEY]" in masked:
            redactions.append("API Key Detected & Redacted")
        if dlp_stats.get("emails", 0) > 0 or "[DLP_REDACTED_EMAIL]" in masked:
            redactions.append("PII Email Detected & Redacted")
        if dlp_stats.get("private_keys", 0) > 0 or "[DLP_REDACTED_PRIVATE_KEY]" in masked:
            redactions.append("Private Key Detected & Redacted")

        results["dlp"] = {
            "has_secrets": had_redactions,
            "detected_types": redactions,
            "stats": dlp_stats,
            "sanitized_output": masked
        }

    if test_type in ("all", "ast"):
        matched_threats = []
        for pattern, desc in AST_MALICIOUS_PATTERNS:
            if re.search(pattern, payload, re.IGNORECASE):
                matched_threats.append({
                    "pattern": pattern,
                    "description": desc,
                    "action": "BLOCKED_BY_LAYER_1_AST"
                })

        results["ast_blacklist"] = {
            "is_blocked": len(matched_threats) > 0,
            "matched_threats": matched_threats,
            "verdict": "REJECTED (LOLBin / Injection Detected)" if matched_threats else "PASSED (Clean Command)"
        }

    if test_type in ("all", "unicode"):
        cleaned = clean_unicode_and_zero_width(payload)
        had_zero_width = cleaned != payload
        results["unicode"] = {
            "cleaned_output": cleaned,
            "zero_width_detected": had_zero_width
        }

    return JSONResponse(results)


telemetry_routes = [
    Route("/api/health", api_health, methods=["GET"]),
    Route("/api/overview", api_overview, methods=["GET"]),
    Route("/api/scheduler", api_get_scheduler, methods=["GET"]),
    Route("/api/tools", api_get_tools, methods=["GET"]),
    Route("/api/telemetry", api_get_telemetry, methods=["GET"]),
    Route("/api/logs", api_list_logs, methods=["GET"]),
    Route("/api/logs/{filename}", api_get_log, methods=["GET"]),
    Route("/api/security/test", api_test_security, methods=["POST"]),
]
