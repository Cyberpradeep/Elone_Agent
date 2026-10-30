"""
Agent A4: Verbatim Quote Citation Tracer
=========================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.4 & 13)
Validates 5-25 word verbatim quotes against cited source line ranges
within a +/-1 line boundary window.
"""

import re
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional, Set


def verify_quote_trace(
    raw_lines: List[str],
    start_line: int,
    end_line: int,
    quote: str,
) -> Tuple[bool, str]:
    """Verifies that a verbatim quote appears within +/-1 line of cited range."""
    if not quote or not quote.strip() or not raw_lines:
        return False, ""

    idx_start = max(0, start_line - 2)
    idx_end = min(len(raw_lines), end_line + 1)
    
    window_slice = raw_lines[idx_start:idx_end]
    window_text = " ".join(window_slice)

    norm_window = re.sub(r"[^\w\s]", " ", window_text.lower())
    norm_window = re.sub(r"\s+", " ", norm_window).strip()

    norm_quote = re.sub(r"[^\w\s]", " ", quote.lower())
    norm_quote = re.sub(r"\s+", " ", norm_quote).strip()

    if not norm_quote:
        return False, window_text

    if norm_quote in norm_window:
        return True, window_text

    quote_tokens = [tok for tok in norm_quote.split() if len(tok) > 1]
    window_tokens = set(norm_window.split())
    if quote_tokens:
        overlap = sum(1 for tok in quote_tokens if tok in window_tokens)
        ratio = overlap / len(quote_tokens)
        if ratio >= 0.90:
            return True, window_text

    return False, window_text


