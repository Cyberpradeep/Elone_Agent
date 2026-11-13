# 05 — Feature Documentation

Status legend: ✅ implemented & verified in code · 🟡 partial/with caveats · ❌ not implemented/disabled.

---
## F1. Authentication & sessions ✅
- **Purpose**: identify callers; issue short-lived tokens.
- **Roles**: all.
- **Frontend**: `js/auth.js` (`renderLoginHtml`, `mountLoginView`, `initAuth`), `js/api.js` (credentials: include; attaches `X-CSRF-Token` from `elone_csrf` cookie on non-GET). 401 → `elone:auth-required` event → login screen.
- **Backend**: `routes_auth.api_auth_login` → `user_store.authenticate` (rate limiter, scrypt verify, dummy-hash timing equalisation) → `tokens.create_access_token` (HS256; 30 min; claims sub/identity/roles/tenant/clearance/actor_type/jti/iss/aud/iat/exp) → sets cookies `elone_session` (HttpOnly, SameSite=Lax, path `/api`, Secure only if `ELONE_COOKIE_SECURE`) and `elone_csrf` (readable).
- **Endpoints**: `POST /api/auth/login|logout`, `GET /api/auth/me`.
- **Storage**: `_auth/users.json`, `_auth/revoked_tokens.json`, `_auth/auth_events.jsonl`.
- **Rules**: lockout after 5 failures / 300 s per (IP, username); agent accounts cannot use UI; logout revokes jti; disabled accounts rejected on every request.
- **Caveats**: roles/clearance live inside the token → changes apply only after expiry; no refresh token; no password change/reset endpoint.

## F2. User & service-account administration ✅
Admin-only, tenant-scoped (`routes_auth`, UI `views/settings.js`). Create/patch users; cannot disable self or drop own admin role; `POST /api/auth/users/{sub}/token` mints an agent JWT (default 480 min; optional `ttl_minutes` is clamped only to a **minimum** of 60 s — there is **no maximum**, so an admin can mint a multi-year token; non-integer `ttl_minutes` raises an unhandled 500). `auth/cli.py` bootstraps first users (no seeding exists — `ELONE_DEV_SEED_USERS` appears only in `.env.example`).

## F3. Document upload & Gate 1 ✅
- **Backend**: `api_upload_file` — `sanitize_filename`, extension allow-list, size check *after* reading whole body into memory, writes to `_uploads/<tenant>/`, records owner in `_upload_owners.json`, then `validate_sop_file` (extension, size, magic bytes, zip-bomb ratio/size, page/line/word/row caps). **Invalid files remain on disk** (flagged `gate1_passed=false`).
- **UI**: `views/ingestion.js`. **Role**: process_owner (admin may list).
- `GET /api/uploads` reconciles files ↔ ledger jobs ↔ drafts ↔ published playbooks ↔ manifest to compute a per-file status (success, awaiting_review, approved, rejected, quarantined, failed, unactionable, pending).

## F4. Governed ingestion pipeline ✅ (core feature)
`POST /api/uploads/ingest` (`routes_ingestion.api_ingest_single`). Detailed in [09](09-business-workflows.md). Highlights: single in-flight job per (tenant, file) (`_INGESTS`), cooperative cancel (`/ingest/cancel` via thread-local event checked before each LLM call), duplicate detection by SHA-256 per tenant, `reingest` supersedes unpublished jobs, outputs a staged draft + review task.

