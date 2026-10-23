"""LLM triage invocation logic for Intake Agent."""

import json
from pydantic import ValidationError

from shared.llm_config import get_llm
from okf_engine import parse_sops_catalog_index
from .schemas import TriageResult
from .prompts import get_system_prompt


def run_triage(
    ticket_raw: str,
    category: str | None = None,
    entities: dict | None = None
) -> tuple[TriageResult | None, str | None]:
    """Invokes LLM to perform triage and returns (TriageResult, api_error_summary)."""
    llm = get_llm("triage", temperature=0).with_structured_output(TriageResult)

    catalog_map = parse_sops_catalog_index()
    dynamic_prompt = get_system_prompt(catalog_map)

    user_content = f"Ticket text:\n{ticket_raw}"
    if category:
        user_content += f"\n\nPre-assigned category: {category}"
    if entities:
        user_content += f"\n\nAlready Extracted Entities:\n{entities}"

    last_error = None
    try:
        result = llm.invoke(
            [
                {"role": "system", "content": dynamic_prompt},
                {"role": "user", "content": user_content},
            ]
        )
        if result:
            return result, None
    except Exception as e:
        last_error = str(e)
        print(f"[Warning] Intake structured LLM failed: {e}")

    try:
        fallback_llm = get_llm("triage", temperature=0)
        json_prompt = dynamic_prompt + "\n\nOutput raw valid JSON only matching the schema."
        resp = fallback_llm.invoke(
            [
                {"role": "system", "content": json_prompt},
                {"role": "user", "content": user_content},
            ]
        )
        content = resp.content if hasattr(resp, "content") else str(resp)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        data = json.loads(content)
        return TriageResult(**data), None
    except Exception as e:
        last_error = str(e)
        print(f"[Warning] Intake fallback JSON LLM failed: {e}")

    err_lower = (last_error or "").lower()
    is_quota = any(term in err_lower for term in ["429", "rate limit", "overloaded", "quota", "exhausted", "too many requests"])
    if is_quota:
        error_summary = "AI API Rate Limit / Quota Exhausted (HTTP 429)"
    else:
        error_summary = f"LLM Invocation Failed ({last_error[:80]})" if last_error else "LLM Invocation Returned Empty"

    return None, error_summary
