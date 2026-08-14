import os
import re
import hashlib
import requests
from typing import Tuple, List
from markitdown import MarkItDown

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_CACHE_DIR = os.path.join(BASE_DIR, "knowledge_base", "logs", "web_cache")

IGNORED_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".exe", ".dmg", ".iso", ".mp4", ".mp3"
)


def extract_urls_from_markdown(text: str) -> List[str]:
    """Extracts valid web URLs from markdown links and raw text.
    
    Filters out binary/image assets and deduplicates results.
    """
    if not text:
        return []

    # 1. Match Markdown links [text](url) and raw URLs https:// or http://
    markdown_link_pattern = r'\[(?:[^\]]+)\]\((https?://[^\s)]+)\)'
    raw_url_pattern = r'(?<!\()https?://[^\s<\'">\])]+'

    urls = []
    # Markdown links first
    for match in re.finditer(markdown_link_pattern, text):
        urls.append(match.group(1))

    # Raw URLs second
    for match in re.finditer(raw_url_pattern, text):
        urls.append(match.group(0))

    # Clean trailing punctuation and filter out binary assets
    cleaned_urls = []
    for u in urls:
        u_clean = u.rstrip(".,;:!)")
        path_lower = u_clean.split("?")[0].lower()
        if not path_lower.endswith(IGNORED_EXTENSIONS):
            cleaned_urls.append(u_clean)

    # Deduplicate preserving order
    return list(dict.fromkeys(cleaned_urls))


def fetch_and_convert_url(url: str, timeout_seconds: int = 10) -> Tuple[bool, str, str]:
    """Fetches a URL, converts HTML to Markdown using MarkItDown, and caches to disk.
    
    Returns (success_bool, markdown_content_or_error, relative_cache_path)
    """
    os.makedirs(WEB_CACHE_DIR, exist_ok=True)
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
    cache_path = os.path.join(WEB_CACHE_DIR, f"{url_hash}.log")
    rel_cache_path = f"knowledge_base/logs/web_cache/{url_hash}.log"

    # Check cache first
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                content = f.read()
                print(f"[LinkScraper Cache] Loaded cached web content for URL: {url}")
                return True, content, rel_cache_path
        except Exception as e:
            print(f"[LinkScraper Warning] Failed reading cache for {url}: {e}")

    # Fetch fresh content via HTTP
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SOP-Ingestion-Pipeline/1.0"
    }

    try:
        print(f"[LinkScraper] Fetching URL: {url} ...")
        resp = requests.get(url, headers=headers, timeout=timeout_seconds)
        resp.raise_for_status()

        md = MarkItDown()
        import io
        stream = io.BytesIO(resp.content)
        
        # Convert HTML binary stream to Markdown
        try:
            result = md.convert_stream(stream, file_extension=".html")
            md_text = result.text_content if result and result.text_content else ""
        except Exception as conv_err:
            print(f"[LinkScraper Warning] MarkItDown stream conversion failed: {conv_err}")
            md_text = ""

        # Fallback to BeautifulSoup clean text extraction if MarkItDown output is empty or HTML
        if not md_text or "<html" in md_text.lower() or "<!doctype" in md_text.lower():
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.content, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            md_text = soup.get_text(separator="\n\n").strip()

        # Format cache file content
        cache_entry = f"URL: {url}\nStatus Code: {resp.status_code}\n\n--- SCRAPED MARKDOWN CONTENT START ---\n{md_text}\n--- SCRAPED MARKDOWN CONTENT END ---\n"
        
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(cache_entry)

        print(f"[LinkScraper] Successfully scraped {len(md_text)} chars from {url}")
        return True, md_text, rel_cache_path

    except Exception as err:
        err_msg = f"Failed to fetch linked URL '{url}': {err}"
        print(f"[LinkScraper Warning] {err_msg}")
        return False, err_msg, rel_cache_path
