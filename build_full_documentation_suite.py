import os
import re
import json
import base64
import time
import requests
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE_DIR, "knowledge_base", "logs", "images")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(DOCS_DIR, exist_ok=True)

# =============================================================================
# 1. DEFINITION OF ALL 7 MERMAID DIAGRAMS
# =============================================================================

DIAGRAM_MASTER = """flowchart TD
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

DIAGRAM_SEC1 = """flowchart TD
    classDef inputNode fill:#EBF3FB,stroke:#1B365D,stroke-width:2px,color:#1B365D;
    classDef gateNode fill:#FFF8E7,stroke:#D97706,stroke-width:2px,color:#92400E;
    classDef parseNode fill:#F0FDF4,stroke:#16A34A,stroke-width:2px,color:#166534;
    classDef rejectNode fill:#FFF1F2,stroke:#E11D48,stroke-width:2px,color:#9F1239;

    RawUpload["Uploaded Raw SOP File<br/>knowledge_base/_uploads/"]:::inputNode
    
    RawUpload --> InValidator["Input Validator Engine<br/>core/input_validator.py"]:::gateNode
    
    InValidator --> Step1{"Check 1: File Extension<br/>.pdf, .docx, .csv, .xlsx, .txt"}
    Step1 -->|Disallowed| Rej1["Reject: Unauthorized Extension"]:::rejectNode
    
    Step1 -->|Valid| Step2{"Check 2: Magic-Byte Header<br/>Verify Real Signature vs Spoof"}
    Step2 -->|Disguised Executable| Rej2["Reject: Binary Executable / Spoof"]:::rejectNode
    
    Step2 -->|Valid| Step3{"Check 3: Hard Size & Page Limits<br/>Max 10MB, Max 10 Pages, Max 5000 Words"}
    Step3 -->|Exceeded| Rej3["Reject: Exceeds Size or Page Quota"]:::rejectNode
    
    Step3 -->|Valid| Step4{"Check 4: Decompression Bomb Ratio<br/>Max 50MB uncompressed, ratio max 20x"}
    Step4 -->|Bomb Detected| Rej4["Reject: Decompression Bomb Threat"]:::rejectNode
    
    Step4 -->|All Passed| ParserDispatch["Physical-Order Document Parser<br/>core/document_parser.py"]:::parseNode
    
    ParserDispatch --> Fork1["Stream 1: Text Segments<br/>DLP Secret Masking and Unicode Normalization"]:::parseNode
    ParserDispatch --> Fork2["Stream 2: Inline Images<br/>VLM Vision OCR & Label Extraction"]:::parseNode
    ParserDispatch --> Fork3["Stream 3: URLs<br/>Quarantined Cache Extraction"]:::parseNode
    
    Fork1 --> Splicer["Ordered Multimodal Splicer<br/>Interleaves Text and Vision in Physical Order"]:::inputNode
    Fork2 --> Splicer
    Fork3 -.-> Splicer
