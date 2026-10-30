"""
Pipeline Observability & Rich Console Logger
============================================
Unified, modular Rich logging for all 6 agents and orchestrator under msg/1.0.
"""

from typing import Dict, Any, Optional, List
import os

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.tree import Tree
    from rich.rule import Rule
    from rich.text import Text
    from rich.markup import escape
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    escape = lambda x: str(x)

console = Console() if RICH_AVAILABLE else None


def log_pipeline_header(filename: str, sha256: str, correlation_id: str, tenant_id: str) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"\n==============================================================================")
        print(f"  STARTING FULL PROTOCOL msg/1.0 PIPELINE TRACE FOR: {filename}")
        print(f"==============================================================================")
        print(f"  • Content SHA-256: {sha256}")
        print(f"  • Correlation ID:  {correlation_id}")
        print(f"  • Active Tenant:   {tenant_id}")
        print(f"  • Protocol:        msg/1.0 (Bus-Driven, Pure Artifact References)")
        return

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column(style="bold white")
    table.add_row("Source Document:", filename)
    table.add_row("Content SHA-256:", f"[cyan]{sha256}[/cyan]")
    table.add_row("Correlation ID:", f"[yellow]{correlation_id}[/yellow]")
    table.add_row("Active Tenant:", f"[green]{tenant_id}[/green]")
    table.add_row("Protocol:", "msg/1.0 (Bus-Driven, Pure Artifact References)")

    panel = Panel(
        table,
        title="[bold cyan]SOP GOVERNANCE HUB — msg/1.0 PROTOCOL TRACE[/bold cyan]",
        subtitle="[dim]Zero-Trust End-to-End Autonomous Pipeline[/dim]",
        border_style="cyan",
        expand=False,
    )
    console.print()
    console.print(panel)


def log_stage_header(stage_num: int, agent_id: str, title: str) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"\n{'#' * 78}\n  STAGE {stage_num}: [{agent_id}] {title}\n{'#' * 78}\n")
        return

    console.print()
    console.rule(f"[bold cyan]STAGE {stage_num}: [{agent_id}] {title}[/bold cyan]", style="cyan")


def log_protocol_dispatch(task: Any) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"  [Protocol msg/1.0 Task Dispatch]")
        print(f"    • Sender -> Recipient:   {task.sender} -> {task.recipient} (task_type: '{task.task_type}')")
        print(f"    • Task ID:               {task.task_id}")
        print(f"    • Input Artifacts:       {task.input_artifact_references}")
        return

    console.print(
        f"  [dim]Dispatch msg/1.0:[/dim] [yellow bold]{task.sender}[/yellow bold] → [cyan bold]{task.recipient}[/cyan bold] "
        f"[dim](task: '{task.task_type}')[/dim] | [dim]Task ID:[/dim] [white]{task.task_id}[/white] | [dim]Inputs:[/dim] {task.input_artifact_references}"
    )


def log_protocol_result(result: Any) -> None:
    latency = result.processing_metrics.get("latency_ms", 0) if hasattr(result, "processing_metrics") else 0
    tools = result.processing_metrics.get("tools_used", []) if hasattr(result, "processing_metrics") else []
    status_str = result.status.upper()

    if not RICH_AVAILABLE or console is None:
        print(f"  [Protocol msg/1.0 Result Received]")
        print(f"    • Status:                {status_str}")
        print(f"    • Agent ID:              {result.agent_id}")
        print(f"    • Output Artifact:       {result.output_artifact_reference}")
        print(f"    • Telemetry:             latency={latency}ms | tools={tools}")
        return

    badge = "[bold green]✓ SUCCESS[/bold green]" if status_str == "SUCCESS" else (
        "[bold yellow]⚠ NEEDS_REVIEW[/bold yellow]" if status_str == "NEEDS_REVIEW" else f"[bold red]✗ {status_str}[/bold red]"
    )
    console.print(
        f"  [dim]Result msg/1.0:[/dim]   {badge} | [dim]Agent:[/dim] [cyan]{result.agent_id}[/cyan] | "
        f"[dim]Artifact:[/dim] [yellow]{result.output_artifact_reference or 'None'}[/yellow] | "
        f"[dim]Telemetry:[/dim] {latency}ms ({len(tools)} tools)"
    )


