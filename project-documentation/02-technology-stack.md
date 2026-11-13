# 02 — Technology Stack

## Languages
- **Python 3.10+** (venv uses CPython 3.11) — entire backend.
- **JavaScript (ES modules, no bundler/transpiler)**, HTML5, CSS3 — frontend SPA.
- JSON / YAML / Markdown as the persistence formats.

## Backend (`backend/requirements.txt`, `backend/pyproject.toml`)
| Concern | Library | Where used |
|---|---|---|
| Web framework | FastAPI (`fastapi>=0.115`) + Starlette (static files, threadpool) | `server.py`, `api/*` |
| ASGI server | **uvicorn** — *imported in `server.py` but NOT listed in `requirements.txt` or `pyproject.toml`* | `server.py:129` |
| Validation / models | Pydantic v2 | `schemas/*` |
| Auth | PyJWT[crypto] (HS256 local, RS/ES via JWKS), stdlib `hashlib.scrypt` | `auth/*` |
| Doc parsing | MarkItDown, PyMuPDF (`fitz`), python-docx | `agents/a1_ingestion/*` |
| Web scraping | requests, beautifulsoup4 (link scraper — **not wired into the live pipeline**) | `link_scraper.py` |
| LLM orchestration | LangChain core + `langchain-mistralai`, `-google-genai`, `-openai` (used for Groq, Z.ai, OpenRouter via OpenAI-compatible endpoints), `-nvidia-ai-endpoints`, `langchain-groq` | `config/llm_config.py` |
| MCP | `mcp` (FastMCP / MCPServer) | `mcp_server.py` |
| Config / env | python-dotenv | `config/settings.py`, `config/llm_config.py` |
| Front-matter YAML | pyyaml, python-frontmatter | `okf_builder.py`, `canonical_builder.py` |
| Console UX | rich | `utils/pipeline_logger.py` |
| Tests | pytest; **deepeval** used by `tests/deepeval/*` but not in requirements | `tests/` |

## Frontend (`frontend/`)
- Hand-written ES-module SPA: `js/app.js` (router/shell), `js/api.js` (single fetch client), `js/auth.js`, `js/ui.js` (helpers, `esc()` HTML escaping, modal/toast), `js/charts.js` (custom SVG charts), `js/progress.js`, 11 view modules under `js/views/`.
- Import-map based cache busting (`?v=20261112c` in `index.html`) — manual version bumps required.
- Only external runtime dependency: **Google Fonts** (Inter, JetBrains Mono, Outfit) via `<link>`. No JS CDN libs.
- No npm, no build, no frontend tests.

## LLM providers (all optional, chosen by env)
Gemini, Mistral (multi-key rotation `MISTRAL_API_KEY[2|3]`), Groq (4 key slots), Z.ai/GLM, OpenRouter, NVIDIA NIM. Defaults in code (`config/llm_config.py`): planning = Mistral `codestral-latest`, validation = Mistral `codestral-latest`, VLM = NVIDIA `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`, fallbacks = Groq `qwen/qwen3.8-27b` (VLM: OpenRouter then NVIDIA llama-3.2-11b-vision).

## Infrastructure / tooling
- **No Dockerfile, no docker-compose, no CI workflow, no IaC** in the repo (`git ls-files` shows none).
- Launchers: `start.ps1`, `start.bat`, `backend/start.ps1`, `backend/start.bat`.
- `postman/` — Postman collection + environment (outdated: lacks auth, drafts, delete endpoints).
- `.agents/` — local AI-assistant skills/rules (Obsidian MCP config, code-review skills). Not part of the app. It is **tracked in git although `.gitignore` lists `.agents/`**.

## Persistence
Plain files under `knowledge_base/` (see [07](07-database-documentation.md)); JSON written atomically via temp file + `os.replace`. In-process `threading.RLock`s guard concurrent access; no cross-process locking.

## Configuration surfaces (three overlapping ones)
1. Environment / `.env` (`backend/config/llm_config.py`, `auth/config.py`, `utils/security.py`).
2. `backend/config/settings.json` (+ mirrored `pipeline_config.json`) — hot-reloadable limits via `config/settings.py` and `/api/config`.
3. Hard-coded defaults in `settings._DEFAULT_CONFIG`.
Model/provider selection is read **only** from env in `llm_config.py`; the `llm_models` block in `settings.json` is *not consumed by the LLM builder* (see 10 and 13).
