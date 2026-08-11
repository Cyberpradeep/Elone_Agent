"""Internal helper tools for Intake Agent."""

import os
from shared.asset_lookup import extract_and_lookup_asset, is_application_allowed
from okf_engine.loader import parse_sops_catalog_index


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
UPLOADS_DIR = os.path.join(KB_DIR, "_uploads")


def get_raw_uploads_list() -> list[dict[str, str]]:
    """Scans knowledge_base/_uploads/ for raw SOP documents (PDF/Docx/TXT)."""
    raw_files = []
    if os.path.exists(UPLOADS_DIR):
        for f in os.listdir(UPLOADS_DIR):
            if f.lower().endswith((".pdf", ".docx", ".txt")):
                clean_title = os.path.splitext(f)[0].replace("_", " ").replace("-", " ")
                raw_files.append({
                    "raw_filename": f,
                    "clean_title": clean_title,
                    "path": os.path.join(UPLOADS_DIR, f)
                })
    return raw_files


def lookup_matching_playbook(query_keywords: str, category: str = None) -> dict:
    """Helper tool: searches sops index for matching playbook by keywords or category."""
    catalog_map = parse_sops_catalog_index()
    query_lower = query_keywords.lower()
    for sop_title, info in catalog_map.items():
        if query_lower in sop_title.lower() or query_lower in info.get("description", "").lower():
            if not category or category.lower() == info.get("category", "").lower():
                return {
                    "found": True,
                    "sop_title": sop_title,
                    "category": info.get("category"),
                    "matched_file_path": info.get("rel_path"),
                }
    return {"found": False}


def lookup_user_asset(email_or_emp_id: str) -> dict:
    """Helper tool: queries asset management database for user details."""
    return extract_and_lookup_asset(email_or_emp_id, {})


def check_software_permission(emp_id: str, app_target: str) -> dict:
    """Helper tool: queries software policy database for approval status."""
    is_allowed = is_application_allowed(emp_id, app_target)
    return {"approved": is_allowed, "emp_id": emp_id, "application": app_target}
