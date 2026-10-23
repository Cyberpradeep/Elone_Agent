"""
Elone Ingestion Pipeline — Centralized Security & Data Loss Prevention (DLP) Module
===================================================================================
Provides modular, production-ready security defenses for the SOP ingestion pipeline:
1. Data Loss Prevention (DLP): Real-time regex masking for passwords, API keys, emails, phones, private keys.
2. Shannon Entropy: Detects high-randomness cryptographic secrets.
3. Unicode & Zero-Width Cleaner: Strips zero-width characters and normalizes BiDi text.
4. Archive & Zip Bomb Guard: Inspects compression ratios and uncompressed size for .docx and .xlsx.
5. Path Traversal & Filename Sanitizer: Strips directory traversal sequences and unsafe characters.
6. SSRF Protection: Pre-resolves DNS and blocks private RFC1918 subnets, loopback, and cloud metadata IPs.
7. Multimodal Image Guard: Pixel bomb dimension limits and token-efficient downscaling.
8. Prompt Sandbox Delimiter Escaping: Prevents container breakout in LLM prompts.
9. Cryptographic Playbook Integrity: HMAC-SHA256 / SHA256 digital stamp for YAML playbooks.
10. Shell Injection Guard: Enforces double-quotes on dynamic entity placeholders in CLI commands.
"""

import os
import re
import math
import socket
import ipaddress
import urllib.parse
import unicodedata
import zipfile
import json
import hashlib
import hmac
from typing import Tuple, Optional, Dict, Any, List

# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================

class SecurityConfigurationError(RuntimeError):
    """Raised when critical security configuration (like HMAC signing key) is missing or invalid."""
    pass

# Zip Bomb Thresholds
MAX_UNCOMPRESSED_ZIP_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_ZIP_COMPRESSION_RATIO = 20.0               # Maximum 20x ratio

# Image Dimension Caps (Pixel Bomb Defense)
MAX_IMAGE_DIMENSION = 4096                     # Max width or height in pixels
TARGET_IMAGE_DIMENSION = 1024                  # Max downscaled dimension for AI token efficiency
MAX_IMAGES_PER_SOP = 5                         # Cap per document to avoid token bloat

# Image Magic Bytes Signatures (Fail-Closed Header Checks)
IMAGE_MAGIC_SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),                   # WEBP has RIFF....WEBP header
]

# Web Scraper Caps
MAX_SCRAPE_OUTPUT_CHARS = 4000                 # Maximum character length for scraped reference markdown

# Disallowed / Blocked IP Ranges (Comprehensive IANA Special-Use IPv4 & IPv6 SSRF Defense)
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),         # Broadcast / This host
    ipaddress.ip_network("10.0.0.0/8"),        # RFC1918 Private Class A
    ipaddress.ip_network("100.64.0.0/10"),     # RFC6598 Carrier-Grade NAT (CGNAT)
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("169.254.0.0/16"),    # Link-Local / Cloud Metadata (AWS/GCP/Azure)
    ipaddress.ip_network("172.16.0.0/12"),     # RFC1918 Private Class B
    ipaddress.ip_network("192.0.0.0/24"),      # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),      # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),    # RFC1918 Private Class C
    ipaddress.ip_network("198.18.0.0/15"),     # Network benchmark testing
    ipaddress.ip_network("198.51.100.0/24"),   # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),    # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),       # Multicast
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved / Future use
    ipaddress.ip_network("255.255.255.255/32"),# Limited broadcast
    ipaddress.ip_network("::1/128"),           # IPv6 Loopback
    ipaddress.ip_network("::/128"),            # IPv6 Unspecified
    ipaddress.ip_network("::ffff:0:0/96"),     # IPv4-mapped IPv6
    ipaddress.ip_network("64:ff9b::/96"),      # IPv4/IPv6 translation
    ipaddress.ip_network("100::/64"),          # Discard-only
    ipaddress.ip_network("2001::/23"),         # IETF Protocol Assignments
    ipaddress.ip_network("2001:db8::/32"),     # Documentation
    ipaddress.ip_network("2002::/16"),         # 6to4
    ipaddress.ip_network("fc00::/7"),          # IPv6 Unique Local
    ipaddress.ip_network("fe80::/10"),         # IPv6 Link-Local
]

