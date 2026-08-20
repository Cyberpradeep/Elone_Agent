"""
Gemini Monitor & Daily Quota Guard
==================================
Monitors API token usage, calculates per-call USD/INR costs, and enforces
a strict hard ceiling of 50 calls per day.
"""

import os
import json
import datetime
from typing import Dict, Any, Optional, List
from langchain_core.callbacks.base import BaseCallbackHandler

# pyrefly: ignore [missing-import]
from gemini_monitor.cost_calculator import calculate_cost

MONITOR_DIR = os.path.dirname(os.path.abspath(__file__))
USAGE_FILE = os.path.join(MONITOR_DIR, "daily_usage.json")

# Default daily limit (50 calls per day max)
DEFAULT_MAX_DAILY_CALLS = 50


class DailyQuotaExceededError(RuntimeError):
    """Raised when the daily LLM API call limit is reached."""
    pass


def _get_today_str() -> str:
    """Returns today's date string in YYYY-MM-DD format."""
    return datetime.date.today().strftime("%Y-%m-%d")


def _load_usage_data() -> Dict[str, Any]:
    """Loads usage data from JSON file."""
    if not os.path.exists(USAGE_FILE):
        return {}
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_usage_data(data: Dict[str, Any]) -> None:
    """Saves usage data atomically to JSON file."""
    os.makedirs(MONITOR_DIR, exist_ok=True)
    temp_file = f"{USAGE_FILE}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(temp_file, USAGE_FILE)


def get_daily_max_calls() -> int:
    """Returns the configured max daily calls (default 50)."""
    env_val = os.environ.get("MAX_DAILY_GEMINI_CALLS") or os.environ.get("MAX_DAILY_CALLS")
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass
    return DEFAULT_MAX_DAILY_CALLS


def get_today_usage() -> Dict[str, Any]:
    """Returns the usage summary for today, initializing a new entry if date rolled over."""
    today = _get_today_str()
    all_data = _load_usage_data()
    max_limit = get_daily_max_calls()

    if today not in all_data:
        all_data[today] = {
            "date": today,
            "total_calls": 0,
            "max_daily_calls": max_limit,
            "calls_remaining": max_limit,
            "gemini_calls": 0,
            "nvidia_vision_calls": 0,
            "mistral_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_image_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "total_cost_inr": 0.0,
            "call_history": []
        }
        _save_usage_data(all_data)

    # Ensure max_daily_calls reflects current config
    all_data[today]["max_daily_calls"] = max_limit
    all_data[today]["calls_remaining"] = max(0, max_limit - all_data[today]["total_calls"])
    return all_data[today]


def check_daily_limit(provider: str = "gemini") -> None:
    """
    Circuit Breaker: Verifies if today's call limit has been reached.
    Raises DailyQuotaExceededError if limit is reached.
    """
    usage = get_today_usage()
    max_calls = usage["max_daily_calls"]
    current_calls = usage["total_calls"]

    if current_calls >= max_calls:
        err_msg = (
            f"\n"
            f"{'=' * 70}\n"
            f"  [GEMINI MONITOR CIRCUIT BREAKER] DAILY QUOTA REACHED!\n"
            f"{'=' * 70}\n"
            f"  Date:            {usage['date']}\n"
            f"  Total Calls:     {current_calls}/{max_calls} (MAX LIMIT REACHED)\n"
            f"  Total Cost:      ${usage['total_cost_usd']:.4f} USD (~Rs. {usage['total_cost_inr']:.2f} INR)\n"
            f"  Status:          BLOCKED to protect your paid API quota.\n"
            f"  Reset Time:      Tomorrow at 00:00 (Midnight)\n"
            f"{'=' * 70}\n"
        )
        print(err_msg, flush=True)
        raise DailyQuotaExceededError(
            f"Daily API call limit of {max_calls} reached for {usage['date']}. "
            f"Blocked to prevent additional billing charges."
        )


