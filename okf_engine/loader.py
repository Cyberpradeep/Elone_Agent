import os
import re
import frontmatter
from typing import Any


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
SOPS_DIR = os.path.join(KB_DIR, "sops")
PATTERNS_DIR = os.path.join(KB_DIR, "patterns")
HOSTS_DIR = os.path.join(PATTERNS_DIR, "hosts")
LOGS_DIR = os.path.join(KB_DIR, "logs")


def load_okf_concept(filepath: str) -> tuple[dict[str, Any], str]:
    """Loads an OKF Markdown concept file from disk.

    Returns (metadata_dict, markdown_body).
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"OKF Concept file not found at: {filepath}")

    post = frontmatter.load(filepath)
    return dict(post.metadata), post.content.strip()


def parse_sops_catalog_index() -> dict[str, dict[str, str]]:
    """Parses knowledge_base/sops/index.md directly for OKF Progressive Disclosure Triage.

    Returns mapping:
    {
        "L1 Network Connectivity Troubleshooting": {
            "sop_id": "SOP-NET-001",
            "category": "network",
            "rel_path": "network/SOP-NET-001.md",
            "description": "Diagnoses and resolves a user's inability to connect to internet..."
        }
    }
    """
    catalog_map = {}
    master_index_path = os.path.join(SOPS_DIR, "index.md")

    if not os.path.exists(master_index_path):
        return _fallback_scan_sops_dir()

    with open(master_index_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        match = re.search(r"-\s*\[(.*?)\]\(\./(.*?)\)\s*-\s*Category:\s*`(\w+)`(?:\s*-\s*(.*))?", line.strip())
        if match:
            title, rel_path, category, description = match.groups()
            description = (description or "").strip()
            sop_id_match = re.search(r"(SOP-[A-Z0-9-]+)", rel_path)
            sop_id = sop_id_match.group(1) if sop_id_match else os.path.splitext(os.path.basename(rel_path))[0]

            catalog_map[title] = {
                "sop_id": sop_id,
                "category": category,
                "rel_path": rel_path,
                "description": description or f"Playbook for {title}."
            }

    if not catalog_map:
        return _fallback_scan_sops_dir()

    return catalog_map


def _fallback_scan_sops_dir() -> dict[str, dict[str, str]]:
    catalog_map = {}
    if not os.path.exists(SOPS_DIR):
        return catalog_map

    for root, _, files in os.walk(SOPS_DIR):
        for filename in files:
            if filename.endswith(".md") and filename != "index.md":
                filepath = os.path.join(root, filename)
                try:
                    metadata, _ = load_okf_concept(filepath)
                    title = metadata.get("title") or metadata.get("sop_id")
                    category = metadata.get("category", "other")
                    desc = metadata.get("description", f"Playbook for {title}.")
                    sop_id = metadata.get("sop_id", filename)
                    rel_path = os.path.relpath(filepath, SOPS_DIR).replace("\\", "/")

                    if title:
                        catalog_map[title] = {
                            "sop_id": sop_id,
                            "category": category,
                            "rel_path": rel_path,
                            "description": desc
                        }
                except Exception as e:
                    print(f"[OKF Engine Warning] Could not parse {filename}: {e}")

    return catalog_map


def get_active_intent_category_map_from_okf() -> dict[str, str]:
    """Compatibility wrapper returning {sop_title: category} map."""
    catalog = parse_sops_catalog_index()
    return {title: item["category"] for title, item in catalog.items()}


def load_reflection_rulebook(sop_id: str, category: str | None = None) -> str:
    """Loads reflection rules table for sop_id from knowledge_base/patterns/<category>/rules_<sop_id>.md."""
    clean_id = sop_id.replace(" ", "_").replace("-", "_")

    possible_paths = [
        os.path.join(PATTERNS_DIR, category or "", f"rules_{clean_id}.md"),
        os.path.join(PATTERNS_DIR, category or "", f"rules_{sop_id}.md"),
        os.path.join(PATTERNS_DIR, f"rules_{clean_id}.md"),
        os.path.join(PATTERNS_DIR, f"rules_{sop_id}.md"),
    ]

    for path in possible_paths:
        if path and os.path.exists(path):
            try:
                _, body = load_okf_concept(path)
                return body
            except Exception as e:
                print(f"[OKF Engine Warning] Failed reading rules from {path}: {e}")

    for root, _, files in os.walk(PATTERNS_DIR):
        for f in files:
            if f in [f"rules_{clean_id}.md", f"rules_{sop_id}.md"]:
                try:
                    _, body = load_okf_concept(os.path.join(root, f))
                    return body
                except Exception:
                    pass

    return "(No reflection rules recorded yet for this SOP.)"


def load_device_profile(hostname: str) -> str:
    """Loads learned device profile quirks for target hostname from knowledge_base/patterns/hosts/<hostname>.md."""
    if not hostname or hostname in ["(none)", "(unknown)"]:
        return "(No host specified)"

    host_path = os.path.join(HOSTS_DIR, f"{hostname}.md")
    if os.path.exists(host_path):
        try:
            _, body = load_okf_concept(host_path)
            return body
        except Exception as e:
            print(f"[OKF Engine Warning] Failed reading device profile for {hostname}: {e}")

    return f"(No specific device quirks recorded yet for host '{hostname}')"
