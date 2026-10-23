"""
Comprehensive Professional Documentation Generator for Elone_Agent / Elone_Execution.
Builds an executive, medium-low level Word Document (.docx) with embedded section flowcharts.
Reflects the exact 100% factual architecture (OKF Disk-based Knowledge Base, Master Catalog Indexing, Local Fast-Path, etc.).
"""

import os
import requests
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

DOCS_DIR = "docs"
ASSETS_DIR = os.path.join(DOCS_DIR, "assets")
OUTPUT_DOCX_PATH = os.path.join(DOCS_DIR, "ELONE_AGENT_SYSTEM_DOCUMENTATION.docx")

os.makedirs(ASSETS_DIR, exist_ok=True)

# -------------------------------------------------------------
# FACTUAL MERMAID DIAGRAM DEFINITIONS
# -------------------------------------------------------------

DIAGRAMS = {
    "high_level": """flowchart TD
    classDef startEnd fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef primary fill:#1e1b4b,stroke:#818cf8,stroke-width:2px,color:#f8fafc;
    classDef hitl fill:#450a0a,stroke:#f87171,stroke-width:2px,color:#f8fafc;
    classDef execution fill:#022c22,stroke:#34d399,stroke-width:2px,color:#f8fafc;
    classDef escalation fill:#3b0764,stroke:#c084fc,stroke-width:2px,color:#f8fafc;
    classDef success fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    START(["👤 User Support Ticket Ingress"]):::startEnd
    INTAKE["<b>1. Intake & Triage Agent</b><br/>• Asset Identification & Credentials Lookup<br/>• Allowed Software Policy Verification<br/>• Catalog Scanning (sops/index.md)"]:::primary
    PLANNER["<b>2. Discovery & Planning Agent</b><br/>• Progressive Disclosure Discovery (OKF Store)<br/>• Host Quirk & Reflection Memory Injection<br/>• 6-Stage Deep CoT Plan Synthesis"]:::primary
    HITL{"<b>3. Human-in-the-Loop Gate</b><br/>Plan Approval Required?"}:::hitl
    ORCH["<b>4. Orchestrator & Guardrails</b><br/>• Circuit Breakers (Max 3 Retries, 15 Steps)<br/>• Step Advancement & Fallback Swapping"]:::primary
    EXEC["<b>5. Execution Agent</b><br/>• Local Subprocess Fast-Path (0ms Overhead)<br/>• Remote SSH / WinRM Runner<br/>• API Identity Tools (Auth0, Okta, Mock)"]:::execution
    VERIFY{"<b>6. Output Verifier Agent</b><br/>• Fast Structural JSON & Regex Parser<br/>• Dynamic Variable Extraction<br/>Step Verdict: SUCCESS or RETRY?"}:::execution
    ESCALATE["<b>7. Escalation Agent (L2/L3)</b><br/>• Formats Structured Handover Payload<br/>• Diagnostic Traces & Root Cause Log"]:::escalation
    SUMM["<b>8. Summarization Agent</b><br/>• 3-Tier Resilient Report Generator<br/>• Customer Plain-Text Email Response<br/>• Internal Technical Markdown Summary<br/>• Episodic Memory Trace Saved to Disk"]:::success
    END_DONE(["✅ Ticket Resolved (FULLY_RESOLVED)"]):::startEnd
    END_ESC(["⚠️ Ticket Escalated (ESCALATED_L2)"]):::startEnd

    START --> INTAKE
    INTAKE -->|"Policy Approved & Valid Intent"| PLANNER
    INTAKE -->|"Unauthorized App / Unknown User"| ESCALATE
    PLANNER --> HITL
    HITL -->|"Initial Plan -> Requires Approval"| HITL_WAIT["⏸️ Operator Review in Web Console<br/>(Approve / Edit / Reject)"]:::hitl
    HITL_WAIT -->|"Operator Approved"| ORCH
    HITL_WAIT -->|"Operator Rejected"| ESCALATE
    HITL -->|"Auto-Continue (Approved / Retry / Next Step)"| ORCH
    ORCH -->|"Dispatch Next Step"| EXEC
    EXEC --> VERIFY
    VERIFY -->|"RETRY (Attempt < 3)"| ORCH
    VERIFY -->|"SUCCESS (More Steps Remain)"| ORCH
    VERIFY -->|"SUCCESS (All Steps Complete)"| SUMM
    VERIFY -->|"RETRY Budget Exhausted / Fatal Failure"| ESCALATE
    ESCALATE --> SUMM
    SUMM -->|"Workflow Status: Done"| END_DONE
    SUMM -->|"Workflow Status: Escalated"| END_ESC
""",

    "ingestion": """flowchart LR
    classDef storage fill:#172554,stroke:#3b82f6,stroke-width:2px,color:#f8fafc;
    classDef process fill:#022c22,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    DOCS[("Raw SOP Files<br/>_uploads/ & SharePoint<br/>.docx, .pdf, .txt, .xlsx")]:::storage
    SCHED["1. Ingestion Scheduler<br/>(ingestion_pipe/scheduler.py)<br/>Polls on configurable interval"]:::process
    CONV["2. JIT OKF Playbook Converter<br/>(elone_sop / converter.py)<br/>Extracts frontmatter, steps, parse rules"]:::process
    VAL["3. Faithfulness & Linkage Validator<br/>Validates parameter consistency"]:::process
    KB_STORE[("OKF Playbook Store<br/>knowledge_base/sops/{category}/*.md")]:::storage
    CATALOG[("Master Catalog Index<br/>knowledge_base/sops/index.md")]:::storage

    DOCS --> SCHED --> CONV --> VAL
    VAL --> KB_STORE
    VAL --> CATALOG
""",

    "server_streaming": """flowchart TD
    classDef client fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef server fill:#1e1b4b,stroke:#818cf8,stroke-width:2px,color:#f8fafc;
    classDef stream fill:#311042,stroke:#e879f9,stroke-width:2px,color:#f8fafc;

    UI["Operator Web Console (SPA UI)"]:::client
    POST_TICKET["POST /api/tickets<br/>Initializes SupportState & Run Thread"]:::server
    BG_WORKER["Background Execution Thread<br/>_stream_worker (Thread Run Registry)"]:::server
    GRAPH["LangGraph Execution Loop<br/>graph.stream(payload, updates)"]:::server
    SSE["SSE Endpoint (/stream)<br/>Emits: node_start, node, paused, done"]:::stream
    POST_APPROVE["POST /api/tickets/{id}/approve<br/>Sets is_human_approved=True"]:::server

    UI -->|"Submit Ticket"| POST_TICKET --> BG_WORKER --> GRAPH
    GRAPH -.->|"State Update Events"| BG_WORKER -.->|"Queue Payload"| SSE -.->|"Realtime Dashboard Render"| UI
    UI -->|"Approve Execution Plan"| POST_APPROVE --> BG_WORKER
""",

    "intake": """flowchart TD
    classDef process fill:#022c22,stroke:#10b981,stroke-width:2px,color:#f8fafc;
    classDef decision fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#f8fafc;
    classDef alert fill:#450a0a,stroke:#ef4444,stroke-width:2px,color:#f8fafc;

    RAW["Raw Ticket Input"]:::process
    ASSET["Asset Lookup & Enrichment<br/>(Asset Management - Sheet1.csv)"]:::process
    POLICY{"Software Allowed for User?<br/>(Allowed_Applications.csv)"}:::decision
    LLM_TRIAGE["LLM Intent & Entity Extraction<br/>(Mistral Small / Gemini Flash)"]:::process
    CATALOG_SCAN["Master Catalog Scanner<br/>(sops/index.md)"]:::process
    CONF_CHECK{"Triage Confidence >= 0.7<br/>& Complete Information?"}:::decision
    CLARIFY["Set workflow_status='need_clarification'<br/>Present Structured Prompt in UI"]:::alert
    ESCALATE_UNAUTH["Set catalog_permission_approved=False<br/>Route to Escalation"]:::alert
    GOTO_PLAN["Route to planner_agent"]:::process

    RAW --> ASSET --> POLICY
    POLICY -->|"Unauthorized / Policy Denied"| ESCALATE_UNAUTH
    POLICY -->|"Authorized Application"| LLM_TRIAGE
    LLM_TRIAGE --> CATALOG_SCAN --> CONF_CHECK
    CONF_CHECK -->|"Ambiguous / Missing Details"| CLARIFY
    CONF_CHECK -->|"Verified Intent & Confidence"| GOTO_PLAN
""",

    "planner": """flowchart TD
    classDef process fill:#022c22,stroke:#10b981,stroke-width:2px,color:#f8fafc;
    classDef storage fill:#172554,stroke:#3b82f6,stroke-width:2px,color:#f8fafc;
    classDef decision fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#f8fafc;

    INTENT["Verified Ticket Intent & Matched File Path"]:::process
    DISC["Progressive Disclosure Discovery<br/>1. Matched Path -> 2. Category Index -> 3. Global OKF Walk"]:::process
    MEM[("Host Reflection Rules & Device Quirks<br/>knowledge_base/patterns/hosts/{hostname}.md")]:::storage
    RULES[("SOP Reflection Rules<br/>knowledge_base/patterns/rules_{sop_id}.md")]:::storage
    COT["6-Stage Deep CoT Synthesis<br/>1. Data Understanding | 2. Gap Analysis<br/>3. Memory Injection | 4. Update Formulation<br/>5. Variable & Placeholder Binding ({hostname}, {executable})"]:::process
    VAL{"Deterministic Layer 1 Validator<br/>(validate_planner_execution_plan)"}:::decision
    VALID_PLAN["plan_valid = True<br/>Route to Orchestration"]:::process
    INVALID_PLAN["plan_valid = False<br/>validator_result = INVALID_PLAN"]:::process

    INTENT --> DISC
    DISC --> MEM
    DISC --> RULES
    MEM --> COT
    RULES --> COT
    COT --> VAL
    VAL -->|"Passed Linkage & Syntax"| VALID_PLAN
    VAL -->|"Missing Entities / Unbound"| INVALID_PLAN
""",

    "orchestration": """flowchart TD
    classDef decision fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#f8fafc;
    classDef process fill:#022c22,stroke:#10b981,stroke-width:2px,color:#f8fafc;
    classDef alert fill:#450a0a,stroke:#ef4444,stroke-width:2px,color:#f8fafc;

    ENTRY["Orchestrator Ingress"]:::process
    GUARD{"Escalation Guardrails & Circuit Breakers<br/>• is_human_rejected?<br/>• plan_valid == False?<br/>• Retries >= 3? | Total Steps >= 15?"}:::decision
    NEXT_ACT{"State next_action"}:::decision
    ALL_DONE{"current_step_index + 1<br/>>= total_steps?"}:::decision
    SWAP["Apply Fallback Command Swapping<br/>Increment execution_retry_attempts"]:::process
    ADVANCE["Increment current_step_index<br/>Reset retry count to 0"]:::process
    ROUTE_EXEC["Goto: execution_agent"]:::process
    ROUTE_ESC["Goto: escalation_agent"]:::alert
    ROUTE_SUMM["Goto: summarization_agent"]:::process

    ENTRY --> GUARD
    GUARD -->|"Guardrail Tripped"| ROUTE_ESC
    GUARD -->|"Within Budget"| NEXT_ACT

    NEXT_ACT -->|"SUCCESS"| ALL_DONE
    ALL_DONE -->|"Yes (All Steps Finished)"| ROUTE_SUMM
    ALL_DONE -->|"No (More Steps Remain)"| ADVANCE --> ROUTE_EXEC

    NEXT_ACT -->|"RETRY"| SWAP --> ROUTE_EXEC
    NEXT_ACT -->|"None (Initial Step 1)"| ROUTE_EXEC
""",

    "execution": """flowchart TD
    classDef decision fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#f8fafc;
    classDef process fill:#022c22,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    START_EXEC["Execution Step Trigger"]:::process
    PRECOND{"Evaluate execute_if Precondition<br/>(e.g. variables.app_running == true)"}:::decision
    SKIP["Skip Step<br/>next_action='SUCCESS'"]:::process
    TYPE{"Step Type"}:::decision
    LOCAL_CHECK{"Is Target Host<br/>Local Machine?"}:::decision
    LOCAL_RUN["Local Subprocess Fast-Path<br/>powershell.exe (0ms Overhead)"]:::process
    REMOTE_RUN["Remote Runner (Paramiko SSH / WinRM)<br/>with mDNS / .local resolution"]:::process
    TOOL_RUN["API Tool Runner<br/>(Auth0, Okta, Mock Admin, Solandra)"]:::process
    COMM_RUN["Communication Tool<br/>(send_email via SMTP)"]:::process
    FALLBACK_CHECK{"Exit Code != 0 and<br/>fallback_command exists?"}:::decision
    RUN_FALLBACK["Execute Step Fallback Command"]:::process
    OUT["Return stdout, stderr, exit_code<br/>to execution_result_agent"]:::process

    START_EXEC --> PRECOND
    PRECOND -->|"Condition False"| SKIP --> OUT
    PRECOND -->|"Condition True / None"| TYPE

    TYPE -->|"command"| LOCAL_CHECK
    TYPE -->|"tool_call"| TOOL_RUN --> OUT
    TYPE -->|"communication"| COMM_RUN --> OUT

    LOCAL_CHECK -->|"Yes (localhost / COMPUTERNAME)"| LOCAL_RUN --> FALLBACK_CHECK
    LOCAL_CHECK -->|"No (Remote IP / Workstation)"| REMOTE_RUN --> FALLBACK_CHECK

    FALLBACK_CHECK -->|"Yes"| RUN_FALLBACK --> OUT
    FALLBACK_CHECK -->|"No"| OUT
""",

    "verifier": """flowchart TD
    classDef decision fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#f8fafc;
    classDef process fill:#022c22,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    RAW_OUT["CLI stdout/stderr or API JSON Output"]:::process
    IS_JSON{"Is API Tool Call or<br/>Structured JSON stdout?"}:::decision
    FAST_JSON["Fast Structural JSON Parser (Sub-Millisecond)<br/>Direct scalar & nested array extraction"]:::process
    REMOVAL_CHECK{"Is Successful Deletion / Removal<br/>Verification Step?"}:::decision
    LLM_COT["LLM CoT Output Verifier<br/>(Evaluates output_parse_instruction rules)"]:::process
    VAR_EXT["Extract & Normalize Variables<br/>(snake_case dict in state.variables)"]:::process
    VERDICT["Assign Verdict (SUCCESS / RETRY / ESCALATE)<br/>Route to orchestration_agent"]:::process

    RAW_OUT --> IS_JSON
    IS_JSON -->|"Yes"| FAST_JSON --> VAR_EXT
    IS_JSON -->|"No"| REMOVAL_CHECK
    REMOVAL_CHECK -->|"Exit Code 0 / Verified Absent"| LLM_COT --> VAR_EXT
    VAR_EXT --> VERDICT
""",

    "summarization": """flowchart TD
    classDef decision fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#f8fafc;
    classDef process fill:#022c22,stroke:#10b981,stroke-width:2px,color:#f8fafc;
    classDef storage fill:#172554,stroke:#3b82f6,stroke-width:2px,color:#f8fafc;

    IN["Summarization Ingress<br/>(From Orchestrator or Escalation)"]:::process
    T1{"Tier 1: Structured Pydantic LLM<br/>(Gemini 2.5 Flash / Mistral Small)"}:::decision
    T2{"Tier 2: Raw JSON Block Parsing"}:::decision
    T3["Tier 3: Programmatic Rich Markdown Generator<br/>(Guaranteed 100% Fallback Reliability)"]:::process
    OUTS["Synthesize Reports:<br/>1. Plain Language Customer Email Reply<br/>2. Multi-Section Technical Markdown Summary"]:::process
    MEM[("Episodic Memory Logger<br/>knowledge_base/patterns/logs/YYYY-MM/category/ticket_XXX.md")]:::storage
    FINAL(["__end__ (Workflow Complete)"]):::process

    IN --> T1
    T1 -->|"Success"| OUTS
    T1 -->|"Fallback"| T2
    T2 -->|"Success"| OUTS
    T2 -->|"Fallback"| T3
    T3 --> OUTS
    OUTS --> MEM --> FINAL
"""
}


