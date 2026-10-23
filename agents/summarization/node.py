import json
import re
from typing import Literal, Any, Dict, List, Optional
from pydantic import BaseModel, Field
# pyrefly: ignore [missing-import]
from langgraph.types import Command

from shared.state import SupportState
from shared.llm_config import get_llm
from okf_engine.memory_logger import write_episodic_log


class SummarizationOutput(BaseModel):
    executive_summary: str = Field(
        default="",
        description="High-level overview of the issue, target host, and final resolution outcome."
    )
    diagnostic_findings: List[str] = Field(
        default_factory=list,
        description="Key diagnostic findings and root cause analysis bullet points."
    )
    actions_taken: List[str] = Field(
        default_factory=list,
        description="List of automated actions and CLI commands executed during the workflow."
    )
    discovered_variables: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted dynamic variables and values."
    )
    recommendations: str = Field(
        default="",
        description="Next steps or recommendations for the user or engineering team."
    )
    customer_ticket_reply: str = Field(
        description="Professional, plain-language resolution message to the end user explaining what was diagnosed and fixed (sent via email)."
    )
    internal_ticket_summary: str = Field(
        description="Detailed technical engineering summary report in Markdown format analyzing the execution logs, commands run, extracted variables, and final status."
    )
    resolution_type: Literal["FULLY_RESOLVED", "ESCALATED_L2", "MANUAL_INTERVENTION_REQUIRED"] = Field(
        description="Final resolution categorization."
    )


SUMMARIZATION_SYSTEM_PROMPT = """You are an expert IT Operations & Log Analysis Summarization Agent for an L1 Support Automation System.

Your task is to analyze the execution trajectory, audit logs, CLI command outputs, and dynamic variables to produce a thorough, insightful, and professional summary for both the customer and internal IT engineering staff.

## INPUT DATA FOR ANALYSIS:

### 1. TICKET METADATA:
- Ticket Intent: {intent}
- Category: {category}
- Target Workstation: {hostname}
- Matched SOP ID: {sop_id}
- Workflow Status: {workflow_status}

### 2. EXECUTION RESULTS & CLI OUTPUTS:
Execution Results: {execution_results}
Extracted Variables: {variables}

### 3. AUDIT LOG TRAJECTORY:
{audit_log}

---

## OUTPUT REQUIREMENTS:

Thoroughly analyze the audit logs, execution outputs, and variables above and return a valid JSON object with the following fields:

1. **executive_summary**: High-level core issue summary on workstation {hostname}.
2. **diagnostic_findings**: Array of key technical diagnostic observations from command outputs.
3. **actions_taken**: Array of resolution actions and commands executed.
4. **discovered_variables**: Object containing key extracted variables (IPs, registry values, PIDs).
5. **recommendations**: Technical recommendations for next steps or monitoring.
6. **customer_ticket_reply**: Professional, clear, and friendly email response for the end user explaining the diagnosis and status.
7. **internal_ticket_summary**: Comprehensive multi-section Markdown technical report for engineering staff with headings (`### Executive Summary`, `### Diagnostic Findings`, `### Actions Taken & Execution Log`, `### Discovered Variables`, `### Resolution & Recommendations`).
8. **resolution_type**: One of `FULLY_RESOLVED`, `ESCALATED_L2`, or `MANUAL_INTERVENTION_REQUIRED`.

Produce valid JSON matching the SummarizationOutput schema.
"""


