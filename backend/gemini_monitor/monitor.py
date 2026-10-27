
import os
import json
import datetime
import threading
import uuid
from typing import Dict, Any, Optional, List

# pyrefly: ignore [missing-import]
from gemini_monitor.cost_calculator import calculate_cost

MONITOR_DIR = os.path.dirname(os.path.abspath(__file__))
USAGE_FILE = os.path.join(MONITOR_DIR, "daily_usage.json")

# Default daily limit (50 calls per day max)
DEFAULT_MAX_DAILY_CALLS = 50

# ── Per-Execution Session Tracker ──────────────────────────────────────
# Thread-local storage so concurrent runs (if ever) don't collide
_session_local = threading.local()


def start_execution_session(sop_filename: str = "unknown") -> str:
    """Call at the start of each pipeline run. Returns a unique session_id."""
    session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    _session_local.session = {
        "session_id": session_id,
        "sop_filename": sop_filename,
        "started_at": datetime.datetime.now().isoformat(),
        "total_calls": 0,
        "gemini_calls": 0,
        "nvidia_vision_calls": 0,
        "mistral_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "image_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "cost_inr": 0.0,
        "calls": []  # per-call breakdown
    }
    return session_id


def _get_active_session() -> Optional[Dict[str, Any]]:
    """Returns the active session dict, or None if no session is active."""
    return getattr(_session_local, "session", None)


def end_execution_session() -> Optional[Dict[str, Any]]:
    """Finalizes the session and returns the summary. Returns None if no session."""
    session = _get_active_session()
    if session is None:
        return None
    session["ended_at"] = datetime.datetime.now().isoformat()
    summary = dict(session)
    _session_local.session = None
    return summary


def get_execution_summary() -> Optional[Dict[str, Any]]:
    """Returns the current session summary without ending it."""
    return _get_active_session()


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


def is_unlimited_calls() -> bool:
    """Returns True if daily call limits are disabled / set to unlimited."""
    try:
        from config.settings import is_unlimited_daily_calls
        if is_unlimited_daily_calls():
            return True
    except Exception:
        pass

    env_unlimited = os.environ.get("UNLIMITED_DAILY_CALLS", "").strip().lower() in ("1", "true", "yes")
    if env_unlimited:
        return True

    env_max = os.environ.get("MAX_DAILY_CALLS", "").strip()
    if env_max in ("0", "-1", "unlimited", "infinite"):
        return True

    return False


def get_daily_max_calls() -> int:
    """Returns the configured max daily calls (0 means unlimited)."""
    if is_unlimited_calls():
        return 0
    try:
        from config.settings import get_max_daily_calls
        m_calls = get_max_daily_calls()
        if m_calls <= 0:
            return 0
        return m_calls
    except Exception:
        pass
    env_val = os.environ.get("MAX_DAILY_GEMINI_CALLS") or os.environ.get("MAX_DAILY_CALLS")
    if env_val:
        try:
            val = int(env_val)
            if val <= 0:
                return 0
            return val
        except ValueError:
            pass
    return DEFAULT_MAX_DAILY_CALLS