"""

DIAGRAM_SEC2 = """flowchart TD
    classDef inputNode fill:#EBF3FB,stroke:#1B365D,stroke-width:2px,color:#1B365D;
    classDef llmNode fill:#F5F3FF,stroke:#7C3AED,stroke-width:2px,color:#5B21B6;
    classDef gateNode fill:#FFF8E7,stroke:#D97706,stroke-width:2px,color:#92400E;
    classDef successNode fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46;
    classDef rejectNode fill:#FFF1F2,stroke:#E11D48,stroke-width:2px,color:#9F1239;

    InputText["Sanitized Physical-Order Document Text"]:::inputNode
    
    InputText --> Stage1["STAGE 1: TRIAGE ROUTER LLM<br/>gemini-2.5-flash / mistral-small"]:::llmNode
    Stage1 --> ToolInspection["Dynamic Tool Catalog Probing<br/>list_available_platforms and get_platform_tools"]:::gateNode
    
    ToolInspection --> Paradigm{"Classify Paradigm"}
    Paradigm -->|unactionable| Exit1["Early Exit: Informational Policy Only"]:::rejectNode
    Paradigm -->|command| Cmd["Select COMMAND_COT_PROMPT<br/>Windows PowerShell Focus"]:::llmNode
    Paradigm -->|tool_call| Tool["Select TOOL_COT_PROMPT<br/>API Tool Functions Focus"]:::llmNode
    Paradigm -->|hybrid| Hyb["Select HYBRID_COT_PROMPT<br/>PowerShell + API Tool Calls"]:::llmNode
    
    Cmd --> Sandbox["Prompt Isolation Envelope<br/>untrusted_document_payload"]:::gateNode
    Tool --> Sandbox
    Hyb --> Sandbox
    
    Sandbox --> ConverterLLM["STAGE 2: CONVERTER AGENT<br/>Executes 6-Stage Command CoT Mandate"]:::llmNode
    
    ConverterLLM --> CoT1["Stage 1: OS and Shell Assignment powershell"]
    CoT1 --> CoT2["Stage 2: Diagnostic-First Sequencing"]
    CoT2 --> CoT3["Stage 3: Dynamic Entity Scoping entities.*"]
    CoT3 --> CoT4["Stage 4: stdout Parse Planning variables.*"]
    CoT4 --> CoT5["Stage 5: Conditional Remediation execute_if"]
    CoT5 --> CoT6["Stage 6: Human and GUI Noise Omission"]
    
    CoT6 --> OutputJSON["Generated Candidate OKF Playbook JSON"]:::successNode
"""

DIAGRAM_SEC3 = """flowchart TD
    classDef valNode fill:#FEF2F2,stroke:#DC2626,stroke-width:2px,color:#991B1B;
    classDef llmNode fill:#F5F3FF,stroke:#7C3AED,stroke-width:2px,color:#5B21B6;
    classDef retryNode fill:#FFF1F2,stroke:#E11D48,stroke-width:2px,color:#9F1239;
    classDef passNode fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46;

    CandidatePlan["Candidate OKF Playbook Steps JSON"]
    
    CandidatePlan --> L1["LAYER 1: Deterministic AST & Blacklist Scan<br/>core/plan_validator.py (< 1ms)"]:::valNode
    
    L1 --> CheckL1{"Layer 1 Checks Passed?<br/>• Non-empty commands<br/>• Entity consistency<br/>• Banned LOLBins: certutil, bitsadmin<br/>• Banned Encoded scripts: -enc<br/>• Banned Backdoors: net user /add"}
    
    CheckL1 -->|AST Failed| RetryCtrl["Auto-Retry Controller<br/>Attempt Counter <= 3"]:::retryNode
    RetryCtrl -->|Inject Specific Error Directives| ConverterRetry["Converter Agent Regeneration"]:::llmNode
    ConverterRetry --> L1
    
    CheckL1 -->|AST Passed| L2["LAYER 2: LLM Faithfulness & Injection Audit<br/>mistral-small-latest (temp=0)"]:::llmNode
    
    L2 --> CheckL2{"6-Point CoT Faithfulness Audit<br/>1. 100% Action Recall<br/>2. 0 Hallucinated Tools<br/>3. Parameter Accuracy<br/>4. Executability Verification<br/>5. Adversarial Injection Scan<br/>6. Confidence Score >= 0.85"}
    
    CheckL2 -->|Audit Failed or Injected| RetryCtrl
    CheckL2 -->|PASSED - 1.00 High| Approved["VERIFIED APPROVED PLAYBOOK"]:::passNode