def download_diagram_pngs():
    """Renders and downloads PNGs for all Mermaid diagrams via Kroki API."""
    kroki_url = "https://kroki.io/mermaid/png"
    rendered_paths = {}

    for name, m_code in DIAGRAMS.items():
        png_path = os.path.join(ASSETS_DIR, f"flowchart_{name}.png")
        print(f"[...] Rendering diagram: {name}...")
        try:
            resp = requests.post(
                kroki_url,
                json={"diagram_source": m_code.strip(), "output_format": "png"},
                timeout=60
            )
            if resp.status_code == 200 and len(resp.content) > 500:
                with open(png_path, "wb") as f:
                    f.write(resp.content)
                rendered_paths[name] = png_path
                print(f"  -> Successfully saved: {png_path} ({len(resp.content)} bytes)")
            else:
                print(f"  -> Error rendering {name}: {resp.status_code} {resp.text[:100]}")
        except Exception as e:
            print(f"  -> Exception rendering {name}: {e}")

    return rendered_paths


# -------------------------------------------------------------
# DOCX STYLING HELPERS
# -------------------------------------------------------------

def set_cell_background(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def add_styled_heading(doc, text, level):
    h = doc.add_heading(text, level=level)
    h.paragraph_format.space_before = Pt(14)
    h.paragraph_format.space_after = Pt(6)
    for run in h.runs:
        run.font.name = "Segoe UI"
        if level == 1:
            run.font.size = Pt(18)
            run.font.bold = True
            run.font.color.rgb = RGBColor(15, 23, 42)  # Navy
        elif level == 2:
            run.font.size = Pt(14)
            run.font.bold = True
            run.font.color.rgb = RGBColor(30, 58, 138)  # Deep Blue
        elif level == 3:
            run.font.size = Pt(12)
            run.font.bold = True
            run.font.color.rgb = RGBColor(71, 85, 105)  # Slate
    return h

def add_callout(doc, text, title="KEY ARCHITECTURAL HIGHLIGHT", border_color="3B82F6", bg_color="F0F9FF"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=120, bottom=120, left=180, right=180)
    
    # Left border styling
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:top w:val="none"/><w:left w:val="single" w:sz="36" w:space="0" w:color="{border_color}"/><w:bottom w:val="none"/><w:right w:val="none"/></w:tcBorders>')
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    r_title = p.add_run(f"📌 {title}: ")
    r_title.font.name = "Segoe UI"
    r_title.font.bold = True
    r_title.font.size = Pt(10)
    r_title.font.color.rgb = RGBColor(30, 58, 138)
    
    r_text = p.add_run(text)
    r_text.font.name = "Segoe UI"
    r_text.font.size = Pt(9.5)
    r_text.font.color.rgb = RGBColor(51, 65, 85)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def add_table_data(doc, headers, rows):
    tbl = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False

    # Header row
    hdr_cells = tbl.rows[0].cells
    for i, title in enumerate(headers):
        hdr_cells[i].text = title
        set_cell_background(hdr_cells[i], "1E293B")
        set_cell_margins(hdr_cells[i], top=100, bottom=100, left=140, right=140)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for r in p.runs:
            r.font.name = "Segoe UI"
            r.font.bold = True
            r.font.size = Pt(9.5)
            r.font.color.rgb = RGBColor(255, 255, 255)

    # Data rows
    for r_idx, row_data in enumerate(rows):
        row_cells = tbl.rows[r_idx + 1].cells
        bg = "F8FAFC" if r_idx % 2 == 0 else "FFFFFF"
        for c_idx, val in enumerate(row_data):
            row_cells[c_idx].text = str(val)
            set_cell_background(row_cells[c_idx], bg)
            set_cell_margins(row_cells[c_idx], top=80, bottom=80, left=140, right=140)
            p = row_cells[c_idx].paragraphs[0]
            for r in p.runs:
                r.font.name = "Segoe UI"
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(51, 65, 85)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)