# Zero-Width and Invisible Unicode Characters
ZERO_WIDTH_CHARS = [
    "\u200B",  # Zero-width space
    "\u200C",  # Zero-width non-joiner
    "\u200D",  # Zero-width joiner
    "\u200E",  # Left-to-right mark
    "\u200F",  # Right-to-left mark
    "\u202A",  # Left-to-right embedding
    "\u202B",  # Right-to-left embedding
    "\u202C",  # Pop directional formatting
    "\u202D",  # Left-to-right override
    "\u202E",  # Right-to-left override
    "\uFEFF",  # Byte order mark (BOM) / Zero-width no-break space
]

# =============================================================================
# 1. DATA LOSS PREVENTION (DLP) & SECRET MASKING
# =============================================================================

# Known API Key / Token Regex Patterns
VENDOR_API_KEY_PATTERNS = [
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"), "[DLP_REDACTED_API_KEY]"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs)_[A-Za-z0-9_]{36}\b"), "[DLP_REDACTED_API_KEY]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b"), "[DLP_REDACTED_API_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[DLP_REDACTED_API_KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z\\-_]{35}\b"), "[DLP_REDACTED_API_KEY]"),
    (re.compile(r"\bxox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*\b"), "[DLP_REDACTED_API_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[DLP_REDACTED_JWT]"),
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[^-]+-----END [A-Z ]+PRIVATE KEY-----", re.DOTALL), "[DLP_REDACTED_PRIVATE_KEY]"),
]

# Contextual Key-Value Patterns (Matches `api_key = "..."`, `Authorization: Bearer ...`)
CONTEXTUAL_SECRET_PATTERNS = [
    re.compile(r"""(?i)\b(api[_-]?key|access[_-]?token|secret[_-]?key|client[_-]?secret|auth[_-]?token|bearer)\s*[:=\-]+\s*["']?([A-Za-z0-9_\-\.]{16,})["']?"""),
    re.compile(r"""(?i)\b(password|pwd|secret|passphrase)\s*[:=\-]+\s*["']?([^\s"']{4,})["']?"""),
]

# Personal Contact Patterns (Real Email & Phone)
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b")

# Safe documentation placeholders that should NOT be redacted
DOCUMENTATION_TEMPLATE_DOMAINS = {
    "example.com", "example.org", "example.net", "company.com", "yourcompany.com", "domain.com", "test.com"
}


def calculate_shannon_entropy(data: str) -> float:
    """Calculates mathematical Shannon entropy of a string to detect high-randomness secrets."""
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    for x in set(data):
        p_x = float(data.count(x)) / length
        if p_x > 0:
            entropy += - p_x * math.log2(p_x)
    return entropy


def clean_unicode_and_zero_width(text: str) -> str:
    """Normalizes Unicode text and strips zero-width / bidirectional formatting characters."""
    if not text:
        return ""
    # Strip known zero-width and invisible control characters
    for ch in ZERO_WIDTH_CHARS:
        text = text.replace(ch, "")
    # Normalize with Unicode Compatibility Decomposition / Composition (NFKC)
    return unicodedata.normalize("NFKC", text)


