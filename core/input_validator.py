"""
Input Validation & Sanitization Module for SOP Ingestion
=========================================================
Strict pre-ingestion security gate enforcing:
1. File format allowlisting (.pdf, .docx, .csv, .xls, .xlsx, .md, .txt)
2. Hard file size cap (<= 10 MB)
3. Magic-byte file signature validation (anti-spoofing)
4. Maximum document length enforcement (<= 10 pages)
"""

import os
import re
import csv
from typing import Tuple, Optional, Dict, Any

# pyrefly: ignore [missing-import]
from core.security import check_zip_bomb, sanitize_filename

# Security Configuration Constants
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_PAGE_COUNT = 10                     # Maximum 10 document pages
MAX_TEXT_LINES = 600                    # Approx 60 lines/page * 10 pages
MAX_TEXT_WORDS = 5000                   # Approx 500 words/page * 10 pages
MAX_TABLE_ROWS = 600                    # Approx 60 rows/page * 10 pages

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".csv",
    ".xls",
    ".xlsx",
    ".md",
    ".txt",
}

# Dangerous binary executable signatures (reject immediately)
DANGEROUS_MAGIC_BYTES = [
    (b"MZ", "Windows PE Executable / DLL (.exe, .dll, .scr)"),
    (b"\x7fELF", "Linux ELF Executable binary"),
    (b"\xca\xfe\xba\xbe", "Java Classfile / Mach-O Binary"),
    (b"\xfe\xed\xfa", "Mach-O Binary"),
    (b"%!PS", "PostScript Executable"),
]


class SOPInputValidationError(ValueError):
    """Raised when an uploaded SOP fails pre-ingestion security, format, size, or page validation."""
    def __init__(self, filename: str, reason: str, metadata: Optional[Dict[str, Any]] = None):
        self.filename = filename
        self.reason = reason
        self.metadata = metadata or {}
        super().__init__(f"Input validation rejected '{filename}': {reason}")


