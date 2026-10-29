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
from functools import lru_cache
from dotenv import load_dotenv

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
load_dotenv()

# ---------------------------------------------------------------------------
# Role → Provider mapping (only ingestion-relevant roles)
# Supports runtime environment variable overrides:
#   PLANNING_PROVIDER / PLANNING_MODEL
#   VALIDATION_PROVIDER / VALIDATION_MODEL
# ---------------------------------------------------------------------------

_PLANNING_PROVIDER = os.environ.get("PLANNING_PROVIDER", "groq").lower()
_PLANNING_MODEL = os.environ.get("PLANNING_MODEL", "qwen/qwen3.8-27b")

_VALIDATION_PROVIDER = os.environ.get("VALIDATION_PROVIDER", "groq").lower()
_VALIDATION_MODEL = os.environ.get("VALIDATION_MODEL", "qwen/qwen3.8-27b")

_GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")

ROLE_PROVIDER_MAP = {
    "execution_planning": {
        "provider": _PLANNING_PROVIDER,
        "model": _PLANNING_MODEL,
        "fallbacks": [
            {"provider": "gemini", "model": "gemini-2.5-flash"},
        ],
    },
    "planning_validation": {
        "provider": _VALIDATION_PROVIDER,
        "model": _VALIDATION_MODEL,
        "fallbacks": [
            {"provider": "gemini", "model": "gemini-2.5-flash"},
        ],
    },
    "vlm_image_analysis": {
        "provider": "nvidia",
        "model": "meta/llama-3.2-11b-vision-instruct",
        # "model":"nvidia/nemotron-nano-12b-v2-vl",
        # "model":"nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    },
}


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
    return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=temperature)


def _build_mistral_client(model: str, temperature: float = 0.1):
    from langchain_mistralai import ChatMistralAI

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not set in environment (.env)")
    return ChatMistralAI(model=model, mistral_api_key=api_key, temperature=temperature)


def _build_mistral_client2(model: str, temperature: float = 0.2):
    from langchain_mistralai import ChatMistralAI

    api_key = os.environ.get("MISTRAL_API_KEY2")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY2 not set in environment (.env)")
    return ChatMistralAI(model=model, mistral_api_key=api_key, temperature=temperature)


def _build_mistral_client3(model: str, temperature: float = 0.2):
    from langchain_mistralai import ChatMistralAI

    api_key = os.environ.get("MISTRAL_API_KEY3")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY3 not set in environment (.env)")
    return ChatMistralAI(model=model, mistral_api_key=api_key, temperature=temperature)


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
            max_tokens=8192,
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
        max_tokens=8192,
    )

    # If requested model is glm-4.7-flash, attach automatic fallback to glm-4.5-flash
    if "4.7" in primary_model:
        fallback_client = ChatOpenAI(
            model="glm-4.5-flash",
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=8192,
        )
        return primary_client.with_fallbacks([fallback_client])

    return primary_client


def _build_nvidia_client(model: str, temperature: float = 0.2):
    try:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        api_key = os.environ.get("NVIDIA_API_KEY")
        return ChatNVIDIA(
            model=model,
            nvidia_api_key=api_key,
            temperature=temperature,
            max_completion_tokens=350,
            timeout=150,
        )
    except ImportError:
        from langchain_openai import ChatOpenAI
        api_key = os.environ.get("NVIDIA_API_KEY")
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://integrate.api.nvidia.com/v1",
            temperature=temperature,
            max_tokens=350,
            timeout=150.0,
            request_timeout=150.0,
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

    print(f"[LLM Initializer] Role: '{role}' -> Active: {config['provider'].upper()} ({config['model']}, temp={temperature})", flush=True)

    primary_llm = builder(config["model"], temperature=temperature)

    if "fallbacks" in config:
        fallback_llms = []
        for fb_config in config["fallbacks"]:
            fb_builder = _BUILDERS[fb_config["provider"]]
            fallback_llms.append(fb_builder(fb_config["model"], temperature=temperature))
        return primary_llm.with_fallbacks(fallback_llms)

    return primary_llm
