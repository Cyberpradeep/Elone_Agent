# 12 — Deployment & Local Setup Guide

Only commands/files that exist in the repo are listed. **No Dockerfile, compose file, Kubernetes manifest, Terraform, CI pipeline or production server config exists** — anything beyond local development is *not provided* and would have to be created.

## 1. Prerequisites
- Python 3.10+ (the checked-in `venv/` uses 3.11.15; installed: uvicorn 0.54.0, fastapi 0.162.5, PyJWT 2.15.1).
- Windows launchers are provided; the code itself is OS-neutral (paths via `os.path`).
- At least one LLM provider key for real ingestion (Mistral recommended by current defaults) and an NVIDIA/OpenRouter key if documents contain images.

## 2. Install dependencies
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
pip install uvicorn          # REQUIRED but missing from requirements.txt / pyproject.toml
pip install deepeval         # optional: only for tests\deepeval
```
`pyproject.toml` (setuptools, entry points `elone-sop`, `elone-sop-debug`, `elone-sop-mcp`) omits FastAPI, PyJWT, uvicorn, python-multipart and lists a different dependency set than `requirements.txt`; use requirements.txt.

## 3. Environment variables
Copy `.env.example` → `.env` (repo root; `backend/.env.example` is an older/shorter variant). Loaded with `python-dotenv` by `config/settings.py` and `config/llm_config.py`.

| Variable | Purpose | Notes |
|---|---|---|
| `MISTRAL_API_KEY[,2,3]`, `GROQ_API_KEY*`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY`, `ZAI_API_KEY`, `GOOGLE_API_KEY` | provider keys | key rotation via numbered vars |
| `PLANNING_PROVIDER/MODEL`, `VALIDATION_PROVIDER/MODEL`, `VLM_PROVIDER/MODEL`, `GROQ_MODEL` | choose models | **the only effective model selectors** |
| `ELONE_JWT_SECRET` | HS256 secret ≥16 chars | **required** unless dev flag |
| `ELONE_PLAYBOOK_SIGNING_KEY` | HMAC key for playbooks | **required** unless dev flag; *absent from both `.env.example` files* |
| `ELONE_ALLOW_INSECURE_DEV_KEY=1` | dev/test only: ephemeral JWT secret + constant HMAC key | never in production |
| `ELONE_ALLOWED_ORIGINS` | CORS allow-list (default `http://127.0.0.1:8000,http://localhost:8000`) | `*` rejected |
| `ELONE_AUTH_MODE` | `local` \| `oidc` \| `hybrid` + `ELONE_OIDC_*` | |
| `ELONE_TOKEN_TTL_MINUTES` (30), `ELONE_AGENT_TOKEN_TTL_MINUTES` (480) | | |
| `ELONE_LOGIN_MAX_ATTEMPTS` (5), `ELONE_LOGIN_WINDOW_SECONDS` (300) | lockout | |
| `ELONE_DEFAULT_TENANT` (`tn_northwind`), `ELONE_COOKIE_SECURE` (false) | | set `true` behind HTTPS |
| `ELONE_KB_DIR`, `ELONE_AUTH_DIR`, `ELONE_USERS_PATH`, `ELONE_REVOKED_TOKENS_PATH`, `ELONE_AUTH_AUDIT_LOG_PATH` | storage overrides | |
| `MAX_FILE_SIZE_MB`, `MAX_PAGE_COUNT`, `MAX_IMAGES_PER_SOP`, `MAX_DAILY_CALLS`, `UNLIMITED_DAILY_CALLS`, `EXECUTION_MODE` (`command_only`/`auto`), `ELONE_ENABLE_TRIAGE`, `ELONE_ENABLE_TOOL_INSPECTION` | overlay on `settings.json` (env wins) | |
| `ELONE_DEV_SEED_USERS` | listed in `.env.example` but **not implemented** | |

Minimum working dev `.env` (values are placeholders — generate your own):
```
ELONE_JWT_SECRET=<32+ random chars>
ELONE_PLAYBOOK_SIGNING_KEY=<32+ random chars>
MISTRAL_API_KEY=<key>
NVIDIA_API_KEY=<key>          # only if SOPs contain screenshots
```

## 4. First-run bootstrap (there is no seed data)
```powershell
cd backend
python -m auth.cli create-user --username alice  --role process_owner     --tenant tn_northwind --clearance L1
python -m auth.cli create-user --username sam    --role security_reviewer  --tenant tn_northwind --clearance L3
python -m auth.cli create-user --username admin  --role admin              --tenant tn_northwind --clearance L3
python -m auth.cli issue-agent-token --tenant tn_northwind --clearance L1 --agent-id agent_demo --persona service_desk_agent
python -m auth.cli list-users
```
(passwords prompted interactively; min 8 chars). The current working tree has **no `users.json`**, so nobody can log in until this is done.

## 5. Run locally
```powershell
.\start.ps1                 # or start.bat — cd backend; python server.py; opens http://127.0.0.1:8000
# equivalent:
cd backend ; python server.py      # uvicorn.run("server:app", host=127.0.0.1, port=8000, reload=True)
```
Swagger: `/docs`, ReDoc `/redoc`, health `/api/health`. Dashboard served at `/`.
Other entry points: `python backend/mcp_server.py` (stdio MCP; `--test` harness), `python backend/trace_pipeline.py --file <sop>` (governed CLI), `python backend/run.py --models|--status`, `python backend/debug_run.py --file <sop>` (read-only preview).

## 5a. Build
None needed (no bundler/compile step). Frontend cache-busting: bump `?v=` strings in `frontend/index.html` when changing JS/CSS.

## 6. Tests
See [11](11-testing-quality.md): `python -m pytest tests -q --ignore=tests\deepeval` from `backend/` with the two env vars set.

## 7. Moving toward production — what is missing (not invented, just absent)
| Need | Current state |
|---|---|
| Process manager / ASGI config | `reload=True`, bound to 127.0.0.1; no gunicorn/uvicorn workers config. **Do not run >1 worker** (in-memory ledger/catalog/rate-limiter/lockout) |
| TLS & cookies | none; set reverse proxy TLS + `ELONE_COOKIE_SECURE=true`; also `get_client_ip` uses the socket peer, so behind a proxy all clients share one lockout key |
| Secrets | `.env` file only; no vault integration |
| Database | none — move users/ledger/catalog to a transactional DB before multi-instance use |
| Backups | none; back up `knowledge_base/` (esp. `_auth/`, ledger, sops) and `config/*.json` |
| Containers / CI/CD / IaC | none |
| Observability | stdout + `auth_events.jsonl`; no metrics/health beyond `/api/health` (public, shallow) |
| Static asset hosting | served by FastAPI `StaticFiles`; Google Fonts external |
| Config drift | `settings.json` is a *tracked* file rewritten by the admin UI at runtime |

## 8. Operational notes
- Logs & data live in `knowledge_base/`; delete is soft (`_trash/`).
- Daily LLM cost breaker: `governance.max_daily_calls` (settings.json currently 110) — **overridden to unlimited by local `.env` (`UNLIMITED_DAILY_CALLS=true`)**.
- Restarting the server without `ELONE_JWT_SECRET` (dev flag) invalidates all sessions.