"""

DIAGRAM_SEC4 = """flowchart TD
    classDef successNode fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46;
    classDef gateNode fill:#FFF8E7,stroke:#D97706,stroke-width:2px,color:#92400E;
    classDef storageNode fill:#EBF3FB,stroke:#1B365D,stroke-width:2px,color:#1B365D;

    Approved["Approved Playbook Data Structure"]:::successNode
    
    Approved --> SlugSanitize["SOP ID Sanitization<br/>Whitelist Alphanumeric Slug: re.sub r'[^A-Za-z0-9_-]'"]:::gateNode
    
    SlugSanitize --> HMACSign["HMAC-SHA256 Cryptographic Signature<br/>Generates Tamper-Proof Digital Stamp"]:::gateNode
    
    HMACSign --> MarkdownSynth["Playbook Markdown File Generation<br/>knowledge_base/sops/category/SOP-ID.md<br/>YAML Frontmatter + Execution Steps"]:::storageNode
    
    MarkdownSynth --> RulebookInit["Auto-Initialize Reflection Rulebook<br/>knowledge_base/patterns/category/rules_SOP-ID.md<br/>Runtime Error Learning Matrix"]:::storageNode
    
    RulebookInit --> ManifestUpdate["Update Manifest and Token Telemetry<br/>knowledge_base/manifest.json"]:::storageNode
    
    ManifestUpdate --> Ready["Production Ready for Live Execution Dispatcher"]:::successNode
"""

DIAGRAM_SEC5 = """flowchart TD
    classDef llmNode fill:#F5F3FF,stroke:#7C3AED,stroke-width:2px,color:#5B21B6;
    classDef monitorNode fill:#FFF8E7,stroke:#D97706,stroke-width:2px,color:#92400E;
    classDef successNode fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46;

    TaskRequest["Pipeline Task Request<br/>(triage / converter / validator / vision)"]
    
    TaskRequest --> RoleMapper["Role-to-Provider Router<br/>config/llm_config.py"]:::llmNode
    
    RoleMapper --> QuotaCheck["Daily Quota and Token Monitor<br/>gemini_monitor/monitor.py"]:::monitorNode
    
    QuotaCheck --> ModelDispatch{"Target Role?"}
    
    ModelDispatch -->|execution_planning| Gemini["Primary: gemini-2.5-flash<br/>Fallback: mistral-small-latest"]:::llmNode
    ModelDispatch -->|planning_validation| Mistral["Primary: mistral-small-latest<br/>Fallback: NVIDIA AI Endpoints"]:::llmNode
    ModelDispatch -->|vlm_vision| Vision["Primary: nvidia/nemotron-vision<br/>Fallback: gemini-2.5-flash"]:::llmNode
    
    Gemini --> Telemetry["Record Call Telemetry<br/>Input/Output Tokens, Latency, Execution Cost"]:::monitorNode
    Mistral --> Telemetry
    Vision --> Telemetry
    
    Telemetry --> LogSummary["Full Debug Log and Daily Cost Accounting<br/>knowledge_base/logs/debug/"]:::successNode
"""

DIAGRAM_SEC6 = """flowchart TD
    classDef gateNode fill:#FFF8E7,stroke:#D97706,stroke-width:2px,color:#92400E;
    classDef valNode fill:#FEF2F2,stroke:#DC2626,stroke-width:2px,color:#991B1B;
    classDef successNode fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46;

    RawData["Untrusted Inbound Data Stream<br/>(Documents, Screenshots, Web Links)"]
    
    RawData --> DLP["Gate A: Real-Time DLP Secret Redactor<br/>Masks Passwords, API Keys, Employee PII"]:::gateNode
    
    DLP --> SSRF["Gate B: SSRF Link Scraper Defense<br/>Blocks 169.254.169.254 and RFC1918 Private IPs"]:::gateNode
    
    SSRF --> PromptIso["Gate C: Delimiter Sandboxing Envelope<br/>untrusted_document_payload XML Isolation"]:::gateNode
    
    PromptIso --> Guardrails["Gate D: Deterministic AST Blacklist<br/>Blocks LOLBins, Encoded Scripts, Backdoors"]:::valNode
    
    Guardrails --> MistralAudit["Gate E: Layer 2 Adversarial Injection Audit<br/>Mistral Small 3 Verification"]:::valNode
    
    MistralAudit --> OWASPCompliance["FULL OWASP TOP 10 FOR LLM COMPLIANCE<br/>(LLM01 - LLM10 Fully Enforced)"]:::successNode
