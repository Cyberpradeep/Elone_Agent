import os
import base64
import fitz  # PyMuPDF
from typing import Tuple

from shared.llm_config import get_llm


def extract_full_text(filepath: str) -> Tuple[str, str]:
    """Universal Document Extractor using Microsoft MarkItDown as primary engine for ALL formats.

    Supports: .pdf, .docx, .doc, .xlsx, .xls, .pptx, .html, .txt, .md.
    Fallback: PyMuPDF + Vision OCR for scanned image PDFs.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found at: {filepath}")

    filename = os.path.basename(filepath)

    # 1. PRIMARY ENGINE: Microsoft MarkItDown for all document formats
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(filepath)
        if result and result.text_content and len(result.text_content.strip()) > 20:
            print(f"[DocumentParser] [MarkItDown Universal Engine] Extracted clean markdown from: {filename}")
            return "markitdown_parser", result.text_content
    except Exception as md_err:
        print(f"[DocumentParser Warning] MarkItDown engine failed for {filename}: {md_err}")

    # 2. FALLBACK ENGINE: Plaintext / PyMuPDF OCR for scanned files
    ext = os.path.splitext(filepath)[1].lower()

    if ext in [".txt", ".md"]:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return "txt_fallback", f.read()

    if ext == ".pdf":
        return _fallback_pdf_ocr(filepath)

    # Fallback read for all other text files
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return "fallback_reader", f.read()
    except Exception as e:
        raise ValueError(f"Could not parse document '{filename}': {e}") from e


def _fallback_pdf_ocr(filepath: str) -> Tuple[str, str]:
    """Fallback PDF extractor using PyMuPDF and Vision OCR for scanned images."""
    doc = fitz.open(filepath)
    text_content = ""

    for page in doc:
        text_content += page.get_text() + "\n"

    if len(text_content.strip()) > 50:
        return "pymupdf_fallback", text_content

    # Vision OCR for scanned PDF pages
    print(f"[DocumentParser] Attempting Vision OCR transcription for scanned PDF: {os.path.basename(filepath)}...")
    ocr_text = _run_vision_ocr(doc, filepath)
    return "vision_ocr", ocr_text


def _run_vision_ocr(doc: fitz.Document, filepath: str) -> str:
    """Uses PyMuPDF to render pages to PNG images and Vision LLM to OCR transcribe."""
    try:
        llm = get_llm("execution_planning", temperature=0)
        full_ocr = []

        for idx, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            b64_img = base64.b64encode(img_bytes).decode("utf-8")

            # pyrefly: ignore [missing-import]
            from langchain_core.messages import HumanMessage

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