def redact_sensitive_dlp(text: str) -> Tuple[str, Dict[str, int]]:
    """Scans and masks sensitive PII and access credentials before LLM dispatch.
    
    Redacts:
    - Cleartext passwords (contextual `password: ...`)
    - Vendor API keys (OpenAI, GitHub, AWS, Google, Slack, JWTs, SSH private keys)
    - High-entropy custom secret tokens
    - Real employee email addresses (preserves documentation placeholders like @example.com)
    - Phone numbers

    Returns:
        (sanitized_text: str, stats_dict: Dict[str, int])
    """
    if not text:
        return "", {}

    stats: Dict[str, int] = {
        "passwords": 0,
        "api_keys": 0,
        "emails": 0,
        "phones": 0,
        "private_keys": 0,
    }

    sanitized = text

    # 1. Redact Private Keys and Vendor API Keys
    for pattern, replacement in VENDOR_API_KEY_PATTERNS:
        matches = pattern.findall(sanitized)
        if matches:
            count = len(matches)
            if "PRIVATE_KEY" in replacement:
                stats["private_keys"] += count
            else:
                stats["api_keys"] += count
            sanitized = pattern.sub(replacement, sanitized)

    # 2. Contextual Passwords and Secrets
    def _redact_password(match):
        stats["passwords"] += 1
        prefix = match.group(1)
        return f"{prefix}: [DLP_REDACTED_PASSWORD]"

    sanitized = CONTEXTUAL_SECRET_PATTERNS[1].sub(_redact_password, sanitized)

    def _redact_contextual_key(match):
        stats["api_keys"] += 1
        prefix = match.group(1)
        return f"{prefix}: [DLP_REDACTED_API_KEY]"

    sanitized = CONTEXTUAL_SECRET_PATTERNS[0].sub(_redact_contextual_key, sanitized)

    # 3. Email Addresses (Exclude documentation template domains)
    def _redact_email(match):
        full_email = match.group(0)
        domain = full_email.split("@")[-1].lower()
        # Keep documentation placeholders intact
        if domain in DOCUMENTATION_TEMPLATE_DOMAINS or full_email.startswith(("user@", "test@", "admin@example")):
            return full_email
        stats["emails"] += 1
        return "[DLP_REDACTED_EMAIL]"

    sanitized = EMAIL_PATTERN.sub(_redact_email, sanitized)

    # 4. Phone Numbers (Min 10 digits total)
    def _redact_phone(match):
        val = match.group(0)
        digits_only = re.sub(r"\D", "", val)
        if len(digits_only) >= 10:
            stats["phones"] += 1
            return "[DLP_REDACTED_PHONE]"
        return val

    sanitized = PHONE_PATTERN.sub(_redact_phone, sanitized)

    # 5. Shannon Entropy Scan for Standalone Cryptographic Secrets (Tokens with length >= 24)
    # Match standalone alphanumeric tokens of length 24-80 characters
    token_candidates = re.finditer(r"\b([A-Za-z0-9+/=_-]{24,80})\b", sanitized)
    high_entropy_replacements = []
    for match in token_candidates:
        candidate = match.group(1)
        # Avoid redacting hex hashes or URLs if already handled
        if "http" in candidate.lower() or candidate.startswith("DLP_REDACTED"):
            continue
        entropy = calculate_shannon_entropy(candidate)
        # High entropy threshold for random API keys / secrets
        if entropy > 4.2:
            high_entropy_replacements.append((candidate, "[DLP_REDACTED_API_KEY]"))

    for orig, repl in high_entropy_replacements:
        stats["api_keys"] += 1
        sanitized = sanitized.replace(orig, repl)

    return sanitized, stats


# =============================================================================
# 2. ARCHIVE & ZIP BOMB DECOMPRESSION GUARD
# =============================================================================

def check_zip_bomb(
    filepath: str,
    max_uncompressed_bytes: int = MAX_UNCOMPRESSED_ZIP_BYTES,
    max_ratio: float = MAX_ZIP_COMPRESSION_RATIO
) -> Tuple[bool, Optional[str]]:
    """Inspects a zip-based archive (.docx, .xlsx) for decompression bombs without uncompressing.
    
    Guards against:
    - Excessive cumulative uncompressed size (> 50 MB)
    - Abnormally high compression ratios (> 20x)
    """
    if not os.path.exists(filepath):
        return False, f"File does not exist: {filepath}"

    try:
        if not zipfile.is_zipfile(filepath):
            return True, None

        total_uncompressed = 0
        total_compressed = 0

        with zipfile.ZipFile(filepath, "r") as zf:
            for info in zf.infolist():
                total_uncompressed += info.file_size
                total_compressed += info.compress_size

                # Immediate check per single file
                if info.file_size > max_uncompressed_bytes:
                    return False, (
                        f"Zip bomb detected: Single entry '{info.filename}' uncompressed size "
                        f"({info.file_size / (1024*1024):.1f} MB) exceeds maximum limit "
                        f"of {max_uncompressed_bytes / (1024*1024):.1f} MB."
                    )

        # Check total cumulative uncompressed size
        if total_uncompressed > max_uncompressed_bytes:
            return False, (
                f"Zip bomb detected: Cumulative uncompressed size "
                f"({total_uncompressed / (1024*1024):.1f} MB) exceeds maximum limit "
                f"of {max_uncompressed_bytes / (1024*1024):.1f} MB."
            )

        # Check compression ratio
        if total_compressed > 0:
            ratio = total_uncompressed / total_compressed
            if ratio > max_ratio and total_uncompressed > (10 * 1024 * 1024):
                return False, (
                    f"Zip bomb detected: Compression ratio ({ratio:.1f}x) exceeds "
                    f"maximum allowed limit ({max_ratio:.1f}x)."
                )

        return True, None

    except Exception as e:
        return False, f"Archive inspection error: {e}"


# =============================================================================
# 3. FILENAME & PATH TRAVERSAL SANITIZATION
# =============================================================================