"""

ALL_DIAGRAMS = {
    "flowchart_master.png": DIAGRAM_MASTER,
    "flowchart_sec1_ingestion.png": DIAGRAM_SEC1,
    "flowchart_sec2_converter.png": DIAGRAM_SEC2,
    "flowchart_sec3_validator.png": DIAGRAM_SEC3,
    "flowchart_sec4_storage.png": DIAGRAM_SEC4,
    "flowchart_sec5_orchestration.png": DIAGRAM_SEC5,
    "flowchart_sec6_security.png": DIAGRAM_SEC6,
}

# =============================================================================
# 2. IMAGE DOWNLOADING UTILITY (MERMAID.INK)
# =============================================================================

def download_all_images():
    print("\n[RENDERER] Downloading high-resolution rendered diagrams from mermaid.ink...")
    downloaded = {}
    for filename, diag_code in ALL_DIAGRAMS.items():
        img_path = os.path.join(IMG_DIR, filename)
        b64_raw = base64.urlsafe_b64encode(diag_code.encode("utf-8")).decode("utf-8")
        url = f"https://mermaid.ink/img/{b64_raw}?bgColor=FFFFFF"
        try:
            resp = requests.get(url, timeout=25)
            if resp.status_code == 200 and len(resp.content) > 1000:
                with open(img_path, "wb") as f:
                    f.write(resp.content)
                print(f"  [OK] Saved {filename} ({len(resp.content):,} bytes)")
                downloaded[filename] = img_path
            else:
                print(f"  [WARN] Failed to render {filename}: status {resp.status_code}")
        except Exception as e:
            print(f"  [ERROR] Network error rendering {filename}: {e}")
        time.sleep(0.5)
    return downloaded

# =============================================================================
# 3. BUILD WORD DOCUMENT (COMPLETE SYSTEM DOCUMENTATION)
# =============================================================================

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

def add_callout(doc, text, title="NOTE", color="1B365D", bg_color="F0F4F8"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    cell = tbl.rows[0].cells[0]
    cell.width = Inches(6.5)
    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=120, bottom=120, left=180, right=180)
    
    tcPr = cell._element.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:left w:val="single" w:sz="24" w:space="0" w:color="{color}"/>'
        f'<w:top w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'<w:bottom w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(2)
    run_title = p.add_run(f"■  {title}: ")
    run_title.bold = True
    run_title.font.name = "Calibri"
    run_title.font.size = Pt(9.5)
    run_title.font.color.rgb = RGBColor.from_string(color)
    
    run_text = p.add_run(text)
    run_text.font.name = "Calibri"
    run_text.font.size = Pt(9)
    run_text.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def add_image_figure(doc, img_path, caption):
    if img_path and os.path.exists(img_path):
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img.paragraph_format.space_before = Pt(6)
        p_img.paragraph_format.space_after = Pt(2)
        doc.add_picture(img_path, width=Inches(6.5))
        
        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_after = Pt(8)
        r_cap = p_cap.add_run(caption)
        r_cap.font.name = "Calibri"
        r_cap.font.size = Pt(8.5)
        r_cap.font.italic = True
        r_cap.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

def build_full_docx_suite(images_map):
    doc = Document()
    
    for s in doc.sections:
        s.top_margin = Inches(0.75)
        s.bottom_margin = Inches(0.75)
        s.left_margin = Inches(0.8)
        s.right_margin = Inches(0.8)
        
    # Document Title
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_after = Pt(2)
    r = p_title.add_run("Elone Agent — Complete System Documentation")
    r.font.name = "Calibri"
    r.font.size = Pt(24)
    r.bold = True
    r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    
    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_after = Pt(12)
    r_sub = p_sub.add_run("Autonomous L1 IT Ingestion, Multimodal Splicing, JIT Playbook Compilation & Dual-Layer Guardrails")
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(12)
    r_sub.font.color.rgb = RGBColor(0x55, 0x6B, 0x82)
    
    # Metadata Table
    meta_tbl = doc.add_table(rows=4, cols=2)
    meta_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_data = [
        ("System Architecture:", "Elone Autonomous Knowledge-to-Execution Engine"),
        ("Core Capabilities:", "Multimodal SOP Ingestion, 6-Stage CoT Reasoning, AST & LLM Validation, OWASP LLM10"),
        ("Supported Formats:", "PDF, DOCX, CSV, Excel, TXT, Markdown, Embedded UI Screenshots, Web URLs"),
        ("Target Output:", "Open Knowledge Format (OKF) Executable PowerShell & API Playbooks")
    ]
    for i, (k, v) in enumerate(meta_data):
        row = meta_tbl.rows[i]
        c1, c2 = row.cells[0], row.cells[1]
        c1.width = Inches(1.8)
        c2.width = Inches(4.7)
        set_cell_background(c1, "F4F6F9")
        set_cell_background(c2, "FAFCFD")
        set_cell_margins(c1, 40, 40, 80, 80)
        set_cell_margins(c2, 40, 40, 80, 80)
        p1, p2 = c1.paragraphs[0], c2.paragraphs[0]
        p1.paragraph_format.space_after = Pt(1)
        p2.paragraph_format.space_after = Pt(1)
        r1 = p1.add_run(k)
        r1.bold = True
        r1.font.size = Pt(9)
        r1.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
        r2 = p2.add_run(v)
        r2.font.size = Pt(9)
        r2.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        
    set_table_borders(meta_tbl, color="D0D7DE", sz="4")
    doc.add_paragraph().paragraph_format.space_after = Pt(10)
    
    # =========================================================================
    # EXECUTIVE OVERVIEW & MASTER FLOWCHART
    # =========================================================================
    h_exec = doc.add_heading(level=1)
    r = h_exec.add_run("Executive Architecture & Master End-to-End Flowchart")
    r.font.name = "Calibri"
    r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15
    p.add_run(
        "The Elone Agent is an enterprise-grade autonomous IT automation system. It bridges the gap between unstructured, "
        "human-authored Standard Operating Procedures (SOPs) and deterministic, executable PowerShell commands and REST API tool calls. "
        "The pipeline is divided into five rigorous phases: Pre-Ingestion Guardrails, Document-Order Multimodal Extraction, "
        "JIT 6-Stage CoT Playbook Compilation, Dual-Layer Validation with Auto-Retry, and Cryptographic Storage."
    ).font.size = Pt(10)
    
    add_image_figure(doc, images_map.get("flowchart_master.png"), "Figure 1: Master 5-Phase End-to-End Ingestion, Validation & Storage Flowchart")
    
    # =========================================================================
    # SECTION 1: INGESTION TRIGGER & MULTIMODAL PARSER
    # =========================================================================
    h1 = doc.add_heading(level=1)
    r = h1.add_run("1. Ingestion Trigger & Multimodal Document-Order Parsing")
    r.font.name = "Calibri"
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15
    p.add_run(
        "Ingestion begins either via the background polling scheduler (scheduler.py) watching knowledge_base/_uploads/ or direct CLI invocation. "
        "Before any parsing occurs, Gate 1 enforces anti-spoofing magic-byte checks (%PDF-, PK Zip Header), hard size limits (<=10MB), "
        "decompression bomb limits (<=50MB uncompressed, <=20x ratio), and page quotas (<=10 pages). Once verified, the document is walked "
        "in its physical reading sequence so inline screenshots remain anchored directly to their corresponding text steps."
    ).font.size = Pt(10)
    
    add_image_figure(doc, images_map.get("flowchart_sec1_ingestion.png"), "Figure 2: Section 1 — Pre-Ingestion File Checks & Multimodal Splicing Flow")
    
    # =========================================================================
    # SECTION 2: JIT CONVERTER & 6-STAGE COT REASONING
    # =========================================================================
    h2 = doc.add_heading(level=1)
    r = h2.add_run("2. JIT Converter Agent & 6-Stage Command CoT Reasoning")
    r.font.name = "Calibri"
    r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15
    p.add_run(
        "In Stage 1, the Triage Router probes available platform tools (list_available_platforms, get_platform_tools) to classify "
        "the document into COMMAND (pure PowerShell), TOOL_CALL (REST APIs), HYBRID, or UNACTIONABLE. "
        "In Stage 2, the Converter Agent wraps the text in an untrusted sandbox envelope (<untrusted_document_payload>) and enforces "
        "the 6-Stage Command Chain-of-Thought (CoT) Reasoning Mandate:"
    ).font.size = Pt(10)
    
    cot_items = [
        ("Stage 1 (OS & Shell): ", "Set target_os: windows, platform: system, and shell: powershell for every command step."),
        ("Stage 2 (Diagnostic-First): ", "Place non-destructive connectivity and query checks (Test-Connection, reg query) before destructive actions (reg delete, taskkill)."),
        ("Stage 3 (Entity Scoping): ", "Harmonize dynamic ticket variables using double-brace placeholders ({{entities.hostname}}, {{entities.application}})."),
        ("Stage 4 (stdout Parsing): ", "Define deterministic stdout parsing rules in parse_instruction (e.g. set variables.ifeo_blocked = true)."),
        ("Stage 5 (Conditional Remediation): ", "Bind execute_if to prior variables and declare fallback_command strings for resilient execution."),
        ("Stage 6 (Noise Omission): ", "Discard GUI setup instructions ('Open Command Prompt') and manual human checks to ensure 100% autonomous execution.")
    ]
    for ct, cd in cot_items:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_after = Pt(2)
        bp.add_run(ct).bold = True
        bp.add_run(cd).font.size = Pt(9.5)
        
    add_image_figure(doc, images_map.get("flowchart_sec2_converter.png"), "Figure 3: Section 2 — Triage Classification & 6-Stage Command CoT Synthesis")
    
    # =========================================================================
    # SECTION 3: DUAL-LAYER VALIDATION & AUTO-RETRY
    # =========================================================================
    h3 = doc.add_heading(level=1)
    r = h3.add_run("3. Dual-Layer Plan Validation & Self-Healing Guardrails")
    r.font.name = "Calibri"
    r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15
    p.add_run(
        "To guarantee zero execution errors and absolute safety on endpoints, candidate playbooks undergo dual-layer validation. "
        "Layer 1 executes in < 1ms using deterministic Python AST checks, enforcing entity quotation wrapping and blocking banned LOLBins "
        "(certutil, bitsadmin, mshta, powershell -enc, net user /add). Layer 2 utilizes Mistral Small 3 to perform an independent "
        "6-point CoT faithfulness and prompt injection audit. If validation fails, the Auto-Retry Controller feeds surgical error directives "
        "back to the Converter Agent for automatic self-healing (up to 3 attempts)."
    ).font.size = Pt(10)
    
    add_image_figure(doc, images_map.get("flowchart_sec3_validator.png"), "Figure 4: Section 3 — Dual-Layer Validation Gates & Auto-Retry Loop")
    
    # =========================================================================
    # SECTION 4: OKF PLAYBOOK STORAGE & REFLECTION RULEBOOKS
    # =========================================================================
    h4 = doc.add_heading(level=1)
    r = h4.add_run("4. OKF Playbook Specification, Cryptographic Signatures & Adaptive Memory")
    r.font.name = "Calibri"
    r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15
    p.add_run(
        "Approved playbooks are saved as Open Knowledge Format (OKF) markdown documents (knowledge_base/sops/{category}/{SOP-ID}.md). "
        "SOP IDs are sanitized to prevent directory traversal. To prevent post-approval disk tampering, a cryptographic HMAC-SHA256 digital stamp "
        "is embedded into the frontmatter. Concurrently, an adaptive Reflection Rulebook (knowledge_base/patterns/{category}/rules_{SOP-ID}.md) "
        "is auto-initialized to dynamically record runtime execution errors and corrective actions."
    ).font.size = Pt(10)
    
    add_image_figure(doc, images_map.get("flowchart_sec4_storage.png"), "Figure 5: Section 4 — Storage Sandboxing, HMAC Signing & Reflection Rulebooks")
    
    # =========================================================================
    # SECTION 5: MULTI-MODEL ORCHESTRATION & TELEMETRY
    # =========================================================================
    h5 = doc.add_heading(level=1)
    r = h5.add_run("5. Multi-Provider LLM Orchestration & Telemetry")
    r.font.name = "Calibri"
    r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15
    p.add_run(
        "The pipeline optimizes latency, cost, and reliability across distinct LLM roles: Gemini 2.5 Flash for planning and conversion, "
        "Mistral Small 3 for high-speed Layer 2 validation (~2.3s latency), and NVIDIA Vision for screenshot OCR. "
        "The integrated gemini_monitor tracks token consumption, latency, and daily budget limits on every execution."
    ).font.size = Pt(10)
    
    add_image_figure(doc, images_map.get("flowchart_sec5_orchestration.png"), "Figure 6: Section 5 — Multi-Model Role Routing, Quota Monitoring & Telemetry")
    
    # =========================================================================
    # SECTION 6: SECURITY & OWASP TOP 10 FOR LLM COMPLIANCE
    # =========================================================================
    h6 = doc.add_heading(level=1)
    r = h6.add_run("6. Comprehensive Security, PII Protection & OWASP LLM 10 Compliance")
    r.font.name = "Calibri"
    r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15
    p.add_run(
        "Security is enforced at every layer of the architecture, satisfying all requirements of the OWASP Top 10 for LLM Applications "
        "(LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM05 Improper Output Handling, LLM10 Unbounded Consumption). "
        "Real-time DLP redacts passwords, employee PII, and API tokens before AI transmission, while SSRF guards block internal cloud metadata IPs."
    ).font.size = Pt(10)
    
    add_image_figure(doc, images_map.get("flowchart_sec6_security.png"), "Figure 7: Section 6 — End-to-End Security Interceptors & DLP Quarantine")
    
    # Save the master document
    out_path = os.path.join(BASE_DIR, "Elone_Agent_Complete_System_Documentation.docx")
    doc.save(out_path)
    print(f"\n[SUCCESS] Master System Documentation Word Document saved to: {out_path}")
    return out_path

# =============================================================================
# 4. BUILD MASTER MARKDOWN DOCUMENTATION
# =============================================================================

def build_master_markdown():
    md_content = f"""# Elone Agent — Complete System Architecture & Documentation