def log_stage1_intake(
    parser_type: str,
    char_count: int,
    word_count: int,
    line_count: int,
    seg_count: int,
    img_count: int,
    max_imgs: int,
    sample_text: Optional[str] = None
) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"  • Extraction Engine:      {parser_type}")
        print(f"  • Extracted Text Stats:   {char_count} chars, {word_count} words, {line_count} lines")
        print(f"  • Ordered Segments:       {seg_count} segments identified")
        print(f"  • Embedded Images Found:  {img_count} (Capped to max {max_imgs} per policy)")
        if sample_text:
            print(f"  [Sample Extracted Content (first 250 chars)]:\n  " + "-" * 70)
            print(f"  {sample_text[:250].strip()}")
            print(f"  " + "-" * 70)
        return

    tree = Tree(f"[bold cyan]Agent A1: Document Extraction & Intake Audit[/bold cyan]")
    tree.add(f"[dim]Engine:[/dim]       [white bold]{parser_type}[/white bold]")
    tree.add(f"[dim]Text Metrics:[/dim] {char_count:,} chars | {word_count:,} words | {line_count} lines")
    tree.add(f"[dim]Layout:[/dim]       {seg_count} ordered segment(s) | {img_count} embedded image(s) (cap: {max_imgs})")
    if sample_text:
        snippet = sample_text[:300].strip().replace("\n", "\n    ")
        tree.add(f"[dim]Sample Extracted Content:[/dim]\n    [dim italic]{snippet}...[/dim italic]")
    console.print(tree)


def log_stage2_security(
    total_redacted: int,
    redaction_counts: dict,
    ast_count: int,
    ast_threats: Optional[List[Any]] = None,
    is_quarantined: bool = False
) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"  • DLP Secret Redaction:   {total_redacted} secret token(s) identified & masked")
        if total_redacted > 0:
            print(f"  • Masked Breakdown:       {redaction_counts}")
        print(f"  • AST Sandbox Safety:     {'CLEAR (No malicious payloads)' if ast_count == 0 else f'ALERT: {ast_count} threats detected'}")
        if ast_threats:
            for t in ast_threats:
                print(f"    - Threat: {t}")
        if is_quarantined:
            print(f"  • Status:                 TERMINAL QUARANTINE")
        return

    tree = Tree("[bold cyan]Agent A3: Security & DLP Threat Sandbox[/bold cyan]")
    
    # AST Threat Status
    if ast_count == 0:
        tree.add(f"[dim]AST Sandbox:[/dim]      [bold green]CLEAR (No malicious payloads)[/bold green]")
    else:
        threat_branch = tree.add(f"[dim]AST Sandbox:[/dim]      [bold red]ALERT: {ast_count} threat(s) detected[/bold red]")
        if ast_threats:
            for t in ast_threats:
                threat_branch.add(f"[red]• {t}[/red]")

    # DLP Secret Redaction Status
    if total_redacted == 0:
        tree.add(f"[dim]DLP Secret Gate:[/dim]  [bold green]0 secrets detected[/bold green]")
    else:
        tree.add(f"[dim]DLP Secret Gate:[/dim]  [bold yellow]{total_redacted} secret token(s) identified & masked[/bold yellow]")
        if redaction_counts:
            tree.add(f"[dim]Masked Breakdown:[/dim] [yellow]{redaction_counts}[/yellow]")

    if is_quarantined:
        tree.add(f"[dim]Quarantine Gate:[/dim] [bold red]TERMINAL QUARANTINE (Pipeline Halted — Zero AI Calls)[/bold red]")

    console.print(tree)


