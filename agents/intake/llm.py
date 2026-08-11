"""LLM triage invocation logic for Intake Agent."""

import json
from pydantic import ValidationError

from shared.llm_config import get_llm
from okf_engine.loader import parse_sops_catalog_index
from .schemas import TriageResult
from .prompts import get_system_prompt
from .tools import get_raw_uploads_list


def run_triage(ticket_raw: str, category: str | None = None, entities: dict | None = None) -> TriageResult:
    """Invokes LLM to perform triage and returns structured TriageResult."""
    llm = get_llm("triage", temperature=0).with_structured_output(TriageResult)

    catalog_map = parse_sops_catalog_index()
    raw_uploads = get_raw_uploads_list()
    dynamic_prompt = get_system_prompt(catalog_map, raw_uploads)

    user_content = f"Ticket text:\n{ticket_raw}"
    if category:
        user_content += f"\n\nPre-assigned category: {category}"
    if entities:
        user_content += f"\n\nAlready Extracted Entities:\n{entities}"

    try:
        result = llm.invoke(
            [
                {"role": "system", "content": dynamic_prompt},
                {"role": "user", "content": user_content},
            ]
        )
    except (ValidationError, Exception):
        result = None

    if not result:
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
            result = TriageResult(**data)
        except Exception:
            result = TriageResult(
                intent="general_inquiry",
                category=category or "other",
                priority="low",
                detailed_description=ticket_raw,
                ticket_details_confidence=0.4,
                sop_match_confidence=0.2,
            )

    return result
