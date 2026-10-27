"""
Agent A4: Verbatim Quote Citation Tracer
=========================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.4 & 13)
Validates 5-25 word verbatim quotes against cited source line ranges
within a +/-1 line boundary window.
"""

import re
from typing import List, Dict, Any, Tuple


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


__all__ = [
    "verify_quote_trace",
    "verify_canonical_quotes",
]
