# 07 — Data Storage ("Database") Documentation

**There is no SQL/NoSQL database.** All persistence is JSON / Markdown / binary files under `knowledge_base/` (override `ELONE_KB_DIR`), plus two JSON files in `backend/` (`config/settings.json`, `gemini_monitor/daily_usage.json`). No migrations framework, no seed data (users must be created with `python -m auth.cli`), no foreign-key enforcement — referential integrity is maintained by application code only.

## 1. File inventory
| Path | Format | Owner module | Contents |
|---|---|---|---|
| `_auth/users.json` | `{schema_version, updated_at, users:[UserRecord]}` | `auth/user_store.py` | accounts incl. scrypt hash |
| `_auth/revoked_tokens.json` | `{jti: exp_epoch}` | `auth/tokens.RevocationStore` | revoked ids, auto-pruned |
| `_auth/auth_events.jsonl` | JSONL append-only | `auth/dependencies.log_auth_event` | login/logout/denied/config events (never tokens) |
| `_uploads/<tenant>/<file>` | raw docs | `api/context`, `routes_ingestion` | tenant-namespaced uploads (legacy flat files in `_uploads/` still resolved) |
| `_uploads/_upload_owners.json` | `{"<tenant>/<file>": {uploaded_by,sha256,…}}` | context | upload provenance |
| `_uploads/_processed_manifest.json` | `{"<tenant>::<file>": {status,sop_id,job_id,task_id,sha256,…}}` | context | UI status cache (derived; reconciled on list) |
| `_uploads/_governance_ledger.json` | `{job_id: JobRecord}` | `orchestrator/ledger.py` | **authoritative lifecycle state + full history** |
| `_uploads/_drafts/<SOP>.draft.json` | `{draft, canonical_draft, raw_filename, tenant_id, uploaded_by, task_id, job_id, sop_id, last_editor?, …}` | `routes_ingestion`, `routes_governance` | staged unapproved work (contains `raw_text`) |
| `_uploads/_retrieval_catalog.json` | `{sop_id: IndexedSOP}` | `a6_hub/retrieval_catalog.py` | searchable published SOPs incl. full canonical |
| `sops/<category>/<SOP>.md` | YAML frontmatter + Markdown | `okf_builder`, `canonical_builder.sync_*` | executable playbook, `integrity_hmac_sha256` |
| `sops/<category>/<SOP>.canonical.json` | Canonical SOP 1.0 | `canonical_builder` | audit/governance record |
| `sops/index.md`, `sops/<cat>/index.md` | Markdown | `okf_builder._update_sops_catalog_indexes` | **cross-tenant** catalog listing |
| `patterns/<cat>/rules_<SOP>.md` | Markdown table | `okf_builder` | empty "reflection rulebook" |
| `_trash/<stamp>_<SOP>/…` + `_manifest.json` | mirrored files | `routes_playbooks.api_delete_sop` | soft-deleted artefacts |
| `logs/debug/*_full_debug.log`, `logs/parser/*.log`, `logs/converter_input/*.log`, `logs/images/<slug>/`, `logs/web_cache/`, `logs/<YYYY-Www>.md`, `logs/_log_owners.json` | text/JSON | various | audit traces; `converter_input` holds the exact text sent to the LLM |
| `backend/knowledge_base/logs/config_audit.jsonl` | JSONL | `config/settings.audit_config_change` | config change audit — **path is relative to `backend/`, not `KB_DIR`, and not visible in `/api/logs`** |
| `backend/gemini_monitor/daily_usage.json` | `{YYYY-MM-DD: {...,call_history[]}}` | `gemini_monitor/monitor.py` | LLM usage & cost, global |
| `backend/config/{settings,pipeline_config}.json` | JSON | `config/settings.py` | tunable limits (tracked in git; rewritten at runtime) |

## 2. Logical entities and relationships

