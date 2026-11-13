# 06 — API Reference

Base URL (dev): `http://127.0.0.1:8000`. 43 REST routes + `/docs`, `/redoc`, `/openapi.json` (**public**, unauthenticated) + static SPA at `/`.

**Auth conventions**
- Credential = `Authorization: Bearer <jwt>` *or* cookie `elone_session`. If both present, header wins.
- Cookie-authenticated **POST/PUT/PATCH/DELETE** require `X-CSRF-Token` == cookie `elone_csrf`. Bearer requests skip CSRF. GETs never check CSRF.
- "human" = `actor_type == human`. Roles: PO=process_owner, SR=security_reviewer, AD=admin, AG=agent.
- Errors from the auth layer: `{"error": "...", "error_code": "..."}` with 401 (`auth_required`, `token_invalid`, `token_expired`, `token_revoked`, `account_disabled`) or 403 (`insufficient_role`, `not_human`, `tenant_isolation`, `insufficient_clearance`, `csrf_invalid`).
- Tenant & clearance always come from the token, never from body/query.

**Inconsistency to know about**: success/error bodies vary (`{"error"}`, `{"error","error_code"}`, `{"success":false,"status":…}`, `{"status":"success"}`, raw objects). The SPA copes via `ApiError` + `soft` mode.

## 1. Authentication (`routes_auth.py`)
| Method & path | Auth | Request | Success | Errors / notes | UI caller |
|---|---|---|---|---|---|
| POST `/api/auth/login` | public | `{username,password}` | `{access_token,token_type,expires_in,csrf_token,user}` + 2 cookies | 400 `missing_credentials`; 401 `invalid_credentials`; 429 `rate_limited` (+`Retry-After`) | `auth.js` |
| POST `/api/auth/logout` | any role, CSRF | — | `{status:"logged_out"}`; revokes jti, clears cookies | 401 | `app.js` |
| GET `/api/auth/me` | any | — | `{user,capabilities}` | 401 | `auth.initAuth` |
| GET `/api/auth/users` | AD | — | users in caller's tenant | 403 | settings |
| POST `/api/auth/users` | AD, CSRF | `{username,password,roles,clearance,identity?,display_name?,agent_id?,agent_persona?,disabled?}` | 201 `{status:"created",user}` | 400 validation; 403 other tenant; 409 duplicate | settings |
| PATCH `/api/auth/users/{sub}` | AD, CSRF | any of `roles,clearance,display_name,disabled,password,agent_persona` | `{status:"updated",user}` | 400 `self_lockout_prevented`; 403 tenant; 404 | settings |
| POST `/api/auth/users/{sub}/token` | AD, CSRF | `{ttl_minutes?}` | `{access_token,jti,expires_in,user}` | 400 if target not `agent`/disabled | settings |

## 2. Ingestion (`routes_ingestion.py`)
| Method & path | Auth | Request | Response | Notes |
|---|---|---|---|---|
| GET `/api/uploads` | PO, AD (human) | — | `{tenant_id,files[{filename,status,sop_id,job_id,task_id,gate1_*,reingest_allowed,…}],allowed_extensions,max_size_mb}` | re-runs Gate 1 + SHA-256 on every file each call (perf) and may rewrite the manifest |
| POST `/api/uploads/upload` | PO, CSRF | multipart `file` | `{success,filename,gate1_passed,gate1_error,metadata}` | 400 ext/size; whole file read into RAM first; invalid files stay on disk |
| POST `/api/uploads/ingest` | PO, CSRF | `{filename, sop_id?, reingest?}` (`uploaded_by`/`tenant_id` ignored) | 200 `awaiting_review` (+draft, canonical_draft, quality, confidentiality) / 200 `unactionable` / 200 `cancelled` | 400 `REJECTED_GATE_1`; 403 `quarantined` or `blocked` (`ast_threat_detected`); 404; 409 `duplicate`/`already_running`; 500 `INGESTION_ERROR`. Long-running (LLM calls) |
| POST `/api/uploads/ingest/cancel` | PO, CSRF | `{filename}` | `{status:"cancelling"|"not_running"}` | tenant-scoped |
| POST `/api/uploads/scan` | PO, CSRF | — | **410** `UNGOVERNED_SCAN_DISABLED` | intentionally disabled |
| POST `/api/plan-preview` | PO, CSRF | `{filename}` | `{success,draft,filename,tenant_id}` | LLM call, **no quarantine/AST pre-scan, no ledger entry** |

