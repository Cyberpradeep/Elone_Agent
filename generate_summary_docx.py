import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def set_cell_background(cell, fill_hex):
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=140, right=140):
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)

def set_table_borders(table, color="D0D7DE", sz="4", val="single"):
    tblPr = table._element.xpath('w:tblPr')
    if tblPr:
        borders = parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            f'<w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:insideV w:val="none"/>'
            f'<w:left w:val="none"/>'
            f'<w:right w:val="none"/>'
            f'</w:tblBorders>'
        )
        tblPr[0].append(borders)

def build_summary_doc():
    doc = Document()
    
    for s in doc.sections:
        s.top_margin = Inches(0.75)
        s.bottom_margin = Inches(0.75)
        s.left_margin = Inches(0.8)
        s.right_margin = Inches(0.8)
        
    # Title
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_after = Pt(2)
    r = p_title.add_run("SOP Ingestion Pipeline — Security Summary Guide")
    r.font.name = "Calibri"
    r.font.size = Pt(20)
    r.bold = True
    r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    
    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_after = Pt(12)
    r_sub = p_sub.add_run("A Simple, Intent-Based Guide: What Security is Implemented, What it Does, and When it Works")
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(11)
    r_sub.font.color.rgb = RGBColor(0x55, 0x6B, 0x82)
    
    # Overview
    p_intro = doc.add_paragraph()
    p_intro.paragraph_format.space_after = Pt(10)
    p_intro.paragraph_format.line_spacing = 1.15
    p_intro.add_run(
        "This guide outlines the 10 security defenses implemented in the Elone SOP Ingestion Pipeline. "
        "Every defense is explained in simple terms: what it is, what threat it stops, and the exact pipeline stage where it runs."
    ).font.size = Pt(10)

    # 10 Security Items
    items = [
        ("1. Zip Bomb & Decompression Guard (check_zip_bomb)",
         "A pre-flight safety check for Word (.docx) and Excel (.xlsx) files.",
         "Stops Zip Bombs (tiny 50 KB documents crafted to explode into 20+ GB in RAM, crashing the server process). Enforces max 50 MB uncompressed and max 20x compression ratio.",
         "Stage 1 (Pre-Ingestion): Runs immediately upon file upload before reading document content."),
         
        ("2. Filename & Path Sanitizer (sanitize_filename & sanitize_slug)",
         "A path cleaner that strips directory traversal sequences.",
         "Stops Directory Traversal attacks (e.g. naming files ../../../../System32/file.docx to overwrite critical operating system files).",
         "On Upload & On Playbook Save: Cleans incoming file names and outgoing SOP IDs."),
         
        ("3. Zero-Width & Invisible Character Cleaner (clean_unicode_and_zero_width)",
         "A text filter that strips invisible zero-width unicode spaces.",
         "Stops attackers from hiding invisible spaces inside dangerous commands (e.g. n[invisible]e[invisible]t user /add) to sneak past keyword filters.",
         "Stage 2 (Text Extraction): Runs the moment text is extracted from PDFs or Word documents."),
         
        ("4. Data Loss Prevention / DLP Masker (redact_sensitive_dlp)",
         "A real-time secret and personal privacy mask.",
         "Replaces real default passwords (Welcome@2026!), API keys (sk-proj-...), employee emails, and phones with safe placeholders like [DLP_REDACTED_PASSWORD] and [DLP_REDACTED_EMAIL].",
         "Stage 2 (Pre-AI Dispatch): Runs before text is sent to external AI models or written to disk logs."),
         
        ("5. Shannon Entropy Secret Hunter (calculate_shannon_entropy)",
         "A mathematical randomness scanner.",
         "Detects proprietary or custom API keys that lack standard prefixes like 'sk-'. If a 24+ character string has high mathematical randomness (>4.2), it is masked as an API key.",
         "Stage 2 (During DLP Scan): Runs automatically during text sanitization before the AI call."),
         
        ("6. Image & Pixel Bomb Guard (validate_and_sanitize_image_bytes)",
         "An image dimension validator and automatic image compressor.",
         "Rejects Pixel Bombs (> 4,096 pixels) that cause Out-of-Memory crashes, and downscales large screenshots to 1,024 pixels (max 5 images per SOP) to stop token bloat.",
         "Stage 2 (Image Extraction): Runs whenever an inline screenshot is extracted, before calling Vision AI."),
         
        ("7. Web Scraper Firewall / SSRF Blocker (is_safe_external_url)",
         "A network firewall for hyperlinks found inside SOP documents.",
         "Stops Server-Side Request Forgery (SSRF). Resolves DNS and strictly blocks links to cloud password vaults (169.254.169.254), localhost (127.0.0.1), and private corporate LANs.",
         "Stage 2 (Link Scraping): Runs right before the scraper initiates any network HTTP connection."),
         
        ("8. Prompt Sandbox Delimiter Escaper (escape_prompt_delimiters)",
         "An XML tag escaper for AI prompt envelopes.",
         "Stops Prompt Injection Delimiter Breakouts. Converts closing tags (</untrusted_document_payload>) into safe entities (&lt;...&gt;), trapping hostile instructions inside the data container.",
         "Stage 3 (Prompt Assembly): Runs right before the prompt payload is sent to Gemini or Mistral."),
         
        ("9. Command Injection Double-Quote Enforcer (enforce_entity_double_quotes)",
         "A syntax corrector for generated PowerShell commands.",
         "Prevents command splitting injection. If a user passes an application name like 'calc.exe & del C:\\*', double-quoting forces PowerShell to treat it as a single literal string argument.",
         "Stage 4 (Layer 1 Validation): Runs immediately when inspecting candidate PowerShell commands."),
         
        ("10. Playbook Tamper-Proof Digital Stamp (compute_playbook_hmac & verify_playbook_hmac)",
         "A cryptographic digital wax seal (HMAC-SHA256) embedded in YAML frontmatter.",
         "Detects post-approval file tampering. If someone secretly alters a command on disk, the digital signature fails to match and execution is aborted immediately.",
         "When Saving & When Running: Stamped when saving to disk, verified before execution.")
    ]

    for title, concept, does, when in items:
        h = doc.add_heading(level=2)
        r = h.add_run(title)
        r.font.name = "Calibri"
        r.font.size = Pt(12)
        r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
        
        tbl = doc.add_table(rows=3, cols=2)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_table_borders(tbl, color="D0D7DE", sz="4")
        
        row_data = [
            ("Concept:", concept),
            ("What It Does:", does),
            ("When It Works:", when)
        ]
        
        for idx, (lbl, val) in enumerate(row_data):
            row = tbl.rows[idx]
            c1, c2 = row.cells[0], row.cells[1]
            c1.width = Inches(1.5)
            c2.width = Inches(5.0)
            set_cell_background(c1, "F4F6F9")
            set_cell_background(c2, "FAFCFD")
            set_cell_margins(c1, 30, 30, 70, 70)
            set_cell_margins(c2, 30, 30, 70, 70)
            p1, p2 = c1.paragraphs[0], c2.paragraphs[0]
            p1.paragraph_format.space_after = Pt(0)
            p2.paragraph_format.space_after = Pt(0)
            r1 = p1.add_run(lbl)
            r1.bold = True
            r1.font.size = Pt(8.5)
            r1.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
            r2 = p2.add_run(val)
            r2.font.size = Pt(8.5)
            r2.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
            
        doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # Summary Table
    h_sum = doc.add_heading(level=1)
    r_sum = h_sum.add_run("Summary Reference Table")
    r_sum.font.name = "Calibri"
    r_sum.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    
    summary_tbl = doc.add_table(rows=11, cols=3)
    summary_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(summary_tbl, color="D0D7DE", sz="4")
    
    headers = ["Security Defense", "Threat Prevented", "Pipeline Timing"]
    hdr_row = summary_tbl.rows[0]
    for i, h_text in enumerate(headers):
        cell = hdr_row.cells[i]
        set_cell_background(cell, "1B365D")
        set_cell_margins(cell, 40, 40, 70, 70)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(h_text)
        r.bold = True
        r.font.size = Pt(8.5)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        
    summary_rows = [
        ("1. Zip Bomb Guard", "RAM exhaustion / server freeze", "Stage 1: Pre-Ingestion upload"),
        ("2. Path Sanitizer", "Overwriting server system files", "Upload & Playbook save stages"),
        ("3. Zero-Width Cleaner", "Sneaking banned commands past filters", "Stage 2: Text extraction"),
        ("4. DLP Masker", "Leaking passwords, emails, API keys to AI", "Stage 2: Pre-AI dispatch"),
        ("5. Shannon Entropy", "Unlabeled or custom secret keys", "Stage 2: During DLP text scan"),
        ("6. Image Bomb Guard", "Pixel bombs & excessive vision token costs", "Stage 2: Image extraction & OCR"),
        ("7. SSRF Link Blocker", "Cloud credential theft & intranet attacks", "Stage 2: Before fetching any URL"),
        ("8. Sandbox Escaper", "Prompt injection container breakout", "Stage 3: AI prompt assembly"),
        ("9. Quote Enforcer", "Variable-based command splitting injection", "Stage 4: Layer 1 AST validation"),
        ("10. HMAC Digital Seal", "Secretly modifying approved playbooks", "When saving & before running")
    ]
    
    for idx, (c1_txt, c2_txt, c3_txt) in enumerate(summary_rows, 1):
        row = summary_tbl.rows[idx]
        bg = "F9FAFB" if idx % 2 == 1 else "FFFFFF"
        for c_i, val in enumerate([c1_txt, c2_txt, c3_txt]):
            cell = row.cells[c_i]
            set_cell_background(cell, bg)
            set_cell_margins(cell, 30, 30, 70, 70)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(val)
            r.font.size = Pt(8.0)
            if c_i == 0:
                r.bold = True
                r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
            else:
                r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SOP_Ingestion_Security_Summary.docx")
    doc.save(out_path)
    print(f"[SUCCESS] Security Summary Word document saved to: {out_path}")
    return out_path

if __name__ == "__main__":
    build_summary_doc()