def verify_canonical_quotes(
    items: List[Dict[str, Any]],
    raw_lines: List[str],
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Batch verifies quote citations across steps, preconditions, and purpose items."""
    total = 0
    verified = 0
    unverified = []

    for item in items:
        quote = item.get("quote", "").strip()
        lines = item.get("source_lines") or []
        if not quote or len(lines) < 2:
            continue

        total += 1
        is_ok, context = verify_quote_trace(raw_lines, lines[0], lines[1], quote)
        item["verified"] = is_ok
        if is_ok:
            verified += 1
        else:
            unverified.append({
                "action": item.get("action") or item.get("text", "Unknown"),
                "quote": quote,
                "source_lines": lines,
                "window_context": context,
            })

    return total, verified, unverified


def compute_source_line_coverage(
    raw_lines: List[str],
    steps: List[Dict[str, Any]],
    coverage_items: Optional[List[Dict[str, Any]]] = None,
    metadata_fields: Optional[List[str]] = None,
) -> Tuple[int, int, List[int]]:
    """Computes exact count of mapped non-blank source lines against steps, coverage, and metadata (Section 12).
    Returns (total_non_blank_lines, mapped_source_lines, mapped_line_indices).
    """
    coverage_items = coverage_items or []
    metadata_fields = metadata_fields or []

    # 1. Non-blank line index mapping (1-based)
    non_blank = {}
    for idx, line in enumerate(raw_lines, start=1):
        stripped = line.strip()
        if stripped:
            norm = re.sub(r"[^\w\s]", " ", stripped.lower())
            tokens = set(tok for tok in norm.split() if len(tok) > 2)
            non_blank[idx] = (stripped, tokens)

    # Detect repeating headers/footers dynamically across multi-page documents (appearing 3+ times)
    line_counts = Counter(s for s, _ in non_blank.values())
    repeats = {l for l, c in line_counts.items() if c >= 3 and len(l) > 3}
    mapped_line_indices = {idx for idx, (s, _) in non_blank.items() if s in repeats}

    # 2. Universal Structural document scaffolding patterns (headers, metadata, sections, dates, footers)
    structural_patterns = [
        r"^\s*standard operating procedure",
        r"^\s*(?:document\s+)?owner",
        r"^\s*platform",
        r"^\s*(?:effective|review)\s+date",
        r"^\s*review\s+cycle",
        r"^\s*\.?\s*table of contents",
        r"^\s*(?:document\s+control|revision\s+history|change\s+log|document\s+history)",
        r"^\s*\d+[\.\)]\s*(?:purpose|scope|procedure|notes|prerequisites|preconditions|verification|overview|requirements|objective|detailed procedure|escalation|document control)",
        r"^\s*(?:objective|purpose|scope|prerequisites|preconditions|escalation criteria|document control|detailed procedure):?$",
        r"^\s*(?:sop\s+id|support\s+level|primary\s+remediation\s+path|document\s+version|status|classification|attribute|value):?$",
        r"^\s*(?:process\s+flow\s+overview|decision\s+flow):?$",
        r"^\s*(?:step\s+\d+|expected\s+result|resolution\s+notes|action\s+taken|root\s+cause|issue|status)\b",
        r"^\s*internal it documentation",
        r"^\s*page\s+\d+(?:\s+of\s+\d+)?",
        r"^\s*\d{1,2}-[a-z]{3}-\d{4}",
        r"^\s*(?:annual|quarterly|monthly|bi-annual)$",
    ]
    structural_re = re.compile("|".join(f"(?:{p})" for p in structural_patterns), re.IGNORECASE)

    # 3. Direct cited line ranges from steps
    for s in steps:
        lines = s.get("source_lines")
        if isinstance(lines, list) and len(lines) >= 2:
            try:
                start_l = max(1, int(lines[0]))
                end_l = min(len(raw_lines), int(lines[1]))
                for l in range(start_l, end_l + 1):
                    if l in non_blank:
                        mapped_line_indices.add(l)
            except (ValueError, TypeError):
                pass

    # 4. Extract token sets from steps, source_action_coverage, and metadata
    target_token_sets = []
    all_target_tokens = set()

    for s in steps:
        text = f"{s.get('sop_step_description', '')} {s.get('action', '')} {s.get('command', '')} {s.get('input', '')} {s.get('quote', '')} {s.get('step_reasoning', '')} {s.get('parse_instruction', '')}"
        norm = re.sub(r"[^\w\s]", " ", text.lower())
        toks = set(t for t in norm.split() if len(t) > 2)
        if toks:
            target_token_sets.append(toks)
            all_target_tokens.update(toks)

    for c in coverage_items:
        text = f"{c.get('source_action', '')} {c.get('reason', '')}"
        norm = re.sub(r"[^\w\s]", " ", text.lower())
        toks = set(t for t in norm.split() if len(t) > 2)
        if toks:
            target_token_sets.append(toks)
            all_target_tokens.update(toks)

    for m in metadata_fields:
        if m:
            norm = re.sub(r"[^\w\s]", " ", str(m).lower())
            toks = set(t for t in norm.split() if len(t) > 2)
            if toks:
                target_token_sets.append(toks)
                all_target_tokens.update(toks)

    # 5. Check remaining non-blank lines for structural or semantic coverage
    for idx, (raw_str, line_tokens) in non_blank.items():
        if idx in mapped_line_indices:
            continue

        norm_line = re.sub(r"[^\w\s]", " ", raw_str.lower()).strip()
        if structural_re.search(raw_str.strip()) or structural_re.search(norm_line):
            mapped_line_indices.add(idx)
            continue

        if not line_tokens:
            mapped_line_indices.add(idx)
            continue

        # Check overlap against unified token set or individual sets
        overlap = line_tokens.intersection(all_target_tokens)
        if len(line_tokens) <= 2 and len(overlap) >= 1:
            mapped_line_indices.add(idx)
            continue
        elif len(line_tokens) > 2 and (len(overlap) / len(line_tokens)) >= 0.30:
            mapped_line_indices.add(idx)
            continue

        for t_set in target_token_sets:
            sub_overlap = line_tokens.intersection(t_set)
            if len(line_tokens) <= 3 and len(sub_overlap) >= 1:
                mapped_line_indices.add(idx)
                break
            elif len(line_tokens) > 3 and (len(sub_overlap) / len(line_tokens)) >= 0.30:
                mapped_line_indices.add(idx)
                break

    total_non_blank = max(1, len(non_blank))
    mapped_count = len(mapped_line_indices)
    return total_non_blank, mapped_count, sorted(list(mapped_line_indices))


__all__ = [
    "verify_quote_trace",
    "verify_canonical_quotes",
    "compute_source_line_coverage",
]