def log_execution_plan(data: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        return

    title = data.get("title", "Untitled Playbook")
    status = str(data.get("automation_status", "fully_automated")).upper()
    c_score = float(data.get("confidence_score") or 0.95)
    c_level = data.get("confidence_level") or ("High" if c_score >= 0.85 else "Medium")
    c_reason = data.get("confidence_reason")
    entities = data.get("required_entities") or []
    steps = data.get("steps") or []

    if not RICH_AVAILABLE or console is None:
        print(f"[Stage 2: Execution Planner] Plan: '{title}' | Status: {status} | Confidence: {c_score:.2f} ({c_level})")
        if c_reason:
            print(f"[Stage 2: Execution Planner] Reason: {c_reason}")
        if entities:
            print(f"[Stage 2: Execution Planner] Entities: {entities}")
        if steps:
            print(f"[Stage 2: Execution Planner] Planned Steps ({len(steps)}):")
            for s in steps:
                cmd = s.get("command") or f"{s.get('platform')}.{s.get('function_name')}"
                print(f"  • [{s.get('step_number')}] {s.get('sop_step_description')}")
                if s.get("step_reasoning"):
                    print(f"    - Reasoning: {s.get('step_reasoning')}")
                print(f"    - Command:   {cmd}")
                if s.get("execute_if"):
                    print(f"    - Gate:      {s.get('execute_if')}")
        return

    tree = Tree(f"[bold cyan]Agent A2 Planned Playbook:[/bold cyan] [bold white]{title}[/bold white]")
    tree.add(f"[dim]Status:[/dim] [green bold]{status}[/green bold] | [dim]Confidence:[/dim] {c_score:.2f} ({c_level})")
    if c_reason:
        tree.add(f"[dim]Reason:[/dim] {c_reason}")
    if entities:
        tree.add(f"[dim]Entities:[/dim] [yellow]{entities}[/yellow]")

    if steps:
        step_branch = tree.add(f"[bold cyan]Execution Steps ({len(steps)})[/bold cyan]")
        for s in steps:
            s_num = s.get("step_number", "?")
            s_desc = s.get("sop_step_description") or "Execution step"
            s_cmd = s.get("command") or f"{s.get('platform')}.{s.get('function_name')}"
            node = step_branch.add(f"[bold white][{s_num}][/bold white] {s_desc}")
            if s.get("step_reasoning"):
                node.add(f"[dim]Reasoning:[/dim] {s.get('step_reasoning')}")
            node.add(f"[green]Command:[/green]   [bold]{s_cmd}[/bold]")
            if s.get("execute_if"):
                node.add(f"[yellow]Gate:[/yellow]      {s.get('execute_if')}")
            if s.get("fallback_command"):
                node.add(f"[magenta]Fallback:[/magenta]  {s.get('fallback_command')}")
            if s.get("parse_instruction"):
                node.add(f"[blue]Parse:[/blue]     {s.get('parse_instruction')}")
    console.print(tree)


def log_stage3_structuring(sop_id: str, title: str, platform: str, target_os: str, step_count: int, conf_tier: str, conf_score: int) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"  • SOP ID Generated:       {sop_id}")
        print(f"  • SOP Title:              {title}")
        print(f"  • Target Platform / OS:   {platform} / {target_os}")
        print(f"  • Execution Steps Built:  {step_count} procedural step(s)")
        print(f"  • Confidentiality Tier:   {conf_tier} (Score: {conf_score})")
        return

    tree = Tree(f"[bold cyan]Agent A2: Canonical OKF Model Structured[/bold cyan]")
    tree.add(f"[dim]Identifier:[/dim] [white bold]{sop_id}[/white bold] — {title}")
    tree.add(f"[dim]Platform / OS:[/dim]      {platform} / {target_os}")
    tree.add(f"[dim]Procedural Steps:[/dim]   [green bold]{step_count}[/green bold] step(s)")
    tree.add(f"[dim]Confidentiality Tier:[/dim] [yellow bold]{conf_tier}[/yellow bold] (Score: {conf_score})")
    console.print(tree)


