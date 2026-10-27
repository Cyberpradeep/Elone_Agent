"""
Agent A1: Ingestion & Document Parsing Agent
============================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.1 & 7)
- Stage 1: Intake Validation (Allowlisting, magic bytes, file size cap)
- Stage 2: Universal Document Extraction (MarkItDown engine, ordered segments)
- Stage 3: Multi-Modal VLM Image Extraction (Vision LLM & confidence scoring)
"""

from agents.a1_ingestion.intake_validator import (
    validate_sop_file,
    check_file_extension,
    check_file_size,
    check_magic_bytes,
    count_document_pages,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    MAX_PAGE_COUNT,
    SOPInputValidationError,
)
from agents.a1_ingestion.document_extractor import (
    extract_full_text,
    extract_ordered_sop_content,
    _log_parsed_text,
    _is_valid_text_quality,
)
from agents.a1_ingestion.link_scraper import (
    extract_urls_from_markdown,
    fetch_and_convert_url,
)
from agents.a1_ingestion.vlm_extractor import (
    analyze_and_save_image,
    analyze_image_bytes,
    process_sop_images,
    extract_images_from_pdf,
    extract_images_from_docx,
    extract_confidence_score,
    guess_mime_type,
)

__all__ = [
    "validate_sop_file",
    "check_file_extension",
    "check_file_size",
    "check_magic_bytes",
    "count_document_pages",
    "ALLOWED_EXTENSIONS",
    "MAX_FILE_SIZE_BYTES",
    "MAX_PAGE_COUNT",
    "SOPInputValidationError",
    "extract_full_text",
    "extract_ordered_sop_content",
    "_log_parsed_text",
    "_is_valid_text_quality",
    "extract_urls_from_markdown",
    "fetch_and_convert_url",
    "analyze_and_save_image",
    "analyze_image_bytes",
    "process_sop_images",
    "extract_images_from_pdf",
    "extract_images_from_docx",
    "extract_confidence_score",
    "guess_mime_type",
]
