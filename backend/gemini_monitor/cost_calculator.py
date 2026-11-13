"""
Gemini & Vision Pricing and Cost Calculator
===========================================
Defines standard pricing tiers for:
  - Gemini 2.5 Flash (Text Input, Text Output with Thinking Tokens)
  - NVIDIA Vision / Llama-3.2 Vision (Image & Multimodal Tokens)
"""

from typing import Dict, Any

# Pricing in USD per 1,000,000 tokens (1M tokens)
PRICING_CATALOG = {
    "gemini-3.7-flash": {
        "input_text_per_1m": 0.75,   # $0.75 / 1M input tokens (through Dec 31, 2026)
        "output_text_per_1m": 3.75,  # $3.75 / 1M output tokens (incl. thinking)
        "image_per_1m": 0.75,        # $0.75 / 1M image tokens
    },
    "gemini-2.5-flash": {
        "input_text_per_1m": 0.30,   # $0.30 / 1M input tokens
        "output_text_per_1m": 2.50,  # $2.50 / 1M output tokens (incl. thinking)
        "image_per_1m": 0.30,        # $0.30 / 1M input image tokens
    },
    "gemini-1.5-flash": {
        "input_text_per_1m": 0.075,
        "output_text_per_1m": 0.30,
        "image_per_1m": 0.075,
    },
    "nvidia-vision": {
        "input_text_per_1m": 0.06,
        "output_text_per_1m": 0.06,
        "image_per_1m": 0.06,        # NVIDIA NIM Vision pricing ($0.06 / 1M tokens)
    },
    "codestral-latest": {
        "input_text_per_1m": 0.30,   # Mistral Codestral
        "output_text_per_1m": 0.90,
        "image_per_1m": 0.00,
    },
    "mistral-small-latest": {
        "input_text_per_1m": 0.10,   # Mistral Small
        "output_text_per_1m": 0.30,
        "image_per_1m": 0.00,
    },
    "mistral-large-latest": {
        "input_text_per_1m": 2.00,
        "output_text_per_1m": 6.00,
        "image_per_1m": 0.00,
    },
    "groq-llama-3.3-70b": {
        "input_text_per_1m": 0.59,   # Groq LLaMA 3.3 70B
        "output_text_per_1m": 0.79,
        "image_per_1m": 0.00,
    },
    "groq-llama-3.1-8b": {
        "input_text_per_1m": 0.05,   # Groq LLaMA 3.1 8B Instant
        "output_text_per_1m": 0.08,
        "image_per_1m": 0.00,
    },
    "groq-qwen-32b": {
        "input_text_per_1m": 0.20,   # Groq Qwen 2.5 32B / 3.8 27B
        "output_text_per_1m": 0.20,
        "image_per_1m": 0.00,
    },
    "zai-glm-4-flash": {
        "input_text_per_1m": 0.01,   # Z.ai / Zhipu GLM-4 Flash / 4.5 / 4.7
        "output_text_per_1m": 0.01,
        "image_per_1m": 0.00,
    },
    "zai-glm-4-plus": {
        "input_text_per_1m": 0.50,   # Z.ai / Zhipu GLM-4 Plus
        "output_text_per_1m": 0.50,
        "image_per_1m": 0.00,
    },
    "zai-glm-4-air": {
        "input_text_per_1m": 0.10,   # Z.ai / Zhipu GLM-4 Air
        "output_text_per_1m": 0.10,
        "image_per_1m": 0.00,
    },
    "openrouter-free": {
        "input_text_per_1m": 0.00,
        "output_text_per_1m": 0.00,
        "image_per_1m": 0.00,
    },
    "openrouter-default": {
        "input_text_per_1m": 0.50,
        "output_text_per_1m": 1.50,
        "image_per_1m": 0.00,
    },
}

# Currency conversion rate (USD -> INR). M4: config/settings.json -> cost.usd_to_inr_rate
USD_TO_INR_RATE = 87.0  # last-resort fallback only


def _usd_to_inr_rate() -> float:
    try:
        from config.settings import get_settings
        return get_settings().usd_to_inr_rate
    except Exception:
        return USD_TO_INR_RATE


def calculate_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    image_tokens: int = 0,
    provider: str = "gemini"
) -> Dict[str, Any]:
    """Calculates exact USD and INR cost for a single LLM or VLM call."""
    prov_lower = (provider or "").lower()
    model_lower = (model or "").lower()

    if "groq" in prov_lower or "groq" in model_lower:
        if "8b" in model_lower:
            pricing_key = "groq-llama-3.1-8b"
        elif "qwen" in model_lower:
            pricing_key = "groq-qwen-32b"
        else:
            pricing_key = "groq-llama-3.3-70b"
    elif any(k in prov_lower for k in ("zai", "glm", "zhipu")) or "glm" in model_lower:
        if "plus" in model_lower:
            pricing_key = "zai-glm-4-plus"
        elif "air" in model_lower:
            pricing_key = "zai-glm-4-air"
        else:
            pricing_key = "zai-glm-4-flash"
    elif "openrouter" in prov_lower or "openrouter" in model_lower:
        if ":free" in model_lower or "free" in model_lower:
            pricing_key = "openrouter-free"
        else:
            pricing_key = "openrouter-default"
    elif "nvidia" in prov_lower or "llama-3.2" in model_lower or "nemotron" in model_lower:
        pricing_key = "nvidia-vision"
    elif "mistral" in prov_lower or "codestral" in model_lower or "mistral" in model_lower:
        if "codestral" in model_lower:
            pricing_key = "codestral-latest"
        elif "small" in model_lower:
            pricing_key = "mistral-small-latest"
        else:
            pricing_key = "mistral-large-latest"
    elif "1.5-flash" in model_lower:
        pricing_key = "gemini-1.5-flash"
    elif "3.7" in model_lower:
        pricing_key = "gemini-3.7-flash"
    else:
        pricing_key = "gemini-2.5-flash"

    pricing = PRICING_CATALOG.get(pricing_key, PRICING_CATALOG["gemini-2.5-flash"])

    input_cost = (input_tokens / 1_000_000.0) * pricing["input_text_per_1m"]
    output_cost = (output_tokens / 1_000_000.0) * pricing["output_text_per_1m"]
    image_cost = (image_tokens / 1_000_000.0) * pricing["image_per_1m"]

    total_cost_usd = input_cost + output_cost + image_cost
    total_cost_inr = total_cost_usd * _usd_to_inr_rate()

    return {
        "model": model,
        "provider": provider,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "image_tokens": image_tokens,
        "total_tokens": input_tokens + output_tokens + image_tokens,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "image_cost_usd": round(image_cost, 6),
        "total_cost_usd": round(total_cost_usd, 6),
        "total_cost_inr": round(total_cost_inr, 4),
    }
