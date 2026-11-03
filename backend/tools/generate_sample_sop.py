"""
Generate Professional Enterprise SOP (.docx)
==============================================
Creates a realistic enterprise SOP in Word format (.docx) with complete metadata:
- Document Owner, Author, Reviewer
- Preconditions, Objective, Process Flow
- Step-by-step CLI commands & diagnostic checks
- Escalation criteria & Document Control table
"""

import os
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    """Sets background shading of a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tc_pr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Sets internal padding for a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tc_pr.append(tc_mar)

def create_sop_docx(output_path: str):
    doc = docx.Document()

    # Set page margins (1 inch)
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

        # Header & Footer
        footer = section.footer
        f_p = footer.paragraphs[0]
        f_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        f_run = f_p.add_run("IT Service Desk — Confidential / Internal Use Only")
        f_run.font.size = Pt(8.5)
        f_run.font.color.rgb = RGBColor(128, 128, 128)

    # ---------------------------------------------------------------------------
    # Document Header Box (Metadata Block)
    # ---------------------------------------------------------------------------
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(4)
    run_sop_id = title_p.add_run("SOP-L1-APP-003\n")
    run_sop_id.font.size = Pt(13)
    run_sop_id.font.bold = True
    run_sop_id.font.color.rgb = RGBColor(0, 51, 102)

    run_title = title_p.add_run("Software Application Cache and Credential Vault Reset")
    run_title.font.size = Pt(18)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(30, 30, 30)

    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_before = Pt(2)
    sub_p.paragraph_format.space_after = Pt(12)
    run_sub = sub_p.add_run("STANDARD OPERATING PROCEDURE  |  Endpoint Support → Application Management")
    run_sub.font.size = Pt(9.5)
    run_sub.font.bold = True
    run_sub.font.color.rgb = RGBColor(100, 100, 100)

    # Metadata Quick Table
    meta_table = doc.add_table(rows=5, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_table.autofit = False

    meta_data = [
        ("SOP ID", "SOP-L1-APP-003"),
        ("Category", "Endpoint Support / Application Management"),
        ("Document Owner", "Marcus Vance <marcus.vance@corp.example>"),
        ("Author", "Sarah Jenkins <sarah.jenkins@corp.example>"),
        ("Effective Date", "01-Nov-2026 (Review Date: 31-Dec-2026 | Version: 1.0)"),
    ]

    for row_idx, (k, v) in enumerate(meta_data):
        row = meta_table.rows[row_idx]
        cell_k, cell_v = row.cells[0], row.cells[1]
        cell_k.width = Inches(2.2)
        cell_v.width = Inches(4.3)
        set_cell_background(cell_k, "F2F4F7")
        set_cell_background(cell_v, "FFFFFF")
        set_cell_margins(cell_k, top=60, bottom=60, left=100, right=100)
        set_cell_margins(cell_v, top=60, bottom=60, left=100, right=100)

        p_k = cell_k.paragraphs[0]
        p_k.paragraph_format.space_before = Pt(1)
        p_k.paragraph_format.space_after = Pt(1)
        r_k = p_k.add_run(k)
        r_k.font.bold = True
        r_k.font.size = Pt(9.5)
        r_k.font.color.rgb = RGBColor(50, 50, 50)

        p_v = cell_v.paragraphs[0]
        p_v.paragraph_format.space_before = Pt(1)
        p_v.paragraph_format.space_after = Pt(1)
        r_v = p_v.add_run(v)
        r_v.font.size = Pt(9.5)
        r_v.font.color.rgb = RGBColor(30, 30, 30)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ---------------------------------------------------------------------------
    # Table of Contents
    # ---------------------------------------------------------------------------
    toc_head = doc.add_paragraph()
    r_toc = toc_head.add_run("Table of Contents")
    r_toc.font.bold = True
    r_toc.font.size = Pt(12)
    r_toc.font.color.rgb = RGBColor(0, 51, 102)

    toc_items = [
        "1. Objective",
        "2. Preconditions",
        "3. Process Flow Overview",
        "4. Detailed Procedure",
        "    • Step 1 — Verify Endpoint Connectivity",
        "    • Step 2 — Inspect Target Application Process Status",
        "    • Step 3 — Forcibly Terminate Hanging Application Process",
        "    • Step 4 — Clear Corrupted Application Cache and Temp Store",
        "    • Step 5 — Restart Application Background Service",
        "    • Step 6 — Verify Service Operational Status",
        "    • Step 7 — Validate Resolution with End User",
        "    • Step 8 — Update Ticket and Document Root Cause",
        "5. Escalation Criteria",
        "6. Document Control",
    ]
    for item in toc_items:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.left_indent = Inches(0.2)
        r = p.add_run(item)
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(70, 70, 70)

    doc.add_page_break()

    # ---------------------------------------------------------------------------
    # 1. Objective
    # ---------------------------------------------------------------------------
    h1 = doc.add_paragraph()
    r = h1.add_run("1. Objective")
    r.font.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor(0, 51, 102)

    p_obj = doc.add_paragraph(
        "This standard operating procedure describes the authorized technical workflow to diagnose and resolve "
        "application launch hangs, corrupted local cache locks, and frozen credential states on Windows endpoints. "
        "When an approved business application fails to start due to orphaned lockfiles or damaged local profiles, "
        "the L1 Support Engineer or automation agent safely terminates lingering processes, purges transient cache, "
        "and recycles the background helper service to restore standard application performance."
    )
    p_obj.paragraph_format.space_after = Pt(10)

    # ---------------------------------------------------------------------------
    # 2. Preconditions
    # ---------------------------------------------------------------------------
    h2 = doc.add_paragraph()
    r = h2.add_run("2. Preconditions")
    r.font.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor(0, 51, 102)

    preconditions = [
        "Ticket is assigned to an authorized L1 Service Desk Engineer or autonomous support agent.",
        "Remote PowerShell or WinRM access is enabled on the target Windows endpoint.",
        "Target client device is online and reachable on the corporate network or VPN.",
        "Local administrative privileges are available for command execution.",
        "The application in question is an approved corporate software package.",
    ]
    for prec in preconditions:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(prec)
        r.font.size = Pt(10)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ---------------------------------------------------------------------------
    # 3. Process Flow Overview
    # ---------------------------------------------------------------------------
    h3 = doc.add_paragraph()
    r = h3.add_run("3. Process Flow Overview")
    r.font.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor(0, 51, 102)

    p_flow = doc.add_paragraph(
        "The diagram below outlines the remediation lifecycle. All diagnostic and modifying steps must follow "
        "the sequential order specified in Section 4:\n\n"
        "[1. Connectivity Check] → [2. Process Inspection] → [3. Safe Termination] → "
        "[4. Cache Clearance] → [5. Service Restart] → [6. Health Verification] → [7. User Sign-Off]"
    )
    p_flow.paragraph_format.space_after = Pt(10)

    # ---------------------------------------------------------------------------
    # 4. Detailed Procedure
    # ---------------------------------------------------------------------------
    h4 = doc.add_paragraph()
    r = h4.add_run("4. Detailed Procedure")
    r.font.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor(0, 51, 102)

    steps_data = [
        {
            "num": "STEP 1",
            "title": "Verify Endpoint Network Connectivity",
            "desc": "Confirm target client endpoint is reachable over ICMP/WinRM before executing remote administrative tasks.",
            "cmd": "Test-Connection \"{{entities.hostname}}\" -Count 2",
            "expected": "Expected Result: Reply received with 0% packet loss from target system.",
            "fallback": "If unreachable: Check VPN connectivity and device status. Escalate if offline.",
        },
        {
            "num": "STEP 2",
            "title": "Inspect Target Application Process Status",
            "desc": "Check if orphaned or hung process threads for the application are currently running in the background.",
            "cmd": "Get-Process -Name \"{{entities.application}}\" -ErrorAction SilentlyContinue",
            "expected": "Expected Result 1: Process object returned (process is running or hung). Proceed to Step 3.\nExpected Result 2: Process not found. Proceed directly to Step 4.",
            "fallback": None,
        },
        {
            "num": "STEP 3",
            "title": "Forcibly Terminate Hanging Application Process",
            "desc": "Terminate all hanging or non-responsive process threads to release file locks on local application profile directories.",
            "cmd": "Stop-Process -Name \"{{entities.application}}\" -Force",
            "expected": "Expected Result: Process terminated without error. Exit code 0.",
            "fallback": "Alternative fallback command: taskkill /F /IM \"{{entities.application}}.exe\"",
        },
        {
            "num": "STEP 4",
            "title": "Clear Corrupted Application Cache and Temp Store",
            "desc": "Purge temporary cache files and lockfiles from the user's local application data directory to resolve corrupted launch states.",
            "cmd": "Remove-Item -Path \"C:\\Users\\{{entities.username}}\\AppData\\Local\\{{entities.application}}\\Cache\\*\" -Recurse -Force",
            "expected": "Expected Result: Cache directory cleared. Lockfiles successfully removed.",
            "fallback": "If files remain locked: Confirm all sub-processes are terminated, then re-execute.",
        },
        {
            "num": "STEP 5",
            "title": "Restart Application Background Service",
            "desc": "Restart the local application service daemon to re-initialize configuration files and network listeners.",
            "cmd": "Restart-Service -Name \"{{entities.application}}_Service\" -Force",
            "expected": "Expected Result: Service status changes to 'Running'.",
            "fallback": "If service fails to restart: Check Windows Event Log (Application) for error details.",
        },
        {
            "num": "STEP 6",
            "title": "Verify Service Operational Status",
            "desc": "Confirm the background service is actively running and responsive after the restart.",
            "cmd": "Get-Service -Name \"{{entities.application}}_Service\"",
            "expected": "Expected Result: Status = 'Running', StartType = 'Automatic'.",
            "fallback": "If status is not 'Running': Trigger L2 Application Support escalation.",
        },
        {
            "num": "STEP 7",
            "title": "Validate Resolution with End User",
            "desc": "Contact the end user and request that they launch the target application to verify normal operation.",
            "cmd": None,
            "expected": "Expected Result:\n• Application launches successfully without freezing or crashing.\n• User confirms normal operational performance.\n• No error dialogs or licensing alerts displayed.",
            "fallback": "If application still fails to start: Proceed to Section 5, Escalation Criteria.",
        },
        {
            "num": "STEP 8",
            "title": "Update Ticket and Document Root Cause",
            "desc": "Record remediation details in the ITSM ticket and mark incident as resolved.",
            "cmd": None,
            "expected": "Resolution Notes:\nIssue: Application launch freeze and local cache lock.\nRoot Cause: Orphaned background thread held stale lockfile in local AppData cache.\nAction Taken: Terminated lingering processes, cleared local cache, recycled background service.\nStatus: Resolved.",
            "fallback": None,
        },
    ]

    for s in steps_data:
        p_step = doc.add_paragraph()
        p_step.paragraph_format.space_before = Pt(8)
        p_step.paragraph_format.space_after = Pt(2)
        r_step = p_step.add_run(f"{s['num']}  —  {s['title']}")
        r_step.font.bold = True
        r_step.font.size = Pt(11)
        r_step.font.color.rgb = RGBColor(0, 51, 102)

        p_desc = doc.add_paragraph(s["desc"])
        p_desc.paragraph_format.space_before = Pt(1)
        p_desc.paragraph_format.space_after = Pt(3)

        if s["cmd"]:
            # Command Box Table
            cmd_table = doc.add_table(rows=1, cols=1)
            cmd_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            cell = cmd_table.rows[0].cells[0]
            cell.width = Inches(6.5)
            set_cell_background(cell, "F7F9FA")
            set_cell_margins(cell, top=60, bottom=60, left=120, right=120)

            p_cmd = cell.paragraphs[0]
            p_cmd.paragraph_format.space_before = Pt(1)
            p_cmd.paragraph_format.space_after = Pt(1)
            r_cmd = p_cmd.add_run(s["cmd"])
            r_cmd.font.name = "Consolas"
            r_cmd.font.size = Pt(9.5)
            r_cmd.font.bold = True
            r_cmd.font.color.rgb = RGBColor(30, 30, 30)

        p_exp = doc.add_paragraph()
        p_exp.paragraph_format.space_before = Pt(3)
        p_exp.paragraph_format.space_after = Pt(2)
        r_exp = p_exp.add_run(s["expected"])
        r_exp.font.size = Pt(9.5)
        r_exp.font.italic = True
        r_exp.font.color.rgb = RGBColor(60, 60, 60)

        if s.get("fallback"):
            p_fb = doc.add_paragraph()
            p_fb.paragraph_format.space_before = Pt(1)
            p_fb.paragraph_format.space_after = Pt(4)
            r_fb = p_fb.add_run(s["fallback"])
            r_fb.font.size = Pt(9.0)
            r_fb.font.color.rgb = RGBColor(120, 60, 0)

    doc.add_page_break()

    # ---------------------------------------------------------------------------
    # 5. Escalation Criteria
    # ---------------------------------------------------------------------------
    h5 = doc.add_paragraph()
    r = h5.add_run("5. Escalation Criteria")
    r.font.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor(0, 51, 102)

    p_esc_intro = doc.add_paragraph("Escalate to Tier 2 Application Engineering or Desktop Systems if:")
    p_esc_intro.paragraph_format.space_after = Pt(2)

    esc_items = [
        "Target client device is completely unreachable after network and VPN verification.",
        "Access is denied when terminating process threads or deleting cache files (permission error).",
        "The background application service fails to start or crashes repeatedly upon start.",
        "Application continues to crash or display corruption errors after cache reset.",
        "Application event log records database corruption or missing DLL dependencies.",
        "User profile is corrupted requiring full local profile rebuild.",
    ]
    for item in esc_items:
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(item)
        r.font.size = Pt(10)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ---------------------------------------------------------------------------
    # 6. Document Control
    # ---------------------------------------------------------------------------
    h6 = doc.add_paragraph()
    r = h6.add_run("6. Document Control")
    r.font.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor(0, 51, 102)

    doc_ctrl_table = doc.add_table(rows=9, cols=2)
    doc_ctrl_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    doc_ctrl_table.autofit = False

    ctrl_data = [
        ("SOP ID", "SOP-L1-APP-003"),
        ("Title", "Software Application Cache and Credential Vault Reset"),
        ("Category", "Endpoint Support → Application Management"),
        ("Support Level", "L1 Service Desk"),
        ("Document Owner", "Marcus Vance <marcus.vance@corp.example>"),
        ("Author", "Sarah Jenkins <sarah.jenkins@corp.example>"),
        ("Reviewer", "David Chen <david.chen@corp.example>"),
        ("Version", "1.0"),
        ("Status", "Approved for use"),
    ]

    for row_idx, (attr, val) in enumerate(ctrl_data):
        row = doc_ctrl_table.rows[row_idx]
        cell_a, cell_v = row.cells[0], row.cells[1]
        cell_a.width = Inches(2.2)
        cell_v.width = Inches(4.3)
        set_cell_background(cell_a, "F2F4F7")
        set_cell_background(cell_v, "FFFFFF")
        set_cell_margins(cell_a, top=60, bottom=60, left=100, right=100)
        set_cell_margins(cell_v, top=60, bottom=60, left=100, right=100)

        p_a = cell_a.paragraphs[0]
        p_a.paragraph_format.space_before = Pt(1)
        p_a.paragraph_format.space_after = Pt(1)
        r_a = p_a.add_run(attr)
        r_a.font.bold = True
        r_a.font.size = Pt(9.5)
        r_a.font.color.rgb = RGBColor(50, 50, 50)

        p_v = cell_v.paragraphs[0]
        p_v.paragraph_format.space_before = Pt(1)
        p_v.paragraph_format.space_after = Pt(1)
        r_v = p_v.add_run(val)
        r_v.font.size = Pt(9.5)
        r_v.font.color.rgb = RGBColor(30, 30, 30)

    # Save to disk
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
    print(f"[SUCCESS] SOP .docx created at: {output_path}")

if __name__ == "__main__":
    out_dir = r"D:\Projects\Elone\Elone_Agent\knowledge_base\_uploads"
    out_file = os.path.join(out_dir, "sop_software_application_cache_reset.docx")
    create_sop_docx(out_file)

