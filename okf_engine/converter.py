"""SOP Playbook Writer & Converter for OKF Engine."""

import os
import re
import yaml
from typing import Dict, Any, Optional, Tuple

from okf_engine.loader import KB_DIR, SOPS_DIR
from okf_engine.validator import validate_plan_faithfulness_and_linkage


def write_okf_playbook(
    draft: Dict[str, Any],
    raw_filename: str = "(reviewed draft)",
    tenant_id: Optional[str] = None,
    uploaded_by: Optional[str] = None,
    canonical_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Renders and commits an OKF Playbook markdown file to knowledge_base/sops/{category}/{sop_id}.md."""
    frontmatter_dict = draft.get("frontmatter", draft)
    category = (frontmatter_dict.get("category") or "other").lower().strip()
    sop_id = frontmatter_dict.get("sop_id") or "SOP-DYN-001"
    title = frontmatter_dict.get("title") or "Dynamic SOP Playbook"
    steps = frontmatter_dict.get("steps") or []

    cat_dir = os.path.join(SOPS_DIR, category)
    os.makedirs(cat_dir, exist_ok=True)
    sop_file_path = os.path.join(cat_dir, f"{sop_id}.md")

    # Clean frontmatter
    fm_export = {
        "sop_id": sop_id,
        "title": title,
        "category": category,
        "target_os": frontmatter_dict.get("target_os", "windows"),
        "platform": frontmatter_dict.get("platform", "system"),
        "required_entities": frontmatter_dict.get("required_entities", []),
        "steps": steps,
    }

    yaml_header = yaml.dump(fm_export, sort_keys=False, default_flow_style=False)
    md_content = f"---\n{yaml_header}---\n\n# {title}\n\nAutomated execution playbook for {title}.\n"

    with open(sop_file_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return sop_file_path


def plan_okf_from_raw(file_path: str, override_sop_id: Optional[str] = None) -> Dict[str, Any]:
    """Stub converter that loads an existing or generated OKF structure."""
    sop_id = override_sop_id or "SOP-DYN-001"
    return {
        "frontmatter": {
            "sop_id": sop_id,
            "title": f"Playbook {sop_id}",
            "category": "other",
            "steps": [],
        },
        "raw_chars": 0,
        "is_executable": True,
    }


def convert_raw_sop_to_okf(file_path: str, category: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """Converts a raw SOP file into an OKF playbook file."""
    draft = plan_okf_from_raw(file_path)
    if category:
        draft["frontmatter"]["category"] = category
    okf_path = write_okf_playbook(draft, raw_filename=os.path.basename(file_path))
    return okf_path, draft["frontmatter"]