def log_stage4_quality(
    completeness: float,
    traceability: float,
    blocking_count: int,
    q_score: float,
    q_status: str,
    unresolved_issues: Optional[List[Any]] = None,
    quotes_verified: Optional[int] = None,
    total_quotes: Optional[int] = None,
) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"  • Completeness (C):       {completeness:.1f}%")
        print(f"  • Traceability (T):       {traceability:.1f}%")
        print(f"  • Blocking Issues (B):    {blocking_count}")
        print(f"  • Quality Formula:        Q = 0.4({completeness:.1f}) + 0.4({traceability:.1f}) + 20 - 5({blocking_count})")
        print(f"  • Final Governance Score: {q_score:.1f} / 100.0 (Status: {q_status})")
        if unresolved_issues:
            for iss in unresolved_issues:
                print(f"    - Issue: {iss}")
        return

    score_color = "green" if q_score >= 80 else ("yellow" if q_score >= 60 else "red")
    tree = Tree(f"[bold cyan]Agent A4: Quality Scoring & Governance Verification[/bold cyan]")
    tree.add(f"[dim]Completeness (C):[/dim]    {completeness:.1f}%")
    quotes_str = f" ({quotes_verified}/{total_quotes} quotes verified)" if total_quotes else ""
    tree.add(f"[dim]Traceability (T):[/dim]    {traceability:.1f}%{quotes_str}")
    tree.add(f"[dim]Blocking Issues (B):[/dim] {blocking_count}")
    tree.add(f"[dim]Formula:[/dim]              0.4({completeness:.1f}) + 0.4({traceability:.1f}) + 20 - 5({blocking_count})")
    tree.add(f"[dim]Governance Score:[/dim]    [{score_color} bold]{q_score:.1f} / 100.0[/{score_color} bold] [dim](Status: {q_status})[/dim]")
    
    if unresolved_issues:
        issues_branch = tree.add(f"[red bold]Flagged Unresolved Issues ({len(unresolved_issues)}):[/red bold]")
        for iss in unresolved_issues:
            err_msg = iss.get("error") if isinstance(iss, dict) else str(iss)
            issues_branch.add(f"[yellow]{err_msg}[/yellow]")

    console.print(tree)


def log_validation_audit(inspection_result: Any) -> None:
    if not inspection_result:
        return

    is_faithful = getattr(inspection_result, "is_faithful", True)
    has_injection = getattr(inspection_result, "injection_detected", False)
    score = getattr(inspection_result, "confidence_score", 1.0)
    level = getattr(inspection_result, "confidence_level", "High")
    reason = getattr(inspection_result, "confidence_reason", "Validation complete")

    cmd_preservation = getattr(inspection_result, "command_preservation_reasoning", None)
    hallucination_check = getattr(inspection_result, "hallucination_check_reasoning", None)
    fallback_referral = getattr(inspection_result, "fallback_referral_reasoning", None)
    threat_sandbox = getattr(inspection_result, "injection_reasoning", None)
    dropped = getattr(inspection_result, "dropped_commands", []) or []
    hallucinated = getattr(inspection_result, "hallucinated_commands", []) or []
    malicious = getattr(inspection_result, "malicious_steps", []) or []
    feedback = getattr(inspection_result, "validation_feedback", "")

    verdict_str = "PASSED" if is_faithful and not has_injection else "FAILED"

    if not RICH_AVAILABLE or console is None:
        print(f"\n[PlanValidator Layer 2] Faithfulness Verdict: {verdict_str} | Confidence: {score:.2f} ({level}) | Injection Detected: {has_injection}")
        print(f"[PlanValidator Layer 2] Reason: {reason}")
        print("[PlanValidator Layer 2] CoT Inspection:")
        if cmd_preservation:
            print(f"  • Preservation:      {cmd_preservation}")
        if hallucination_check:
            print(f"  • Anti-Hallucination:{hallucination_check}")
        if fallback_referral:
            print(f"  • Fallbacks & Errors:{fallback_referral}")
        if threat_sandbox:
            print(f"  • Threat Sandbox:    {threat_sandbox}")
        if dropped:
            print(f"  • Dropped Commands:  {dropped}")
        if hallucinated:
            print(f"  • Fabricated/Halluc: {hallucinated}")
        return

    border_color = "green" if verdict_str == "PASSED" else "red"
    body_lines = [
        f"[bold]Verdict:[/bold] [{border_color} bold]{verdict_str}[/{border_color} bold] | [bold]Confidence:[/bold] {score:.2f} ({level}) | [bold]Threat Detected:[/bold] {has_injection}",
        f"[dim]Reason:[/dim] {escape(str(reason))}",
        "",
        "[bold underline]Chain-of-Thought Inspection Audit:[/bold underline]",
    ]
    if cmd_preservation:
        body_lines.append(f"  [cyan]• Preservation:[/cyan]      {escape(str(cmd_preservation))}")
    if hallucination_check:
        body_lines.append(f"  [cyan]• Anti-Hallucination:[/cyan]{escape(str(hallucination_check))}")
    if fallback_referral:
        body_lines.append(f"  [cyan]• Fallbacks & Errors:[/cyan]{escape(str(fallback_referral))}")
    if threat_sandbox:
        body_lines.append(f"  [cyan]• Threat Sandbox:[/cyan]    {escape(str(threat_sandbox))}")

    if dropped:
        body_lines.append(f"\n  [red bold]Dropped Commands:[/red bold] {escape(str(dropped))}")
    if hallucinated:
        body_lines.append(f"  [red bold]Fabricated/Hallucinated Commands:[/red bold] {escape(str(hallucinated))}")
    if malicious:
        body_lines.append(f"  [red bold]Malicious Steps Flagged:[/red bold] {escape(str(malicious))}")
    if feedback and feedback != "PASSED FAITHFULNESS INSPECTION":
        body_lines.append(f"\n  [yellow bold]Required Feedback Directive:[/yellow bold] {escape(str(feedback))}")

    panel = Panel(
        "\n".join(body_lines),
        title=f"[{border_color} bold]PlanValidator Layer 2 Audit: {verdict_str}[/{border_color} bold]",
        border_style=border_color,
        expand=False,
    )
    console.print()
    console.print(panel)