## F5. Secret quarantine ✅/🟡
After extraction: `redact_sensitive_dlp` counts passwords/API keys/private keys → `ledger.trigger_quarantine` → incident `INC-xxxxxx`, source file + parser log deleted, **no LLM call**. 🟡 Caveats in [08](08-authentication-security.md#dlp) (PDF/DOCX path pre-redacts so only some secret types still trigger quarantine; placeholder substrings such as "reset" disable detection; screenshots not scanned).

## F6. Threat scan (“AST sandbox”) 🟡
`scan_raw_sop_for_ast_threats` — **regex blacklist** (10 patterns: encoded PowerShell, IEX, certutil/bitsadmin, `net user /add`, local-admin add, curl/wget to raw IP, curl upload, chmod 777/useradd, mimikatz) after Unicode normalisation, run on raw SOP lines (Stage 2) and on commands (Layer 1 and again at publish gates). It is not an AST parser. Hit → state `blocked`, 403, 0 LLM calls.

## F7. LLM structuring (JIT planner) ✅
`plan_okf_from_raw` — builds enriched text (document text + VLM reports interleaved), escapes `<untrusted_document_payload>` delimiters, optional triage (disabled when `execution_mode == command_only`, which is the shipped setting), up to 3 attempts with error feedback, up to 5 tool turns per attempt (catalog-inspection tools only), per-job call budget (`max_calls_per_job`), tolerant JSON repair (`sanitize_json_text`, `ast.literal_eval`), Pydantic `OKFPlaybookModel`. See [10](10-ai-implementation.md).

## F8. Verification & scoring ✅
- Layer-1 validation (`plan_validator`): malicious patterns, placeholder steps, variable/entity linkage, tool schema, coverage ledger.
- Layer-2 LLM faithfulness/injection audit (fails closed on exceptions, **fails open on unparsable/“valid-looking” output** — see 13).
- `build_canonical_sop_from_draft`: finds quote line ranges in code (`_locate_quote`, ±window), `verify_canonical_quotes`, coverage via `compute_source_line_coverage`, quality `Q = 0.4·C + 0.4·T + 20 − 5·B`, status Ready/Needs attention/Failed checks.
- Confidentiality (`confidentiality_engine`): baseline 5 + secrets 45 + infra (≤25) + PII (≤25) + label 15 + OCR 10 + AI-evidence points; tiers L0 <21, L1 ≤50, L2 ≤75, L3 ≥76. **AI advisory is never supplied in the live path** so `ai_suggested_level == rule_level` and conflict is always false.

## F9. Human review & dual custody ✅
`GET /api/governance/review-tasks` (filtered by tenant + `principal.can_access_tier`, with `eligible_for_me` and overdue flag), `POST …/decision` (security_reviewer only). On *approve* the **server** recomputes all 6 gates (`evaluate_draft_publication_gates`), requires body `confirmed_classification is True` (Gate 6), stamps the draft (approvals list, `classification.confirmed=true`, version, tenant, file hash), stores `canonical_sha256` + `draft_sha256` in the decision. SoD: reviewer ≠ uploader and ≠ last editor (by identity string, case-insensitive). SLA: 24 h if score ≥ 60 or L2/L3 else 48 h (informational — nothing escalates).

## F10. Draft editing & resubmission ✅
Process Owner edits steps (`PUT /drafts/{id}/steps`) or canonical JSON (`…/canonical`, allow-listed keys only, protected keys must be unchanged) in states `awaiting_review`/`changes_requested`. `_apply_step_edits` re-runs the AST scan on new commands, re-extracts the *source* upload, rebuilds quality, **resets `classification.confirmed`**, records `last_editor` (feeds SoD). `POST …/resubmit` moves `changes_requested → awaiting_review` with a new task.

## F11. Publication ✅
`POST /api/governance/sops/{id}/publish` (process_owner). Ignores request body. Requires state `approved`; re-validates id/tenant/file-hash binding; recomputes hashes and gates (`for_publish=True`); `ledger.publish_approved_sop` checks version, content hash, canonical hash, draft hash; writes `.md` (HMAC v2 over *frontmatter*), `.canonical.json`, rulebook, catalog index pages; indexes into retrieval catalog; purges draft; rolls back ledger on write failure.

## F12. Published-SOP maintenance 🟡 (governance gap)
`PUT /api/governance/sops/{id}/canonical` and `POST …/sync-playbook` (process_owner **or** admin) rewrite the canonical JSON and **re-sign** the playbook for an already-published SOP **without** AST scan, gates, quote re-verification, SoD or re-approval. Details in [13](13-gaps-and-recommendations.md) (P0).

## F13. Playbook browsing, integrity check, soft delete ✅
`GET /api/sops`, `GET /api/sops/{id}`, `POST …/verify` (HMAC recomputation via `verify_playbook_before_execution`), `DELETE /api/sops/{id}` (admin; moves files to `_trash/<stamp>_<id>/` with manifest, purges catalog, soft-deletes ledger jobs, cleans manifest/drafts). Not restorable via API (manual copy-back).

## F14. Downstream agent catalog ✅
`POST /api/governance/downstream/search` — tenant, clearance, agent id, persona come from the token only; token-substring relevance scoring, persona boost, department filter, limit ≤ 100; returns summary (no steps). `GET …/downstream/stats`. UI: `views/catalog.js` (humans can use it too).

## F15. Incidents ✅
`GET /api/governance/incidents` (security_reviewer, admin) lists quarantine incidents for the tenant.

## F16. Admin config hot-reload ✅
`GET/POST/PUT /api/config` (admin). Allow-listed keys with type/range validation (`validate_config_updates`); writes `settings.json` **and** `pipeline_config.json`, reloads, audits to `config_audit.jsonl` and auth log. Config is **global**, not per tenant.

## F17. Telemetry & logs ✅/🟡
`/api/telemetry`, `/api/overview` (admin sees usage totals), `/api/logs`, `/api/logs/{file}` (admin; per-tenant attribution via `_log_owners.json` or header regex). Usage store is global and unlocked (see 13). The overview's "gates" panel is **hard-coded text** (refers to non-existent `core/*.py`, says 10 MB / 5 images).

## F18. Security Lab ✅
`POST /api/security/test` (security_reviewer, admin) runs DLP, regex-AST and unicode cleaning on a pasted payload and shows results (`views/security.js`).

## F19. Tool catalog view ✅ (read-only)
`GET /api/tools` → `config/tool_catalog.py` (`TOOL_CATALOG`), 5 platform schemas (solandra, auth0, email, airretailer, mock). Informational only.

## F20. MCP server 🟡
`mcp_server.py` tools: `plan_sop` (LLM draft, no write), `validate_playbook_plan`, `list_knowledge_base_playbooks`, `read_playbook` (HMAC-verified), `get_registered_tool_catalog`, `get_ingestion_scheduler_status`; `ingest_sop`/`scan_uploads_now` return "GOVERNANCE BLOCKED". No authentication/tenant filtering.

## F21. CLI tools ✅/❌
`python -m auth.cli` (create/list/disable/enable users, issue-agent-token) ✅; `trace_pipeline.py` governed tracer ✅ (needs live LLM keys); `run.py --file|--scan|--watch` ❌ disabled; `scripts/migrate_playbook_signatures.py` ✅ one-off v1→v2 HMAC migration.

## Hidden / supporting
- `ELONE_ENABLE_TRIAGE`, `ELONE_ENABLE_TOOL_INSPECTION`, `EXECUTION_MODE` toggles.
- Weekly Markdown creation log `logs/<YYYY-Www>.md` (`okf_builder._log_okf_creation`).
- Per-image VLM artefacts under `logs/images/<slug>/`.
- OIDC/hybrid auth (`ELONE_AUTH_MODE`) — implemented, untested against a live IdP.
