# Elone Agent — Complete System Architecture & Documentation

---

## Executive Summary & System Overview
The **Elone Agent** is an autonomous L1 IT automation and Knowledge-to-Execution pipeline. It ingests raw, unstructured human Standard Operating Procedures (PDF, Word, Excel, CSV, text, and screenshots) and compiles them Just-In-Time (JIT) into deterministic, structured, and executable Open Knowledge Format (OKF) Playbooks.

### Master End-to-End Architecture Flowchart
```mermaid
flowchart TD
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

```

---

## 1. Ingestion Trigger & Multimodal Document-Order Parsing
Ingestion begins via the background polling scheduler (`scheduler.py`) or manual CLI invocation (`debug_run.py`).
* **Pre-Ingestion File Checks**: Enforces magic-byte anti-spoofing (`%PDF-`, `PK`), 10 MB size limits, decompression bomb ratios (<= 20x), and page quotas (<= 10 pages).
* **Physical-Order Parser**: Preserves visual reading sequence across PDF, Word, and Excel files so inline screenshots stay anchored to their corresponding text instructions.
* **Multimodal Splicing**: Interleaves sanitized text segments, Vision OCR reports, and quarantined web links.

```mermaid
flowchart TD
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

```

---

## 2. JIT Converter Agent & 6-Stage Command CoT Reasoning
* **Stage 1 (Triage Router)**: Inspects live platform tools dynamically to classify the document into `command` (pure PowerShell), `tool_call` (REST APIs), `hybrid`, or `unactionable`.
* **Stage 2 (Converter Agent)**: Quarantines raw text inside `<untrusted_document_payload>` tags and executes the **6-Stage Command CoT Reasoning Mandate**:
  1. Target OS & Shell assignment (`windows`, `powershell`).
  2. Diagnostic-First Sequencing (`Test-Connection`, `reg query` before `reg delete`).
  3. Dynamic Entity Harmonization (`{entities.hostname}`, `{entities.application}`).
  4. stdout Parse Instruction Planning (`variables.app_running = true`).
  5. Conditional Remediation & Fallback Binding (`execute_if`, `fallback_command`).
  6. Human & GUI Noise Omission.

```mermaid
flowchart TD
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

```

---

## 3. Dual-Layer Plan Validation & Self-Healing Guardrails
* **Layer 1 (Deterministic AST & Blacklist Scan <1ms)**: Checks step syntax, ensures dynamic entity quotation wrapping (`"{entities.app}.exe"`), and blocks banned LOLBins (`certutil`, `bitsadmin`, `mshta`, `powershell -enc`, `net user /add`).
* **Layer 2 (LLM Faithfulness & Injection Audit)**: Uses `mistral-small-latest` (temp=0) to perform a 6-point CoT audit (100% action recall, 0 hallucinations, prompt injection scan).
* **Auto-Retry Controller**: On validation failure, injects surgical error feedback into the Converter Agent (up to 3 retry attempts).

```mermaid
flowchart TD
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

```

---

## 4. OKF Playbook Specification, Storage & Adaptive Memory
* **OKF Markdown Playbooks**: Saved to `knowledge_base/sops/{category}/{SOP-ID}.md` with YAML frontmatter.
* **Cryptographic Signatures**: Embeds an HMAC-SHA256 digital stamp to detect post-approval disk tampering.
* **Adaptive Reflection Rulebooks**: Auto-initializes `knowledge_base/patterns/{category}/rules_{SOP-ID}.md` to dynamically learn from runtime execution errors.

```mermaid
flowchart TD
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

```

---

## 5. Multi-Model Orchestration & Telemetry
* **Role Routing**: Gemini 2.5 Flash for planning/conversion, Mistral Small 3 for Layer 2 validation (~2.3s latency), and NVIDIA Vision for screenshot OCR.
* **Telemetry & Cost Accounting**: Tracks input/output tokens, latency, and costs via `gemini_monitor`.

```mermaid
flowchart TD
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

```

---

## 6. Comprehensive Security & OWASP Top 10 for LLM Compliance
* **Full OWASP LLM 10 Alignment**: Covers LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM05 Improper Output Handling, and LLM10 Unbounded Consumption.
* **Real-Time DLP Masking**: Automatically masks passwords (`[DLP_REDACTED_PASSWORD]`), API keys (`[DLP_REDACTED_API_KEY]`), and employee PII before external AI transmission.
* **SSRF Defense**: Blocks internal cloud metadata endpoints (`169.254.169.254`) and private RFC1918 subnets.

```mermaid
flowchart TD
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

```
