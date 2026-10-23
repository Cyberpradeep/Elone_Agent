import os
import re
import json
import base64
import requests
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

MERMAID_DIAGRAM = """flowchart TD
    classDef inputNode fill:#EBF3FB,stroke:#1B365D,stroke-width:2px,color:#1B365D;
    classDef gateNode fill:#FFF8E7,stroke:#D97706,stroke-width:2px,color:#92400E;
    classDef parseNode fill:#F0FDF4,stroke:#16A34A,stroke-width:2px,color:#166534;
    classDef llmNode fill:#F5F3FF,stroke:#7C3AED,stroke-width:2px,color:#5B21B6;
    classDef valNode fill:#FEF2F2,stroke:#DC2626,stroke-width:2px,color:#991B1B;
    classDef successNode fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46;
    classDef rejectNode fill:#FFF1F2,stroke:#E11D48,stroke-width:2px,color:#9F1239;

    subgraph PHASE1 [PHASE 1: INGESTION TRIGGER AND PRE-CHECKS]
        Upload["Raw SOP Document Upload<br/>.pdf, .docx, .csv, .xlsx, .txt"]:::inputNode
        Scheduler["Scheduler Polling Worker<br/>knowledge_base/_uploads/"]:::inputNode
        
        Upload --> Gate1["GATE 1: Pre-Ingestion File Validator<br/>core/input_validator.py"]:::gateNode
        Scheduler --> Gate1
        
        Gate1 --> CheckExt{"1. Allowed Extension?<br/>.pdf, .docx, .csv, .xlsx, .txt"}
        CheckExt -->|No| RejectExt["Reject: Unsupported Format"]:::rejectNode
        CheckExt -->|Yes| CheckMagic{"2. Magic-Bytes Valid?<br/>Reject .exe or .dll disguised as doc"}
        
        CheckMagic -->|No or Spoofed| RejectMagic["Reject: File Spoofing Detected"]:::rejectNode
        CheckMagic -->|Yes| CheckSize{"3. Size and Page Caps?<br/>Max 10MB, 10 Pages, 5000 Words"}
        
        CheckSize -->|Exceeded| RejectSize["Reject: Size or Page Cap Exceeded"]:::rejectNode
        CheckSize -->|Yes| CheckZip{"4. Zip Bomb Ratio?<br/>Max 50MB uncompressed, ratio max 20x"}
        
        CheckZip -->|Decompression Bomb| RejectZip["Reject: Bomb or Memory Threat"]:::rejectNode
    end

    subgraph PHASE2 [PHASE 2: DOCUMENT-ORDER EXTRACTION AND DATA ENRICHMENT]
        CheckZip -->|Passed All Pre-Checks| DocParser["Document Parser and Physical Walk<br/>core/document_parser.py"]:::parseNode
        
        DocParser --> StreamText["Stream 1: Ordered Text Segments"]
        DocParser --> StreamImg["Stream 2: Embedded Screenshots and Images"]
        DocParser --> StreamLink["Stream 3: External Web Hyperlinks"]
        
        StreamText --> Gate2["GATE 2: Text and DLP Sanitizer<br/>Mask Passwords, API Keys, Emails<br/>Strip Zero-Width Unicode and BiDi Overrides"]:::gateNode
        
        StreamImg --> Gate3["GATE 3: VLM Vision Security<br/>Pixel Bomb Cap Max 4096px<br/>Downscale to 1024px JPEG Anti-Bloat<br/>Vision LLM extracts UI labels OCR"]:::gateNode
        
        StreamLink --> Gate4["GATE 4: SSRF and Web Quarantine<br/>Scrape cache to disk Max 4KB<br/>Excluded from direct prompt Anti-Injection"]:::gateNode
        
        Gate2 --> Splicer["Ordered Context Splicer<br/>Interleaves Text and Vision Reports"]:::parseNode
        Gate3 --> Splicer
        Gate4 -.-> Splicer
    end

    subgraph PHASE3 [PHASE 3: JIT CONVERTER AGENT AND REASONING]
        Splicer --> TriageRouter["Stage 1: Triage Router LLM<br/>gemini-2.5-flash or mistral-small<br/>Inspects dynamic platform tools"]:::llmNode
        
        TriageRouter --> TriageDecision{"Classification Paradigm?"}
        TriageDecision -->|unactionable| InformationalExit["Stage 1 Early Exit:<br/>Save Informational Metadata"]:::rejectNode
        
        TriageDecision -->|command| CmdPrompt["Select COMMAND_COT_PROMPT<br/>Pure PowerShell Focus"]:::llmNode
        TriageDecision -->|tool_call| ToolPrompt["Select TOOL_COT_PROMPT<br/>Cloud and REST API Focus"]:::llmNode
        TriageDecision -->|hybrid| HybridPrompt["Select HYBRID_COT_PROMPT<br/>PowerShell and API Focus"]:::llmNode
        
        CmdPrompt --> PromptSandbox["GATE 5: Prompt Sandboxing<br/>Wrap in untrusted_document_payload<br/>Escape closing XML delimiter tags<br/>Enforce passive data contract"]:::gateNode
        ToolPrompt --> PromptSandbox
        HybridPrompt --> PromptSandbox
        
        PromptSandbox --> ConverterLLM["Converter Agent LLM<br/>gemini-2.5-flash or mistral-small<br/>Executes 6-Stage CoT Reasoning"]:::llmNode
        
        ConverterLLM --> CandidateJSON["Generated Candidate OKF Playbook JSON"]:::inputNode
    end

    subgraph PHASE4 [PHASE 4: DUAL-LAYER VALIDATION AND GUARDRAILS]
        CandidateJSON --> Layer1["GATE 6.1: Deterministic AST and Blacklist Scan<br/>core/plan_validator.py<br/>Check empty or placeholder steps<br/>Verify required_entities consistency<br/>Ban LOLBins: certutil, bitsadmin, mshta<br/>Ban Encoded PowerShell: -enc<br/>Ban backdoor user creation: net user /add<br/>Double-quote variable placeholders"]:::valNode
        
        Layer1 --> Layer1Check{"Layer 1 Passed?"}
        
        Layer1Check -->|No| RetryLoop["Auto-Retry Controller<br/>Up to 3 Retry Attempts<br/>Injects specific error feedback"]:::rejectNode
        RetryLoop -->|Feed Error Directives| PromptSandbox
        
        Layer1Check -->|Yes| Layer2["GATE 6.2: LLM Faithfulness and Injection Audit<br/>mistral-small-latest<br/>100% Action and tool recall inspection<br/>Hallucination and fabrication detection<br/>Adversarial prompt injection scan<br/>Confidence scoring: High >= 0.85"]:::valNode
        
        Layer2 --> Layer2Check{"Layer 2 Passed?"}
        Layer2Check -->|No or Injection Detected| RetryLoop
    end

    subgraph PHASE5 [PHASE 5: CRYPTOGRAPHIC INTEGRITY AND STORAGE]
        Layer2Check -->|PASSED - 1.00 High| Gate7["GATE 7: Storage Sandbox and Integrity<br/>SOP ID alphanumeric whitelist slugging<br/>Embed HMAC-SHA256 digital stamp<br/>Auto-init Reflection Rulebook: patterns/<br/>Write audit log: tokens, latency, cost"]:::gateNode
        
        Gate7 --> FinalPlaybook["VERIFIED EXECUTABLE OKF PLAYBOOK<br/>knowledge_base/sops/category/SOP-ID.md<br/>Ready for live Execution Dispatcher"]:::successNode
    end
"""