def check_file_extension(filepath: str) -> Tuple[bool, Optional[str], str]:
    """Validates that file extension is within strict allowlist."""
    ext = os.path.splitext(filepath)[1].lower()
    if not ext:
        return False, f"File has no extension. Only allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}", ""
    if ext not in ALLOWED_EXTENSIONS:
        return False, (
            f"Unsupported or disallowed file extension '{ext}'. "
            f"Strict allowlist permits only: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        ), ext
    return True, None, ext


def check_file_size(filepath: str) -> Tuple[bool, Optional[str], int, float]:
    """Validates that file size is strictly <= 10 MB."""
    size_bytes = os.path.getsize(filepath)
    size_mb = size_bytes / (1024 * 1024)
    if size_bytes > MAX_FILE_SIZE_BYTES:
        return False, (
            f"File size ({size_mb:.2f} MB / {size_bytes:,} bytes) exceeds maximum limit of 10.0 MB."
        ), size_bytes, size_mb
    return True, None, size_bytes, size_mb


def check_magic_bytes(filepath: str, ext: str) -> Tuple[bool, Optional[str]]:
    """Verifies file header signature against declared extension to prevent spoofing."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(16)
    except Exception as e:
        return False, f"Could not read file header: {e}"

    # 1. Reject known dangerous executable magic signatures
    for magic, desc in DANGEROUS_MAGIC_BYTES:
        if header.startswith(magic):
            return False, f"Security Violation: File header matches dangerous executable format ({desc})."

    # 2. Verify format-specific signatures
    if ext == ".pdf":
        if not header.startswith(b"%PDF-"):
            return False, "File spoofing detected: .pdf extension provided, but file does not start with '%PDF-' signature."

    elif ext in [".docx", ".xlsx"]:
        # DOCX / XLSX are zip archives starting with PK\x03\x04
        if not header.startswith(b"PK\x03\x04"):
            return False, f"File spoofing detected: '{ext}' file does not contain a valid Office Open XML (PKZip) header."

    elif ext == ".xls":
        # Legacy OLE Compound Document or Zip
        is_ole = header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
        is_zip = header.startswith(b"PK\x03\x04")
        if not (is_ole or is_zip):
            return False, "File spoofing detected: .xls file does not contain a valid Excel binary header."

    elif ext in [".txt", ".md", ".csv"]:
        # Ensure text file does not contain embedded null bytes (typical of binary executables)
        try:
            with open(filepath, "r", encoding="utf-8", errors="strict") as f:
                sample = f.read(4096)
                if "\x00" in sample:
                    return False, f"Security Violation: Binary null bytes detected in plain text '{ext}' file."
        except UnicodeDecodeError:
            # Try latin-1 fallback with strict check on null bytes
            try:
                with open(filepath, "r", encoding="latin-1", errors="strict") as f:
                    sample = f.read(4096)
                    if "\x00" in sample:
                        return False, f"Security Violation: Binary null bytes detected in plain text '{ext}' file."
            except Exception as read_err:
                return False, f"Could not decode text file: {read_err}"

    return True, None


def count_document_pages(filepath: str, ext: str) -> Tuple[bool, Optional[str], int, Dict[str, Any]]:
    """Calculates or estimates document page count and enforces the 10-page maximum."""
    details: Dict[str, Any] = {}

    if ext == ".pdf":
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
            doc = fitz.open(filepath)
            page_count = len(doc)
            doc.close()
            details["pdf_page_count"] = page_count
            if page_count > MAX_PAGE_COUNT:
                return False, (
                    f"PDF document contains {page_count} pages, which exceeds the maximum limit of {MAX_PAGE_COUNT} pages."
                ), page_count, details
            return True, None, page_count, details
        except Exception as pdf_err:
            return False, f"Failed to parse PDF page count: {pdf_err}", 0, details

    elif ext == ".docx":
        try:
            from docx import Document
            doc = Document(filepath)
            
            # Count paragraphs, tables, words
            total_paragraphs = len(doc.paragraphs)
            total_words = sum(len(p.text.split()) for p in doc.paragraphs)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        total_words += len(cell.text.split())

            details["total_words"] = total_words
            details["total_paragraphs"] = total_paragraphs
            
            # Word-based page estimation (~500 words per page)
            estimated_pages = max(1, (total_words + 499) // 500)
            details["estimated_pages"] = estimated_pages

            if estimated_pages > MAX_PAGE_COUNT or total_words > MAX_TEXT_WORDS:
                return False, (
                    f"DOCX document contains approximately {estimated_pages} pages (~{total_words} words), "
                    f"which exceeds the maximum limit of {MAX_PAGE_COUNT} pages ({MAX_TEXT_WORDS} words max)."
                ), estimated_pages, details
            return True, None, estimated_pages, details
        except Exception as docx_err:
            return False, f"Failed to inspect DOCX page count: {docx_err}", 0, details

    elif ext == ".csv":
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                row_count = sum(1 for _ in reader)
            
            details["csv_rows"] = row_count
            estimated_pages = max(1, (row_count + 59) // 60)
            details["estimated_pages"] = estimated_pages

            if row_count > MAX_TABLE_ROWS:
                return False, (
                    f"CSV file contains {row_count} rows (~{estimated_pages} pages), "
                    f"which exceeds the maximum limit of {MAX_TABLE_ROWS} rows (~{MAX_PAGE_COUNT} pages)."
                ), estimated_pages, details
            return True, None, estimated_pages, details
        except Exception as csv_err:
            return False, f"Failed to inspect CSV row count: {csv_err}", 0, details

    elif ext in [".xls", ".xlsx"]:
        try:
            # Inspect using python markitdown or simple line estimate
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(filepath)
            content = result.text_content if result else ""
            lines = [l for l in content.splitlines() if l.strip()]
            line_count = len(lines)
            words = sum(len(l.split()) for l in lines)
            estimated_pages = max(1, max((line_count + 59) // 60, (words + 499) // 500))
            details["line_count"] = line_count
            details["words"] = words
            details["estimated_pages"] = estimated_pages

            if line_count > MAX_TABLE_ROWS or estimated_pages > MAX_PAGE_COUNT:
                return False, (
                    f"Spreadsheet '{ext}' contains ~{line_count} rows (~{estimated_pages} pages), "
                    f"which exceeds the maximum limit of {MAX_PAGE_COUNT} pages ({MAX_TABLE_ROWS} rows max)."
                ), estimated_pages, details
            return True, None, estimated_pages, details
        except Exception:
            # Fallback size-based check
            return True, None, 1, details

    elif ext in [".txt", ".md"]:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            
            line_count = len(lines)
            total_words = sum(len(line.split()) for line in lines)
            estimated_pages = max(1, max((line_count + 59) // 60, (total_words + 499) // 500))
            
            details["line_count"] = line_count
            details["total_words"] = total_words
            details["estimated_pages"] = estimated_pages

            if line_count > MAX_TEXT_LINES or total_words > MAX_TEXT_WORDS:
                return False, (
                    f"Text document contains {line_count} lines and {total_words} words (~{estimated_pages} pages), "
                    f"which exceeds the maximum limit of {MAX_PAGE_COUNT} pages ({MAX_TEXT_LINES} lines / {MAX_TEXT_WORDS} words max)."
                ), estimated_pages, details
            return True, None, estimated_pages, details
        except Exception as txt_err:
            return False, f"Failed to inspect text file length: {txt_err}", 0, details

    return True, None, 1, details


def validate_sop_file(filepath: str) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """Comprehensive Input Validation & Sanitization Gate.
    
    Checks:
    1. File existence
    2. Strict extension allowlist (.pdf, .docx, .csv, .xls, .xlsx, .md, .txt)
    3. File size limit (<= 10 MB)
    4. Magic-byte signature match & dangerous binary rejection
    5. Maximum document length (<= 10 pages)

    Returns:
        (is_valid: bool, error_message: Optional[str], metadata: Dict[str, Any])
    """
    metadata: Dict[str, Any] = {
        "filepath": filepath,
        "filename": os.path.basename(filepath) if filepath else "",
    }

    if not filepath or not os.path.exists(filepath):
        return False, f"File does not exist at path: '{filepath}'", metadata

    # 1. Extension Check
    is_ext_valid, ext_err, ext = check_file_extension(filepath)
    metadata["extension"] = ext
    if not is_ext_valid:
        return False, ext_err, metadata

    # 2. File Size Check
    is_size_valid, size_err, size_bytes, size_mb = check_file_size(filepath)
    metadata["size_bytes"] = size_bytes
    metadata["size_mb"] = round(size_mb, 2)
    if not is_size_valid:
        return False, size_err, metadata

    # 3. Magic-Byte Header Verification
    is_magic_valid, magic_err = check_magic_bytes(filepath, ext)
    if not is_magic_valid:
        return False, magic_err, metadata

    # 4. Zip Bomb & Decompression Ratio Guard (.docx, .xlsx)
    if ext in [".docx", ".xlsx"]:
        is_zip_safe, zip_err = check_zip_bomb(filepath)
        if not is_zip_safe:
            return False, zip_err, metadata

    # 5. Page Count / Length Check
    is_page_valid, page_err, page_count, page_details = count_document_pages(filepath, ext)
    metadata["page_count"] = page_count
    metadata["page_details"] = page_details
    if not is_page_valid:
        return False, page_err, metadata

    return True, None, metadata