def log_stage5_review(draft_file: str, review_task_id: str, assigned_role: str, due_date: str) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"  • Staged Location:        {draft_file}")
        print(f"  • Review Task Created:    {review_task_id} (Role: {assigned_role})")
        print(f"  • SLA Due Date:           {due_date}")
        print(f"  • Separation of Duties:   Enforced (Author != Reviewer; Human Approver Required)")
        return

    tree = Tree(f"[bold cyan]Agent A5: Dual-Custody HITL Staging[/bold cyan]")
    tree.add(f"[dim]Staged Draft:[/dim]        [white]{draft_file}[/white]")
    tree.add(f"[dim]Review Task:[/dim]         [yellow bold]{review_task_id}[/yellow bold] (Role: {assigned_role})")
    tree.add(f"[dim]SLA Due Date:[/dim]        {due_date}")
    tree.add(f"[dim]Separation of Duties:[/dim] [green]Enforced[/green] (Dual-custody verification required)")
    console.print(tree)


def log_stage6_publication(sop_id: str, published_path: str, canonical_path: str, hmac_sig: str, verified: bool, tenant_id: str, clearance: str, citation: str) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"  • Production Playbook:    {published_path}")
        print(f"  • Canonical JSON 1.0:     {canonical_path}")
        print(f"  • Cryptographic Stamp:    HMAC-SHA256 ({hmac_sig[:12]}...) [Verified: {verified}]")
        print(f"  • Retrieval Indexing:     Indexed in Catalog (Tenant: '{tenant_id}', Clearance: '{clearance}')")
        print(f"  • Citation Stamp:         {citation}")
        return

    sig_short = f"{hmac_sig[:12]}...{hmac_sig[-8:]}" if len(hmac_sig) > 20 else hmac_sig
    tree = Tree(f"[bold cyan]Agent A6: Publication & Cryptographic Catalog Indexing[/bold cyan]")
    tree.add(f"[dim]Production Playbook:[/dim] [white bold]{published_path}[/white bold]")
    tree.add(f"[dim]Canonical Model:[/dim]     [white]{canonical_path}[/white]")
    tree.add(f"[dim]Cryptographic Stamp:[/dim] HMAC-SHA256 ({sig_short}) [green bold]Verified: {verified}[/green bold]")
    tree.add(f"[dim]Catalog Indexing:[/dim]    Tenant: [green]{tenant_id}[/green] | Clearance: [yellow]{clearance}[/yellow]")
    tree.add(f"[dim]Citation Stamp:[/dim]      [cyan bold]{citation}[/cyan bold]")
    console.print(tree)


