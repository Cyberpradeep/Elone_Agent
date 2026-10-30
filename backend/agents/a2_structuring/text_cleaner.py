"""
Agent A2: Text Cleaner & Transformation Logger
=============================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.2 & 16)
Implements deterministic cleaning rules:
- WS-01: Whitespace normalization (wording unchanged, trims leading/trailing/multiple spaces)
- HF-01: Page header/footer removal (pattern 'Page n of m', running footer)
- HF-02: Repeated all-caps header removal (repeated >= 2 times, length >= 12 chars)

Every removal or normalization is logged in canonical_sop['transformations'] with:
- cleaning_rule_id
- type
- detail
- original_line
"""

import re
from collections import Counter
from typing import Tuple, List, Dict, Any, Optional


PAGE_HEADER_FOOTER_PATTERNS = [
    re.compile(r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*-\s*\d+\s*-\s*$"),
    re.compile(r"^\s*page\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:confidential|internal|all rights reserved|proprietary)\s*[-•|/]\s*page\s+\d+.*$", re.IGNORECASE),
    re.compile(r"^\s*page\s+\d+\s*[-•|/]\s*(?:confidential|internal|all rights reserved|proprietary).*$", re.IGNORECASE),
    re.compile(r"^\s*(?:page|pg\.)\s*\d+\s*/\s*\d+\s*$", re.IGNORECASE),
]


def is_page_header_footer(line: str) -> bool:
    """Checks if a line matches standard page header or footer patterns (HF-01)."""
    s = line.strip()
    if not s:
        return False
    for pat in PAGE_HEADER_FOOTER_PATTERNS:
        if pat.match(s):
            return True
    return False


def is_candidate_caps_header(line: str) -> bool:
    """Checks if a line qualifies as candidate all-caps header: >= 12 chars, all uppercase letters."""
    s = line.strip()
    if len(s) < 12:
        return False
    # Must contain at least one letter and all letters must be uppercase
    letters = [ch for ch in s if ch.isalpha()]
    return len(letters) >= 5 and all(ch.isupper() for ch in letters)


def clean_and_normalize_text(raw_text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Applies deterministic cleaning rules WS-01, HF-01, and HF-02 per Section 5.2 & 16.
    
    Returns:
        (cleaned_text: str, transformations: List[Dict[str, Any]])
    """
    if not raw_text:
        return "", []

    raw_lines = raw_text.splitlines()
    transformations: List[Dict[str, Any]] = []

    # Pass 1: Identify candidate repeated all-caps headers (HF-02)
    # Header appears >= 2 times and is all-caps >= 12 chars
    caps_freq = Counter()
    for line in raw_lines:
        s = line.strip()
        if is_candidate_caps_header(s):
            caps_freq[s] += 1

    repeated_headers = {s for s, count in caps_freq.items() if count >= 2}

    cleaned_lines: List[str] = []
    seen_caps_headers = set()

    # Pass 2: Clean and log transformations
    for line_idx, line in enumerate(raw_lines, start=1):
        stripped = line.strip()

        # Rule HF-01: Page header/footer pattern
        if is_page_header_footer(stripped):
            transformations.append({
                "cleaning_rule_id": "HF-01",
                "type": "header_footer_removal",
                "detail": f"Removed page header/footer line at source line {line_idx}",
                "original_line": line,
            })
            continue

        # Rule HF-02: Repeated all-caps corporate header
        if stripped in repeated_headers:
            if stripped in seen_caps_headers:
                # Remove subsequent repetitions of the running header
                transformations.append({
                    "cleaning_rule_id": "HF-02",
                    "type": "repeated_header_removal",
                    "detail": f"Removed repeated all-caps header: '{stripped[:60]}'",
                    "original_line": line,
                })
                continue
            else:
                seen_caps_headers.add(stripped)

        # Blank lines
        if not stripped:
            if line:  # Line had whitespace characters but was blank
                transformations.append({
                    "cleaning_rule_id": "WS-01",
                    "type": "whitespace_normalization",
                    "detail": f"Removed whitespace-only blank line at source line {line_idx}",
                    "original_line": line,
                })
            continue

        # Rule WS-01: Whitespace normalization (wording unchanged)
        # Collapse multiple internal whitespace / tabs, trim ends
        normalized_line = re.sub(r"[ \t]+", " ", stripped)
        if normalized_line != line:
            transformations.append({
                "cleaning_rule_id": "WS-01",
                "type": "whitespace_normalization",
                "detail": "Normalized leading, trailing, or multiple whitespace characters",
                "original_line": line,
            })

        cleaned_lines.append(normalized_line)

    cleaned_text = "\n".join(cleaned_lines)
    return cleaned_text, transformations

