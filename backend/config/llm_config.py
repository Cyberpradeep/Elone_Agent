"""
Standalone LLM Configuration for SOP Ingestion Pipeline
=========================================================
Self-contained version of shared/llm_config.py from the main app.
Reads API keys from .env and builds LangChain chat model clients.

Only includes the LLM roles used by the ingestion pipeline:
  - execution_planning  (JIT Converter)
  - planning_validation (Plan Validator Layer 2)
  - vlm_image_analysis  (Multimodal VLM Inspector)

Supports Providers:
  - Google Gemini (gemini-2.5-flash)
  - Mistral AI (mistral-small-latest)
  - Groq (llama-3.3-70b-versatile, llama-3.1-8b-instant, qwen-2.5-32b, etc.)
  - Z.ai / Zhipu AI GLM (glm-4-flash, glm-4-plus, glm-4-air, glm-4-long)
  - OpenRouter (openrouter.ai)
  - NVIDIA NIM (llama-3.2-11b-vision-instruct)
"""

import os
import warnings
from functools import lru_cache
from dotenv import load_dotenv

warnings.filterwarnings("ignore", message=".*automatic function calling.*")
warnings.filterwarnings("ignore", category=UserWarning, module=".*google.*")

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
load_dotenv()

# ---------------------------------------------------------------------------
# Role → Provider mapping (only ingestion-relevant roles)
# Supports runtime environment variable overrides:
#   PLANNING_PROVIDER / PLANNING_MODEL
#   VALIDATION_PROVIDER / VALIDATION_MODEL
# ---------------------------------------------------------------------------

_PLANNING_PROVIDER = os.environ.get("PLANNING_PROVIDER", "mistral").lower()
_PLANNING_MODEL = os.environ.get("PLANNING_MODEL", "codestral-latest")

_VALIDATION_PROVIDER = os.environ.get("VALIDATION_PROVIDER", "mistral").lower()
_VALIDATION_MODEL = os.environ.get("VALIDATION_MODEL", "codestral-latest")

_VLM_PROVIDER = os.environ.get("VLM_PROVIDER", "nvidia").lower()
_VLM_MODEL = os.environ.get("VLM_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")

_GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")

ROLE_PROVIDER_MAP = {
    "execution_planning": {
        "provider": _PLANNING_PROVIDER,
        "model": _PLANNING_MODEL,
        "fallbacks": [
            {"provider": "groq", "model": _GROQ_MODEL},
            # {"provider": "gemini", "model": "gemini-2.5-flash"},
        ],
    },
    "planning_validation": {
        "provider": _VALIDATION_PROVIDER,
        "model": _VALIDATION_MODEL,
        "fallbacks": [
            {"provider": "groq", "model": _GROQ_MODEL},
            # {"provider": "gemini", "model": "gemini-2.5-flash"},
        ],
    },
    "vlm_image_analysis": {
        "provider": _VLM_PROVIDER,
        "model": _VLM_MODEL,
        "fallbacks": [
            {"provider": "openrouter", "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"},
            {"provider": "nvidia", "model": "meta/llama-3.2-11b-vision-instruct"},
            # {"provider": "gemini", "model": "gemini-2.5-flash"},
        ],
    },
}


def _limits() -> dict:
    """Timeout / retry limits applied to every LLM client (H2)."""
    try:
        from config.settings import get_settings
        st = get_settings()
        return {"timeout": st.llm_timeout_seconds, "max_retries": st.llm_max_retries}
    except Exception:
        return {"timeout": 120.0, "max_retries": 2}


# ---------------------------------------------------------------------------
# Provider builder functions
# ---------------------------------------------------------------------------

def _build_gemini_client(model: str, temperature: float = 0.2):
    from langchain_google_genai import ChatGoogleGenerativeAI
    try:
        # pyrefly: ignore [missing-import]
        from gemini_monitor.monitor import check_daily_limit
        check_daily_limit("gemini")
    except Exception as e:
        # Re-raise quota exceeded errors directly
        if "Quota" in type(e).__name__ or "DailyQuotaExceededError" in str(type(e)):
            raise e

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set in environment (.env)")
    return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=temperature, **_limits())