def generate_interactive_html():
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Elone JIT SOP Ingestion Pipeline — Interactive Low-Level Flowchart</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #0F172A;
            color: #E2E8F0;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
        }}
        header {{
            background: linear-gradient(135deg, #1E293B, #0F172A);
            border-bottom: 1px solid #334155;
            padding: 14px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10;
        }}
        .title-group h1 {{
            font-size: 18px;
            font-weight: 700;
            color: #F8FAFC;
            letter-spacing: -0.02em;
        }}
        .title-group p {{
            font-size: 12px;
            color: #94A3B8;
            margin-top: 2px;
        }}
        .controls {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .btn {{
            background: #334155;
            color: #F8FAFC;
            border: 1px solid #475569;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 4px;
        }}
        .btn:hover {{
            background: #475569;
            border-color: #64748B;
        }}
        .btn-primary {{
            background: #2563EB;
            border-color: #3B82F6;
        }}
        .btn-primary:hover {{
            background: #1D4ED8;
        }}
        #canvas-container {{
            flex: 1;
            position: relative;
            background: radial-gradient(circle, #1E293B 1px, #0F172A 1px);
            background-size: 24px 24px;
            overflow: hidden;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        #mermaid-wrapper {{
            width: 100%;
            height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        .mermaid {{
            width: 100%;
            height: 100%;
        }}
        .legend {{
            position: absolute;
            bottom: 20px;
            left: 20px;
            background: rgba(30, 41, 59, 0.9);
            backdrop-filter: blur(8px);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 12px 16px;
            font-size: 11px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            z-index: 5;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .legend-color {{
            width: 14px;
            height: 14px;
            border-radius: 3px;
            border: 1px solid rgba(255,255,255,0.2);
        }}
    </style>
</head>
<body>
    <header>
        <div class="title-group">
            <h1>Elone JIT SOP Ingestion Pipeline — Low-Level Architecture Flowchart</h1>
            <p>Interactive Pan & Zoom Visualizer | Pre-Ingestion, DLP, Prompt Sandboxing, Dual-Layer Validation & Storage</p>
        </div>
        <div class="controls">
            <button class="btn" onclick="zoomIn()">➕ Zoom In</button>
            <button class="btn" onclick="zoomOut()">➖ Zoom Out</button>
            <button class="btn" onclick="resetZoom()">🔄 Reset View</button>
            <button class="btn btn-primary" onclick="fitView()">⛶ Fit Screen</button>
        </div>
    </header>

    <div id="canvas-container">
        <div id="mermaid-wrapper">
            <div class="mermaid" id="flowchart-svg">
{MERMAID_DIAGRAM}
            </div>
        </div>

        <div class="legend">
            <div style="font-weight: 700; color: #F8FAFC; margin-bottom: 2px;">Pipeline Stage Legend</div>
            <div class="legend-item"><div class="legend-color" style="background: #EBF3FB; border-color: #1B365D;"></div> <span>Ingestion Upload / Input</span></div>
            <div class="legend-item"><div class="legend-color" style="background: #FFF8E7; border-color: #D97706;"></div> <span>Security Gate / Sanitizer</span></div>
            <div class="legend-item"><div class="legend-color" style="background: #F0FDF4; border-color: #16A34A;"></div> <span>Parser / Extraction Stream</span></div>
            <div class="legend-item"><div class="legend-color" style="background: #F5F3FF; border-color: #7C3AED;"></div> <span>AI Reasoning & LLM Conversion</span></div>
            <div class="legend-item"><div class="legend-color" style="background: #FEF2F2; border-color: #DC2626;"></div> <span>Validation & Security Guardrail</span></div>
            <div class="legend-item"><div class="legend-color" style="background: #ECFDF5; border-color: #059669;"></div> <span>Verified Playbook Output</span></div>
        </div>
    </div>

    <script>
        let panZoomInstance = null;

        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            flowchart: {{
                useMaxWidth: false,
                htmlLabels: true,
                curve: 'basis'
            }}
        }});

        window.addEventListener('load', function() {{
            setTimeout(() => {{
                const svgElement = document.querySelector('#mermaid-wrapper svg');
                if (svgElement) {{
                    svgElement.style.width = '100%';
                    svgElement.style.height = '100%';
                    panZoomInstance = svgPanZoom(svgElement, {{
                        zoomEnabled: true,
                        controlIconsEnabled: false,
                        fit: true,
                        center: true,
                        minZoom: 0.2,
                        maxZoom: 10,
                        zoomScaleSensitivity: 0.3
                    }});
                }}
            }}, 800);
        }});

        function zoomIn() {{ if (panZoomInstance) panZoomInstance.zoomIn(); }}
        function zoomOut() {{ if (panZoomInstance) panZoomInstance.zoomOut(); }}
        function resetZoom() {{ if (panZoomInstance) {{ panZoomInstance.resetZoom(); panZoomInstance.center(); }} }}
        function fitView() {{ if (panZoomInstance) {{ panZoomInstance.fit(); panZoomInstance.center(); }} }}
    </script>
</body>
</html>
"""
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "INGESTION_PIPELINE_INTERACTIVE_FLOWCHART.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[SUCCESS] Interactive Flowchart HTML saved to: {html_path}")
    return html_path

def update_markdown_documentation():
    md_content = f"""# Complete Low-Level Ingestion Pipeline Flowchart & Architecture

---

## 1. Native Interactive Mermaid Diagram

```mermaid
{MERMAID_DIAGRAM}
```

---

## 2. Interactive Browser App
You can open [`INGESTION_PIPELINE_INTERACTIVE_FLOWCHART.html`](../INGESTION_PIPELINE_INTERACTIVE_FLOWCHART.html) in your browser for a **full-screen interactive experience with Pan, Zoom, and Stage Highlighting**.
"""
    docs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    md_path = os.path.join(docs_dir, "INGESTION_PIPELINE_LOW_LEVEL_FLOWCHART.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[SUCCESS] Markdown Flowchart saved to: {md_path}")

def build_flowchart_docx():
    """Builds a dedicated, standalone Word document containing the visual flowchart image, low-level stage descriptions, and interactive links."""
    img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_base", "logs", "images", "ingestion_pipeline_flowchart.png")
    docx_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SOP_Ingestion_Low_Level_Flowchart_Architecture.docx")
    
    doc = Document()
    
    for s in doc.sections:
        s.top_margin = Inches(0.7)
        s.bottom_margin = Inches(0.7)
        s.left_margin = Inches(0.75)
        s.right_margin = Inches(0.75)
        
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_after = Pt(2)
    r = p_title.add_run("SOP Ingestion Pipeline — Low-Level Architecture Flowchart")
    r.font.name = "Calibri"
    r.font.size = Pt(20)
    r.bold = True
    r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    
    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_after = Pt(10)
    r_sub = p_sub.add_run("Complete End-to-End Decision Flow, Security Gates, Retry Loops & Validation Lifecycle")
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(11)
    r_sub.font.color.rgb = RGBColor(0x55, 0x6B, 0x82)
    
    # Metadata table
    meta_tbl = doc.add_table(rows=3, cols=2)
    meta_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_data = [
        ("Diagram Type:", "Interactive Mermaid Architectural Flowchart (High-Resolution Vector Render)"),
        ("Lifecycle Scope:", "Pre-Ingestion → Multimodal Parsing → Triage → JIT Conversion → Dual Validation → Storage"),
        ("Interactive Viewer:", "Open INGESTION_PIPELINE_INTERACTIVE_FLOWCHART.html for Full Pan & Zoom in Browser")
    ]
    for i, (k, v) in enumerate(meta_data):
        row = meta_tbl.rows[i]
        c1, c2 = row.cells[0], row.cells[1]
        c1.width = Inches(1.8)
        c2.width = Inches(4.7)
        set_cell_background(c1, "F4F6F9")
        set_cell_background(c2, "FAFCFD")
        set_cell_margins(c1, 30, 30, 70, 70)
        set_cell_margins(c2, 30, 30, 70, 70)
        p1, p2 = c1.paragraphs[0], c2.paragraphs[0]
        p1.paragraph_format.space_after = Pt(0)
        p2.paragraph_format.space_after = Pt(0)
        r1 = p1.add_run(k)
        r1.bold = True
        r1.font.size = Pt(8.5)
        r1.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
        r2 = p2.add_run(v)
        r2.font.size = Pt(8.5)
        r2.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        
    set_table_borders(meta_tbl, color="D0D7DE", sz="4")
    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    
    # Flowchart Visual
    if os.path.exists(img_path):
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img.paragraph_format.space_after = Pt(4)
        doc.add_picture(img_path, width=Inches(6.8))
        
        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_after = Pt(10)
        r_cap = p_cap.add_run("Figure 1: Complete Ingestion Pipeline Flowchart (Pre-Checks, Splicer, Reasoning, Guardrails & Retry Loops)")
        r_cap.font.name = "Calibri"
        r_cap.font.size = Pt(8.5)
        r_cap.font.italic = True
        r_cap.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        
    doc.save(docx_path)
    print(f"[SUCCESS] Standalone Flowchart Word Document saved to: {docx_path}")

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

if __name__ == "__main__":
    generate_interactive_html()
    update_markdown_documentation()
    build_flowchart_docx()