def get_today_usage() -> Dict[str, Any]:
    """Returns the usage summary for today, initializing a new entry if date rolled over."""
    today = _get_today_str()
    all_data = _load_usage_data()
    max_limit = get_daily_max_calls()
    unlimited = is_unlimited_calls() or max_limit <= 0

    if today not in all_data:
        all_data[today] = {
            "date": today,
            "total_calls": 0,
            "max_daily_calls": "unlimited" if unlimited else max_limit,
            "calls_remaining": "unlimited" if unlimited else max_limit,
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
    if unlimited:
        all_data[today]["max_daily_calls"] = "unlimited"
        all_data[today]["calls_remaining"] = "unlimited"
    else:
        all_data[today]["max_daily_calls"] = max_limit
        all_data[today]["calls_remaining"] = max(0, max_limit - all_data[today]["total_calls"])
    return all_data[today]


def check_daily_limit(provider: str = "gemini") -> None:
    """
    Circuit Breaker: Verifies if today's call limit has been reached.
    If unlimited calls are configured, returns immediately.
    Raises DailyQuotaExceededError only if a positive finite limit is reached.
    """
    if is_unlimited_calls():
        return

    usage = get_today_usage()
    max_calls = usage.get("max_daily_calls")
    current_calls = usage.get("total_calls", 0)

    if max_calls in (0, "unlimited", None):
        return

    if isinstance(max_calls, (int, float)) and current_calls >= max_calls:
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
    unlimited = is_unlimited_calls() or max_limit <= 0

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
    if unlimited:
        day_entry["max_daily_calls"] = "unlimited"
        day_entry["calls_remaining"] = "unlimited"
    else:
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

    # ── Track in active execution session (if any) ──
    session = _get_active_session()
    if session is not None:
        session["total_calls"] += 1
        session["input_tokens"] += input_tokens
        session["output_tokens"] += output_tokens
        session["image_tokens"] += image_tokens
        session["total_tokens"] += (input_tokens + output_tokens + image_tokens)
        session["cost_usd"] = round(session["cost_usd"] + cost_info["total_cost_usd"], 6)
        session["cost_inr"] = round(session["cost_inr"] + cost_info["total_cost_inr"], 4)
        prov_lower_s = provider.lower()
        if "gemini" in prov_lower_s:
            session["gemini_calls"] += 1
        elif "nvidia" in prov_lower_s or "vision" in caller.lower():
            session["nvidia_vision_calls"] += 1
        elif "mistral" in prov_lower_s:
            session["mistral_calls"] += 1
        session["calls"].append({
            "caller": caller,
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "image_tokens": image_tokens,
            "cost_usd": cost_info["total_cost_usd"]
        })

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

    limit_display = "Unlimited" if unlimited else max_limit
    print(
        f"[Gemini Monitor] Call #{day_entry['total_calls']}/{limit_display} | "
        f"Caller: {caller} | In: {input_tokens} tok, Out: {output_tokens} tok, Img: {image_tokens} tok | "
        f"Call Cost: ${cost_info['total_cost_usd']:.5f} | Day Total: ${day_entry['total_cost_usd']:.4f} USD (~Rs. {day_entry['total_cost_inr']:.2f} INR) | "
        f"Remaining: {day_entry['calls_remaining']}",
        flush=True
    )

    return {
        "call_cost": cost_info,
        "day_summary": day_entry
    }


def print_execution_session_banner(session: Optional[Dict[str, Any]] = None) -> None:
    """Prints a per-execution session summary banner."""
    if session is None:
        session = _get_active_session()
    if session is None:
        return

    print("\n" + "=" * 70)
    print("  THIS EXECUTION — LLM CALL SUMMARY")
    print("=" * 70)
    print(f"  Session ID:         {session['session_id']}")
    print(f"  SOP File:           {session['sop_filename']}")
    print(f"  Total LLM Calls:    {session['total_calls']}")
    print(f"    Gemini:           {session['gemini_calls']}")
    print(f"    NVIDIA Vision:    {session['nvidia_vision_calls']}")
    print(f"    Mistral:          {session['mistral_calls']}")
    print("  --------------------------------------------------------------------")
    print(f"  Input Tokens:       {session['input_tokens']:,}")
    print(f"  Output Tokens:      {session['output_tokens']:,}")
    print(f"  Image Tokens:       {session['image_tokens']:,}")
    print(f"  Total Tokens:       {session['total_tokens']:,}")
    print("  --------------------------------------------------------------------")
    print(f"  Execution Cost:     ${session['cost_usd']:.4f} USD (~Rs. {session['cost_inr']:.2f} INR)")
    print("=" * 70)

    # Per-call breakdown table
    if session["calls"]:
        print(f"  {'#':<4} {'Caller':<25} {'Provider':<12} {'In Tok':>8} {'Out Tok':>8} {'Img Tok':>8} {'Cost':>10}")
        print(f"  {'—'*4} {'—'*25} {'—'*12} {'—'*8} {'—'*8} {'—'*8} {'—'*10}")
        for i, c in enumerate(session["calls"], 1):
            print(f"  {i:<4} {c['caller']:<25} {c['provider']:<12} {c['input_tokens']:>8,} {c['output_tokens']:>8,} {c['image_tokens']:>8,} ${c['cost_usd']:>8.5f}")
    print("=" * 70 + "\n", flush=True)


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