def log_pipeline_summary(filename: str, sop_id: str, elapsed: float, msg_count: int, calls: int, max_calls: int, playbook_path: str, canonical_path: str, status: str) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"\n==============================================================================")
        print(f"  END-TO-END PIPELINE TRACE COMPLETE")
        print(f"==============================================================================")
        print(f"  • Total Pipeline Latency: {elapsed:.2f}s")
        print(f"  • Total Bus Messages:     {msg_count}")
        print(f"  • Agent Calls Dispatched: {calls} / {max_calls}")
        print(f"  • SOP Published ID:       {sop_id}")
        print(f"  • Final Status:           {status}")
        print(f"==============================================================================\n")
        return

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column(style="bold white")
    table.add_row("Total Pipeline Latency:", f"[cyan bold]{elapsed:.2f}s[/cyan bold]")
    table.add_row("Total Bus Messages:", str(msg_count))
    table.add_row("Agent Call Budget:", f"{calls} / {max_calls}")
    table.add_row("SOP Identifier:", f"[green bold]{sop_id}[/green bold]")
    table.add_row("Playbook Markdown:", playbook_path or "N/A")
    table.add_row("Canonical JSON:", canonical_path or "N/A")
    table.add_row("Governance Status:", f"[bold green]{status}[/bold green]")

    panel = Panel(
        table,
        title="[bold green]END-TO-END PIPELINE TRACE COMPLETE[/bold green]",
        subtitle="[dim]SOP Governance Verified & Fully Retrievable[/dim]",
        border_style="green",
        expand=False,
    )
    console.print()
    console.print(panel)
    console.print()


def log_session_summary(session: Dict[str, Any]) -> None:
    if not RICH_AVAILABLE or console is None:
        print("\n" + "=" * 70)
        print("  THIS EXECUTION — LLM CALL SUMMARY")
        print("=" * 70)
        print(f"  Session ID:         {session.get('session_id')}")
        print(f"  SOP File:           {session.get('sop_filename')}")
        print(f"  Total LLM Calls:    {session.get('total_calls')}")
        print(f"  Execution Cost:     ${session.get('cost_usd', 0):.4f} USD (~Rs. {session.get('cost_inr', 0):.2f} INR)")
        print("=" * 70 + "\n", flush=True)
        return

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column(style="bold white")
    table.add_row("Session ID:", str(session.get("session_id")))
    table.add_row("SOP File:", str(session.get("sop_filename")))
    table.add_row("Total LLM Calls:", f"[cyan bold]{session.get('total_calls')}[/cyan bold]")
    table.add_row("Token Breakdown:", f"{session.get('input_tokens', 0):,} in | {session.get('output_tokens', 0):,} out | {session.get('total_tokens', 0):,} total")
    table.add_row("Execution Cost:", f"[green bold]${session.get('cost_usd', 0):.4f} USD[/green bold] (~Rs. {session.get('cost_inr', 0):.2f} INR)")

    panel = Panel(
        table,
        title="[bold cyan]LLM EXECUTION TELEMETRY & COST SUMMARY[/bold cyan]",
        border_style="cyan",
        expand=False,
    )
    console.print()
    console.print(panel)