## 3. Governance (`routes_governance.py`)
| Method & path | Auth | Purpose / key rules |
|---|---|---|
| GET `/api/governance/jobs` | any human | tenant's jobs (reloads ledger from disk) |
| GET `/api/governance/jobs/{job_id}` | any human | 404, 403 tenant |
| GET `/api/governance/review-tasks` | any human | tenant + clearance filtered; adds `sop_tier,is_overdue,eligible_for_me` |
| POST `/api/governance/review-tasks/{task_id}/decision` | **SR**, CSRF | body `{decision: approve|changes_requested|reject, notes?, confirmed_classification?:true}`. Errors: 403 `separation_of_duties`/`not_human`/`insufficient_clearance`; 400 `gates_failed{failures[]}`, `invalid_state`; 404 |
| POST `/api/governance/sops/{sop_id}/publish` | **PO**, CSRF | body ignored. 409 `stale_approval`; 400 `not_approved`/`gates_failed`; 404 |
| GET `/api/governance/sops/{sop_id}/canonical` | any role | published canonical, or draft canonical for humans only; tenant+clearance; agents only if `state==published` |
| PUT `/api/governance/sops/{sop_id}/canonical` | PO, AD, CSRF | **published SOPs only**; replaces canonical file with body (forces `sop_id`, `tenant_id`, `lifecycle.state=published`) and re-signs playbook. No gates (see 13) |
| POST `/api/governance/sops/{sop_id}/sync-playbook` | PO, AD, CSRF | body `{canonical_sop}` or canonical itself; regenerates `.md` + HMAC |
| GET `/api/governance/drafts/{sop_id}` | any human | `{steps, editable, editable_reason, last_editor, last_review_decision, …}` |
| PUT `/api/governance/drafts/{sop_id}/steps` | PO, CSRF | `{steps:[{ref?,sop_step_description,command,fallback_command,source_quote,parse_instruction,comm_inputs}]}`; 422 validation/AST; 409 wrong state |
| PUT `/api/governance/drafts/{sop_id}/canonical` | PO, CSRF | `{canonical:{…}}` ≤ 300 KB; protected keys must be unchanged |
| POST `/api/governance/drafts/{sop_id}/resubmit` | PO, CSRF | `{notes?}`; 409 `invalid_state` |
| POST `/api/governance/downstream/search` | any role, CSRF(cookie) | `{query,department?,limit≤100}` → `{results[],count,caller_*}` |
| GET `/api/governance/downstream/stats` | any role | tier counts for caller tenant |
| GET `/api/governance/incidents` | SR, AD | quarantine incidents |
| GET `/api/config` | AD | full active config (incl. file+env overlay) |
| POST/PUT `/api/config` | AD, CSRF | allow-listed numeric keys (`file_upload.*`, `images.*`, `governance.*`); 422 `{error,details[]}`; global effect |

## 4. Playbooks (`routes_playbooks.py`)
| Method & path | Auth | Notes |
|---|---|---|
| GET `/api/sops` | any role | tenant+clearance filtered; agents see published only; **recomputes HMAC for every playbook on every call** |
| GET `/api/sops/{sop_id}` | any role | frontmatter, body, raw_content, integrity, rulebook |
| POST `/api/sops/{sop_id}/verify` | any role, CSRF | `{is_valid,status:AUTHENTIC|TAMPERED_OR_CORRUPT,reason,metadata}` |
| DELETE `/api/sops/{sop_id}` | **AD**, CSRF | body `{reason}`; soft delete to `_trash` |

## 5. Telemetry & diagnostics (`routes_telemetry.py`)
| Method & path | Auth | Notes |
|---|---|---|
| GET `/api/health` | **public** | `{status,service,timestamp,auth_enabled}` |
| GET `/api/overview` | any human | stats (tenant-scoped), static `gates` array, usage (AD only) |
| GET `/api/scheduler` | any human | stub state (`disabled:true`) |
| GET `/api/tools` | PO, AD | platform schemas |
| GET `/api/telemetry` | AD | **global** (all tenants) LLM usage history |
| GET `/api/logs`, `/api/logs/{filename}` | AD | text logs for caller's tenant; filename must be a bare `*.log` |
| POST `/api/security/test` | SR, AD, CSRF | `{payload,type: all|dlp|ast|unicode}` |

## Frontend → endpoint map
`overview.js`: overview/jobs/review-tasks/incidents · `playbooks.js`: sops, verify, delete · `review.js`: decision, publish, canonical GET/PUT, sync-playbook · `review-task.js`: tasks, canonical, job, draft GET, steps/canonical PUT, resubmit · `ingestion.js`: uploads, upload, ingest, plan-preview · `catalog.js`: search, stats · `settings.js`: config, users · `telemetry.js`, `audit.js`, `tools.js`, `security.js`: one endpoint each. `api.cancelIngest` and `api.runScan` exist in `api.js`; `runScan` hits the disabled endpoint.

## Validation & API-security observations
- ✅ SOP ids validated by `[A-Za-z0-9_-]+`; log filenames basename-checked; tenant ids regex-checked.
- 🟡 `ttl_minutes` unvalidated (non-numeric → 500; no max).
- 🟡 Several handlers swallow body parse errors (`except: body = {}`), so malformed JSON silently becomes defaults.
- 🟡 Business errors often returned as HTTP 400 with raw `str(e)` (information leakage of paths/config errors, e.g. missing signing key message seen in tests).
- ❌ No rate limiting except login; no pagination on list endpoints; no request size limits except upload/canonical.
- ❌ `/docs` & `/openapi.json` public.
- Postman collection is stale (no auth/draft/delete routes; calls `/downstream/stats?tenant_id=` which is ignored).
