from typing import TypedDict, Optional, Annotated
import operator


class SupportState(TypedDict, total=False):
    ticket_id: Optional[int]
    customer_email: Optional[str]
    ticket_raw: str
    intent: str
    priority: str
    category: str
    detailed_description: str
    keywords: list[str]
    entities: dict[str, str]
    environment: Optional[str]
    is_vague: Optional[bool]
    is_ambiguous: Optional[bool]
    triage_notes: Optional[str]
    clarification_question: Optional[str]
    clarification_ui: Optional[dict]
    clarification_attempts: Optional[int]

    sop: Optional[dict]
    knowledge_docs: list
    retrieval_query: Optional[str]

    # OKF Knowledge Base & Reflection Memory Fields
    okf_file_path: Optional[str]
    relevant_memories: Optional[str]
    device_quirks: Optional[str]

    workflow_status: str
    orchestrator_reasoning: Optional[str]

    replan_attempts: int
    sop_fetch_attempts: int
    execution_retry_attempts: int

    execution_plan: Optional[dict]
    tool_catalog: list
    plan_feedback: Optional[str]  
    plan_valid: Optional[bool]
    validator_result: Optional[str] 
    plan_errors: Optional[list]
    replan_reason: Optional[str]

    execution_results: Optional[dict]
    # Per-step exit code, keyed by execution position (1-based) exactly like
    # execution_results. Kept separate because execution_results holds raw
    # stdout/stderr text: a non-zero exit still records output there, so the
    # text alone cannot tell a healthy step from a failed one.
    execution_exit_codes: Optional[dict]
    last_failed_step: Optional[int]
    current_step_index: Optional[int]
    last_executed_step: Optional[int]
    last_executed_command: Optional[str]
    last_executed_stdout: Optional[str]
    last_executed_stderr: Optional[str]
    last_executed_exit_code: Optional[int]
    completed_actions: Annotated[list, operator.add]

    next_action: Optional[str] 
    execution_reasoning: Optional[str]

    variables: Optional[dict]
    needs_clarification: Optional[bool]
    is_human_rejected: Optional[bool]

    final_response: Optional[str]
    customer_ticket_reply: Optional[str]
    internal_ticket_summary: Optional[str]
    summarization_details: Optional[dict]
    resolution_type: Optional[str]
    escalation_reason: Optional[str]
    escalation_payload: Optional[dict]

    # Intake Confidence & Discovery Fields
    ticket_details_confidence: Optional[float]
    sop_match_confidence: Optional[float]
    sop_source: Optional[str]
    matched_file_path: Optional[str]

    audit_log: Annotated[list, operator.add]
