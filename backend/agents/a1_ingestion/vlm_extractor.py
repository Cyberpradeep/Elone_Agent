"""
Agent A1: VLM Extractor
=======================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.1 & 7)
Vision LLM image extraction and analysis for multi-modal SOP documents.
"""

import os
import json
import re
import time
import base64
from typing import List, Tuple, Dict, Any, Optional

from langchain_core.messages import HumanMessage
# pyrefly: ignore [missing-import]
from config.llm_config import get_llm
from config.settings import get_max_images_per_sop
from utils.security import validate_and_sanitize_image_bytes
# pyrefly: ignore [missing-import]
from prompts.vlm_prompts import VLM_SUPPORT_PROMPT

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_DIR = os.getenv("ELONE_KB_DIR", os.path.join(BASE_DIR, "knowledge_base"))
IMAGES_LOG_DIR = os.path.join(KB_DIR, "logs", "images")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


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
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            print("[VLM Inspector Warning] PyMuPDF is not installed. PDF image extraction skipped.")
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
                ext = base_image["ext"]
                mime_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
                results.append((page_number + 1, image_index, image_bytes, mime_type))
        doc.close()
    except Exception as e:
        print(f"[VLM Inspector Warning] Error extracting images from PDF '{pdf_path}': {e}")
    return results


def extract_images_from_docx(docx_path: str) -> List[Tuple[bytes, str]]:
    """Returns a list of (image_bytes, mime_type) for every image embedded in the document body."""
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


def extract_confidence_score(report_text: str) -> Dict[str, Any]:
    """Extracts CONFIDENCE SCORE / LEVEL / REASON from VLM report text."""
    if not report_text or "VLM Analysis FAILED" in report_text or ("FAILED" in report_text and "CONFIDENCE SCORE:" not in report_text):
        return {
            "score": 0.0,
            "level": "Low",
            "reason": "VLM vision analysis failed or encountered an upstream API error."
        }

    score = 0.50
    level = "Medium"
    reason = "Visual evidence interpreted by Vision LLM."

    score_match = re.search(r"CONFIDENCE SCORE:\s*([0-9\.]+)%?", report_text, re.IGNORECASE)
    if score_match:
        try:
            val = float(score_match.group(1))
            score = val / 100.0 if val > 1.0 else val
            score = round(max(0.0, min(1.0, score)), 2)
        except ValueError:
            pass

    level_match = re.search(r"CONFIDENCE LEVEL:\s*([A-Za-z]+)", report_text, re.IGNORECASE)
    if level_match:
        level = level_match.group(1).capitalize()
    else:
        level = "High" if score >= 0.85 else ("Medium" if score >= 0.60 else "Low")

    reason_match = re.search(r"CONFIDENCE REASON:\s*(.+)", report_text, re.IGNORECASE)
    if reason_match:
        reason = reason_match.group(1).strip()

    return {"score": score, "level": level, "reason": reason}