def sanitize_filename(filename: str) -> str:
    """Sanitizes an uploaded filename by stripping directory traversal sequences and unsafe characters."""
    if not filename:
        return "unnamed_sop"
    # Remove directory paths
    base = os.path.basename(filename)
    # Strip null bytes and control characters
    base = base.replace("\0", "").replace("..", "")
    # Whitelist characters: letters, digits, underscores, hyphens, periods
    sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", base).strip("._-")
    return sanitized if sanitized else "sanitized_sop"


def sanitize_slug(text: str) -> str:
    """Sanitizes an SOP slug or ID to prevent path traversal in storage directories."""
    if not text:
        return "SOP-DYN-001"
    # Only keep alphanumeric characters, hyphens, and underscores
    clean = re.sub(r"[^A-Za-z0-9_-]", "-", text).strip("-")
    return clean.upper() if clean else "SOP-DYN-001"


# =============================================================================
# 4. NETWORK & SSRF PROTECTION FOR LINK SCRAPER
# =============================================================================

def is_safe_external_url(url: str) -> Tuple[bool, Optional[str]]:
    """Inspects a URL to verify it does NOT target private internal networks or cloud metadata.
    
    Blocks:
    - Non-HTTP/HTTPS schemes (e.g. file://, gopher://, ftp://)
    - Loopback addresses (127.0.0.1, localhost)
    - RFC1918 Private networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Cloud metadata IP (169.254.169.254)
    - Link-local and multicast ranges
    """
    if not url:
        return False, "Empty URL provided."

    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return False, f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are permitted."

        hostname = parsed.hostname
        if not hostname:
            return False, "Could not extract valid hostname from URL."

        # Reject obvious loopback names immediately
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False, "Access to localhost and loopback interfaces is strictly forbidden."

        # Reject AWS/GCP/Azure cloud metadata endpoint hostname directly
        if hostname == "169.254.169.254":
            return False, "Access to cloud metadata service (169.254.169.254) is strictly forbidden."

        # Resolve hostname to IP addresses
        addr_info = socket.getaddrinfo(hostname, None)
        resolved_ips = {item[4][0] for item in addr_info}

        for ip_str in resolved_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                for blocked_net in BLOCKED_IP_NETWORKS:
                    if ip_obj in blocked_net:
                        return False, (
                            f"SSRF Protection: Hostname '{hostname}' resolved to blocked private "
                            f"or internal network IP ({ip_str} in {blocked_net})."
                        )
            except ValueError:
                return False, f"Invalid IP address resolved for hostname '{hostname}': {ip_str}"

        return True, None

    except socket.gaierror as dns_err:
        return False, f"DNS resolution failed for hostname in URL '{url}': {dns_err}"
    except Exception as e:
        return False, f"URL security check failed: {e}"


# =============================================================================
# 5. MULTIMODAL IMAGE SECURITY & TOKEN OPTIMIZATION (FAIL-CLOSED)
# =============================================================================

def validate_and_sanitize_image_bytes(
    image_bytes: bytes,
    mime_type: str = "image/png",
    max_dimension: int = MAX_IMAGE_DIMENSION,
    target_dimension: int = TARGET_IMAGE_DIMENSION
) -> Tuple[bool, Optional[str], bytes, str]:
    """Validates image data against pixel bombs and downscales large images, strictly failing closed on error.
    
    Returns:
        (is_valid: bool, error_msg: Optional[str], processed_bytes: bytes, actual_mime_type: str)
    """
    if not image_bytes or len(image_bytes) < 12:
        return False, "Security rejection: Empty or truncated image data stream.", b"", mime_type

    # 1. Header Magic Byte Signature Check (Reject disguised non-image files immediately)
    is_recognized_magic = False
    detected_mime = mime_type
    for sig, sig_mime in IMAGE_MAGIC_SIGNATURES:
        if image_bytes.startswith(sig):
            if sig == b"RIFF" and b"WEBP" not in image_bytes[:16]:
                continue
            is_recognized_magic = True
            detected_mime = sig_mime
            break

    if not is_recognized_magic:
        return (
            False,
            "Security rejection: Header magic bytes do not match allowed image formats (PNG, JPEG, GIF, WEBP).",
            b"",
            mime_type,
        )

    try:
        import fitz
        # Inspect dimensions using PyMuPDF Pixmap
        pix = fitz.Pixmap(image_bytes)
        width, height = pix.width, pix.height

        # Pixel Bomb dimension check
        if width > max_dimension or height > max_dimension:
            return False, (
                f"Pixel bomb threat: Image dimensions ({width}x{height}) exceed "
                f"maximum allowed limit of {max_dimension}x{max_dimension} pixels."
            ), b"", detected_mime

        # If dimensions are within target budget, return as-is with verified MIME
        if width <= target_dimension and height <= target_dimension:
            return True, None, image_bytes, detected_mime

        # Downscale to target_dimension preserving aspect ratio
        scale = min(target_dimension / width, target_dimension / height)
        new_w = max(1, int(width * scale))
        new_h = max(1, int(height * scale))

        # PyMuPDF resize via scale
        doc = fitz.open()
        page = doc.new_page(width=new_w, height=new_h)
        rect = fitz.Rect(0, 0, new_w, new_h)
        page.insert_image(rect, pixmap=pix)
        resized_pix = page.get_pixmap()
        resized_bytes = resized_pix.tobytes("jpeg")
        doc.close()

        # Synchronize MIME type to image/jpeg because output was converted to JPEG
        return True, None, resized_bytes, "image/jpeg"

    except Exception as e:
        # STRICT FAIL-CLOSED: Any decoding error or malformed byte stream is rejected
        return False, f"Security rejection: Corrupted or unparseable image stream ({e})", b"", mime_type


