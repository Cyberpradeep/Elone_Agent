import os
import base64
import datetime
from typing import Tuple, Optional, List, Dict, Any
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


# ---------------------------------------------------------------------------
# Document-order-preserving extraction (text + inline images, interleaved
# exactly as they appear in the source file, not text-then-all-images-at-end)
# ---------------------------------------------------------------------------

def _extract_ordered_docx(filepath: str) -> List[Dict[str, Any]]:
    """Walks a DOCX body in true document order (including inside tables),
    returning text and inline image segments in the exact sequence Word
    stores them. Each image segment appears right after the paragraph(s)
    that precede it in the file.
    """
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(filepath)
    segments: List[Dict[str, Any]] = []
    text_buffer: List[str] = []
    seen_embed_ids = set()
    image_counter = 0

    def flush_text():
        if text_buffer:
            combined = "\n".join(t for t in text_buffer if t.strip())
            if combined.strip():
                segments.append({"type": "text", "content": combined})
            text_buffer.clear()

    # lxml's .iter() is a document-order, depth-first walk: a paragraph node
    # is yielded, and any images nested inside it are yielded shortly after
    # as the walk descends into that paragraph's children.
    for elem in doc.element.body.iter():
        tag = elem.tag
        if tag == qn("w:p"):
            para_text = "".join(node.text or "" for node in elem.iter(qn("w:t")))
            if para_text.strip():
                text_buffer.append(para_text)
        elif tag == qn("a:blip"):
            embed_id = elem.get(qn("r:embed"))
            if not embed_id or embed_id in seen_embed_ids:
                continue
            seen_embed_ids.add(embed_id)
            try:
                image_part = doc.part.related_parts[embed_id]
            except KeyError:
                continue
            image_counter += 1
            flush_text()  # commit the text that precedes this image before inserting it
            segments.append({
                "type": "image",
                "bytes": image_part.blob,
                "mime_type": image_part.content_type,
                "label": f"Image {image_counter} (inline, following the text above)",
            })

    flush_text()
    return segments


def _extract_ordered_pdf(filepath: str) -> List[Dict[str, Any]]:
    """Walks a PDF page-by-page, sorting each page's text and image blocks
    into top-to-bottom reading order so a screenshot stays interleaved with
    the instruction text it illustrates instead of being pulled out separately.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(filepath)
    segments: List[Dict[str, Any]] = []
    image_counter = 0

    for page_index in range(len(doc)):
        page = doc[page_index]
        raw_blocks = page.get_text("dict").get("blocks", [])
        raw_blocks.sort(key=lambda b: (round(b.get("bbox", [0, 0, 0, 0])[1]), b.get("bbox", [0, 0, 0, 0])[0]))

        for block in raw_blocks:
            if block.get("type") == 0:  # text block
                lines_text = []
                for line in block.get("lines", []):
                    spans_text = "".join(span.get("text", "") for span in line.get("spans", []))
                    if spans_text.strip():
                        lines_text.append(spans_text)
                block_text = "\n".join(lines_text)
                if block_text.strip():
                    segments.append({"type": "text", "content": block_text})
            elif block.get("type") == 1:  # image block
                img_bytes = block.get("image")
                if not img_bytes:
                    continue
                ext = block.get("ext", "png")
                mime_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
                image_counter += 1
                segments.append({
                    "type": "image",
                    "bytes": img_bytes,
                    "mime_type": mime_type,
                    "label": f"Page {page_index + 1}, Image {image_counter} (inline, following the text above)",
                })

    doc.close()
    return segments


def extract_ordered_sop_content(filepath: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Document-order-preserving extractor.

    Returns (parser_type, segments) where segments is a list of
    {"type": "text", "content": str} and
    {"type": "image", "bytes": bytes, "mime_type": str, "label": str}
    entries in the exact sequence they appear in the source file -- so the
    image that illustrates a step stays positioned right after that step's
    text, matching the original SOP layout.

    Falls back to the plain extract_full_text() result (wrapped as a single
    text segment) for formats without embedded-image support (.txt, .xlsx,
    .pptx, ...) or if the ordered walk fails for any reason -- e.g. a
    corrupt/legacy .doc masquerading as .docx.
    """
    ext = os.path.splitext(filepath)[1].lower()
    filename = os.path.basename(filepath)

    try:
        if ext == ".docx":
            segments = _extract_ordered_docx(filepath)
            text_only = "\n\n".join(s["content"] for s in segments if s["type"] == "text")
            has_images = any(s["type"] == "image" for s in segments)
            if segments and (_is_valid_text_quality(text_only) or has_images):
                print(f"[DocumentParser] [Ordered DOCX Walk] Extracted {len(segments)} ordered segment(s) from: {filename}")
                _log_parsed_text(filepath, "ordered_docx_walk", text_only)
                return "ordered_docx_walk", segments
        elif ext == ".pdf":
            segments = _extract_ordered_pdf(filepath)
            text_only = "\n\n".join(s["content"] for s in segments if s["type"] == "text")
            if segments and _is_valid_text_quality(text_only):
                print(f"[DocumentParser] [Ordered PDF Walk] Extracted {len(segments)} ordered segment(s) from: {filename}")
                _log_parsed_text(filepath, "ordered_pdf_walk", text_only)
                return "ordered_pdf_walk", segments
            # No usable embedded text (likely a scanned PDF) -> fall through
            # to the legacy path, which handles Vision OCR transcription.
    except Exception as e:
        print(f"[DocumentParser Warning] Ordered content walk failed for {filename}: {e}")

    parser_type, raw_text = extract_full_text(filepath)
    return parser_type, [{"type": "text", "content": raw_text}]

