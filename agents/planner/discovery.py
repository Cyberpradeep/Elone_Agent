"""SOP Discovery & Memory Resolution for Unified Planner Agent."""

import os
import re
from typing import Optional, Tuple, Dict, Any

from okf_engine.loader import load_okf_concept, parse_sops_catalog_index, load_reflection_rulebook, load_device_profile


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
SOPS_DIR = os.path.join(KB_DIR, "sops")
UPLOADS_DIR = os.path.join(KB_DIR, "_uploads")

GENERIC_NOISE_KEYWORDS = {
    "windows", "linux", "macos", "software", "hardware", "system",
    "app", "application", "request", "issue", "problem", "sop", "l1", "help", "guide"
}


def discover_sop_and_memory_paths(
    intent: str,
    category: Optional[str],
    detailed_description: str,
    keywords: list[str],
    hostname: str,
    sop_source: Optional[str] = None,
    matched_file_path: Optional[str] = None
) -> Tuple[Optional[str], Optional[Dict[str, Any]], float, str, str]:
    """Process 1 & 2: Progressive SOP Discovery, Intent Verification & Memory Resolution."""
    os.makedirs(SOPS_DIR, exist_ok=True)
    sop_file_path = None
    metadata = None
    discovery_confidence = 0.0

    # 1. Analyze & Verify Intake Agent's Matched SOP
    if matched_file_path:
        sop_file_path, metadata, discovery_confidence = _analyze_and_verify_intake_match(
            intent=intent,
            matched_file_path=matched_file_path,
            keywords=keywords
        )

    # 2. Fallback Best Match Search based strictly on INTENT
    if not sop_file_path:
        print(f"[Discovery] Searching knowledge base for best SOP match for intent: '{intent}'...")

        # 2a. Category Index Search
        if category and os.path.exists(os.path.join(SOPS_DIR, category)):
            cat_index_path = os.path.join(SOPS_DIR, category, "index.md")
            if os.path.exists(cat_index_path):
                sop_file_path, metadata, discovery_confidence = _match_sop_from_category_index(
                    cat_index_path, intent, detailed_description, keywords
                )

        # 2b. Global OKF Store Scan
        if not sop_file_path:
            intent_clean = intent.lower().strip()
            for root, _, files in os.walk(SOPS_DIR):
                for filename in files:
                    if filename.endswith(".md") and filename != "index.md":
                        filepath = os.path.join(root, filename)
                        try:
                            meta, _ = load_okf_concept(filepath)
                            title = meta.get("title", "").lower()
                            sop_id = meta.get("sop_id", "").lower()
                            if title == intent_clean or sop_id == intent_clean or (len(intent_clean) > 5 and intent_clean in title):
                                sop_file_path = filepath
                                metadata = meta
                                discovery_confidence = 1.0
                                print(f"[Discovery] [OKF Global Hit] Matched playbook by intent: {filepath}")
                                break
                        except Exception as e:
                            print(f"[Discovery Warning] Error checking {filename}: {e}")
                if sop_file_path:
                    break

    if not sop_file_path or not metadata:
        return None, None, 0.0, "(No reflection rules found)", "(No device quirks found)"

    # 3. Memory Path Resolution: Read rules_<SOP_ID>.md and hosts/<hostname>.md
    sop_id = metadata.get("sop_id", "SOP-DYN-000")
    sop_cat = metadata.get("category", category or "other")

    reflection_rules = load_reflection_rulebook(sop_id, category=sop_cat)
    device_quirks = load_device_profile(hostname) if hostname else "(No device quirks needed for tool call)"

    return sop_file_path, metadata, discovery_confidence, reflection_rules, device_quirks


def normalize_intent_text(text: str) -> str:
    """Normalizes text by lowercasing, stripping, and unifying Unicode dashes."""
    if not text:
        return ""
    return text.replace("\u2013", "-").replace("\u2014", "-").replace("–", "-").replace("—", "-").lower().strip()