def log_daily_usage_banner(usage: Dict[str, Any]) -> None:
    if not RICH_AVAILABLE or console is None:
        print("\n" + "=" * 70)
        print("  DAILY API USAGE & COST REPORT")
        print("=" * 70)
        print(f"  Date:               {usage.get('date')}")
        print(f"  Daily Quota:        {usage.get('total_calls')}/{usage.get('max_daily_calls')} calls (Remaining: {usage.get('calls_remaining')})")
        print(f"  Today's Cost:       ${usage.get('total_cost_usd', 0):.4f} USD (~Rs. {usage.get('total_cost_inr', 0):.2f} INR)")
        print("=" * 70 + "\n", flush=True)
        return

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column(style="bold white")
    table.add_row("Date:", str(usage.get("date")))
    table.add_row("Quota Usage:", f"[cyan bold]{usage.get('total_calls')}[/cyan bold] / {usage.get('max_daily_calls')} calls (Remaining: {usage.get('calls_remaining')})")
    table.add_row("Total Tokens:", f"{usage.get('total_tokens', 0):,}")
    table.add_row("Today's Total Cost:", f"[green bold]${usage.get('total_cost_usd', 0):.4f} USD[/green bold] (~Rs. {usage.get('total_cost_inr', 0):.2f} INR)")

    panel = Panel(
        table,
        title="[bold green]DAILY LLM USAGE & COST AUDIT[/bold green]",
        border_style="green",
        expand=False,
    )
    console.print()
    console.print(panel)


def log_active_models(role_map: Dict[str, Any]) -> None:
    if not RICH_AVAILABLE or console is None:
        print("\n" + "=" * 65)
        print("  ACTIVE AGENT LLM CONFIGURATION")
        print("=" * 65)
        for role, conf in role_map.items():
            fb_str = f" | Fallbacks: {[f['provider'] + '/' + f['model'] for f in conf.get('fallbacks', [])]}" if "fallbacks" in conf else ""
            print(f"  • {role:22s} -> Provider: {conf['provider']:10s} | Model: {conf['model']}{fb_str}")
        print("=" * 65 + "\n", flush=True)
        return

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column(style="green")
    table.add_column(style="white")
    table.add_column(style="dim")
    for role, conf in role_map.items():
        fb_list = [f"{f['provider']}/{f['model']}" for f in conf.get("fallbacks", [])]
        fb_str = f"Fallbacks: {', '.join(fb_list)}" if fb_list else ""
        table.add_row(role, conf["provider"].upper(), conf["model"], fb_str)

    panel = Panel(
        table,
        title="[bold cyan]ACTIVE AGENT LLM CONFIGURATION[/bold cyan]",
        subtitle="[dim]Multi-Role Model Orchestration[/dim]",
        border_style="cyan",
        expand=False,
    )
    console.print()
    console.print(panel)


def log_triage_result(classification: str, conf_score: float, conf_level: str, is_exec: bool, conf_reason: str, summary: str) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"[Stage 1: Triage Router] Classification: '{classification.upper()}' | Confidence: {conf_score:.2f} ({conf_level}) | Executable: {is_exec}")
        print(f"[Stage 1: Triage Router] Reason: {conf_reason}")
        print(f"[Stage 1: Triage Router] Summary: {summary}")
        return

    tree = Tree(f"[bold cyan]Agent A2 Triage Classification:[/bold cyan] [bold white]{escape(classification.upper())}[/bold white]")
    tree.add(f"[dim]Confidence:[/dim]  {conf_score:.2f} ({conf_level}) | [dim]Executable:[/dim] {is_exec}")
    if conf_reason:
        tree.add(f"[dim]Reason:[/dim]      {escape(str(conf_reason))}")
    if summary and summary != "N/A":
        tree.add(f"[dim]Summary:[/dim]     {escape(str(summary))}")
    console.print(tree)


def log_info(tag: str, message: str) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"[{tag}] {message}")
    else:
        console.print(f"  [dim cyan][{escape(tag)}][/dim cyan] [dim white]{escape(str(message))}[/dim white]")


def log_warning(tag: str, message: str) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"[{tag} Warning] {message}")
    else:
        console.print(f"  [bold yellow][{escape(tag)} Warning][/bold yellow] [yellow]{escape(str(message))}[/yellow]")


def log_error(tag: str, message: str) -> None:
    if not RICH_AVAILABLE or console is None:
        print(f"[{tag} Error] {message}")
    else:
        console.print(f"  [bold red][{escape(tag)} Error][/bold red] [red]{escape(str(message))}[/red]")