---

## Executive Summary & System Overview
The **Elone Agent** is an autonomous L1 IT automation and Knowledge-to-Execution pipeline. It ingests raw, unstructured human Standard Operating Procedures (PDF, Word, Excel, CSV, text, and screenshots) and compiles them Just-In-Time (JIT) into deterministic, structured, and executable Open Knowledge Format (OKF) Playbooks.

### Master End-to-End Architecture Flowchart
```mermaid
{DIAGRAM_MASTER}
```

---

## 1. Ingestion Trigger & Multimodal Document-Order Parsing
Ingestion begins via the background polling scheduler (`scheduler.py`) or manual CLI invocation (`debug_run.py`).
* **Pre-Ingestion File Checks**: Enforces magic-byte anti-spoofing (`%PDF-`, `PK\x03\x04`), 10 MB size limits, decompression bomb ratios (<= 20x), and page quotas (<= 10 pages).
* **Physical-Order Parser**: Preserves visual reading sequence across PDF, Word, and Excel files so inline screenshots stay anchored to their corresponding text instructions.
* **Multimodal Splicing**: Interleaves sanitized text segments, Vision OCR reports, and quarantined web links.

```mermaid
{DIAGRAM_SEC1}
```

---

## 2. JIT Converter Agent & 6-Stage Command CoT Reasoning
* **Stage 1 (Triage Router)**: Inspects live platform tools dynamically to classify the document into `command` (pure PowerShell), `tool_call` (REST APIs), `hybrid`, or `unactionable`.
* **Stage 2 (Converter Agent)**: Quarantines raw text inside `<untrusted_document_payload>` tags and executes the **6-Stage Command CoT Reasoning Mandate**:
  1. Target OS & Shell assignment (`windows`, `powershell`).
  2. Diagnostic-First Sequencing (`Test-Connection`, `reg query` before `reg delete`).
  3. Dynamic Entity Harmonization (`{{entities.hostname}}`, `{{entities.application}}`).
  4. stdout Parse Instruction Planning (`variables.app_running = true`).
  5. Conditional Remediation & Fallback Binding (`execute_if`, `fallback_command`).
  6. Human & GUI Noise Omission.

