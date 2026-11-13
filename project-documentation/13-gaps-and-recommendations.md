# 13 — Gaps, Risks & Recommendations

Every item cites evidence. "Verified" = I reproduced it by running code or reading the exact lines; "Reasoned" = follows from code but not executed.

## A. Implementation status matrix

| Area | Status |
|---|---|
| Local auth, JWT, CSRF, RBAC, tenant & clearance enforcement | **Fully implemented** (well tested) |
| Governed ingestion → draft → review → publish with server-side gates & hash binding | **Fully implemented** |
| HMAC playbook signing/verification | **Fully implemented** (frontmatter only) |
| Secret quarantine | **Partially implemented** (see P1-1) |
| Command-safety ("AST sandbox") | **Partially** — regex blacklist (P1-3) |
| LLM faithfulness audit | **Partially** — fail-open path (P1-2) |
| OIDC / hybrid auth | Implemented, **needs verification** against a real IdP |
| Downstream retrieval | **Partially** — keyword matching only; audit log not persisted |
| Deactivate / archive / restore lifecycle | **Not exposed** (ledger methods only) |
| Scheduler / batch scan / `run.py` ingest / MCP ingest | **Intentionally disabled** (C1) |
| Link scraper / SSRF protection | Implemented but **not wired** into live flow |
| AI confidentiality advisory ("AI floor rule") | **Dormant** |
| Tool execution (solandra/auth0/email/…) | **Not implemented** (schemas only) |
| msg/1.0 bus in the API | **Not used** (CLI/tests only) |
| Database, migrations, seeds | **Not implemented** (JSON files) |
| CI/CD, Docker, IaC, linting, monitoring, frontend tests | **Not implemented** |
| UI "Gates" panel on Overview | **Misleading** — static text (see P2-8) |

## B. Prioritised findings