def _build_mistral_client(model: str, temperature: float = 0.1):
    """
    Builds a LangChain chat model client for Mistral with multi-key fallback rotation.
    Rotates automatically across MISTRAL_API_KEY, MISTRAL_API_KEY2, MISTRAL_API_KEY3.
    """
    from langchain_mistralai import ChatMistralAI

    raw_keys = [
        os.environ.get("MISTRAL_API_KEY"),
        os.environ.get("MISTRAL_API_KEY2"),
        os.environ.get("MISTRAL_API_KEY3"),
    ]
    seen = set()
    keys = []
    for k in raw_keys:
        if k and k not in seen:
            seen.add(k)
            keys.append(k)

    if not keys:
        raise RuntimeError("MISTRAL_API_KEY not set in environment (.env)")

    clients = [
        ChatMistralAI(model=model, mistral_api_key=k, temperature=temperature, **_limits())
        for k in keys
    ]
    if len(clients) > 1:
        return clients[0].with_fallbacks(clients[1:])
    return clients[0]


def _build_mistral_client2(model: str, temperature: float = 0.2):
    from langchain_mistralai import ChatMistralAI

    api_key = os.environ.get("MISTRAL_API_KEY2")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY2 not set in environment (.env)")
    return ChatMistralAI(model=model, mistral_api_key=api_key, temperature=temperature, **_limits())


def _build_mistral_client3(model: str, temperature: float = 0.2):
    from langchain_mistralai import ChatMistralAI

    api_key = os.environ.get("MISTRAL_API_KEY3")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY3 not set in environment (.env)")
    return ChatMistralAI(model=model, mistral_api_key=api_key, temperature=temperature, **_limits())


def _build_openrouter_client(model: str, temperature: float = 0.2):
    from langchain_openai import ChatOpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set in environment (.env)")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=temperature,
        **_limits(),
    )


def _build_groq_client(model: str, temperature: float = 0.2):
    """
    Builds a LangChain chat model client for Groq with multi-key fallback rotation.
    Models include: llama-3.3-70b-versatile, llama-3.1-8b-instant, qwen-2.5-32b, etc.
    Rotates automatically across GROQ_API_KEY, GROQ_API_KEY_FALLBACK, GROQ_API_KEY_EXECUTION_RESULT.
    """
    raw_keys = [
        os.environ.get("GROQ_API_KEY"),
        os.environ.get("GROQ_API_KEY_FALLBACK"),
        os.environ.get("GROQ_API_KEY_EXECUTION_RESULT"),
        os.environ.get("GROQ_API_KEY_SUMMARIZATION"),
    ]
    seen = set()
    keys = []
    for k in raw_keys:
        if k and k not in seen:
            seen.add(k)
            keys.append(k)

    if not keys:
        raise RuntimeError("GROQ_API_KEY not set in environment (.env)")

    from langchain_openai import ChatOpenAI
    clients = [
        ChatOpenAI(
            model=model,
            api_key=k,
            base_url="https://api.groq.com/openai/v1",
            temperature=temperature,
            max_tokens=2048,
            **_limits(),
        )
        for k in keys
    ]
    if len(clients) > 1:
        return clients[0].with_fallbacks(clients[1:])
    return clients[0]


def _build_zai_glm_client(model: str = "glm-4.7-flash", temperature: float = 0.2):
    """
    Builds a LangChain chat model client for Z.ai / Zhipu AI GLM models.
    Supports auto-switching:
      Tries 'glm-4.7-flash' first; if rate-limited or overloaded (HTTP 429), automatically falls back to 'glm-4.5-flash'.
    Compatible with:
      - International endpoint: https://api.z.ai/api/paas/v4 (default)
      - Domestic China endpoint: https://open.bigmodel.cn/api/paas/v4
    """
    api_key = (
        os.environ.get("ZAI_API_KEY")
        or os.environ.get("GLM_API_KEY")
        or os.environ.get("ZHIPUAI_API_KEY")
    )
    if not api_key:
        raise RuntimeError("ZAI_API_KEY / GLM_API_KEY / ZHIPUAI_API_KEY not set in environment (.env)")

    base_url = (
        os.environ.get("ZAI_BASE_URL")
        or os.environ.get("GLM_BASE_URL")
        or os.environ.get("ZHIPUAI_BASE_URL")
        or "https://api.z.ai/api/paas/v4"
    ).rstrip("/")

    from langchain_openai import ChatOpenAI

    primary_model = model or "glm-4.7-flash"
    primary_client = ChatOpenAI(
        model=primary_model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=2048,
        **_limits(),
    )

    # If requested model is glm-4.7-flash, attach automatic fallback to glm-4.5-flash
    if "4.7" in primary_model:
        fallback_client = ChatOpenAI(
            model="glm-4.5-flash",
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=2048,
            **_limits(),
        )
        return primary_client.with_fallbacks([fallback_client])

    return primary_client


