# 14 — Complete Project Summary (read this first if you read only one)

## In one paragraph
Elone is a **governance gate between human-written SOP documents and AI automation agents**. A Process Owner uploads a PDF/DOCX/TXT; a FastAPI backend scrubs and scans it, uses LLMs to turn it into structured executable steps with verbatim source quotes, scores its quality and confidentiality (L0–L3), and parks it as a *draft*. A different person (Security Reviewer) must approve it — the server recomputes six publication gates itself and binds the approval to SHA-256 hashes of what was reviewed. The Process Owner then publishes: a **HMAC-signed Markdown playbook** + **Canonical JSON** are written to `knowledge_base/` and indexed so tenant- and clearance-scoped *agent* service accounts can search and fetch them. A vanilla-JS dashboard drives all of this. There is no database (JSON files), no execution engine (downstream), and no deployment tooling yet.

## Mental model (draw this)
```
upload → Gate1 → extract(+VLM) → DLP/quarantine → regex threat scan → LLM planner ↻ validator(L1 code + L2 LLM)
      → canonical JSON (quote tracing, coverage, quality Q, tier) → DRAFT (state awaiting_review)
      → Security Reviewer decision (SoD, 6 gates recomputed server-side, hash stamp) → approved
      → Process Owner publish (gates again + hash match) → .md (HMAC) + .canonical.json + catalog
      → agents: POST /downstream/search (tenant+clearance from JWT) → GET /api/sops/{id} → verify HMAC → execute (elsewhere)
```

## Components at a glance
| Layer | Tech | Key files |
|---|---|---|
| UI | vanilla ES modules | `frontend/js/app.js`, `api.js`, `views/*` |
| API | FastAPI | `backend/server.py`, `backend/api/routes_*.py`, `api/context.py` |
| Identity | PyJWT, scrypt, JSON user store | `backend/auth/*` |
| Pipeline | plain Python "agents" | `backend/agents/a1…a6`, `orchestrator/ledger.py` |
| Policy core | gates + SoD + hashing | `agents/a5_review/sod_policy.py`, `ledger.py` |
| AI | LangChain → Mistral/Groq/NVIDIA/… | `config/llm_config.py`, `prompts/*`, `execution_planner.py`, `plan_validator.py` |
| Storage | files | `knowledge_base/**` |
| Side doors | MCP stdio, CLI tracer | `mcp_server.py`, `trace_pipeline.py` |

## Roles → powers (memorise)
- **process_owner**: upload, ingest, edit drafts, resubmit, publish, edit published canonical.
- **security_reviewer**: decide reviews (only within clearance; never on own upload/edit).
- **admin**: users, tokens, config, telemetry, logs, delete, view incidents; *cannot approve or publish*.
- **agent**: machine search/read only.

## What works well
- Layered, mostly fail-closed auth with extensive tests (roles × tenants × clearance × CSRF × CORS).
- Approval is *bound* to hashes of the reviewed artefacts; gates are recomputed server-side; request bodies cannot spoof actor/tenant/gates.
- Quote tracing done by code, not by the LLM.
- Cost brakes: per-job call budget, daily breaker, timeouts/retries, usage ledger.
- Clear lifecycle ledger with audit history; ungoverned paths deliberately disabled (C1).

## What is incomplete or wrong (top items; full list in 13)
1. **P0** — Post-publication edit endpoints re-sign playbooks without review/gates/AST scan.
2. **P1** — DLP/quarantine gaps (substring allow-list, PDF/DOCX API keys silently masked, screenshots and preview endpoint unscanned).
3. **P1** — LLM validator fails open on malformed replies; regex command blacklist lets destructive commands through.
4. **P1** — Single-process JSON state, no prod deployment tooling, `uvicorn` undeclared.
5. **P1** — JWT claims trusted until expiry; no cap/revocation for service tokens.
6. Docs/UI claims drift (14 vs 18 states, model table, static "gates" panel, 91 tests).

## Test status (measured)
Sandboxed run: **148 passed, 2 failed (env/key-dependent), 2 skipped**; 6 DeepEval modules cannot import (dependency missing). See 11.