### P0 — Critical
**P0-1. Published SOPs can be changed (and re-signed) with no review, gates or AST scan.** *Verified by code read.*
`PUT /api/governance/sops/{id}/canonical` and `POST …/sync-playbook` (`routes_governance.py:689-816`) accept **process_owner or admin**, require only tenant/clearance and `lifecycle.state==published`, then call `write_canonical_sop_json` + `sync_canonical_to_playbook` (`canonical_builder.py:493-565`), which rebuilds the executable frontmatter and **recomputes a valid HMAC**. Not run: Pydantic schema validation, quote tracing, AST/secret scans, SoD, `security_reviewer` approval, hash binding. What can be injected: **new steps** (a step number not in the old playbook takes `command` from the body's `input`), **`fallback_command`** (taken from `warning`), step descriptions, title/description, and the **classification tier** (a body `classification.level: "L0"` is accepted and, because `resolve_sop_access_meta` prefers the canonical file, widens visibility in `/api/sops` and `/canonical` — the retrieval-index entry itself is not re-indexed, so catalog search keeps the old tier). Existing steps keep their prior `command` (the code prefers `matched_prev.command`), which limits but does not remove the impact. A single compromised/malicious Process Owner (or any admin) therefore defeats the dual-custody promise *after* publication; downstream agents will see a validly-signed playbook.
*Fix*: treat any post-publication change as a new version that re-enters the review pipeline (or restrict these endpoints to non-executable metadata); run `validate_canonical_sop_dict`, AST scan and secret scan; forbid tier changes; require SR re-approval; log to ledger (`record_draft_edit` equivalent).

### P1 — High
**P1-1. Secret gate has several holes.** *Verified by executing `redact_sensitive_dlp`.*
(a) Placeholder allow-list is matched by substring: `password: ResetMe2026!` is neither redacted nor counted (`DOCUMENTATION_SECRET_PLACEHOLDERS` contains `reset`, `change`, `policy`, `management`, `rotation`, `example`, `todo`…). (b) For PDF/DOCX, extraction pre-redacts, so the route's secret count after that is only re-triggered for the `password:` pattern; **API keys/tokens are silently masked with no quarantine/incident**. (c) For TXT/MD, emails/phones are **not masked** before the text goes to the external LLM (the route discards the redacted copy). (d) Secrets inside screenshots are not scanned; VLM report text is appended to the prompt unscanned. (e) `/api/plan-preview` and MCP `plan_sop` send file text to the LLM without quarantine/AST scan. *Fix*: one scan on the **raw** extracted text before any redaction; exact/anchored placeholder matching; use the redacted copy for LLM prompts; scan VLM output; apply the same gate to preview.
**P1-2. LLM validator fails open on malformed output.** `plan_validator.py:417-530`: a JSON reply missing fields defaults `is_faithful=True`, `injection_detected=False`; unparsable replies are accepted unless they contain `"is_faithful": false`. An attacker who can make the validator emit prose (e.g. via injection in the SOP) bypasses Layer 2. *Fix*: require schema-valid verdict, otherwise fail closed.
**P1-3. Command blacklist is narrow.** *Verified*: `Remove-Item -Recurse -Force C:\Users`, `rm -rf /`, `format C: /q`, `Stop-Computer`, `reg delete`, `Start-BitsTransfer`, `… | iex`, `powershell -e <b64>` all pass `scan_commands_for_ast_threats`. Also the wrapper in `utils/security.py:739` returns `[]` on any exception (fail-open). *Fix*: allow-list/tokenised PowerShell parsing, deny destructive verbs by default, mark risky steps `requires_approval` (currently every canonical step is hard-coded `risk:"low"`, `requires_approval:false`).
**P1-4. No production deployment path / single-process state.** `uvicorn` undeclared; `reload=True`; no Docker/CI; JSON files + in-memory ledger/catalog/limiter — a second worker silently diverges; `governance_ledger.load()` on GETs swaps the dict under concurrent writers; usage file read-modify-write is unlocked. *Fix*: declare deps, document single-worker constraint now, move state to a DB (SQLite/Postgres) with transactions, add Dockerfile/CI.
**P1-5. Token claims are authoritative until expiry.** Role/clearance changes and (for OIDC) disablement don't apply until the JWT expires (30 min humans, 8 h agents); `ttl_minutes` for service tokens has no maximum and no listing/revocation endpoint (`routes_auth.py:334-336`). *Fix*: look up role/clearance from the store per request (as already done for `disabled`), cap TTL, add token registry + revoke endpoint.
**P1-6. Playbook integrity model is shallow.** HMAC covers frontmatter only; canonical JSON, catalog JSON, ledger and drafts are unsigned; the same process holds the signing key and re-signs on edit (links to P0-1). Dev flag in local `.env` makes the key a public constant if `ELONE_PLAYBOOK_SIGNING_KEY` is ever removed.

### P2 — Medium
1. **Tenant-agnostic globals**: `/api/config` (writes shared `settings.json`), `/api/telemetry`, usage totals, `sops/index.md` visible/changeable across tenants — contradicts "multi-tenant".
2. `normalize_clearance()` falls back to **L0** for unknown strings (fail-open for resource tiers).
3. Session cookie `Secure` defaults off; no CSP / X-Frame-Options / HSTS / nosniff; `/docs` + `/openapi.json` public; login not CSRF-protected.
4. No rate limiting on upload/ingest/search; upload body fully buffered before size check; `list_uploads` re-hashes and re-validates every file per call; `list_sops` verifies HMAC for every playbook per call (O(N)).
5. MCP server unauthenticated; `plan_sop(file_path)` reads **any** readable path (`_resolve_sop_path`) and ships it to an LLM; `read_playbook`/`list_knowledge_base_playbooks` ignore tenant/clearance.
6. Concurrency hazards: usage-ledger lost updates, `_FILE_SHA_CACHE`/`_INGESTS` are process-local, multi-file publish/delete not atomic.
7. Mismatched model configuration (README vs `settings.json` vs `llm_config.py`); `lru_cache` on `get_llm` freezes provider choice and timeouts until restart; cost table prices non-Mistral/Gemini models incorrectly; hard-coded `model=` in `record_call`.
8. Overview "Gates" panel is static marketing text (`routes_telemetry.py:117-211`): cites non-existent `core/*.py`, "≤10 MB", "5 images", "Mistral Small", and marks the unused link-scraper/SSRF gate "active". Operators may over-trust it.
9. Missing tests for: P0-1, P1-1…P1-3, concurrency, frontend, OIDC with real JWKS.
10. Test-suite hermeticity (needs `ELONE_PLAYBOOK_SIGNING_KEY`, LLM keys), undeclared dev deps (`deepeval`).
11. Error leakage: raw `str(e)` returned as 400/500 bodies (e.g. missing signing key text; filesystem paths).
12. Pre-`74ff7c7` git history may contain sensitive/client content (commit message says untracked/scrubbed) — audit history before any external sharing.

### P3 — Low / maintainability
- README/backend README stale: "14-state" (18 states), "91 tests" (152 collectable), `core/` directory (now `agents/`), model table, "AST sandbox" (regex).
- Dead/duplicate code: scheduler stub, msg/1.0 parallel pipeline, `draft_store` write helpers, `rulebook_manager` stub, redundant `pipeline_config.json`, `ELONE_DEV_SEED_USERS`, `run.py` blocked modes, `api.runScan` in SPA.
- `pyproject.toml` vs `requirements.txt` drift; Postman collection stale; `.agents/` tracked despite `.gitignore` (also leaks a local username path).
- `config_audit.jsonl` is written under `backend/knowledge_base/logs/` (different from `KB_DIR`) and invisible in the Audit view.
- `ttl_minutes` non-numeric → 500; many `except: pass`/`except Exception: pass` blocks hide failures (manifest writes, log writes).
- Hard-coded `verified: True` on purpose/scope/notes/preconditions/exceptions in canonical build — only steps are really quote-verified, so "traceability %" measures steps only.
- Retrieval audit trail is in-memory and unbounded; `include_full_content` never exposed (agents must fetch steps via `/api/sops/{id}`).
- Same-name uploads overwrite each other within a tenant; `logs/images/<slug>` is not tenant-scoped.
- Duplicate path logic (`KB_DIR` resolution repeated in 6 modules).

## C. Technical debt & architecture notes
- The ingest pipeline is a 500-line route function (`api_ingest_single`) — extract into a service so CLI, API and tests share one implementation (removes the msg/1.0 duplication).
- Auth is enforced by calling `authenticate_request` inside every handler; a forgotten call = open endpoint. Prefer router-level dependencies and a test that enumerates all routes and asserts an auth requirement (only `/api/health`, `/api/auth/login` and docs should be public).
- Filesystem-as-database will not scale: O(N) globbing and YAML parsing on hot paths.
- Frontend has no build, types or tests; cache-busting is manual.

## D. Recommended order of work
1. P0-1 (close the post-publication bypass) + regression test.
2. P1-1/P1-2/P1-3 (DLP, validator fail-closed, command policy) with tests built from `tests/golden_set/adversarial`.
3. P1-4/P1-5 (declare deps, single-worker note, per-request claims lookup, token TTL cap) → then DB migration.
4. P2 hardening (headers, Secure cookie, tenant-scoped config/telemetry, MCP auth, route-auth enumeration test).
5. Docs/README correction and CI (pytest + lint), then remove dead code.