```mermaid
{DIAGRAM_SEC2}
```

---

## 3. Dual-Layer Plan Validation & Self-Healing Guardrails
* **Layer 1 (Deterministic AST & Blacklist Scan <1ms)**: Checks step syntax, ensures dynamic entity quotation wrapping (`"{{entities.app}}.exe"`), and blocks banned LOLBins (`certutil`, `bitsadmin`, `mshta`, `powershell -enc`, `net user /add`).
* **Layer 2 (LLM Faithfulness & Injection Audit)**: Uses `mistral-small-latest` (temp=0) to perform a 6-point CoT audit (100% action recall, 0 hallucinations, prompt injection scan).
* **Auto-Retry Controller**: On validation failure, injects surgical error feedback into the Converter Agent (up to 3 retry attempts).

```mermaid
{DIAGRAM_SEC3}
```

---

## 4. OKF Playbook Specification, Storage & Adaptive Memory
* **OKF Markdown Playbooks**: Saved to `knowledge_base/sops/{{category}}/{{SOP-ID}}.md` with YAML frontmatter.
* **Cryptographic Signatures**: Embeds an HMAC-SHA256 digital stamp to detect post-approval disk tampering.
* **Adaptive Reflection Rulebooks**: Auto-initializes `knowledge_base/patterns/{{category}}/rules_{{SOP-ID}}.md` to dynamically learn from runtime execution errors.