def _build_nvidia_client(model: str, temperature: float = 0.2):
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY not set in environment (.env)")
    lim = _limits()
    try:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        return ChatNVIDIA(
            model=model,
            api_key=api_key,
            temperature=temperature,
            top_p=0.95,
            max_completion_tokens=4096,
            timeout=lim["timeout"],
        )
    except ImportError:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://integrate.api.nvidia.com/v1",
            temperature=temperature,
            max_tokens=4096,
            timeout=lim["timeout"],
            request_timeout=lim["timeout"],
            max_retries=lim["max_retries"],
        )


_BUILDERS = {
    "gemini": _build_gemini_client,
    "mistral": _build_mistral_client,
    "mistral2": _build_mistral_client2,
    "mistral3": _build_mistral_client3,
    "openrouter": _build_openrouter_client,
    "groq": _build_groq_client,
    "zai": _build_zai_glm_client,
    "glm": _build_zai_glm_client,
    "zhipu": _build_zai_glm_client,
    "nvidia": _build_nvidia_client,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def print_active_models():
    """Prints a formatted summary of all agent roles and their assigned LLMs."""
    try:
        from utils.pipeline_logger import log_active_models
        log_active_models(ROLE_PROVIDER_MAP)
    except Exception:
        try:
            from backend.utils.pipeline_logger import log_active_models
            log_active_models(ROLE_PROVIDER_MAP)
        except Exception:
            print("\n" + "=" * 65)
            print("  ACTIVE AGENT LLM CONFIGURATION")
            print("=" * 65)
            for role, conf in ROLE_PROVIDER_MAP.items():
                fb_str = f" | Fallbacks: {[f['provider'] + '/' + f['model'] for f in conf.get('fallbacks', [])]}" if "fallbacks" in conf else ""
                print(f"  • {role:22s} -> Provider: {conf['provider']:10s} | Model: {conf['model']}{fb_str}")
            print("=" * 65 + "\n", flush=True)


@lru_cache(maxsize=None)
def get_llm(role: str, temperature: float = 0.2):
    """
    Returns a LangChain chat model client for the given agent role.
    `role` must be a key in ROLE_PROVIDER_MAP above.
    Cached so repeated calls for the same role reuse the same client instance.
    """
    if role not in ROLE_PROVIDER_MAP:
        raise ValueError(f"Unknown role '{role}'. Add it to ROLE_PROVIDER_MAP first.")
    config = ROLE_PROVIDER_MAP[role]
    builder = _BUILDERS[config["provider"]]

    try:
        from utils.pipeline_logger import log_info
        log_info("LLM Initializer", f"Role: '{role}' -> Active: {config['provider'].upper()} ({config['model']}, temp={temperature})")
    except Exception:
        try:
            from backend.utils.pipeline_logger import log_info
            log_info("LLM Initializer", f"Role: '{role}' -> Active: {config['provider'].upper()} ({config['model']}, temp={temperature})")
        except Exception:
            print(f"[LLM Initializer] Role: '{role}' -> Active: {config['provider'].upper()} ({config['model']}, temp={temperature})", flush=True)

    primary_llm = builder(config["model"], temperature=temperature)

    if "fallbacks" in config:
        fallback_llms = []
        for fb_config in config["fallbacks"]:
            fb_builder = _BUILDERS[fb_config["provider"]]
            fallback_llms.append(fb_builder(fb_config["model"], temperature=temperature))
        return primary_llm.with_fallbacks(fallback_llms)

    return primary_llm