def _analyze_and_verify_intake_match(
    intent: str,
    matched_file_path: str,
    keywords: list[str]
) -> Tuple[Optional[str], Optional[Dict[str, Any]], float]:
    """Analyzes the SOP matched by Intake Agent to verify if it genuinely matches the ticket INTENT."""
    if not matched_file_path:
        return None, None, 0.0

    candidate_path = matched_file_path
    if not os.path.isabs(candidate_path):
        kb_path = os.path.join(KB_DIR, matched_file_path)
        if os.path.exists(kb_path):
            candidate_path = kb_path
        else:
            target_fname = os.path.basename(matched_file_path)
            for root, _, files in os.walk(SOPS_DIR):
                if target_fname in files:
                    candidate_path = os.path.join(root, target_fname)
                    break

    if not os.path.exists(candidate_path):
        print(f"[Discovery Warning] Intake matched_file_path '{matched_file_path}' could not be resolved on disk.")
        return None, None, 0.0

    filename_clean = os.path.splitext(os.path.basename(candidate_path))[0].lower().replace("_", " ").replace("-", " ")
    intent_norm = normalize_intent_text(intent)

    intent_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", intent_norm)) - GENERIC_NOISE_KEYWORDS
    file_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", filename_clean)) - GENERIC_NOISE_KEYWORDS

    is_intent_match = False
    if candidate_path.endswith(".md"):
        try:
            meta, _ = load_okf_concept(candidate_path)
            title_norm = normalize_intent_text(meta.get("title", ""))
            sop_id_norm = normalize_intent_text(meta.get("sop_id", ""))
            
            if intent_norm in title_norm or title_norm in intent_norm or sop_id_norm in intent_norm:
                is_intent_match = True
            else:
                title_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", title_norm)) - GENERIC_NOISE_KEYWORDS
                if intent_words and title_words and intent_words.intersection(title_words):
                    is_intent_match = True
            
            if is_intent_match:
                print(f"[Discovery] [Intake Analysis] Intake OKF SOP '{os.path.basename(candidate_path)}' VERIFIED for intent '{intent}'.")
                return candidate_path, meta, 1.0
        except Exception as err:
            print(f"[Discovery Error] Failed to load intake OKF concept {candidate_path}: {err}")

    if intent_norm in filename_clean or filename_clean in intent_norm:
        is_intent_match = True
    elif intent_words and file_words and intent_words.intersection(file_words):
        is_intent_match = True

    if is_intent_match:
        try:
            meta, _ = load_okf_concept(candidate_path)
            return candidate_path, meta, 1.0
        except Exception:
            pass

    print(f"[Discovery] [Intake Analysis] Intake suggested SOP '{os.path.basename(candidate_path)}' did NOT pass intent verification for '{intent}'. Proceeding to search best match...")
    return None, None, 0.0


def _match_sop_from_category_index(
    cat_index_path: str,
    intent: str,
    detailed_description: str,
    keywords: list[str]
) -> Tuple[Optional[str], Optional[Dict[str, Any]], float]:
    """Navigates category index file and matches candidate SOPs strictly by INTENT."""
    cat_dir = os.path.dirname(cat_index_path)
    with open(cat_index_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    best_match_path = None
    best_metadata = None
    highest_score = 0.0

    intent_clean = normalize_intent_text(intent)
    intent_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", intent_clean)) - GENERIC_NOISE_KEYWORDS

    for line in lines:
        match = re.search(r"-\s*\[(.*?)\]\(\./(.*?)\)(?:\s*-\s*(.*))?", line.strip())
        if match:
            title, rel_filename, desc = match.groups()
            filepath = os.path.join(cat_dir, rel_filename)
            title_clean = normalize_intent_text(title)
            desc_clean = (desc or "").lower()

            score = 0.0
            if title_clean == intent_clean:
                score += 0.90
            elif intent_clean in title_clean or title_clean in intent_clean:
                score += 0.60
            else:
                title_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", title_clean)) - GENERIC_NOISE_KEYWORDS
                desc_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", desc_clean)) - GENERIC_NOISE_KEYWORDS
                
                matched_intent_words = intent_words.intersection(title_words.union(desc_words))
                if intent_words and matched_intent_words:
                    word_ratio = len(matched_intent_words) / len(intent_words)
                    score += round(0.50 * word_ratio, 2)

            for kw in keywords:
                kw_clean = kw.lower().strip()
                if kw_clean not in GENERIC_NOISE_KEYWORDS and len(kw_clean) > 3:
                    if kw_clean in title_clean or kw_clean in desc_clean:
                        score += 0.05

            if score > highest_score and os.path.exists(filepath):
                highest_score = score
                try:
                    meta, _ = load_okf_concept(filepath)
                    best_match_path = filepath
                    best_metadata = meta
                except Exception:
                    pass

    MIN_MATCH_THRESHOLD = 0.40
    if highest_score < MIN_MATCH_THRESHOLD:
        return None, None, 0.0

    return best_match_path, best_metadata, min(highest_score, 1.0)
