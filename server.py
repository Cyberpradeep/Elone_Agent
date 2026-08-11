import datetime
import json
import os
import queue
import re
import shutil
import threading
import time
import uuid
from typing import Any, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# pyrefly: ignore [missing-import]
from langgraph.types import Command

from graph import graph
from shared.tool_catalog import (
    TOOL_CATALOG,
    PROVIDER_NAMES,
    get_tool_names,
    get_function_names,
)
from agents.jit_converter.node import plan_okf_from_raw, write_okf_playbook
from agents.plan_validator.validator import validate_plan_faithfulness_and_linkage
from shared.ticket_logger import save_ticket_log, load_ticket_log, list_saved_tickets
from ingestion_pipe.scheduler import start_sop_ingestion_scheduler, get_scheduler_status


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

UPLOAD_DIR = os.path.join(BASE_DIR, "knowledge_base", "_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="EloneAgent API")



class NewTicketBody(BaseModel):
    ticket_raw: str
    customer_email: Optional[str] = None
    category: Optional[str] = None
    entities: Optional[dict] = None


class ClarifyBody(BaseModel):
    type: str  # "dropdown" | "dropdown_other" | "text"
    intent: Optional[str] = None
    environment: Optional[str] = None
    description: Optional[str] = None
    reply: Optional[str] = None


class ApproveBody(BaseModel):
    # Console edits to step descriptions/commands, matched by step_number.
    edited_steps: Optional[list[dict]] = None


class RejectBody(BaseModel):
    reason: Optional[str] = None
    rejected_step: Optional[int] = None
    escalation_team: Optional[str] = None


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _serialize(thread_id: str, snap) -> dict:
    values = snap.values or {}
    next_nodes = list(snap.next or [])
    awaiting_approval = "execution_agent" in next_nodes
    awaiting_clarification = values.get("workflow_status") == "need_clarification"

    if values:
        try:
            save_ticket_log(thread_id, values)
        except Exception:
            pass

    return {
        "thread_id": thread_id,
        "done": len(next_nodes) == 0 and not awaiting_clarification,
        "awaiting_approval": awaiting_approval,
        "awaiting_clarification": awaiting_clarification,
        "workflow_status": values.get("workflow_status"),
        "intent": values.get("intent"),
        "category": values.get("category"),
        "environment": values.get("environment"),
        "priority": values.get("priority"),
        "customer_email": values.get("customer_email"),
        "entities": values.get("entities") or {},
        "clarification_question": values.get("clarification_question"),
        "clarification_ui": values.get("clarification_ui"),
        "sop": values.get("sop"),
        "plan_valid": values.get("plan_valid"),
        "execution_plan": values.get("execution_plan"),
        "current_step_index": values.get("current_step_index", 0),
        "execution_results": values.get("execution_results") or {},
        "execution_exit_codes": values.get("execution_exit_codes") or {},
        "variables": values.get("variables") or {},
        "user_response": values.get("user_response"),
        "customer_ticket_reply": values.get("customer_ticket_reply"),
        "internal_ticket_summary": values.get("internal_ticket_summary"),
        "summarization_details": values.get("summarization_details"),
        "resolution_type": values.get("resolution_type"),
        "escalation_reason": values.get("escalation_reason"),
        "escalation_payload": values.get("escalation_payload"),
        "audit_log": values.get("audit_log", []),
        "elapsed_seconds": _elapsed_seconds(thread_id),
    }


# ---------- Run registry (one in-flight graph execution per ticket) ----------
#
# The graph is driven on a background thread that publishes an SSE event per
# agent node, and /stream drains that queue. Kicking the workflow off inside the
# POST handler instead would block the request for the whole intake -> planning
# phase (and, after approval, for every remaining step), which is exactly the
# window the operator console needs to be showing progress.

END_SENTINEL = "__stream_end__"
KEEPALIVE_SECONDS = 15.0


class Run:
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.events: queue.Queue = queue.Queue()
        self.finished = False
        self.thread: Optional[threading.Thread] = None


RUNS: dict[str, Run] = {}
STARTED_AT: dict[str, float] = {}
RUNS_LOCK = threading.Lock()


def _elapsed_seconds(thread_id: str) -> int:
    started = STARTED_AT.get(thread_id)
    return int(time.time() - started) if started else 0


def _emit(run: Run, event: str, payload: Optional[dict]):
    run.events.put((event, payload))


def _pending_node(snap) -> Optional[str]:
    for node in (snap.next or ()):
        return node
    return None


def _stream_worker(run: Run, kickoff: Any):
    """
    Drives the graph to its next genuine stopping point, emitting one event per
    agent node so the console updates while each agent works.

    `interrupt_before=["execution_agent"]` fires before EVERY step, not just the
    first. Mirroring main.py's CLI loop, a pause past step 0 is resumed silently
    (steps 2..N auto-continue while they keep passing execution_result_agent's
    verification); only an unapproved step-1 gate, a clarification request, or a
    finished graph is reported to the client.
    """
    config = _config(run.thread_id)
    payload = kickoff
    try:
        while True:
            snap = graph.get_state(config)
            first = _pending_node(snap) or "intake_agent"
            _emit(run, "node_start", {"node": first})

            for update in graph.stream(payload, config=config, stream_mode="updates"):
                if not isinstance(update, dict):
                    continue
                for node_name in update:
                    # Interrupts surface as a reserved "__interrupt__" key, not
                    # as a node that ran.
                    if node_name.startswith("__"):
                        continue
                    snap = graph.get_state(config)
                    _emit(run, "node", {"node": node_name, "state": _serialize(run.thread_id, snap)})
                    upcoming = _pending_node(snap)
                    if upcoming:
                        _emit(run, "node_start", {"node": upcoming})

            snap = graph.get_state(config)
            state = _serialize(run.thread_id, snap)

            if state["awaiting_approval"] and (snap.values.get("current_step_index") or 0) > 0:
                # Between-step interrupt -- the human already approved this plan.
                payload = None
                continue

            _emit(run, "done" if state["done"] else "paused", {"state": state})
            break
    except Exception as e:
        _emit(run, "error", {"message": str(e)})
    finally:
        run.finished = True
        run.events.put((END_SENTINEL, None))


def _start_run(thread_id: str, kickoff: Any) -> Run:
    with RUNS_LOCK:
        existing = RUNS.get(thread_id)
        if existing and not existing.finished:
            raise HTTPException(status_code=409, detail="A run is already in flight for this ticket.")
        run = Run(thread_id)
        run.thread = threading.Thread(target=_stream_worker, args=(run, kickoff), daemon=True)
        RUNS[thread_id] = run
        STARTED_AT.setdefault(thread_id, time.time())
    run.thread.start()
    return run


@app.post("/api/tickets")
def create_ticket(body: NewTicketBody):
    thread_id = f"AGT-{uuid.uuid4().hex[:12]}"

    initial_state = {
        "ticket_raw": body.ticket_raw,
        "customer_email": body.customer_email,
        "category": body.category,
        "entities": body.entities or {},
        "tool_catalog": TOOL_CATALOG,
        "replan_attempts": 0,
        "sop_fetch_attempts": 0,
        "execution_retry_attempts": 0,
        "clarification_attempts": 0,
        "workflow_status": "pending",
        "audit_log": [],
    }

    _start_run(thread_id, initial_state)

    # Returns as soon as the thread exists; the client opens /stream to watch it.
    return {
        "thread_id": thread_id,
        "done": False,
        "awaiting_approval": False,
        "awaiting_clarification": False,
        "workflow_status": "pending",
        "current_step_index": 0,
        "elapsed_seconds": 0,
        "audit_log": [],
    }


@app.get("/api/tickets/{thread_id}/stream")
def stream_ticket(thread_id: str):
    """Server-sent events for one run: node_start / node / paused / done / error."""
    with RUNS_LOCK:
        run = RUNS.get(thread_id)
    if not run:
        raise HTTPException(status_code=404, detail="No active run for this ticket.")

    def event_gen():
        while True:
            try:
                event, payload = run.events.get(timeout=KEEPALIVE_SECONDS)
            except queue.Empty:
                if run.finished:
                    # Nothing left to send and the worker is done (a reconnect
                    # after the stream already ended) -- close instead of
                    # holding the response open forever.
                    break
                # Comment-only frame: keeps intermediaries from dropping an idle
                # stream while a slow LLM call is in flight.
                yield ": keepalive\n\n"
                continue
            if event == END_SENTINEL:
                break
            yield f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/tickets")
def list_tickets():
    """Returns all historical saved ticket logs for the UI sidebar queue."""
    return {"tickets": list_saved_tickets()}


@app.get("/api/tickets/{thread_id}/state")
def get_ticket_state(thread_id: str):
    snap = graph.get_state(_config(thread_id))
    if snap.values:
        return _serialize(thread_id, snap)

    # Fallback to persistent JSON ticket log on disk if RAM checkpoint is gone
    saved = load_ticket_log(thread_id)
    if saved:
        return saved

    raise HTTPException(status_code=404, detail="Unknown thread_id")


@app.post("/api/tickets/{thread_id}/clarify")
def clarify_ticket(thread_id: str, body: ClarifyBody):
    config = _config(thread_id)
    snap = graph.get_state(config)
    if not snap.values:
        raise HTTPException(status_code=404, detail="Unknown thread_id")
    ticket_raw = snap.values.get("ticket_raw", "")

    # Clearing sop/execution_plan/plan_valid re-runs retrieval and planning with
    # the clarified intent instead of reusing the pre-clarification match.
    reset = {
        "workflow_status": "in_progress",
        "sop": None,
        "execution_plan": None,
        "plan_valid": None,
        "validator_result": None,
        "clarification_question": None,
        "clarification_ui": None,
    }

    if body.type == "dropdown":
        new_state = {**reset, "intent": body.intent, "environment": body.environment}
    elif body.type == "dropdown_other":
        new_state = {
            **reset,
            "intent": "other",
            "environment": "other",
            "ticket_raw": f"{ticket_raw}\nCustomer stated: Other issue. Description: {body.description or ''}",
        }
    elif body.type == "text":
        new_state = {
            **reset,
            "ticket_raw": f"{ticket_raw}\nCustomer Clarification: {body.reply or ''}",
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid clarify type")

    _start_run(thread_id, new_state)
    return _serialize(thread_id, graph.get_state(config))


def _apply_step_edits(plan: dict, edited: list[dict]) -> tuple[dict, list[str]]:
    """
    Folds the operator's console edits back into the plan, matched by
    step_number (what the UI stamps on each row). Only the description and the
    command are editable; a cleared field is ignored rather than wiping the
    step, since a blank command is never what the operator meant.
    """
    steps = [dict(s) for s in (plan.get("steps") or [])]
    by_number: dict[Any, dict] = {}
    for step in steps:
        by_number.setdefault(step.get("step_number"), step)

    notes: list[str] = []
    for entry in edited or []:
        target = by_number.get(entry.get("step_number"))
        if not target:
            continue
        step_label = target.get("step_number")
        new_desc = (entry.get("sop_step_description") or "").strip()
        if new_desc and new_desc != (target.get("sop_step_description") or ""):
            target["sop_step_description"] = new_desc
            notes.append(f"step {step_label} description")
        new_cmd = (entry.get("command") or "").strip()
        if new_cmd and new_cmd != (target.get("command") or ""):
            target["command"] = new_cmd
            notes.append(f"step {step_label} command")

    updated = dict(plan)
    updated["steps"] = steps
    return updated, notes


@app.post("/api/tickets/{thread_id}/approve")
def approve_ticket(thread_id: str, body: Optional[ApproveBody] = None):
    config = _config(thread_id)
    snap = graph.get_state(config)
    if not snap.values:
        raise HTTPException(status_code=404, detail="Unknown thread_id")
    if "execution_agent" not in (snap.next or ()):
        raise HTTPException(status_code=409, detail="This ticket is not waiting for plan approval.")

    # The approval marker and any operator edits ride along on the resume
    # payload. They must NOT go through graph.update_state(): at an
    # interrupt_before pause that discards the pending execution_agent task
    # (`next` collapses to ()), so the workflow ended having run zero steps.
    audit = ["[HITL] User approved the execution plan. Resuming execution..."]
    update: dict[str, Any] = {}

    if body and body.edited_steps:
        edited_plan, notes = _apply_step_edits(snap.values.get("execution_plan") or {}, body.edited_steps)
        if notes:
            update["execution_plan"] = edited_plan
            audit.append(f"[HITL] Operator edited {', '.join(notes)} before approval.")

    update["audit_log"] = audit
    _start_run(thread_id, Command(update=update))
    return _serialize(thread_id, graph.get_state(config))


@app.post("/api/tickets/{thread_id}/reject")
def reject_ticket(thread_id: str, body: RejectBody):
    config = _config(thread_id)
    snap = graph.get_state(config)
    if not snap.values:
        raise HTTPException(status_code=404, detail="Unknown thread_id")

    step_info = f"Step {body.rejected_step}" if body.rejected_step else "execution plan"
    team_info = f" to [{body.escalation_team}]" if body.escalation_team else ""
    reason_info = body.reason or "Step/plan rejected by operator."
    audit_msg = f"[HITL REJECT] Operator rejected {step_info}{team_info}. [REASON]: {reason_info}"

    # Unlike approve, reject DOES need update_state: it deliberately discards
    # the pending execution_agent task so the rejected step cannot still run
    # alongside the jump to escalation.
    graph.update_state(
        config,
        {
            "workflow_status": "escalated",
            "next_action": "ESCALATE",
            "escalation_reason": reason_info,
            "escalation_payload": {
                "rejected_step": body.rejected_step,
                "escalation_team": body.escalation_team,
                "reason": reason_info,
            },
            "audit_log": [audit_msg],
            "is_human_rejected": True,
        },
        as_node="execution_agent",
    )
    _start_run(thread_id, Command(goto="escalation_agent"))
    return _serialize(thread_id, graph.get_state(config))



# ============================================================
# SOP Ingestion
#
# Flow: upload -> (background) read + LLM OKF conversion + faithfulness and
# deterministic checks -> "awaiting_review" with the full draft plan returned to
# the UI for a human to inspect/edit -> confirm (re-validates, then writes the
# OKF playbook, its reflection rulebook, the category catalogs and the weekly
# audit log).
#
# Nothing touches the knowledge base until confirm: plan_okf_from_raw is
# read-only and write_okf_playbook is the only committing phase.
# ============================================================

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _set_job(job_id: str, **fields):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(fields)


def _infer_sop_id_title(filename: str) -> tuple[str, str]:
    match = re.match(r"^(SOP-[A-Z0-9-]+)_(.*?)\.[a-zA-Z0-9]+$", filename, re.IGNORECASE)
    if match:
        return match.group(1).upper(), match.group(2).replace("_", " ").strip()
    return (
        f"SOP-DYN-{uuid.uuid4().hex[:6].upper()}",
        os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title(),
    )


NO_TOOL_MESSAGE = "There is no tool provided for this operation in this SOP. Check that and add."


def _catalog_and_shape_errors(steps: list[dict]) -> list[str]:
    """
    Deterministic per-step checks for a reviewed SOP template.

    Note this deliberately does NOT flag `{{entities.x}}` placeholders the way
    the live-ticket planner validator does: in a stored template placeholders
    are correct and expected, and only get bound at execution time.
    """
    tool_names = get_tool_names(TOOL_CATALOG)
    errors: list[str] = []

    for idx, step in enumerate(steps, start=1):
        step_type = (step.get("step_type") or "command").strip().lower()
        tool_name = step.get("tool_name")
        function_name = step.get("function_name")
        command = (step.get("command") or "").strip()

        if not (step.get("sop_step_description") or "").strip():
            errors.append(f"Step {idx}: description is empty")

        if step_type not in ("command", "manual", "communication"):
            errors.append(f"Step {idx}: unknown step_type '{step_type}' (expected command, manual or communication)")

        if tool_name:
            if tool_name not in tool_names:
                errors.append(f"Step {idx}: unknown tool '{tool_name}'")
            elif function_name and function_name not in get_function_names(TOOL_CATALOG, tool_name):
                errors.append(f"Step {idx}: unknown function '{function_name}' on tool '{tool_name}'")
            elif not function_name:
                errors.append(f"Step {idx}: tool '{tool_name}' is set but no function_name is chosen")

        if step_type == "command" and not command:
            errors.append(f"Step {idx}: step_type is 'command' but no command is set")
        if step_type == "communication" and not tool_name and not command:
            errors.append(f"Step {idx}: unknown tool for this communication step")

    return errors


def _linkage_errors(steps: list[dict]) -> list[str]:
    """Layer-1 linkage check, reused from the plan validator (raw text omitted
    so it stays deterministic and never spends an LLM call)."""
    _, errors = validate_plan_faithfulness_and_linkage("", {"steps": steps})
    return errors


def _deterministic_errors(steps: list[dict]) -> list[str]:
    return _catalog_and_shape_errors(steps) + _linkage_errors(steps)


def _attach_step_errors(steps: list[dict], det_errors: list[str]) -> list[str]:
    """
    Splits flat check errors (which name their step inline, e.g.
    "Step 3: unknown tool 'xyz'" or "Layer 1 Error: Step 3 ...") into a per-step
    `errors` list (mutates `steps` in place) and returns whatever could not be
    attributed to a specific step.
    """
    per_step: dict[int, list[str]] = {}
    plan_level: list[str] = []
    for err in det_errors:
        match = re.search(r"\bStep (\d+)\b", err)
        if match:
            message = re.sub(r"^(?:.*?)\bStep \d+\b[:\s]*", "", err).strip() or err
            per_step.setdefault(int(match.group(1)), []).append(message)
        else:
            plan_level.append(err)

    # Errors are reported by 1-based position, which is what the reviewer sees
    # in the editor; a template's own step_number values are LLM-generated and
    # not guaranteed to match.
    for pos, step in enumerate(steps, start=1):
        errs = []
        for msg in per_step.get(pos, []):
            if msg.startswith("unknown tool") or msg.startswith("unknown function"):
                errs.append(f"{NO_TOOL_MESSAGE} ({msg})")
            else:
                errs.append(msg)
        if step.get("tool_gap"):
            errs.insert(0, f"{NO_TOOL_MESSAGE} ({step['tool_gap']})")
        step["errors"] = errs

    return plan_level


def _run_ingestion_job(job_id: str, path: str, sop_id: str, title: str, category: str, provider: str):
    try:
        _set_job(job_id, status="running", stage="reading", pct=15, message="Reading document...")
        _set_job(job_id, stage="planning", pct=40, message="Converting SOP to an OKF playbook with the LLM...")

        draft = plan_okf_from_raw(path, override_sop_id=sop_id)
        frontmatter = draft["frontmatter"]

        # The user already told us the category and which system this SOP
        # targets, so their choices win over the LLM's guesses.
        frontmatter["category"] = (category or frontmatter.get("category") or "other").lower().strip()
        frontmatter["provider"] = provider
        if title:
            frontmatter["title"] = title

        steps = [dict(s) for s in (frontmatter.get("steps") or [])]
        _set_job(
            job_id,
            stage="validating",
            pct=75,
            message="Running deterministic checks...",
            steps=len(steps),
            chars=draft.get("raw_chars"),
        )

        plan_level_errors = _attach_step_errors(steps, _deterministic_errors(steps))

        semantic_issues = list(draft.get("validation_errors") or [])
        semantic_status = "PASSED" if draft.get("is_valid") else "ISSUES_FOUND"
        semantic_reasoning = (
            "Passed SOP faithfulness inspection: every CLI command in the source document is "
            "represented in the plan, with none fabricated."
            if draft.get("is_valid")
            else "; ".join(str(i) for i in semantic_issues) or "Faithfulness inspection reported issues."
        )

        job_draft = {
            "sop_id": frontmatter.get("sop_id", sop_id),
            "sop_title": frontmatter.get("title", title),
            "sop_description": frontmatter.get("description", ""),
            "category": frontmatter["category"],
            "target_os": frontmatter.get("target_os", "windows"),
            "planning_reasoning": "\n".join(draft.get("reasoning_chain") or []),
            "required_entities": frontmatter.get("required_entities") or [],
            "trigger_words": frontmatter.get("trigger_words") or [],
            "provider": provider,
            "steps": steps,
            "plan_errors": plan_level_errors,
            "semantic_status": semantic_status,
            "semantic_reasoning": semantic_reasoning,
            "semantic_issues": semantic_issues,
        }
        has_issues = bool(plan_level_errors) or any(s.get("errors") for s in steps)

        _set_job(
            job_id,
            status="awaiting_review",
            stage="review",
            pct=85,
            message="Some steps need attention before storing." if has_issues else "Review the generated plan before storing.",
            draft=job_draft,
            raw_filename=os.path.basename(path),
        )
    except Exception as e:
        _set_job(job_id, status="error", message=str(e))


@app.get("/api/catalog")
def get_catalog():
    return {"providers": PROVIDER_NAMES, "tools": TOOL_CATALOG}


@app.post("/api/ingestion/upload")
def upload_sop(
    file: UploadFile = File(...),
    category: str = Form("Access Management"),
    provider: str = Form(...),
    sop_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
):
    if provider not in PROVIDER_NAMES:
        raise HTTPException(status_code=400, detail=f"Invalid provider '{provider}'. Must be one of {PROVIDER_NAMES}.")

    inferred_id, inferred_title = _infer_sop_id_title(file.filename)
    sop_id = sop_id or inferred_id
    title = title or inferred_title

    # Stored under its own name (no uuid prefix) and kept after conversion, so
    # retrieval's raw-upload fallback can match it by filename later.
    dest_path = os.path.join(UPLOAD_DIR, os.path.basename(file.filename))
    with open(dest_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued", "stage": "reading", "pct": 0, "message": "Queued...",
            "sop_id": sop_id, "title": title, "category": category, "provider": provider,
            "steps": None, "chars": None, "result": None, "draft": None,
        }

    thread = threading.Thread(
        target=_run_ingestion_job,
        args=(job_id, dest_path, sop_id, title, category, provider),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@app.get("/api/ingestion/jobs/{job_id}")
def get_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job


class ReviewBody(BaseModel):
    provider: str
    category: str
    sop_title: str
    sop_description: str
    required_entities: list[str]
    trigger_words: list[str]
    steps: list[dict]


def _revalidate(body: ReviewBody) -> tuple[list[dict], list[str], bool]:
    steps = [dict(s) for s in body.steps]
    plan_level_errors = _attach_step_errors(steps, _deterministic_errors(steps))
    valid = not plan_level_errors and not any(s.get("errors") for s in steps)
    return steps, plan_level_errors, valid


@app.post("/api/ingestion/jobs/{job_id}/revalidate")
def revalidate_job(job_id: str, body: ReviewBody):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or not job.get("draft"):
        raise HTTPException(status_code=404, detail="Unknown job or no draft available")

    steps, plan_level_errors, valid = _revalidate(body)
    return {"steps": steps, "plan_errors": plan_level_errors, "valid": valid}


@app.post("/api/ingestion/jobs/{job_id}/confirm")
def confirm_job(job_id: str, body: ReviewBody):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or not job.get("draft"):
        raise HTTPException(status_code=404, detail="Unknown job or no draft available")

    if body.provider not in PROVIDER_NAMES:
        raise HTTPException(status_code=400, detail=f"Invalid provider '{body.provider}'.")

    steps, plan_level_errors, valid = _revalidate(body)
    if not valid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Plan still has unresolved issues.", "steps": steps, "plan_errors": plan_level_errors},
        )

    draft = dict(job["draft"])
    # Strip the review-only annotation before it reaches the playbook file.
    clean_steps = [{k: v for k, v in s.items() if k != "errors"} for s in steps]

    frontmatter = {
        "type": "Playbook",
        "sop_id": draft["sop_id"],
        "title": body.sop_title,
        "category": (body.category or draft.get("category") or "other").lower().strip(),
        "target_os": draft.get("target_os", "windows"),
        "description": body.sop_description,
        "required_entities": body.required_entities,
        "trigger_words": body.trigger_words,
        "provider": body.provider,
        "steps": clean_steps,
    }

    _set_job(job_id, status="storing", stage="embedding", pct=95,
             message="Writing OKF playbook, rulebook and catalogs...")
    try:
        okf_path = write_okf_playbook(
            {"frontmatter": frontmatter},
            raw_filename=job.get("raw_filename") or "(reviewed draft)",
        )
    except Exception as e:
        _set_job(job_id, status="error", message=f"Storage failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    _set_job(
        job_id,
        status="completed",
        stage="completed",
        pct=100,
        message="SOP ingestion completed successfully",
        result={
            "sop_id": frontmatter["sop_id"],
            "sop_title": frontmatter["title"],
            "provider": frontmatter["provider"],
            "category": frontmatter["category"],
            "required_entities": frontmatter["required_entities"],
            "steps": len(clean_steps),
            "okf_path": os.path.relpath(okf_path, BASE_DIR).replace("\\", "/"),
            "ingested_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
    )
    with JOBS_LOCK:
        return JOBS[job_id]


# ============================================================
# Scheduled SOP Ingestion Worker
# ============================================================

@app.get("/api/ingestion/scheduler/status")
def scheduler_status():
    """Returns the current state of the background SOP ingestion scheduler."""
    return get_scheduler_status()


# Start the background scheduler (runs once on module load; safe to call
# multiple times -- only the first invocation spawns the thread).
start_sop_ingestion_scheduler()


# ============================================================
# Static frontend (mounted last so /api/* routes above take priority)
# ============================================================

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
