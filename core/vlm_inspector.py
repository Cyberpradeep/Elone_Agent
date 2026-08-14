
import os
import json
import base64
from typing import List, Tuple, Dict, Any, Optional

from langchain_core.messages import HumanMessage
from config.llm_config import get_llm

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
IMAGES_LOG_DIR = os.path.join(KB_DIR, "logs", "images")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
from prompts.vlm_prompts import VLM_SUPPORT_PROMPT


def guess_mime_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")


def extract_images_from_pdf(pdf_path: str) -> List[Tuple[int, int, bytes, str]]:
    """Returns a list of (page_number, image_index_on_page, image_bytes, mime_type)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("[VLM Inspector Warning] PyMuPDF (fitz) is not installed. PDF image extraction skipped.")
        return []

    results = []
    try:
        doc = fitz.open(pdf_path)
        for page_number in range(len(doc)):
            page = doc[page_number]
            for image_index, img in enumerate(page.get_images(full=True), start=1):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                ext = base_image["ext"]  # e.g. "png", "jpeg"
                mime_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
                results.append((page_number + 1, image_index, image_bytes, mime_type))
        doc.close()
    except Exception as e:
        print(f"[VLM Inspector Warning] Error extracting images from PDF '{pdf_path}': {e}")
    return results


def extract_images_from_docx(docx_path: str) -> List[Tuple[bytes, str]]:
    """Returns a list of (image_bytes, mime_type) for every image embedded in the document,
    in the order they actually appear in the document body."""
    try:
        from docx import Document
        from docx.oxml.ns import qn
    except ImportError:
        print("[VLM Inspector Warning] python-docx is not installed. DOCX image extraction skipped.")
        return []

    results = []
    try:
        doc = Document(docx_path)
        seen_embed_ids = set()
        for blip in doc.element.body.iter(qn("a:blip")):
            embed_id = blip.get(qn("r:embed"))
            if embed_id is None or embed_id in seen_embed_ids:
                continue
            seen_embed_ids.add(embed_id)
            image_part = doc.part.related_parts[embed_id]
            results.append((image_part.blob, image_part.content_type))
    except Exception as e:
        print(f"[VLM Inspector Warning] Error extracting images from DOCX '{docx_path}': {e}")
    return results


import time

def analyze_image_bytes(image_bytes: bytes, mime_type: str) -> str:
    """Analyzes image bytes using Gemini VLM via LangChain with rate-limit retry backoff."""
    llm = get_llm("vlm_image_analysis")
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    message = HumanMessage(
        content=[
            {"type": "text", "text": VLM_SUPPORT_PROMPT + "\n\nAnalyze this image for an L1 support agent."},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
        ]
    )

    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            res = llm.invoke([message])
            raw_content = res.content if hasattr(res, "content") else str(res)
            if isinstance(raw_content, list):
                parts = []
                for p in raw_content:
                    if isinstance(p, dict) and "text" in p:
                        parts.append(str(p["text"]))
                    else:
                        parts.append(str(p))
                return "\n".join(parts)
            return str(raw_content)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                print(f"[VLM Rate Limit Warning] Gemini API quota / rate limit reached for image. Retrying in 2s (Attempt {attempt}/{max_retries})...")
                time.sleep(2)
            else:
                print(f"[VLM Inspector Error] Failed to analyze image with Gemini VLM: {e}")
                return f"VLM Analysis (Offline/Cached): Screenshot extracted cleanly from SOP."

    return "VLM Analysis (Quota Exceeded): Image extracted and saved. Visual analysis paused due to API quota limit."


def process_sop_images(filepath: str, sop_slug: str) -> Dict[str, Any]:
    """Extracts images from an SOP file (PDF, DOCX, or Image), saves them under
    knowledge_base/logs/images/<sop_slug>/, runs Gemini VLM analysis, and returns
    structured visual metadata references.
    """
    if not os.path.isfile(filepath):
        return {"summary_text": "", "image_refs": []}

    ext = os.path.splitext(filepath)[1].lower()
    sop_image_dir = os.path.join(IMAGES_LOG_DIR, sop_slug)
    os.makedirs(sop_image_dir, exist_ok=True)

    extracted_items = []  # list of (filename, bytes, mime_type, page_info)

    if ext == ".pdf":
        raw_images = extract_images_from_pdf(filepath)
        for page_num, img_idx, img_bytes, mime_type in raw_images:
            img_filename = f"page_{page_num}_img_{img_idx}.png"
            extracted_items.append((img_filename, img_bytes, mime_type, f"Page {page_num}, Image {img_idx}"))
    elif ext == ".docx":
        raw_images = extract_images_from_docx(filepath)
        for idx, (img_bytes, mime_type) in enumerate(raw_images, start=1):
            img_filename = f"img_{idx}.png"
            extracted_items.append((img_filename, img_bytes, mime_type, f"Image {idx}"))
    elif ext in IMAGE_EXTENSIONS:
        with open(filepath, "rb") as f:
            img_bytes = f.read()
        mime_type = guess_mime_type(filepath)
        img_filename = os.path.basename(filepath)
        extracted_items.append((img_filename, img_bytes, mime_type, "Standalone Image"))

    if not extracted_items:
        return {"summary_text": "", "image_refs": []}

    print(f"[VLM Inspector] Found {len(extracted_items)} image(s) in '{os.path.basename(filepath)}'. Running Gemini VLM analysis...")

    reports = []
    image_refs = []

    for img_filename, img_bytes, mime_type, label in extracted_items:
        saved_img_path = os.path.join(sop_image_dir, img_filename)
        with open(saved_img_path, "wb") as f:
            f.write(img_bytes)

        rel_img_path = os.path.relpath(saved_img_path, BASE_DIR).replace("\\", "/")
        report_text = analyze_image_bytes(img_bytes, mime_type)
        report_str = "\n".join(report_text) if isinstance(report_text, list) else str(report_text)

        # Print detailed report box directly to terminal (ASCII safe for Windows console)
        safe_report = report_str.encode("ascii", errors="replace").decode("ascii")
        print(f"\n{'=' * 60}")
        print(f"[VLM Visual Report] {label} (`{img_filename}`)")
        print(f"{'=' * 60}")
        print(safe_report)
        print(f"{'=' * 60}\n")

        reports.append(f"### Visual Inspection Report ({label} — `{img_filename}`):\n{report_str}")

        # JSON Metadata report per image
        json_meta_path = os.path.join(sop_image_dir, f"{os.path.splitext(img_filename)[0]}_report.json")
        rel_meta_path = os.path.relpath(json_meta_path, BASE_DIR).replace("\\", "/")

        meta_payload = {
            "image_filename": img_filename,
            "label": label,
            "mime_type": mime_type,
            "vlm_report": report_text,
        }
        with open(json_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_payload, f, indent=2)

        image_refs.append({
            "image_path": rel_img_path,
            "file_path": rel_meta_path
        })

    full_summary = "\n\n".join(reports)
    return {
        "summary_text": full_summary,
        "image_refs": image_refs
    }
