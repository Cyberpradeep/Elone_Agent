# 01 — Project Overview

> Evidence base: every statement below was checked against source code in the repo at branch `dev-ingestion` (HEAD `0d2a67b`). Where the README says one thing and the code another, the code wins and the discrepancy is listed in [13-gaps-and-recommendations.md](13-gaps-and-recommendations.md).

## What the project is

**Elone Agent — SOP Governance Hub** turns messy human Standard Operating Procedures (PDF / DOCX / TXT / MD / CSV / XLSX) into **signed, machine-readable "playbooks"** that downstream automation agents can look up and (outside this repo) execute. A human review step sits between the AI and publication.

In plain language:

1. A *Process Owner* uploads an SOP document.
2. The system extracts text (and reads screenshots with a vision model), scans for secrets and dangerous commands, then asks an LLM to convert the prose into ordered, structured steps (PowerShell commands or tool calls).
3. Deterministic code checks the output: every step must quote the source document verbatim, the quote must be found at the claimed line, coverage and quality are scored, and a confidentiality tier (L0–L3) is computed.
4. A *different* person (*Security Reviewer*) must approve it (separation of duties). Only then can the Process Owner publish.
5. Publishing writes a Markdown playbook with a **HMAC-SHA256 integrity stamp**, a Canonical JSON record, and adds it to an in-memory/JSON search catalog. Downstream *agent* accounts (JWT service tokens) can search the catalog, filtered by tenant and clearance.

## Business objective

Make it safe to let an LLM-driven L1/L2 support agent act on company procedures: every automated step is traceable to a source sentence, screened for malicious commands, reviewed by a second human, tamper-evident on disk, and visible only to agents with matching tenant + clearance.

## Target users (roles actually implemented — `backend/auth/models.py`)

| Role | Who | Can do (verified in code) |
|---|---|---|
| `process_owner` | SOP author | upload, ingest, cancel, plan-preview, edit drafts (awaiting_review / changes_requested), resubmit, **publish**, edit *published* canonical JSON, view tools |
| `security_reviewer` | second-person approver | record approve / changes_requested / reject on tasks within their clearance; view incidents; Security Lab |
| `admin` | tenant administrator | users & service tokens, `/api/config`, telemetry, audit logs, delete (soft) playbooks, view tools/incidents, Security Lab, edit published canonical |
| `agent` | downstream machine account | search catalog, read published playbooks/canonicals, verify integrity. Cannot sign in to the UI |

## Main capabilities (all verified as implemented unless flagged)

- Local username/password login, scrypt hashing, HS256 JWT in HttpOnly cookie *or* Bearer header, CSRF double-submit, login lockout, jti revocation, optional OIDC/JWKS mode.
- Multi-tenant + L0–L3 clearance enforcement at the API layer (file-backed storage, no DB).
- Governed ingestion pipeline: intake validation → extraction (MarkItDown / PyMuPDF / python-docx) → DLP secret scan with quarantine → regex "AST" threat scan → LLM triage + planning → LLM faithfulness audit → quote tracing → quality & confidentiality scoring → human review.
- 18-state lifecycle ledger (README says 14) with persisted audit history.
- Server-side computation of the 6 publication gates (never trusts client values) and hash-binding of approval → publish (canonical + draft SHA-256).
- HMAC-signed playbooks and integrity verification endpoint.
- Admin dashboard (vanilla JS SPA): overview, playbooks, review queue/task, agent catalog, ingestion, tool catalog, telemetry, audit logs, security lab, settings (users + config).
- LLM cost controls: per-job call budget, daily quota circuit breaker, per-request timeouts/retries, usage ledger.
- MCP stdio server exposing read-only helpers (`plan_sop`, `read_playbook`, …).

## What it is *not*

- It does **not execute** playbooks. `backend/tools/platforms/*.py` are *schema descriptions* of tools the LLM may reference, not API clients. Execution is assumed to be a separate downstream runtime (not in this repo).
- It is **not RAG with embeddings**. Retrieval is token-substring matching over an in-memory index (`backend/agents/a6_hub/retrieval_catalog.py`).
- It has **no database**; everything is JSON/Markdown files under `knowledge_base/`.

## Repository stats

~199 tracked files, ≈38.6k lines (backend Python + frontend JS/CSS, including ≈8.5k lines under `backend/tests/`). 45 git commits; the security-hardening series (C1–C4, H1–H3, M5) landed 2026-11-11/12.