def _build_rich_fallback_summary(state: SupportState, is_escalated: bool) -> SummarizationOutput:
    """Generates a complete multi-section Markdown report programmatically when LLM calls fail."""
    intent = state.get("intent") or "System Troubleshooting"
    category = state.get("category") or "general"
    entities = state.get("entities") or {}
    hostname = entities.get("hostname", "target machine")
    sop_id = state.get("sop", {}).get("sop_id") if isinstance(state.get("sop"), dict) else "SOP-DYN-000"
    workflow_status = state.get("workflow_status") or "completed"
    variables = state.get("variables") or {}
    execution_results = state.get("execution_results") or {}
    audit_log = state.get("audit_log") or []

    res_type = "ESCALATED_L2" if is_escalated else "FULLY_RESOLVED"
    status_label = "ESCALATED TO L2" if is_escalated else "FULLY RESOLVED"

    # Executive Summary
    exec_summary = (
        f"Ticket intent '{intent}' on workstation `{hostname}` under category `{category}` using `{sop_id}`. "
        f"Workflow status: **{status_label}**."
    )

    # Actions Taken
    actions = []
    for k, v in execution_results.items():
        actions.append(f"Step {k}: Output snippet — `{str(v)[:120]}`")
    if not actions:
        actions = ["Automated SOP execution plan completed."]

    # Diagnostic Findings
    findings = [
        f"Target host evaluated: `{hostname}`",
        f"Matched playbook ID: `{sop_id}`",
        f"Execution step count: {len(execution_results)}"
    ]

    # Recommendations
    recs = (
        "Verify system behavior with end user. If issues persist, refer to L2 helpdesk documentation."
        if not is_escalated
        else "Review attached escalation handover report for root cause investigation."
    )

    # Customer Reply
    customer_reply = (
        f"Hello,\n\n"
        f"Your support ticket regarding **{intent}** has been processed on workstation **{hostname}**.\n\n"
        f"**Summary of Actions:**\n"
        f"- Diagnostics and resolution steps were performed using automated playbook `{sop_id}`.\n"
        f"- Status: **{status_label}**.\n\n"
        f"If you continue to experience any issues, please reply directly to this email."
    )

    # Internal Technical Markdown
    var_lines = "\n".join([f"- **`{k}`**: `{v}`" for k, v in variables.items()]) if variables else "- *No dynamic variables extracted*"
    action_lines = "\n".join([f"- {a}" for a in actions])
    finding_lines = "\n".join([f"- {f}" for f in findings])

    internal_summary = (
        f"### Executive Summary\n"
        f"{exec_summary}\n\n"
        f"### Diagnostic Findings\n"
        f"{finding_lines}\n\n"
        f"### Actions Taken & Execution Log\n"
        f"{action_lines}\n\n"
        f"### Discovered Variables\n"
        f"{var_lines}\n\n"
        f"### Resolution & Recommendations\n"
        f"- **Resolution Verdict**: `{res_type}`\n"
        f"- **Recommendations**: {recs}"
    )

    return SummarizationOutput(
        executive_summary=exec_summary,
        diagnostic_findings=findings,
        actions_taken=actions,
        discovered_variables=variables,
        recommendations=recs,
        customer_ticket_reply=customer_reply,
        internal_ticket_summary=internal_summary,
        resolution_type=res_type
    )


