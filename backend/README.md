# Elone Agent — Backend Architecture & Services

All backend services, LLM orchestration, security verification gates, schedulers, and API endpoints are organized inside this `backend/` directory.

---

## 📁 Backend Directory Structure

```
backend/
├── server.py              # Starlette/Uvicorn REST API bridge & static frontend host
├── run.py                 # Standalone CLI runner for single SOP conversion & watchers
├── scheduler.py           # Scheduled background polling worker for uploads directory
├── mcp_server.py          # FastMCP server exposing tools for MCP clients
├── debug_run.py           # Debug runner capturing full internal reasoning traces
├── test_standalone.py     # Standalone regression test suite
├── requirements.txt       # Python dependencies
├── pyproject.toml         # Project metadata & build configuration
├── .env                   # Environment variables (API keys, quota limits)
├── start.bat              # Windows batch launcher for backend server
├── start.ps1              # PowerShell launcher for backend server
├── core/                  # Core Ingestion & Security Engine
│   ├── input_validator.py # Gate 1: Magic-byte, 10MB/10-page quota checks
│   ├── document_parser.py # Physical-order document walker
│   ├── vlm_inspector.py   # Gate 3: VLM Vision OCR & dimension downscaling
│   ├── link_scraper.py    # Gate 4: SSRF protection & web quarantine
│   ├── jit_converter.py   # Gate 5: 6-Stage Command CoT reasoning & XML sandboxing
│   ├── plan_validator.py  # Gate 6: Dual-Layer AST blacklist & Mistral audit
│   └── security.py        # Gate 7: HMAC-SHA256 digital stamps & DLP redactor
├── config/                # Platform Configurations & Tool Catalogs
│   ├── llm_config.py      # Multi-model router (Gemini, Mistral, NVIDIA)
│   └── tool_catalog.py    # Registered IT platform tools & schemas
├── tools/                 # Dynamic IT Tool Provider Definitions
├── prompts/               # System and CoT prompts for converter and validator
├── schemas/               # Pydantic schemas and OKF data models
├── gemini_monitor/        # Telemetry, daily usage tracker & cost calculator
└── elone_sop/             # Core package interface
```

---

## 🚀 Running the Backend

From the repository root:
```powershell
.\start.ps1   # or double-click start.bat
```
Or directly from `backend/`:
```powershell
cd backend
python server.py
```

### CLI Runners
* **Process a single SOP:**
  ```bash
  python backend/run.py --file knowledge_base/_uploads/my_sop.pdf
  ```
* **Run full ingestion scan cycle:**
  ```bash
  python backend/run.py --scan
  ```
* **Start background watcher:**
  ```bash
  python backend/run.py --watch
  ```
* **Launch MCP Server:**
  ```bash
  python backend/mcp_server.py
  ```
