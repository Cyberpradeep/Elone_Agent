"""
Script to generate the High-Level Architectural Flowchart for Elone_Agent
in both Markdown (Mermaid) and high-resolution PNG format.
"""

import os
import requests

HIGH_LEVEL_MERMAID = """flowchart TD
    %% Styling
    classDef startEnd fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef primary fill:#1e1b4b,stroke:#818cf8,stroke-width:2px,color:#f8fafc;
    classDef hitl fill:#450a0a,stroke:#f87171,stroke-width:2px,color:#f8fafc;
    classDef execution fill:#022c22,stroke:#34d399,stroke-width:2px,color:#f8fafc;
    classDef escalation fill:#3b0764,stroke:#c084fc,stroke-width:2px,color:#f8fafc;
    classDef success fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    %% 1. Ingress
    START(["👤 User Support Ticket Ingress"]):::startEnd
    
    %% 2. Intake & Triage
    INTAKE["<b>1. Intake & Triage Agent</b><br/>• Asset Identification & Credentials Lookup<br/>• Allowed Software Policy Verification<br/>• Catalog Scanning (sops/index.md)"]:::primary
    
    %% 3. Planning & Discovery
    PLANNER["<b>2. Discovery & Planning Agent</b><br/>• Progressive Disclosure Discovery (OKF Store)<br/>• Host Quirk & Reflection Memory Injection<br/>• 6-Stage Deep CoT Plan Synthesis"]:::primary

    %% 4. Human in the loop Gate
    HITL{"<b>3. Human-in-the-Loop Gate</b><br/>Plan Approval Required?"}:::hitl

    %% 5. Orchestration & Execution
    ORCH["<b>4. Orchestrator & Guardrails</b><br/>• Circuit Breakers (Max 3 Retries, 15 Steps)<br/>• Step Advancement & Fallback Swapping"]:::primary

    EXEC["<b>5. Execution Agent</b><br/>• Local Subprocess Fast-Path (0ms Overhead)<br/>• Remote SSH / WinRM Runner<br/>• API Identity Tools (Auth0, Okta, Mock)"]:::execution

    %% 6. Output Verification
    VERIFY{"<b>6. Output Verifier Agent</b><br/>• Fast Structural JSON & Regex Parser<br/>• Dynamic Variable Extraction<br/>Step Verdict: SUCCESS or RETRY?"}:::execution

    %% 7. Escalation
    ESCALATE["<b>7. Escalation Agent (L2/L3)</b><br/>• Formats Structured Handover Payload<br/>• Diagnostic Traces & Root Cause Log"]:::escalation

    %% 8. Summarization & Resolution
    SUMM["<b>8. Summarization Agent</b><br/>• 3-Tier Resilient Report Generator<br/>• Customer Plain-Text Email Response<br/>• Internal Technical Markdown Summary<br/>• Episodic Memory Trace Saved to Disk"]:::success

    END_DONE(["✅ Ticket Resolved (FULLY_RESOLVED)"]):::startEnd
    END_ESC(["⚠️ Ticket Escalated (ESCALATED_L2)"]):::startEnd

    %% Flow Connections
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
"""

DOCUMENT_CONTENT = f"""# High-Level Architecture Flowchart: Elone_Agent

This document provides a high-level executive overview of the **Elone_Agent** autonomous IT support automation workflow.

---

## 1. High-Level Flowchart Diagram (Interactive Mermaid)

```mermaid
{HIGH_LEVEL_MERMAID}
```

---

## 2. Key High-Level Phases

| Phase | Agent / Component | High-Level Purpose |
| :--- | :--- | :--- |
| **1. Intake & Triage** | `intake_agent` | Identifies caller email, enriches hostname & credentials from asset sheets, checks software authorization, and scans `sops/index.md`. |
| **2. Discovery & Planning** | `planner_agent` | Discovers OKF playbooks via progressive disclosure across disk stores, applies host reflection memory, and generates an executable step-by-step plan. |
| **3. Human-in-the-Loop** | `HITL Gate` | Halts execution before Step 1 for operator inspection and approval; automatically continues subsequent steps and retries once approved. |
| **4. Orchestrator** | `orchestration_agent` | Enforces circuit breakers (max 3 retries, max 15 steps) and routes traffic between steps, retries, and escalation. |
| **5. Execution** | `execution_agent` | Runs native PowerShell commands locally with 0ms network overhead, connects to remote machines via SSH/WinRM, or calls enterprise identity API tools. |
| **6. Output Verification** | `execution_result_agent` | Verifies command exit codes, parses structured JSON, extracts dynamic state variables (e.g. IPs, PIDs, status flags), and determines step success. |
| **7. Escalation** | `escalation_agent` | Assembles a structured L2/L3 handover ticket with full failure logs, error snippets, and diagnostic findings. |
| **8. Summarization** | `summarization_agent` | Generates a user-facing resolution email, an internal technical engineering report, and stores the episodic memory trace on disk. |
"""

def generate():
    output_md_path = os.path.join("docs", "ELONE_HIGH_LEVEL_FLOWCHART.md")
    output_png_path = os.path.join("docs", "elone_agent_high_level_flowchart.png")

    # 1. Write Markdown
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(DOCUMENT_CONTENT)
    print(f"[OK] Written Markdown documentation to: {output_md_path}")

    # 2. Render PNG via Kroki API
    print("[...] Rendering high-level PNG flowchart via Kroki API...")
    kroki_url = "https://kroki.io/mermaid/png"
    try:
        response = requests.post(
            kroki_url,
            json={"diagram_source": HIGH_LEVEL_MERMAID.strip(), "output_format": "png"},
            timeout=60
        )
        if response.status_code == 200 and len(response.content) > 1000:
            with open(output_png_path, "wb") as f:
                f.write(response.content)
            print(f"[OK] Successfully rendered high-res PNG flowchart ({len(response.content)} bytes)")
            print(f"     -> Saved to: {output_png_path}")
        else:
            print(f"[Error] Kroki returned {response.status_code}: {response.text[:300]}")
    except Exception as e:
        print(f"[Error] Failed to render PNG: {e}")

if __name__ == "__main__":
    generate()
