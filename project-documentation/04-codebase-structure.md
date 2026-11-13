# 04 — Codebase Structure

```
Elone-11/
├── README.md                    marketing-style overview (partly stale, see 13)
├── .env / .env.example          local secrets (untracked) / template (missing ELONE_PLAYBOOK_SIGNING_KEY)
├── start.ps1 | start.bat        cd backend → run server.py in venv (opens browser)
├── __init__.py                  root package shim
├── venv/                        local virtualenv (untracked)
├── postman/                     Postman collection + environment (outdated)
├── .agents/                     AI-assistant skills & MCP config (tooling, not app; tracked despite .gitignore)
├── knowledge_base/              ALL runtime data ("database"); mostly gitignored
│   ├── _uploads/<tenant>/       raw uploads, plus _drafts/, _governance_ledger.json,
│   │                            _processed_manifest.json, _retrieval_catalog.json, _upload_owners.json
│   ├── _auth/                   users.json, revoked_tokens.json, auth_events.jsonl
│   ├── sops/<category>/         published <SOP>.md (HMAC-signed) + <SOP>.canonical.json + index.md
│   ├── patterns/<category>/     rules_<SOP>.md "reflection rulebooks" (empty tables)
│   ├── _trash/                  soft-deleted playbooks (+ _manifest.json)
│   └── logs/                    debug/, parser/, converter_input/, images/, web_cache/, weekly .md, _log_owners.json
├── frontend/                    static SPA (served by FastAPI at "/")
│   ├── index.html               importmap cache-busting, app shell
│   ├── css/{style,components}.css
│   └── js/{app,api,auth,ui,charts,progress}.js + views/*.js (11 views)
└── backend/
    ├── server.py                FastAPI app, CORS, router registration, OpenAPI security, static mount
    ├── run.py                   CLI — all ingest modes hard-blocked (C1); only --models/--status work
    ├── trace_pipeline.py        governed CLI tracer using msg/1.0 bus (A1→A6)
    ├── debug_run.py             developer harness
    ├── mcp_server.py            FastMCP stdio server (read-only tools; ingest/scan blocked)
    ├── scheduler.py             stub: state dict only; watcher disabled (C1)
    ├── test_standalone.py       1.1k-line script-style test runner (not pytest-collected as such)
    ├── test_llm_providers.py    manual provider smoke script
    ├── api/                     HTTP layer
    ├── auth/                    identity layer
    ├── agents/                  pipeline logic (a1..a6)
    ├── orchestrator/            ledger (live) + bus/agent_runners (CLI/test only)
    ├── schemas/                 Pydantic + dataclasses + state machine constants
    ├── config/                  settings, LLM builder, tool catalog, JSON configs
    ├── prompts/                 LLM prompt templates
    ├── tools/                   platform tool *schemas* + LangChain catalog-inspection tools
    ├── gemini_monitor/          LLM usage/cost ledger (daily_usage.json, despite the name covers all providers)
    ├── utils/                   security.py (DLP, SSRF, HMAC, sanitizers), logger, cancellation
    ├── scripts/                 migrate_playbook_signatures.py (v1→v2 HMAC)
    ├── elone_sop/               empty package for setuptools entry points
    └── tests/                   pytest suite + golden_set (16 SOP samples) + deepeval LLM evals
```

## `backend/api/`
| File | Purpose |
|---|---|
| `__init__.py` | collects routers (`all_routers`) |
| `context.py` | **shared singletons** (`governance_ledger`, `retrieval_index`, `agent_bus`), all filesystem paths, tenant-scoped upload/manifest/log helpers, `resolve_sop_access_meta`, `resolve_draft_access_meta` (derive tenant/tier from canonical file → index → ledger → frontmatter) |
| `routes_auth.py` | login/logout/me/users/service tokens |
| `routes_ingestion.py` | uploads list/upload/ingest/cancel/scan(410)/plan-preview; ingest pipeline is **inlined** here (~500 lines) |
| `routes_governance.py` | jobs, review tasks, decisions, publish, canonical edit/sync, draft editing/resubmit, downstream search/stats, incidents, config |
| `routes_playbooks.py` | list/get/verify/delete published SOPs |
| `routes_telemetry.py` | health, overview (contains static "gates" metadata), scheduler, tools, telemetry, logs, security lab |

## `backend/auth/`
`config.py` (env loading, fail-closed secrets), `models.py` (roles, capabilities, `AuthPrincipal`, `UserRecord`), `passwords.py` (scrypt), `tokens.py` (JWT issue/verify, OIDC adapter, `RevocationStore`), `user_store.py` (JSON users + `LoginRateLimiter`), `dependencies.py` (`authenticate_request`, CSRF, tenant/clearance enforcement, audit log), `cli.py` (bootstrap users/tokens).

## `backend/agents/`
- `a1_ingestion/`: `intake_validator.py` (Gate 1), `document_extractor.py`, `vlm_extractor.py`, `link_scraper.py`.
- `a2_structuring/`: `execution_planner.py` (main LLM planner `plan_okf_from_raw`), `triage_router.py`, `canonical_builder.py`, `okf_builder.py`, `text_cleaner.py`.
- `a3_security/`: `secret_scanner.py`, `ast_sandbox.py`, `confidentiality_engine.py`.
- `a4_verification/`: `plan_validator.py` (also owns `MALICIOUS_COMMAND_PATTERNS`), `quote_tracer.py`, `quality_engine.py`.
- `a5_review/`: `sod_policy.py` (SoD + gates), `draft_store.py`, `task_manager.py`.
- `a6_hub/`: `retrieval_catalog.py`, `publisher.py` (re-export shim), `rulebook_manager.py` (18-line stub).

## Duplicated / dead / suspect code
| Item | Evidence | Status |
|---|---|---|
| `orchestrator/bus.py` + `agent_runners.py` + `schemas/protocol_msg.py` | only `trace_pipeline.py` & tests import runners; `agent_bus` unused by routes | parallel pipeline implementation, drift risk |
| `scheduler.py` | `run_ingestion_cycle` raises; thread never started | dead (status shim only) |
| `run.py --file/--scan/--watch`, `convert_raw_sop_to_okf`, `ingest_sop`, `scan_uploads_now`, `/api/uploads/scan` | all return/raise "blocked (C1)" | intentionally disabled stubs |
| `link_scraper.py` | referenced only by tests/exports | not in live path, yet UI "gates" claim SSRF/web quarantine is *active* |
| `a5_review/draft_store.py` write funcs | live route writes draft JSON itself; only `purge_staged_draft` used | partial duplication |
| `a6_hub/rulebook_manager.py` | 18 lines | stub |
| `tools/platforms/*` | schema only; `call_platform` tool just returns schema | no executable integration |
| `config/pipeline_config.json` | byte-mirror of `settings.json` written on every config save | redundant |
| `.agents/` | tracked but in `.gitignore` | tooling noise |
| `elone_sop/`, root `__init__.py` | trivial packaging shims | harmless |