```mermaid
erDiagram
  TENANT ||--o{ USER : "tenant_id"
  TENANT ||--o{ JOB : "tenant_id"
  USER ||--o{ JOB : "uploaded_by (identity string)"
  JOB ||--o| REVIEW_TASK : "embedded review_task"
  JOB ||--o| APPROVAL_DECISION : "embedded approval_decision"
  JOB ||--o| QUARANTINE_INCIDENT : "embedded incident"
  JOB ||--o{ HISTORY_EVENT : "embedded history[]"
  JOB ||--o| DRAFT : "sop_id (file name)"
  JOB ||--o| PLAYBOOK : "sop_id after publish"
  DRAFT ||--|| CANONICAL_DRAFT : embeds
  PLAYBOOK ||--|| CANONICAL_SOP : "same sop_id, other file"
  CANONICAL_SOP ||--o| CATALOG_ENTRY : "index_published_sop"
  UPLOAD ||--o{ JOB : "content_sha256"
  UPLOAD ||--o| MANIFEST_ENTRY : "tenant::filename"
  USER { string sub PK; string username; string identity; string password_hash; list roles; string tenant_id; string clearance; string actor_type; bool disabled }
  JOB { string job_id PK; string sop_id; string tenant_id; int version; string content_sha256; string uploaded_by; string current_state; bool purged }
  REVIEW_TASK { string task_id PK; string status; string due_date; string reviewer }
  APPROVAL_DECISION { string decision; string reviewer; string canonical_sha256; string draft_sha256; string content_sha256 }
  CANONICAL_SOP { string sop_id; string tenant_id; json classification; json quality; json lifecycle; list steps }
  CATALOG_ENTRY { string sop_id PK; string tenant_id; string classification_level; string citation }
```

Keys & uniqueness
- `UserRecord.sub = usr_<12hex>`; username & identity unique (case-insensitive) — enforced in `create_user` under a lock.
- `job_id = job_<sha[:10]>[_rN]`; `sop_id = SOP-<SHA[:6]>` unless overridden; `_allocate_sop_id` appends a tenant tag when another tenant already owns the id.
- The **retrieval catalog is keyed by `sop_id` alone** (global key space); cross-tenant protection depends on `_allocate_sop_id`.
- Job-per-SHA duplicate rule: same tenant + same SHA with state ∈ {approved, published, awaiting_review, changes_requested} ⇒ new job becomes `duplicate` (unless `reingest` and none published).

## 3. Data validation
- Pydantic: `CanonicalSOPModel` (`schemas/canonical_sop_schema.py`, validated by `validate_canonical_sop_dict`), `OKFPlaybookModel` (`schemas/okf_schema.py`), `JITFaithfulnessInspectionResult`, msg/1.0 models.
- Regex: tenant `^[a-z0-9][a-z0-9_-]{1,62}$`, username `^[A-Za-z0-9][A-Za-z0-9._@-]{1,63}$`, sop id `[A-Za-z0-9_-]+`.
- `UserRecord.from_dict(cls(**data))` has no schema/versioning; a malformed `users.json` raises on load (no repair).

## 4. Lifecycle ledger — states (18, not 14)
`received, extracting, scanning, structuring, assessing, correcting, awaiting_review, changes_requested, approved, published, deactivated, archived, soft_deleted` + terminal `quarantined, rejected, duplicate, failed, blocked`. Transition table: `schemas/governance_models.ALLOWED_TRANSITIONS`. Notes: `awaiting_review → awaiting_review` is allowed (draft edit log); `approved → awaiting_review` and `awaiting_review → structuring` are allowed; **no route performs `deactivate/archive/restore`** (ledger methods exist; only delete → `soft_deleted` is reachable via API); `blocked` is reachable only from the AST gate in practice.

## 5. Important data flows during business operations
- **Ingest** → creates `JobRecord(received)`, appends history on each transition, writes `_drafts/<SOP>.draft.json`, upserts manifest, writes `logs/debug/*_full_debug.log` and `_log_owners.json`.
- **Approve** → mutates `job.review_task`, `job.approval_decision`, `job.gate_results`, state→`approved`; rewrites draft file with approval stamp; updates manifest. Rolls back in-memory job if draft write fails.
- **Publish** → state→`published`; writes `.md` + `.canonical.json` + rulebook + index.md; `retrieval_index.index_published_sop`; deletes draft; manifest `status=success`. Rolls back ledger if file/index write fails.
- **Delete** → moves files to `_trash`, `purge_sop` from catalog, ledger → `soft_deleted`, manifest entries removed, drafts moved.

## 6. Transaction handling
No transactions. Safety = (a) atomic single-file replace, (b) in-process RLocks, (c) manual rollback of the in-memory job in `record_decision`/`publish`. Multi-file operations (publish, delete) are **not atomic**: a crash between steps leaves partial state (e.g. `.md` written but catalog not updated). `GET /api/uploads` contains self-healing logic for such orphans.

## 7. Indexes
None; every lookup scans `_jobs.values()` or `glob`s `sops/**/*.md` (O(N) per request, with YAML parse + HMAC per file in list endpoints).