def summarization_agent(state: SupportState) -> Command[Literal["__end__"]]:
    """Summarization Agent Node: Generates customer response & internal engineering record."""
    workflow_status = state.get("workflow_status") or "completed"
    is_escalated = workflow_status == "escalated" or state.get("is_human_rejected", False) is True

    entities = state.get("entities") or {}
    hostname = entities.get("hostname", "target machine")
    sop_id = state.get("sop", {}).get("sop_id") if isinstance(state.get("sop"), dict) else "SOP-DYN-000"

    prompt = SUMMARIZATION_SYSTEM_PROMPT.format(
        intent=state.get("intent") or "System Troubleshooting",
        category=state.get("category") or "general",
        hostname=hostname,
        sop_id=sop_id or "SOP-001",
        workflow_status=workflow_status,
        variables=json.dumps(state.get("variables") or {}),
        execution_results=json.dumps(state.get("execution_results") or {}),
        audit_log=json.dumps(state.get("audit_log", []))
    )

    res: Optional[SummarizationOutput] = None
    try:
        # Tier 1: Try structured output directly
        llm_structured = get_llm("summarization", temperature=0).with_structured_output(SummarizationOutput)
        res = llm_structured.invoke([{"role": "user", "content": prompt}])
        if res is None:
            raise ValueError("Structured LLM invocation returned None")
    except Exception as e1:
        print(f"  [Summarization LLM Info] Tier 1 structured output parsing fallback ({e1}). Trying Tier 2 raw JSON parsing.")
        try:
            # Tier 2: Try standard LLM invoke and parse JSON block
            llm_raw = get_llm("summarization", temperature=0)
            raw_msg = llm_raw.invoke([{"role": "user", "content": prompt + "\n\nIMPORTANT: Return ONLY a valid JSON object matching the schema."}])
            raw_text = raw_msg.content if hasattr(raw_msg, "content") else str(raw_msg)
            clean_text = raw_text
            if "```json" in clean_text:
                clean_text = clean_text.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_text:
                clean_text = clean_text.split("```")[1].split("```")[0].strip()
            
            json_match = re.search(r"\{[\s\S]*\}", clean_text)
            if json_match:
                parsed_json = json.loads(json_match.group(0))
                res = SummarizationOutput(**parsed_json)
            else:
                raise ValueError("No JSON object found in response")
        except Exception as e2:
            print(f"  [Summarization LLM Warning] Tier 2 raw JSON parsing failed ({e2}). Using Tier 3 programmatic fallback generator.")
            res = _build_rich_fallback_summary(state, is_escalated)

    if res is None:
        res = _build_rich_fallback_summary(state, is_escalated)

    # If ticket was escalated, consume the L2 Escalation Ticket Handover markdown for internal_summary
    escalation_payload = state.get("escalation_payload") or {}
    if is_escalated and escalation_payload.get("handover_markdown"):
        res.internal_ticket_summary = escalation_payload.get("handover_markdown")
        res.resolution_type = "ESCALATED_L2"
    elif not res.internal_ticket_summary or len(res.internal_ticket_summary.strip()) < 50:
        var_lines = "\n".join([f"- **`{k}`**: `{v}`" for k, v in res.discovered_variables.items()]) if res.discovered_variables else "- *No dynamic variables extracted*"
        action_lines = "\n".join([f"- {a}" for a in res.actions_taken]) if res.actions_taken else "- *Automated execution completed*"
        finding_lines = "\n".join([f"- {f}" for f in res.diagnostic_findings]) if res.diagnostic_findings else f"- Evaluated workstation {hostname}"
        res.internal_ticket_summary = (
            f"### Executive Summary\n"
            f"{res.executive_summary or f'Ticket resolution on workstation {hostname}.'}\n\n"
            f"### Diagnostic Findings\n"
            f"{finding_lines}\n\n"
            f"### Actions Taken & Execution Log\n"
            f"{action_lines}\n\n"
            f"### Discovered Variables\n"
            f"{var_lines}\n\n"
            f"### Resolution & Recommendations\n"
            f"- **Resolution Verdict**: `{res.resolution_type}`\n"
            f"- **Recommendations**: {res.recommendations or 'No further action required.'}"
        )

    customer_reply = res.customer_ticket_reply
    internal_summary = res.internal_ticket_summary
    res_type = res.resolution_type
    final_status = "escalated" if is_escalated else "done"

    # Write episodic trace memory log once upon workflow completion
    ticket_id = state.get("ticket_id") or "1000"
    category = state.get("category") or "general"
    trajectory = state.get("audit_log", [])
    write_episodic_log(
        ticket_id=ticket_id,
        sop_id=sop_id or "SOP-DYN-000",
        hostname=hostname,
        status=final_status,
        user_input=state.get("ticket_raw", ""),
        trajectory=trajectory,
        category=category
    )

    print(f"\n==================================================")
    print(f"--- [SUMMARIZATION AGENT COMPLETE] ---")
    print(f"  Final Status: {final_status} | Resolution Type: {res_type}")
    print(f"--------------------------------------------------")
    print(f"Customer Reply (Email):\n{customer_reply}\n")
    print(f"Internal Engineering Summary:\n{internal_summary}")
    print(f"==================================================\n")

    return Command(
        goto="__end__",
        update={
            "customer_ticket_reply": customer_reply,
            "internal_ticket_summary": internal_summary,
            "summarization_details": res.model_dump(),
            "resolution_type": res_type,
            "workflow_status": final_status,
            "audit_log": ["[Summarization] Final response & engineering log generated"],
        },
    )