```mermaid
{DIAGRAM_SEC4}
```

---

## 5. Multi-Model Orchestration & Telemetry
* **Role Routing**: Gemini 2.5 Flash for planning/conversion, Mistral Small 3 for Layer 2 validation (~2.3s latency), and NVIDIA Vision for screenshot OCR.
* **Telemetry & Cost Accounting**: Tracks input/output tokens, latency, and costs via `gemini_monitor`.

```mermaid
{DIAGRAM_SEC5}
```

---

## 6. Comprehensive Security & OWASP Top 10 for LLM Compliance
* **Full OWASP LLM 10 Alignment**: Covers LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM05 Improper Output Handling, and LLM10 Unbounded Consumption.
* **Real-Time DLP Masking**: Automatically masks passwords (`[DLP_REDACTED_PASSWORD]`), API keys (`[DLP_REDACTED_API_KEY]`), and employee PII before external AI transmission.
* **SSRF Defense**: Blocks internal cloud metadata endpoints (`169.254.169.254`) and private RFC1918 subnets.

```mermaid
{DIAGRAM_SEC6}
```
"""
    md_path = os.path.join(DOCS_DIR, "FULL_SYSTEM_DOCUMENTATION.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[SUCCESS] Master Markdown Documentation saved to: {md_path}")
    return md_path

if __name__ == "__main__":
    downloaded_images = download_all_images()
    build_master_markdown()
    build_full_docx_suite(downloaded_images)
