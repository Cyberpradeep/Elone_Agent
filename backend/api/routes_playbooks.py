"""
Playbooks API Route Handlers
============================
Handles OKF playbook listing, details, and cryptographic HMAC-SHA256 integrity verification.
"""

import os
import glob
import datetime
from starlette.responses import JSONResponse
from starlette.routing import Route

from api.context import (
    SOPS_DIR,
    PATTERNS_DIR,
    PROJECT_ROOT,
    parse_yaml_frontmatter,
)
from utils.security import verify_playbook_before_execution


async def api_list_sops(request):
    playbook_files = glob.glob(os.path.join(SOPS_DIR, "**", "*.md"), recursive=True)
    playbooks = []

    for path in playbook_files:
        if os.path.basename(path).lower() == "index.md":
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            frontmatter, _ = parse_yaml_frontmatter(content)
            category = frontmatter.get("category", os.path.basename(os.path.dirname(path)))
            sop_id = frontmatter.get("sop_id", os.path.splitext(os.path.basename(path))[0])

            # Integrity verification
            is_valid_sig, sig_reason, meta = verify_playbook_before_execution(path)

            playbooks.append({
                "sop_id": sop_id,
                "title": frontmatter.get("title", sop_id),
                "platform": frontmatter.get("platform", "system"),
                "category": category,
                "target_os": frontmatter.get("target_os", "windows"),
                "description": frontmatter.get("description", ""),
                "confidence_score": frontmatter.get("confidence_score", 0.95),
                "confidence_level": frontmatter.get("confidence_level", "High"),
                "step_count": len(frontmatter.get("steps", [])),
                "steps": frontmatter.get("steps", []),
                "file_path": os.path.relpath(path, PROJECT_ROOT).replace("\\", "/"),
                "integrity": {
                    "is_valid": is_valid_sig,
                    "reason": sig_reason,
                    "status": "VALID_HMAC_SHA256" if is_valid_sig else "FAILED_VERIFICATION"
                }
            })
        except Exception as e:
            print(f"[API Error] Failed parsing playbook {path}: {e}")

    return JSONResponse({
        "playbooks": playbooks,
        "total": len(playbooks)
    })


async def api_get_sop(request):
    sop_id = request.path_params.get("sop_id", "").strip()
    clean_id = sop_id.replace(".md", "")

    # Search for playbook file
    playbook_files = glob.glob(os.path.join(SOPS_DIR, "**", "*.md"), recursive=True)
    target_path = None
    for p in playbook_files:
        name = os.path.splitext(os.path.basename(p))[0]
        if name.lower() == clean_id.lower() or os.path.basename(p).lower() == f"{clean_id.lower()}.md":
            target_path = p
            break

    if not target_path or not os.path.exists(target_path):
        return JSONResponse({"error": f"SOP '{sop_id}' not found"}, status_code=404)

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()

        frontmatter, body = parse_yaml_frontmatter(content)
        category = frontmatter.get("category", os.path.basename(os.path.dirname(target_path)))

        # Integrity verification
        is_valid_sig, sig_reason, meta = verify_playbook_before_execution(target_path)

        # Check for Reflection Rulebook
        rulebook_path = os.path.join(PATTERNS_DIR, category, f"rules_{frontmatter.get('sop_id', clean_id)}.md")
        rulebook_content = None
        if os.path.exists(rulebook_path):
            with open(rulebook_path, "r", encoding="utf-8") as rf:
                rulebook_content = rf.read()

        return JSONResponse({
            "sop_id": frontmatter.get("sop_id", clean_id),
            "frontmatter": frontmatter,
            "markdown_body": body,
            "raw_content": content,
            "steps": frontmatter.get("steps", []),
            "file_path": os.path.relpath(target_path, PROJECT_ROOT).replace("\\", "/"),
            "integrity": {
                "is_valid": is_valid_sig,
                "status": "VALID_HMAC_SHA256" if is_valid_sig else "FAILED_VERIFICATION",
                "reason": sig_reason,
            },
            "rulebook": {
                "exists": os.path.exists(rulebook_path),
                "path": os.path.relpath(rulebook_path, PROJECT_ROOT).replace("\\", "/") if os.path.exists(rulebook_path) else None,
                "content": rulebook_content,
            }
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_verify_sop_integrity(request):
    sop_id = request.path_params.get("sop_id", "").strip()
    clean_id = sop_id.replace(".md", "")

    playbook_files = glob.glob(os.path.join(SOPS_DIR, "**", "*.md"), recursive=True)
    target_path = None
    for p in playbook_files:
        name = os.path.splitext(os.path.basename(p))[0]
        if name.lower() == clean_id.lower() or os.path.basename(p).lower() == f"{clean_id.lower()}.md":
            target_path = p
            break

    if not target_path or not os.path.exists(target_path):
        return JSONResponse({"error": f"SOP '{sop_id}' not found"}, status_code=404)

    is_valid, reason, meta = verify_playbook_before_execution(target_path)
    return JSONResponse({
        "sop_id": clean_id,
        "is_valid": is_valid,
        "status": "AUTHENTIC" if is_valid else "TAMPERED_OR_CORRUPT",
        "reason": reason,
        "metadata": meta,
        "checked_at": datetime.datetime.now().isoformat()
    })


playbook_routes = [
    Route("/api/sops", api_list_sops, methods=["GET"]),
    Route("/api/sops/{sop_id}", api_get_sop, methods=["GET"]),
    Route("/api/sops/{sop_id}/verify", api_verify_sop_integrity, methods=["POST"]),
]