def record_call(
    caller: str,
    model: str,
    provider: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    image_tokens: int = 0,
    sop_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculates cost, records the call into daily_usage.json, and returns usage stats.
    """
    today = _get_today_str()
    all_data = _load_usage_data()
    max_limit = get_daily_max_calls()

    if today not in all_data:
        get_today_usage()
        all_data = _load_usage_data()

    day_entry = all_data[today]
    cost_info = calculate_cost(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        image_tokens=image_tokens,
        provider=provider
    )

    day_entry["total_calls"] += 1
    day_entry["max_daily_calls"] = max_limit
    day_entry["calls_remaining"] = max(0, max_limit - day_entry["total_calls"])

    prov_lower = provider.lower()
    if "gemini" in prov_lower:
        day_entry["gemini_calls"] = day_entry.get("gemini_calls", 0) + 1
    elif "nvidia" in prov_lower or "vision" in caller.lower():
        day_entry["nvidia_vision_calls"] = day_entry.get("nvidia_vision_calls", 0) + 1
    elif "mistral" in prov_lower:
        day_entry["mistral_calls"] = day_entry.get("mistral_calls", 0) + 1

    day_entry["total_input_tokens"] += input_tokens
    day_entry["total_output_tokens"] += output_tokens
    day_entry["total_image_tokens"] += image_tokens
    day_entry["total_tokens"] += (input_tokens + output_tokens + image_tokens)
    day_entry["total_cost_usd"] = round(day_entry["total_cost_usd"] + cost_info["total_cost_usd"], 6)
    day_entry["total_cost_inr"] = round(day_entry["total_cost_inr"] + cost_info["total_cost_inr"], 4)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history_record = {
        "timestamp": timestamp,
        "caller": caller,
        "provider": provider,
        "model": model,
        "sop_id": sop_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "image_tokens": image_tokens,
        "cost_usd": cost_info["total_cost_usd"],
        "cost_inr": cost_info["total_cost_inr"]
    }
    day_entry["call_history"].append(history_record)

    _save_usage_data(all_data)

    print(
        f"[Gemini Monitor] Call #{day_entry['total_calls']}/{max_limit} | "
        f"Caller: {caller} | In: {input_tokens} tok, Out: {output_tokens} tok, Img: {image_tokens} tok | "
        f"Call Cost: ${cost_info['total_cost_usd']:.5f} | Day Total: ${day_entry['total_cost_usd']:.4f} USD (~Rs. {day_entry['total_cost_inr']:.2f} INR) | "
        f"Remaining: {day_entry['calls_remaining']}",
        flush=True
    )

    return {
        "call_cost": cost_info,
        "day_summary": day_entry
    }


class GeminiMonitorCallback(BaseCallbackHandler):
    """LangChain callback that validates quota on start and records usage on completion."""

    def __init__(self, caller: str = "llm", provider: str = "gemini", model: str = "gemini-2.5-flash", sop_id: Optional[str] = None):
        super().__init__()
        self.caller = caller
        self.provider = provider
        self.model = model
        self.sop_id = sop_id

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        check_daily_limit(self.provider)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "llm_output") and response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
            input_tokens = token_usage.get("prompt_tokens", 0) or token_usage.get("input_tokens", 0)
            output_tokens = token_usage.get("completion_tokens", 0) or token_usage.get("output_tokens", 0)

        record_call(
            caller=self.caller,
            model=self.model,
            provider=self.provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            sop_id=self.sop_id
        )


def print_daily_usage_banner() -> None:
    """Prints a clean, formatted terminal summary of today's usage and costs."""
    usage = get_today_usage()
    print("\n" + "=" * 70)
    print("  GEMINI & VISION DAILY USAGE & COST REPORT")
    print("=" * 70)
    print(f"  Date:               {usage['date']}")
    print(f"  Daily Call Quota:   {usage['total_calls']}/{usage['max_daily_calls']} calls (Remaining: {usage['calls_remaining']})")
    print(f"  Gemini Calls:       {usage.get('gemini_calls', 0)}")
    print(f"  NVIDIA Vision Calls:{usage.get('nvidia_vision_calls', 0)}")
    print(f"  Mistral Calls:      {usage.get('mistral_calls', 0)}")
    print("  --------------------------------------------------------------------")
    print(f"  Input Tokens:       {usage['total_input_tokens']:,} tokens")
    print(f"  Output Tokens:      {usage['total_output_tokens']:,} tokens")
    print(f"  Image Tokens:       {usage['total_image_tokens']:,} tokens")
    print(f"  Total Tokens:       {usage['total_tokens']:,} tokens")
    print("  --------------------------------------------------------------------")
    print(f"  Today's Total Cost: ${usage['total_cost_usd']:.4f} USD (~Rs. {usage['total_cost_inr']:.2f} INR)")
    print("=" * 70 + "\n", flush=True)
