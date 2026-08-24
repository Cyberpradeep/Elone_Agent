import os
import re
from typing import Any
import frontmatter
from dotenv import load_dotenv

# Ensure environment variables from .env are always loaded first
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv()


def get_kb_dir() -> str:
    return os.getenv("ELONE_KB_DIR", os.path.join(BASE_DIR, "knowledge_base"))


def get_sops_dir() -> str:
    return os.path.join(get_kb_dir(), "sops")


def get_patterns_dir() -> str:
    return os.path.join(get_kb_dir(), "patterns")


def get_hosts_dir() -> str:
    return os.path.join(get_patterns_dir(), "hosts")


def get_logs_dir() -> str:
    return os.path.join(get_kb_dir(), "logs")


KB_DIR = get_kb_dir()
SOPS_DIR = get_sops_dir()
PATTERNS_DIR = get_patterns_dir()
HOSTS_DIR = get_hosts_dir()
LOGS_DIR = get_logs_dir()


def load_okf_concept(filepath: str) -> tuple[dict[str, Any], str]:
    """Loads an OKF Markdown concept file from disk.

    Returns (metadata_dict, markdown_body).
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"OKF Concept file not found at: {filepath}")

    post = frontmatter.load(filepath)
    return dict(post.metadata), post.content.strip()


def parse_sops_catalog_index() -> dict[str, dict[str, str]]:
    """Parses knowledge_base/sops/index.md directly for OKF Progressive Disclosure Triage."""
    catalog_map = {}
    sops_dir = get_sops_dir()
    master_index_path = os.path.join(sops_dir, "index.md")

    if not os.path.exists(master_index_path):
        return _fallback_scan_sops_dir()

    with open(master_index_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        line_str = line.strip()
        if not line_str.startswith("-"):
            continue

        # Extract title and relative path: - [Title](./rel_path) or - [Title](rel_path)
        link_match = re.search(r"-\s*\[(.*?)\]\(\.?\/?(.*?)\)", line_str)
        if not link_match:
            continue

        title, raw_rel_path = link_match.groups()
        rel_path = raw_rel_path.lstrip("./").lstrip("/")

        # Extract category: Category: `logins` or Category: logins
        cat_match = re.search(r"Category:\s*[`'\"]?(\w+)[`'\"]?", line_str, re.IGNORECASE)
        category = cat_match.group(1) if cat_match else "other"

        # Extract sop_id:
        sop_id_match = re.search(r"(SOP-[A-Z0-9-]+)", rel_path, re.IGNORECASE)
        sop_id = sop_id_match.group(1) if sop_id_match else os.path.splitext(os.path.basename(rel_path))[0]

        # Extract description:
        description = ""
        if "|" in line_str:
            parts = [p.strip() for p in line_str.split("|")]
            desc_parts = [
                p for p in parts
                if not p.startswith("- [")
                and not p.lower().startswith("platform:")
                and not p.lower().startswith("category:")
                and not p.lower().startswith("triggers:")
            ]
            if desc_parts:
                description = desc_parts[-1]
        else:
            hyphen_match = re.search(r"Category:\s*`\w+`\s*-\s*(.*)", line_str)
            if hyphen_match:
                description = hyphen_match.group(1).strip()

        catalog_map[title] = {
            "sop_id": sop_id,
            "category": category,
            "rel_path": rel_path,
            "description": description or f"Playbook for {title}.",
        }

    if not catalog_map:
        return _fallback_scan_sops_dir()

    return catalog_map


def _fallback_scan_sops_dir() -> dict[str, dict[str, str]]:
    catalog_map = {}
    sops_dir = get_sops_dir()
    if not os.path.exists(sops_dir):
        return catalog_map

    for root, _, files in os.walk(sops_dir):
        for filename in files:
            if filename.endswith(".md") and filename != "index.md":
                filepath = os.path.join(root, filename)
                try:
                    metadata, _ = load_okf_concept(filepath)
                    title = metadata.get("title") or metadata.get("sop_id")
                    category = metadata.get("category", "other")
                    desc = metadata.get("description", f"Playbook for {title}.")
                    sop_id = metadata.get("sop_id", filename)
                    rel_path = os.path.relpath(filepath, sops_dir).replace("\\", "/")

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
    patterns_dir = get_patterns_dir()

    possible_paths = [
        os.path.join(patterns_dir, category or "", f"rules_{clean_id}.md"),
        os.path.join(patterns_dir, category or "", f"rules_{sop_id}.md"),
        os.path.join(patterns_dir, f"rules_{clean_id}.md"),
        os.path.join(patterns_dir, f"rules_{sop_id}.md"),
    ]

    for path in possible_paths:
        if path and os.path.exists(path):
            try:
                _, body = load_okf_concept(path)
                return body
            except Exception as e:
                print(f"[OKF Engine Warning] Failed reading rules from {path}: {e}")

    if os.path.exists(patterns_dir):
        for root, _, files in os.walk(patterns_dir):
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

    hosts_dir = get_hosts_dir()
    host_path = os.path.join(hosts_dir, f"{hostname}.md")
    if os.path.exists(host_path):
        try:
            _, body = load_okf_concept(host_path)
            return body
        except Exception as e:
            print(f"[OKF Engine Warning] Failed reading device profile for {hostname}: {e}")

    return f"(No specific device quirks recorded yet for host '{hostname}')"