# =============================================================================
# 6. PROMPT SANDBOX DELIMITER ESCAPING
# =============================================================================

def escape_prompt_delimiters(payload_text: str) -> str:
    """Escapes XML sandbox delimiters in untrusted raw text to prevent prompt injection breakouts."""
    if not payload_text:
        return ""
    # Case-insensitive replacement of opening and closing sandbox tags
    sanitized = re.sub(
        r"(?i)</untrusted_document_payload>",
        "&lt;/untrusted_document_payload&gt;",
        payload_text
    )
    sanitized = re.sub(
        r"(?i)<untrusted_document_payload>",
        "&lt;untrusted_document_payload&gt;",
        sanitized
    )
    return sanitized


# =============================================================================
# 7. CRYPTOGRAPHIC PLAYBOOK INTEGRITY & PRE-EXECUTION VERIFIER
# =============================================================================

def get_playbook_signing_key() -> str:
    """Retrieves the mandatory HMAC playbook signing key.
    
    Strict Security Policy:
    - Requires ELONE_PLAYBOOK_SIGNING_KEY in environment.
    - If missing, checks if ELONE_ALLOW_INSECURE_DEV_KEY == '1'.
      Only in this explicit test-only mode, returns a development key.
    - Otherwise raises SecurityConfigurationError.
    """
    key = os.getenv("ELONE_PLAYBOOK_SIGNING_KEY")
    if key and key.strip():
        return key.strip()

    if os.getenv("ELONE_ALLOW_INSECURE_DEV_KEY") == "1":
        return "elone_insecure_development_key_for_testing_only_2026"

    raise SecurityConfigurationError(
        "Security configuration missing: 'ELONE_PLAYBOOK_SIGNING_KEY' environment variable must be set. "
        "For local testing only, set 'ELONE_ALLOW_INSECURE_DEV_KEY=1'."
    )


