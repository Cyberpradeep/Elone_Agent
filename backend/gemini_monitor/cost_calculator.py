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
    "mistral-large-latest": {
        "input_text_per_1m": 2.00,
        "output_text_per_1m": 6.00,
        "image_per_1m": 0.00,
    }
}

# Currency conversion rate (USD -> INR)
USD_TO_INR_RATE = 87.0


def calculate_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    image_tokens: int = 0,
    provider: str = "gemini"
) -> Dict[str, Any]:
    """Calculates exact USD and INR cost for a single LLM or VLM call."""
    pricing_key = "gemini-3.7-flash" if "3.7" in model.lower() else "gemini-2.5-flash"
    if "nvidia" in provider.lower() or "llama-3.2" in model.lower():
        pricing_key = "nvidia-vision"
    elif "mistral" in model.lower():
        pricing_key = "mistral-large-latest"
    elif "1.5-flash" in model.lower():
        pricing_key = "gemini-1.5-flash"

    pricing = PRICING_CATALOG.get(pricing_key, PRICING_CATALOG["gemini-3.7-flash"])

    input_cost = (input_tokens / 1_000_000.0) * pricing["input_text_per_1m"]
    output_cost = (output_tokens / 1_000_000.0) * pricing["output_text_per_1m"]
    image_cost = (image_tokens / 1_000_000.0) * pricing["image_per_1m"]

    total_cost_usd = input_cost + output_cost + image_cost
    total_cost_inr = total_cost_usd * USD_TO_INR_RATE

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