## Reading order (≈ 3 hours)
1. `README.md` (skim; then trust code) → `backend/server.py` → `backend/api/__init__.py`.
2. **Identity**: `auth/models.py` → `auth/config.py` → `auth/tokens.py` → `auth/dependencies.py` → `auth/user_store.py` → `api/routes_auth.py`.
3. **Shared state**: `api/context.py` (tenant helpers, `resolve_*_access_meta`) → `schemas/governance_models.py` (states, transitions, dataclasses) → `orchestrator/ledger.py`.
4. **Ingestion**: `api/routes_ingestion.py::api_ingest_single` (the pipeline in one function) → `agents/a1_ingestion/intake_validator.py` → `document_extractor.py` → `utils/security.py` (DLP, HMAC) → `a3_security/ast_sandbox.py`.
5. **AI**: `config/llm_config.py` → `prompts/jit_converter_prompts.py` (COMMAND prompt) → `a2_structuring/execution_planner.py` → `a4_verification/plan_validator.py`.
6. **Scoring**: `a2_structuring/canonical_builder.py` → `a4_verification/quote_tracer.py`, `quality_engine.py` → `a3_security/confidentiality_engine.py`.
7. **Governance core**: `a5_review/sod_policy.py` → `api/routes_governance.py` (decision → publish → draft edit → **canonical PUT**) → `a2_structuring/okf_builder.py` → `a6_hub/retrieval_catalog.py`.
8. **Frontend**: `index.html` → `js/api.js` → `js/app.js` → `views/review-task.js`, `views/ingestion.js`.
9. **Tests as specification**: `tests/test_auth_and_cors.py`, `test_c3_c4_server_gates_and_publish_integrity.py`, `test_governance_bypass_disabled.py`.
10. Optional: `schemas/protocol_msg.py` + `orchestrator/bus.py` + `trace_pipeline.py` (the second pipeline), `mcp_server.py`.

## What to learn to own this codebase
FastAPI (dependencies, middleware, StaticFiles, threadpool); JWT/CSRF/CORS fundamentals; RBAC/ABAC & separation of duties; HMAC vs signatures; regex-based DLP limits and entropy detection; prompt-injection threat model; LangChain chat clients, fallbacks and tool binding; Pydantic v2; PowerShell command risk; file-based persistence pitfalls (atomic writes, locks, multi-process); migrating to SQL; pytest & subprocess-isolated tests; vanilla ES-module SPAs.

## Questions you should be able to answer
1. Which role can approve, which can publish, and why can an admin do neither?
2. Where do `tenant_id`, `clearance` and `agent_persona` come from on `/downstream/search`, and what happens to values in the body?
3. Name the 6 publication gates and where each is computed. Why are they recomputed at publish?
4. What exactly is hashed at approval time, and which check at publish detects tampering?
5. Walk the states from `received` to `published`; which are terminal; how many states exist and why does the README differ?
6. What does the HMAC cover and not cover? Who holds the key? What changes with `ELONE_ALLOW_INSECURE_DEV_KEY`?
7. How does SoD identify "the same person", and what edge cases does that leave?
8. Why can a PDF containing an API key avoid quarantine while a TXT cannot? What does `ResetMe2026!` demonstrate?
9. Which model actually serves `execution_planning` today and where is that decided?
10. What stops runaway LLM spend, and which of those controls are off on this machine?
11. What does the quote tracer verify, and which canonical sections are *not* really verified?
12. Explain P0-1: which endpoints, which fields an attacker controls, what protects (and fails to protect) the result.
13. Why must the server run as a single worker today?
14. How would you prove every non-public route requires authentication?
15. What is the difference between `/api/uploads/ingest`, `/api/plan-preview`, MCP `plan_sop`, and `trace_pipeline.py` with respect to governance?
16. How do cookies + CSRF + Bearer interact, and why do agents skip CSRF?
17. What does `normalize_clearance("secret")` return and why is that risky?
18. Where would you add per-tenant config, and which files/endpoints currently assume global config?