def estimate_image_tokens(image_bytes: bytes) -> int:
    """Calculates dynamic image token consumption based on image resolution patches."""
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
        tiles_x = max(1, (width + 511) // 512)
        tiles_y = max(1, (height + 511) // 512)
        return min(4096, (tiles_x * tiles_y * 560) + 200)
    except Exception:
        return max(256, min(2400, len(image_bytes) // 256))


def analyze_image_bytes(image_bytes: bytes, mime_type: str) -> str:
    """Analyzes image bytes using VLM via LangChain with rate-limit retry backoff."""
    is_valid, sec_err, sanitized_bytes, actual_mime = validate_and_sanitize_image_bytes(image_bytes, mime_type)
    if not is_valid:
        print(f"[VLM Security Shield] Image rejected: {sec_err}")
        return f"[IMAGE EXCLUDED FOR SECURITY: {sec_err}]"
    image_bytes = sanitized_bytes
    mime_type = actual_mime

    try:
        # pyrefly: ignore [missing-import]
        from gemini_monitor.monitor import check_daily_limit, record_call
        check_daily_limit("nvidia")
    except Exception as e:
        if "Quota" in type(e).__name__ or "DailyQuotaExceededError" in str(type(e)):
            raise e

    llm = get_llm("vlm_image_analysis")
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    message = HumanMessage(
        content=[
            {"type": "text", "text": VLM_SUPPORT_PROMPT + "\n\nAnalyze this image for an L1 support agent."},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
        ]
    )

    max_retries = 2
    last_error: Optional[Exception] = None
    img_tok = estimate_image_tokens(image_bytes)
    for attempt in range(1, max_retries + 1):
        try:
            res = llm.invoke([message])
            in_tok = 0
            out_tok = 0
            if hasattr(res, "usage_metadata") and res.usage_metadata:
                in_tok = res.usage_metadata.get("input_tokens", 0)
                out_tok = res.usage_metadata.get("output_tokens", 0)
            try:
                # pyrefly: ignore [missing-import]
                from gemini_monitor.monitor import record_call
                record_call(
                    caller="vlm_image_analysis",
                    model="meta/llama-3.2-11b-vision-instruct",
                    provider="nvidia",
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    image_tokens=img_tok
                )
            except Exception as mon_err:
                print(f"[Gemini Monitor Warning] Failed to log VLM call: {mon_err}")

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
            last_error = e
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                print(f"[VLM Rate Limit Warning] VLM API quota reached. Retrying in 2s (Attempt {attempt}/{max_retries})...")
                time.sleep(2)
            else:
                print(f"[VLM Inspector Error] Failed to analyze image with VLM: {e}")
                return f"VLM Analysis FAILED (non-retryable error): {err_str}"

    return f"VLM Analysis FAILED (quota/rate-limit exhausted after {max_retries} attempts): {last_error}"


def analyze_and_save_image(image_bytes: bytes, mime_type: str, label: str, sop_slug: str, index: int) -> Tuple[str, Dict[str, str]]:
    """Runs VLM analysis on a single image and saves report under knowledge_base/logs/images/<sop_slug>/."""
    is_valid, sec_err, sanitized_bytes, actual_mime = validate_and_sanitize_image_bytes(image_bytes, mime_type)
    if not is_valid:
        print(f"[VLM Security Shield] Image {index} ('{label}') rejected: {sec_err}")
        return f"[IMAGE EXCLUDED FOR SECURITY: {sec_err}]", {
            "image_path": "",
            "file_path": "",
            "confidence_score": 0.0,
            "confidence_level": "Low"
        }

    sop_image_dir = os.path.join(IMAGES_LOG_DIR, sop_slug)
    os.makedirs(sop_image_dir, exist_ok=True)

    ext = "jpg" if actual_mime == "image/jpeg" else actual_mime.split("/")[-1]
    if ext not in ("png", "jpg", "webp", "gif"):
        ext = "jpg"
    img_filename = f"img_{index}.{ext}"
    saved_img_path = os.path.join(sop_image_dir, img_filename)

    with open(saved_img_path, "wb") as f:
        f.write(sanitized_bytes)

    rel_img_path = os.path.relpath(saved_img_path, BASE_DIR).replace("\\", "/")
    report_text = analyze_image_bytes(sanitized_bytes, actual_mime)
    report_str = "\n".join(report_text) if isinstance(report_text, list) else str(report_text)

    conf_info = extract_confidence_score(report_str)

    json_meta_path = os.path.join(sop_image_dir, f"{os.path.splitext(img_filename)[0]}_report.json")
    rel_meta_path = os.path.relpath(json_meta_path, BASE_DIR).replace("\\", "/")
    meta_payload = {
        "image_filename": img_filename,
        "label": label,
        "mime_type": actual_mime,
        "confidence_score": conf_info["score"],
        "confidence_level": conf_info["level"],
        "confidence_reason": conf_info["reason"],
        "vlm_report": report_text,
    }
    with open(json_meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_payload, f, indent=2)

    image_ref = {
        "image_path": rel_img_path,
        "file_path": rel_meta_path,
        "confidence_score": conf_info["score"],
        "confidence_level": conf_info["level"],
    }
    return report_str, image_ref


def process_sop_images(filepath: str, sop_slug: str) -> Dict[str, Any]:
    """Extracts images from an SOP file, runs Gemini VLM analysis, and returns metadata references."""
    if not os.path.isfile(filepath):
        return {"summary_text": "", "image_refs": []}

    ext = os.path.splitext(filepath)[1].lower()
    sop_image_dir = os.path.join(IMAGES_LOG_DIR, sop_slug)
    os.makedirs(sop_image_dir, exist_ok=True)

    extracted_items = []
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

    max_imgs = get_max_images_per_sop()
    if len(extracted_items) > max_imgs:
        print(f"[VLM Inspector Security] Document contains {len(extracted_items)} image(s). Capping VLM analysis to first {max_imgs} image(s) as configured.")
        extracted_items = extracted_items[:max_imgs]

    print(f"[VLM Inspector] Found {len(extracted_items)} image(s) in '{os.path.basename(filepath)}'. Running VLM analysis...")
    reports = []
    image_refs = []

    for idx, (img_filename, img_bytes, mime_type, label) in enumerate(extracted_items, start=1):
        report_str, image_ref = analyze_and_save_image(img_bytes, mime_type, label, sop_slug, idx)
        reports.append(f"### Visual Inspection Report ({label} — `{img_filename}`):\n{report_str}")
        image_refs.append(image_ref)

    full_summary = "\n\n".join(reports)
    return {
        "summary_text": full_summary,
        "image_refs": image_refs
    }


__all__ = [
    "analyze_and_save_image",
    "analyze_image_bytes",
    "process_sop_images",
    "extract_images_from_pdf",
    "extract_images_from_docx",
    "extract_confidence_score",
]
