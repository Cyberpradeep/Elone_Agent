"""
Standalone LLM Configuration for SOP Ingestion Pipeline
=========================================================
Self-contained version of shared/llm_config.py from the main app.
Reads API keys from .env and builds LangChain chat model clients.

Only includes the LLM roles used by the ingestion pipeline:
  - execution_planning  (JIT Converter)
  - planning_validation (Plan Validator Layer 2)
"""

import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Role → Provider mapping (only ingestion-relevant roles)
# ---------------------------------------------------------------------------

ROLE_PROVIDER_MAP = {
    "execution_planning": {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "fallbacks": [
            {"provider": "gemini", "model": "gemini-2.5-flash"},
        ],
    },
    "planning_validation": {
        "provider": "mistral",
        "model": "mistral-large-latest",
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
    api_key = os.environ.get("GROQ_API_KEY_SUMMARIZATION") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY / GROQ_API_KEY_SUMMARIZATION not set in environment (.env)")
    try:
        # pyrefly: ignore [missing-import]
        from langchain_groq import ChatGroq
        return ChatGroq(model_name=model, groq_api_key=api_key, temperature=temperature)
    except ImportError:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            temperature=temperature,
        )

from langchain_nvidia_ai_endpoints import ChatNVIDIA

def _build_nvidia_client(model: str, temperature: float = 0.2):
    api_key = os.environ.get("NVIDIA_API_KEY")
    return ChatNVIDIA(model=model, nvidia_api_key=api_key, temperature=temperature, max_completion_tokens=350)


_BUILDERS = {
    "gemini": _build_gemini_client,
    "mistral": _build_mistral_client,
    "mistral2": _build_mistral_client2,
    "mistral3": _build_mistral_client3,
    "openrouter": _build_openrouter_client,
    "groq": _build_groq_client,
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
