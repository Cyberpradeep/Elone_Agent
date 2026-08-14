import os
import base64
import datetime
from typing import Tuple, Optional
from langchain_core.messages import HumanMessage

from config.llm_config import get_llm

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_PARSER_DIR = os.path.join(BASE_DIR, "knowledge_base", "logs", "parser")


def _log_parsed_text(filepath: str, parser_engine: str, raw_text: str, page_count: Optional[int] = None) -> str:
    """Audit log helper: writes raw extracted text and metadata header to knowledge_base/logs/parser/."""
    os.makedirs(LOGS_PARSER_DIR, exist_ok=True)
    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d_%H%M%S")
    filename = os.path.basename(filepath)
    log_filename = f"{timestamp_str}_{filename}.log"
    log_path = os.path.join(LOGS_PARSER_DIR, log_filename)

    header_lines = [
        "============================================================",
        "  SOP INGESTION PIPELINE — PARSER AUDIT LOG",
        "============================================================",
        f"  Source File:          {filename}",
        f"  Source Absolute Path: {os.path.abspath(filepath)}",
        f"  Parser Engine:        {parser_engine}",
        f"  Character Count:      {len(raw_text)}",
        f"  Page Count:           {page_count if page_count is not None else 'N/A'}",
        f"  Timestamp:            {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "============================================================",
        "",
        "--- RAW EXTRACTED TEXT START ---",
        raw_text,
        "--- RAW EXTRACTED TEXT END ---",
        ""
    ]

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header_lines))

    print(f"[DocumentParser Log] Saved raw text audit log ({len(raw_text)} chars) to: {log_path}")
    return log_path


def _is_valid_text_quality(text: str) -> bool:
    """Quality Inspector: Checks if extracted text is readable (not unreadable binary junk or control characters)."""
    if not text or len(text.strip()) < 15:
        return False
    
    # Check printable character ratio
    printable_chars = sum(1 for c in text if c.isprintable() or c in ("\n", "\r", "\t"))
    printable_ratio = printable_chars / len(text)
    
    # Check alphanumeric ratio
    alpha_chars = sum(1 for c in text if c.isalnum() or c.isspace())
    alpha_ratio = alpha_chars / len(text)
    
    return printable_ratio > 0.85 and alpha_ratio > 0.40


def extract_full_text(filepath: str) -> Tuple[str, str]:
    """Universal Document Extractor using Microsoft MarkItDown as primary engine for ALL formats.

    Supports: .pdf, .docx, .doc, .xlsx, .xls, .pptx, .html, .txt, .md.
    Fallback: PyMuPDF + Vision OCR for scanned image PDFs.
    Logs all extracted text to knowledge_base/logs/parser/.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found at: {filepath}")

    filename = os.path.basename(filepath)

    # 1. PRIMARY ENGINE: Microsoft MarkItDown for all document formats
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(filepath)
        if result and result.text_content and _is_valid_text_quality(result.text_content):
            print(f"[DocumentParser] [MarkItDown Universal Engine] Extracted clean markdown from: {filename}")
            _log_parsed_text(filepath, "markitdown_parser", result.text_content)
            return "markitdown_parser", result.text_content
    except Exception as md_err:
        print(f"[DocumentParser Warning] MarkItDown engine failed for {filename}: {md_err}")

    # 2. FALLBACK ENGINE: Plaintext / PyMuPDF OCR for scanned files
    ext = os.path.splitext(filepath)[1].lower()

    if ext in [".txt", ".md", ".json", ".csv", ".html"]:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
            _log_parsed_text(filepath, "txt_fallback", text)
            return "txt_fallback", text

    if ext == ".pdf":
        return _fallback_pdf_ocr(filepath)

    # For binary document formats (.docx, .doc, .xlsx, .xls, .pptx), DO NOT read raw bytes as text
    if ext in [".docx", ".doc", ".xlsx", ".xls", ".pptx"]:
        err_msg = f"MarkItDown failed to parse binary document '{filename}' (ext: {ext}). Skipping text fallback to prevent binary corruption."
        print(f"[DocumentParser Error] {err_msg}")
        _log_parsed_text(filepath, "failed_binary_parse", f"ERROR: {err_msg}")
        raise ValueError(err_msg)

    # Fallback read for all other text files
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
            _log_parsed_text(filepath, "fallback_reader", text)
            return "fallback_reader", text
    except Exception as e:
        raise ValueError(f"Could not parse document '{filename}': {e}") from e


def _fallback_pdf_ocr(filepath: str) -> Tuple[str, str]:
    """Fallback PDF extractor using PyMuPDF and Vision OCR for scanned images."""
    import fitz  # PyMuPDF

    doc = fitz.open(filepath)
    page_count = len(doc)
    text_content = ""

    for page in doc:
        text_content += page.get_text() + "\n"

    if len(text_content.strip()) > 50:
        _log_parsed_text(filepath, "pymupdf_fallback", text_content, page_count=page_count)
        return "pymupdf_fallback", text_content

    # Vision OCR for scanned PDF pages
    print(f"[DocumentParser] Attempting Vision OCR transcription for scanned PDF: {os.path.basename(filepath)}...")
    ocr_text = _run_vision_ocr(doc, filepath)
    _log_parsed_text(filepath, "vision_ocr", ocr_text, page_count=page_count)
    return "vision_ocr", ocr_text


def _run_vision_ocr(doc, filepath: str) -> str:
    """Uses PyMuPDF to render pages to PNG images and Vision LLM to OCR transcribe."""
    try:
        llm = get_llm("execution_planning", temperature=0)
        full_ocr = []

        for idx, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            b64_img = base64.b64encode(img_bytes).decode("utf-8")

            message = HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": f"Transcribe all text, commands, and tables from page {idx+1} of this SOP document into clean Markdown."
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_img}"}
                    }
                ]
            )
            res = llm.invoke([message])
            text = res.content if hasattr(res, "content") else str(res)
            full_ocr.append(text)

        return "\n\n".join(full_ocr)
    except Exception as e:
        print(f"[DocumentParser Error] Vision OCR failed: {e}")
        return ""

