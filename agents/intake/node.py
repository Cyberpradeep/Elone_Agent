"""Main LangGraph Node Entrypoint for Intake Agent."""

from typing import Literal
from langgraph.types import Command

from shared.state import SupportState
from shared.asset_lookup import extract_and_lookup_asset
from okf_engine import parse_sops_catalog_index
from .schemas import TriageResult
from .llm import run_triage
from .tools import (
    lookup_matching_playbook,
    lookup_user_asset,
    check_software_permission,
)


def intake_agent(state: SupportState) -> Command[Literal["planner_agent", "orchestration_agent"]]:
    """Intake Agent Node with Dual Confidence Scoring & Catalog Scanning."""

    catalog_map = parse_sops_catalog_index()
    print(f"\n==================================================")
    print(f"--- [INTAKE AGENT: TRIAGE & CATALOG SCAN] ---")
    print(f"  Loaded {len(catalog_map)} active playbooks from sops/index.md:")
    if catalog_map:
        for idx, (title, info) in enumerate(catalog_map.items(), start=1):
            print(f"    [{idx}] '{title}' -> Path: sops/{info.get('rel_path')} (Category: {info.get('category')})")
    else:
        print(f"    (No active playbooks found in sops/index.md)")
    print(f"==================================================")

    ticket_raw = state.get("ticket_raw", "")
    category = state.get("category")
    existing_entities = state.get("entities") or {}

    enriched_entities = extract_and_lookup_asset(ticket_raw, existing_entities)

    # Validate employee email against Asset Management inventory
    target_email = state.get("customer_email") or enriched_entities.get("email")
    if not target_email and ticket_raw:
        import re
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", ticket_raw)
        if email_match:
            target_email = email_match.group(0)

    if target_email:
        from shared.asset_lookup import lookup_asset_by_identifier
        asset_record = lookup_asset_by_identifier(target_email)
        if not asset_record:
            audit_msg = f"[Intake Asset Verification Failed] Employee email '{target_email}' is not present in Asset Management records. Escalating immediately."
            print(f"  {audit_msg}")
            return Command(
                update={
                    "intent": "Employee Identity & Asset Verification",
                    "priority": "high",
                    "category": category or "security",
                    "entities": enriched_entities,
                    "workflow_status": "escalated",
                    "orchestrator_reasoning": f"No employee asset record found: Employee email '{target_email}' is not registered in the Asset Management inventory. Ticket escalated for manual L2 verification.",
                    "audit_log": [audit_msg],
                },
                goto="orchestration_agent",
            )

    result = run_triage(ticket_raw, category=category, entities=enriched_entities)
    if not result:
        result = TriageResult(
            intent="general_inquiry",
            category=category or "other",
            priority="low",
            detailed_description=ticket_raw,
            ticket_details_confidence=0.4,
            sop_match_confidence=0.2,
        )

    print(f"\n  [Intake Triage Result]:")
    print(f"    Intent: '{result.intent}' | Category: '{result.category}'")
    print(f"    SOP Match Confidence: {result.sop_match_confidence:.2f} | Details Confidence: {result.ticket_details_confidence:.2f}")
    print(f"    Matched SOP Path: {result.matched_file_path or '(None - No match in catalog)'}")

    # Dynamic Application & Identity Entity Population
    if result.application_name:
        enriched_entities["application_name"] = result.application_name
    if result.executable:
        enriched_entities["executable"] = result.executable
    if result.user_id:
        enriched_entities["user_id"] = result.user_id
    if result.target_email:
        enriched_entities["email"] = result.target_email

    # Standardize entity key aliases
    if "computername" in enriched_entities and "hostname" not in enriched_entities:
        enriched_entities["hostname"] = enriched_entities["computername"]
    if "host" in enriched_entities and "hostname" not in enriched_entities:
        enriched_entities["hostname"] = enriched_entities["host"]
    if "user_email" in enriched_entities and "email" not in enriched_entities:
        enriched_entities["email"] = enriched_entities["user_email"]
    if "customer_email" in enriched_entities and "email" not in enriched_entities:
        enriched_entities["email"] = enriched_entities["customer_email"]
    if "account_id" in enriched_entities and "user_id" not in enriched_entities:
        enriched_entities["user_id"] = enriched_entities["account_id"]

    effective_environment = state.get("environment") or result.environment or enriched_entities.get("target_os") or "windows"

    app_target = enriched_entities.get("executable") or enriched_entities.get("application_name")
    emp_id = enriched_entities.get("emp_id")
    if app_target and emp_id:
        perm = check_software_permission(emp_id, app_target)
        is_allowed = perm["approved"]
        enriched_entities["catalog_permission_approved"] = "true" if is_allowed else "false"
        if not is_allowed:
            audit_msg = f"[Intake Policy Violation] Application '{app_target}' is NOT authorized for employee {emp_id} in Allowed_Applications.csv. Escalating immediately."
            print(f"  {audit_msg}")
            return Command(
                update={
                    "intent": result.intent,
                    "priority": result.priority,
                    "category": result.category,
                    "detailed_description": result.detailed_description,
                    "keywords": result.keywords,
                    "environment": effective_environment,
                    "entities": enriched_entities,
                    "workflow_status": "escalated",
                    "orchestrator_reasoning": f"Application '{app_target}' is not in the approved software policy for employee {emp_id} ({enriched_entities.get('employee_name', '')}). Policy restriction enforced.",
                    "audit_log": [audit_msg],
                },
                goto="orchestration_agent",
            )

    if category and result.category and category.lower() != result.category.lower():
        return Command(
            update={
                "intent": result.intent,
                "priority": result.priority,
                "category": result.category,
                "detailed_description": result.detailed_description,
                "keywords": result.keywords,
                "environment": effective_environment,
                "entities": enriched_entities,
                "workflow_status": "escalated",
                "orchestrator_reasoning": f"Category discrepancy detected: Ticket pre-assigned category '{category}' differs from classified category '{result.category}'. Escalating for verification.",
                "audit_log": [
                    f"[Intake] Category mismatch ('{category}' vs '{result.category}'). Escalating immediately."
                ],
            },
            goto="orchestration_agent",
        )

    # Check required entity rules for Tool SOPs vs Command SOPs
    intent_str = (result.intent or "").lower()
    requires_identity_entity = any(w in intent_str for w in ["unlock", "password", "mfa", "login", "auth"])
    has_identity_target = bool(enriched_entities.get("email") or enriched_entities.get("user_id"))

    requires_app_entity = any(w in intent_str for w in ["hung", "terminate", "unblock", "ifeo"])
    has_app_target = bool(enriched_entities.get("executable") or enriched_entities.get("application_name"))

    if requires_identity_entity:
        if has_identity_target and result.sop_match_confidence >= 0.7:
            result.ticket_details_confidence = 1.0
            result.sop_match_confidence = 1.0
        else:
            result.ticket_details_confidence = 0.4
    else:
        if enriched_entities.get("hostname") and result.sop_match_confidence >= 0.7:
            if requires_app_entity and not has_app_target:
                result.ticket_details_confidence = 0.4
            else:
                result.ticket_details_confidence = 1.0
                result.sop_match_confidence = 1.0

    # Dual Confidence Escalation Guardrail (Requires low details confidence < 0.5 OR low sop match < 0.4)
    needs_clarification = result.ticket_details_confidence < 0.5 or result.sop_match_confidence < 0.4

    if needs_clarification:
        return Command(
            update={
                "intent": result.intent,
                "priority": result.priority,
                "category": result.category,
                "detailed_description": result.detailed_description,
                "keywords": result.keywords,
                "environment": effective_environment,
                "entities": enriched_entities,
                "ticket_details_confidence": result.ticket_details_confidence,
                "sop_match_confidence": result.sop_match_confidence,
                "sop_source": result.sop_source,
                "matched_file_path": result.matched_file_path,
                "workflow_status": "escalated",
                "orchestrator_reasoning": f"Low details confidence ({result.ticket_details_confidence:.2f}) or SOP match confidence ({result.sop_match_confidence:.2f}). Escalating for human review.",
                "audit_log": [
                    f"[Intake] Low confidence (details: {result.ticket_details_confidence:.2f}, match: {result.sop_match_confidence:.2f}). Escalating immediately."
                ],
            },
            goto="orchestration_agent",
        )

    audit_msg = (
        f"[Intake] Triage applied: intent={result.intent}, priority={result.priority}, "
        f"category={result.category}, details_conf={result.ticket_details_confidence}, sop_match_conf={result.sop_match_confidence}, "
        f"source={result.sop_source}, matched_file={result.matched_file_path}, entities={enriched_entities}"
    )

    return Command(
        update={
            "intent": result.intent,
            "priority": result.priority,
            "category": result.category,
            "detailed_description": result.detailed_description,
            "keywords": result.keywords,
            "environment": effective_environment,
            "entities": enriched_entities,
            "ticket_details_confidence": result.ticket_details_confidence,
            "sop_match_confidence": result.sop_match_confidence,
            "sop_source": result.sop_source,
            "matched_file_path": result.matched_file_path,
            "audit_log": [audit_msg],
        },
        goto="planner_agent",
    )