def compute_playbook_hmac(frontmatter_data: Any, secret_key: Optional[str] = None) -> str:
    """Generates an HMAC-SHA256 digital stamp for validated playbook frontmatter (v2 canonical format).
    
    Excludes signature metadata ('integrity_hmac_sha256', 'integrity_version') and deterministically
    serializes all execution/routing frontmatter properties with sort_keys=True.
    """
    if secret_key is None:
        secret_key = get_playbook_signing_key()
    key_bytes = secret_key.encode("utf-8")

    if isinstance(frontmatter_data, dict):
        # Canonical v2 format: sign all frontmatter fields except the signature metadata
        canonical = {
            k: v for k, v in frontmatter_data.items()
            if k not in ("integrity_hmac_sha256", "integrity_version")
        }
        serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    else:
        # Legacy v1 format (list of steps only)
        serialized = json.dumps(frontmatter_data, sort_keys=True, separators=(",", ":"))

    return hmac.new(key_bytes, serialized.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_playbook_hmac(
    frontmatter_or_steps: Any,
    expected_hmac: str,
    secret_key: Optional[str] = None,
    integrity_version: str = "v2"
) -> bool:
    """Verifies playbook integrity against the expected HMAC-SHA256 stamp.
    
    Supports:
    - Version 'v2': Canonical frontmatter verification.
    - Version 'v1': Legacy steps-only verification for backward compatibility.
    """
    if not expected_hmac:
        return False

    if secret_key is None:
        try:
            secret_key = get_playbook_signing_key()
        except SecurityConfigurationError:
            return False

    if isinstance(frontmatter_or_steps, dict) and integrity_version == "v2":
        actual_hmac = compute_playbook_hmac(frontmatter_or_steps, secret_key)
    elif isinstance(frontmatter_or_steps, dict) and (integrity_version == "v1" or not integrity_version):
        steps = frontmatter_or_steps.get("steps", [])
        actual_hmac = compute_playbook_hmac(steps, secret_key)
    else:
        actual_hmac = compute_playbook_hmac(frontmatter_or_steps, secret_key)

    return hmac.compare_digest(actual_hmac, expected_hmac)


def verify_playbook_before_execution(
    playbook_path_or_dict: Any,
    secret_key: Optional[str] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """CRITICAL SECURITY GATE: Verifies playbook authenticity immediately before execution or dispatch.
    
    Accepts:
    - Path to a markdown playbook file on disk (.md)
    - Already parsed frontmatter dict
    
    Returns:
    - (is_valid: bool, reason_or_error: str, frontmatter: dict)
    """
    import yaml

    frontmatter = {}
    if isinstance(playbook_path_or_dict, str):
        if not os.path.exists(playbook_path_or_dict):
            return False, f"Playbook file does not exist: {playbook_path_or_dict}", {}
        try:
            with open(playbook_path_or_dict, "r", encoding="utf-8") as f:
                content = f.read()
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1]) or {}
        except Exception as e:
            return False, f"Failed to read/parse playbook frontmatter: {e}", {}
    elif isinstance(playbook_path_or_dict, dict):
        frontmatter = playbook_path_or_dict
    else:
        return False, f"Invalid playbook representation: {type(playbook_path_or_dict)}", {}

    if not frontmatter:
        return False, "Playbook has missing or empty frontmatter.", {}

    expected_hmac = frontmatter.get("integrity_hmac_sha256")
    if not expected_hmac:
        return False, "Security rejection: Playbook is missing required 'integrity_hmac_sha256' digital stamp.", frontmatter

    version = str(frontmatter.get("integrity_version", "v1")).lower()
    is_valid = verify_playbook_hmac(frontmatter, expected_hmac, secret_key=secret_key, integrity_version=version)

    if not is_valid:
        sop_id = frontmatter.get("sop_id", "UNKNOWN")
        return False, f"SECURITY ALARM: Playbook '{sop_id}' failed cryptographic integrity verification! File has been altered on disk.", frontmatter

    return True, "Playbook integrity verified successfully.", frontmatter


# =============================================================================
# 8. COMMAND INJECTION & VARIABLE QUOTATION ENFORCEMENT
# =============================================================================

def enforce_entity_double_quotes(command: str) -> str:
    """Enforces that standalone dynamic entity placeholders in PowerShell commands are double-quoted.

    Preserves placeholders already inside enclosing quotes:
      taskkill /F /IM {{entities.app}}.exe                --> taskkill /F /IM "{{entities.app}}.exe"
      Test-Connection -ComputerName {{entities.hostname}}  --> Test-Connection -ComputerName "{{entities.hostname}}"
      Write-Host "Connecting to {{entities.hostname}}..."  --> Write-Host "Connecting to {{entities.hostname}}..."
    """
    if not command or "{{entities." not in command:
        return command

    def is_inside_quotes(text: str, target_pos: int) -> bool:
        in_double = False
        in_single = False
        i = 0
        while i < target_pos and i < len(text):
            char = text[i]
            if char == "\\" and i + 1 < len(text):
                i += 2
                continue
            if char == '"' and not in_single:
                in_double = not in_double
            elif char == "'" and not in_double:
                in_single = not in_single
            i += 1
        return in_double or in_single

    pattern = re.compile(r"\{\{entities\.[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*\}\}[a-zA-Z0-9_\.-]*")
    matches = list(pattern.finditer(command))
    result = command
    for m in reversed(matches):
        start, end = m.span()
        if not is_inside_quotes(command, start):
            has_leading_quote = start > 0 and command[start - 1] in ('"', "'")
            has_trailing_quote = end < len(command) and command[end] in ('"', "'")
            if not (has_leading_quote and has_trailing_quote):
                result = result[:start] + f'"{m.group(0)}"' + result[end:]

    return result