# -------------------------------------------------------------
# MAIN BUILDER FUNCTION
# -------------------------------------------------------------

def build_docx_documentation(rendered_images):
    doc = docx.Document()

    # Page Margins: 0.75 in
    for s in doc.sections:
        s.top_margin = Inches(0.75)
        s.bottom_margin = Inches(0.75)
        s.left_margin = Inches(0.75)
        s.right_margin = Inches(0.75)

    # Document Title Block
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(2)
    run_title = title_p.add_run("Elone_Agent Architecture & Technical Specification")
    run_title.font.name = "Segoe UI"
    run_title.font.size = Pt(24)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(15, 23, 42)

    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_before = Pt(0)
    sub_p.paragraph_format.space_after = Pt(14)
    run_sub = sub_p.add_run("Comprehensive End-to-End System Documentation & Flowchart Guide | Multi-Agent L1 Support Automation")
    run_sub.font.name = "Segoe UI"
    run_sub.font.size = Pt(11)
    run_sub.font.color.rgb = RGBColor(100, 116, 139)

    add_callout(
        doc,
        "Elone_Agent is a deterministic multi-agent IT automation system engineered on top of LangGraph, FastAPI, and Open Knowledge Framework (OKF) disk-based stores. "
        "It features dynamic LLM provider fallback routing (Mistral Small, Gemini 2.5 Flash, Groq GPT-OSS), zero-network-overhead local subprocess execution, "
        "cross-SOP referral swapping, human-in-the-loop (HITL) approval gates, and multi-tier summarization resilience.",
        title="SYSTEM OVERVIEW"
    )

    # =========================================================
    # SECTION 1: HIGH-LEVEL ARCHITECTURE & LIFECYCLE
    # =========================================================
    add_styled_heading(doc, "1. High-Level System Architecture & Execution Lifecycle", level=1)
    
    p = doc.add_paragraph(
        "The Elone_Agent ecosystem automates Level-1 (L1) helpdesk and IT support operations by ingesting standard operating procedures (SOPs), "
        "triaging user requests, dynamically binding execution parameters, running deterministic CLI commands and enterprise API tools, and generating "
        "comprehensive reports. The high-level lifecycle transitions through 8 distinct stages:"
    )
    p.paragraph_format.space_after = Pt(6)

    if "high_level" in rendered_images and os.path.exists(rendered_images["high_level"]):
        doc.add_picture(rendered_images["high_level"], width=Inches(6.8))
        cap = doc.add_paragraph("Figure 1.1: End-to-End High-Level System Lifecycle & Agent Coordination Flowchart")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].font.size = Pt(8.5)
        cap.runs[0].font.italic = True
        cap.paragraph_format.space_after = Pt(10)

    add_table_data(
        doc,
        ["Stage", "Module / Agent", "Core Responsibility", "Primary Technologies"],
        [
            ["1. Ingestion", "ingestion_pipe/scheduler.py", "Continuous SOP conversion & master catalog updating", "SharePoint, PyMuPDF, OKF Engine"],
            ["2. Ingress & Stream", "server.py & frontend/", "FastAPI REST API & live SSE background streaming", "FastAPI, Server-Sent Events, SPA UI"],
            ["3. Intake & Triage", "agents/intake/", "Asset credential lookup & security policy check", "Pandas/CSV, Mistral Small, Gemini"],
            ["4. Planning & CoT", "agents/planner/", "Progressive disclosure discovery, reflection lookup & 6-Stage Deep CoT", "OKF Knowledge Base, Jinja Binding"],
            ["5. HITL Gate", "graph.py & server.py", "Pre-execution operator review & seamless auto-continue", "LangGraph interrupt_before"],
            ["6. Execution", "agents/execution/", "Local fast-path, Remote SSH/WinRM, & API Tools", "Subprocess, Paramiko, PyWinRM, Auth0/Okta"],
            ["7. Result Verifier", "agents/execution_result/", "Fast JSON parsing, regex extraction & variable binding", "Regex, LLM Chain-of-Thought"],
            ["8. Summarization", "agents/summarization/", "Customer resolution email & engineering markdown log", "Pydantic, Gemini Flash, Episodic Memory"]
        ]
    )

    # =========================================================
    # SECTION 2: SOP INGESTION & KNOWLEDGE BASE PIPELINE
    # =========================================================
    add_styled_heading(doc, "2. SOP Ingestion & Knowledge Base Pipeline", level=1)
    doc.add_paragraph(
        "To eliminate manual playbook engineering, the ingestion engine monitors enterprise repositories (SharePoint / Shared Documents and local upload directories) "
        "for raw procedure documents (.docx, .pdf, .txt, .xlsx, .pptx). It automatically transforms raw procedures into standardized Open Knowledge Framework (OKF) playbooks "
        "and updates the master catalog index (knowledge_base/sops/index.md)."
    )

    if "ingestion" in rendered_images and os.path.exists(rendered_images["ingestion"]):
        doc.add_picture(rendered_images["ingestion"], width=Inches(6.8))
        cap = doc.add_paragraph("Figure 2.1: SOP Ingestion, Markdown Standardization & Catalog Indexing Pipeline")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].font.size = Pt(8.5)
        cap.runs[0].font.italic = True
        cap.paragraph_format.space_after = Pt(10)

    add_callout(
        doc,
        "OKF playbooks feature frontmatter metadata (sop_id, title, category, required_entities) and structured markdown steps containing "
        "executable shell commands, API tool calls, timeout specifications, execute_if preconditions, and output_parse_instructions.",
        title="OKF PLAYBOOK ARCHITECTURE"
    )

    add_table_data(
        doc,
        ["OKF Field", "Type", "Description", "Example Value"],
        [
            ["sop_id", "String", "Unique deterministic SOP identifier", "SOP-L1-APP-001"],
            ["step_type", "Enum", "Execution protocol: command, tool_call, communication", "command"],
            ["command", "String", "Deterministic shell command with Jinja placeholders", "tasklist | findstr /I {executable}"],
            ["execute_if", "String", "Dynamic runtime precondition evaluated before execution", "variables.app_running == true"],
            ["parse_instruction", "String", "Rule governing variable extraction & success verdict", "If stdout contains 'Code.exe', set variables.app_running = true"]
        ]
    )

    # =========================================================
    # SECTION 3: INGRESS, FASTAPI & STREAMING ENGINE
    # =========================================================
    add_styled_heading(doc, "3. FastAPI Server & Event Streaming Engine", level=1)
    doc.add_paragraph(
        "The application layer exposes a modern asynchronous REST API powered by FastAPI and a real-time web console. "
        "Execution runs within isolated background worker threads (Run instances), decoupling graph processing from HTTP request handlers."
    )

    if "server_streaming" in rendered_images and os.path.exists(rendered_images["server_streaming"]):
        doc.add_picture(rendered_images["server_streaming"], width=Inches(6.8))
        cap = doc.add_paragraph("Figure 3.1: FastAPI Background Thread Run Registry & SSE Event Streaming")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].font.size = Pt(8.5)
        cap.runs[0].font.italic = True
        cap.paragraph_format.space_after = Pt(10)

    add_table_data(
        doc,
        ["Endpoint", "Method", "Purpose", "Response Schema"],
        [
            ["/api/tickets", "POST", "Submit ticket and launch async graph execution thread", "{\"thread_id\": \"AGT-xxx\", \"done\": false}"],
            ["/api/tickets/{id}/stream", "GET", "Real-time Server-Sent Events (SSE) telemetry stream", "Event stream (node_start, node, paused, done)"],
            ["/api/tickets/{id}/approve", "POST", "Human operator approval of synthesized execution plan", "{\"is_human_approved\": true, \"thread_id\": ...}"],
            ["/api/tickets/{id}/reject", "POST", "Human operator rejection with escalation reason", "{\"workflow_status\": \"escalated\", ...}"],
            ["/api/tickets/{id}/clarify", "POST", "Submit clarification answers for ambiguous tickets", "{\"user_response\": \"...\", \"workflow_status\": ...}"]
        ]
    )

    # =========================================================
    # SECTION 4: INTAKE & TRIAGE AGENT
    # =========================================================
    add_styled_heading(doc, "4. Intake & Triage Agent Node", level=1)
    doc.add_paragraph(
        "The Intake Agent (agents/intake/node.py) serves as the security and classification gatekeeper for the system. "
        "Upon receiving raw ticket input, it cross-references identity records in Asset Management - Sheet1.csv, "
        "validates software against Allowed_Applications.csv, and performs catalog matching against sops/index.md."
    )

    if "intake" in rendered_images and os.path.exists(rendered_images["intake"]):
        doc.add_picture(rendered_images["intake"], width=Inches(6.8))
        cap = doc.add_paragraph("Figure 4.1: Intake Asset Lookup, Policy Enforcement & LLM Triage Decision Tree")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].font.size = Pt(8.5)
        cap.runs[0].font.italic = True
        cap.paragraph_format.space_after = Pt(10)

    add_callout(
        doc,
        "Security Guardrail: If an employee requests an unapproved application (cross-referenced with Allowed_Applications.csv) "
        "or if the caller's email cannot be found in Asset Management - Sheet1.csv, the agent sets catalog_permission_approved=False "
        "and immediately flags the ticket for L2 escalation without running arbitrary commands.",
        title="POLICY COMPLIANCE GATE"
    )

    # =========================================================
    # SECTION 5: UNIFIED PLANNER & DISCOVERY AGENT
    # =========================================================
    add_styled_heading(doc, "5. Unified Planner & Discovery Agent Node", level=1)
    doc.add_paragraph(
        "The Planner Agent (agents/planner/node.py) constructs an executable, host-tailored plan from the retrieved OKF playbook. "
        "It leverages progressive disclosure discovery across category index files and global OKF markdown traversal, "
        "integrates host reflection memory (patterns/hosts/{hostname}.md), and performs 6-Stage Deep CoT placeholder binding."
    )

    if "planner" in rendered_images and os.path.exists(rendered_images["planner"]):
        doc.add_picture(rendered_images["planner"], width=Inches(6.8))
        cap = doc.add_paragraph("Figure 5.1: Progressive Disclosure Discovery & 6-Stage Deep CoT Assembly")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].font.size = Pt(8.5)
        cap.runs[0].font.italic = True
        cap.paragraph_format.space_after = Pt(10)

    add_table_data(
        doc,
        ["Stage", "Name", "CoT Analysis Focus"],
        [
            ["Stage 1", "Data Understanding", "Analyzes ticket intent, category, and target environment (Windows/Linux)."],
            ["Stage 2", "Gap & Delta Analysis", "Identifies required placeholders ({entities.hostname}, {entities.executable})."],
            ["Stage 3", "Memory Pattern Analysis", "Retrieves host-specific quirks and verified recovery rules from patterns/hosts/."],
            ["Stage 4", "Update Formulation", "Adjusts timeouts, step descriptions, and error detection rules."],
            ["Stage 5", "Final Verification", "Deterministic Python validation of syntax and entity linkage before execution."]
        ]
    )

    # =========================================================
    # SECTION 6: ORCHESTRATION AGENT & GUARDRAILS
    # =========================================================
    add_styled_heading(doc, "6. Orchestration Agent & Circuit Breakers", level=1)
    doc.add_paragraph(
        "Acting as the central traffic controller, the Orchestration Agent (agents/orchestration/node.py) enforces strict circuit breakers, "
        "handles step-level retries with fallback swapping, advances steps on SUCCESS, and triggers cross-SOP referrals."
    )

    if "orchestration" in rendered_images and os.path.exists(rendered_images["orchestration"]):
        doc.add_picture(rendered_images["orchestration"], width=Inches(6.8))
        cap = doc.add_paragraph("Figure 6.1: Orchestration State Machine & Circuit Breaker Guardrails")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].font.size = Pt(8.5)
        cap.runs[0].font.italic = True
        cap.paragraph_format.space_after = Pt(10)

    add_callout(
        doc,
        "Circuit Breaker Guardrails: (1) Step Retry Limit: A step is permitted a maximum of 3 retries before escalation. "
        "(2) Execution Budget: A ticket cannot exceed 15 total step executions. (3) Deterministic Swapping: On retry, "
        "the orchestrator automatically substitutes fallback_command into the execution plan.",
        title="CIRCUIT BREAKER SPECIFICATION"
    )

    # =========================================================
    # SECTION 7: EXECUTION AGENT & MULTI-PROTOCOL RUNNER
    # =========================================================
    add_styled_heading(doc, "7. Execution Agent & Multi-Protocol Command Runner", level=1)
    doc.add_paragraph(
        "The Execution Agent (agents/execution/node.py) deterministically executes commands and API tools across local workstations and remote endpoints. "
        "It features intelligent protocol routing and elevation detection."
    )

    if "execution" in rendered_images and os.path.exists(rendered_images["execution"]):
        doc.add_picture(rendered_images["execution"], width=Inches(6.8))
        cap = doc.add_paragraph("Figure 7.1: Multi-Protocol Command Runner (Local Fast-Path vs Remote SSH/WinRM vs API)")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].font.size = Pt(8.5)
        cap.runs[0].font.italic = True
        cap.paragraph_format.space_after = Pt(10)

    add_table_data(
        doc,
        ["Target Destination", "Protocol / Mechanism", "Latency / Performance", "Features"],
        [
            ["Local Machine (matches COMPUTERNAME)", "Native subprocess.run", "0ms Network Overhead", "Runs native powershell.exe with scheduled task elevation for system tools"],
            ["Remote Windows/Linux Workstation", "Paramiko SSH (Port 22)", "Standard Network RTT", "Automatic mDNS (.local) resolution and credential authentication"],
            ["Remote Windows Lab Workstation", "PyWinRM HTTP (Port 5985)", "Standard Network RTT", "NTLM / Basic authentication support with UTF-8 encoding configuration"],
            ["Identity & Cloud Tools", "REST API Client", "< 100ms API Latency", "Auth0, Okta, Mock Admin Console, and Solandra API integrations"]
        ]
    )

    # =========================================================
    # SECTION 8: EXECUTION RESULT VERIFIER & EXTRACTOR
    # =========================================================
    add_styled_heading(doc, "8. Execution Result Verifier & Variable Extractor", level=1)
    doc.add_paragraph(
        "The Execution Result Agent (agents/execution_result/node.py) analyzes execution output (stdout, stderr, exit code). "
        "It dynamically extracts runtime variables and evaluates conditional parse instructions."
    )

    if "verifier" in rendered_images and os.path.exists(rendered_images["verifier"]):
        doc.add_picture(rendered_images["verifier"], width=Inches(6.8))
        cap = doc.add_paragraph("Figure 8.1: Fast Structural JSON Parsing & LLM Output Analysis Pipeline")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].font.size = Pt(8.5)
        cap.runs[0].font.italic = True
        cap.paragraph_format.space_after = Pt(10)

    add_callout(
        doc,
        "Hybrid Verification Architecture: For API JSON responses, structural dictionary lookups complete in < 1ms with 0 token cost. "
        "For complex CLI output with conditional parse rules, a Chain-of-Thought LLM analysis extracts snake_case state variables "
        "(e.g., PIDs, IPs, status flags) and determines the next_action verdict (SUCCESS, RETRY, or ESCALATE).",
        title="HYBRID EXTRACTION ARCHITECTURE"
    )

    # =========================================================
    # SECTION 9: ESCALATION & SUMMARIZATION AGENTS
    # =========================================================
    add_styled_heading(doc, "9. Escalation & 3-Tier Summarization Agents", level=1)
    doc.add_paragraph(
        "The terminal phase of the workflow synthesizes user communication and engineering reports while updating episodic memory on disk."
    )

    if "summarization" in rendered_images and os.path.exists(rendered_images["summarization"]):
        doc.add_picture(rendered_images["summarization"], width=Inches(6.8))
        cap = doc.add_paragraph("Figure 9.1: 3-Tier Resilient Summarization & Episodic Memory Logging")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].font.size = Pt(8.5)
        cap.runs[0].font.italic = True
        cap.paragraph_format.space_after = Pt(10)

    add_table_data(
        doc,
        ["Summarization Tier", "Mechanism", "Resilience & Fallback Behavior"],
        [
            ["Tier 1: Structured Pydantic LLM", "ChatGoogleGenerativeAI (Gemini 2.5 Flash)", "Direct schema-enforced output generating customer reply and engineering markdown."],
            ["Tier 2: Raw JSON Parsing", "Fallback LLM Invoke", "Extracts JSON blocks using regular expressions if structured schema binding fails."],
            ["Tier 3: Programmatic Fallback", "Deterministic Python Generator", "100% reliable programmatic fallback that guarantees a formatted customer email and technical report."]
        ]
    )

    # =========================================================
    # SECTION 10: STATE SCHEMA & DATA CONTRACTS
    # =========================================================
    add_styled_heading(doc, "10. SupportState Schema & Data Contracts", level=1)
    doc.add_paragraph(
        "The LangGraph workflow communicates through a centralized SupportState dictionary defined in shared/state.py. "
        "Key state fields across all agent nodes include:"
    )

    add_table_data(
        doc,
        ["State Key", "Type", "Scope", "Description"],
        [
            ["ticket_raw", "String", "Global", "Raw incoming customer problem statement."],
            ["entities", "Dict[str, str]", "Global", "Extracted entities (email, hostname, executable, username)."],
            ["variables", "Dict[str, Any]", "Dynamic", "Runtime variables extracted by execution_result_agent."],
            ["execution_plan", "Dict[str, Any]", "Planner", "Bound execution steps with commands and parse rules."],
            ["current_step_index", "Integer", "Orchestrator", "0-based index of the currently executing plan step."],
            ["execution_retry_attempts", "Integer", "Orchestrator", "Active retry count for current step (max 3)."],
            ["is_human_approved", "Boolean", "HITL", "Tracks operator plan approval across graph iterations."],
            ["workflow_status", "String", "Global", "Lifecycle status: pending, in_progress, completed, escalated, need_clarification."],
            ["customer_ticket_reply", "String", "Summarizer", "Plain-language resolution email sent to end user."],
            ["internal_ticket_summary", "String", "Summarizer", "Comprehensive Markdown engineering diagnostic report."]
        ]
    )

    # Save document
    try:
        doc.save(OUTPUT_DOCX_PATH)
        print(f"\n=======================================================")
        print(f"[SUCCESS] Complete System Documentation generated!")
        print(f"File Path: {OUTPUT_DOCX_PATH}")
        print(f"=======================================================\n")
    except PermissionError:
        alt_path = os.path.join(DOCS_DIR, "ELONE_AGENT_SYSTEM_DOCUMENTATION_UPDATED.docx")
        doc.save(alt_path)
        print(f"\n=======================================================")
        print(f"[NOTE] Original file was locked (likely open in Word). Saved to alternate path:")
        print(f"File Path: {alt_path}")
        print(f"=======================================================\n")

if __name__ == "__main__":
    images = download_diagram_pngs()
    build_docx_documentation(images)
