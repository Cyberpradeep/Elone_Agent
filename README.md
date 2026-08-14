# SOP Ingestion Pipeline — Standalone Module

Self-contained, independently testable SOP ingestion pipeline extracted from the L1 Support Agent.

Converts raw SOP documents (PDF, DOCX, TXT, XLSX, PPTX) into structured, execution-ready OKF Playbook markdown files.

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup environment variables
cp .env.example .env
# Edit .env with your API keys (MISTRAL_API_KEY, GOOGLE_API_KEY, etc.)

# 4. Run tests (no API keys needed for basic tests)
python test_standalone.py

# 5. Process a single SOP file
python run.py --file knowledge_base/_uploads/sample_account_unlock.txt

# 6. Scan all files in _uploads/
python run.py --scan

# 7. Start background watcher
python run.py --watch --interval 5
```

## Folder Structure

```
sop_ingestion_standalone/
├── .env.example                # API key template
├── .gitignore
├── requirements.txt            # Python dependencies
├── run.py                      # CLI runner (--file, --scan, --watch, --status)
├── scheduler.py                # Background folder watcher
├── test_standalone.py          # Unit tests
│
├── config/                     # Standalone configuration
│   ├── llm_config.py           # LLM provider initializer
│   └── tool_catalog.py         # Dummy tool catalog for testing
│
├── core/                       # Pipeline engine
│   ├── document_parser.py      # MarkItDown document text extractor
│   ├── jit_converter.py        # 8-Stage CoT LLM converter
│   └── plan_validator.py       # Faithfulness & linkage validator
│
└── knowledge_base/             # Same structure as main app
    ├── _uploads/               # INPUT: Drop raw SOP files here
    ├── sops/                   # OUTPUT: Generated OKF Playbooks
    │   └── index.md            # Master playbook catalog
    ├── patterns/               # OUTPUT: Reflection rulebooks
    └── logs/                   # OUTPUT: System audit logs
```

## How It Works

1. **Parse**: Raw documents are parsed using Microsoft MarkItDown (with PyMuPDF + Vision OCR fallback for scanned PDFs).
2. **Convert**: An 8-Stage Chain-of-Thought LLM prompt converts raw text into structured OKF Playbook JSON, matching steps against the tool catalog.
3. **Validate**: A 2-Layer validator checks (Layer 1: deterministic syntax/linkage, Layer 2: LLM faithfulness).
4. **Write**: Generates dual-representation OKF `.md` files, reflection rulebooks, catalog indexes, and audit logs.

## Integration Back to Main App

When ready to integrate:
- Copy generated playbooks from `knowledge_base/sops/` to the main app's `knowledge_base/sops/`.
- Or import the `core/` modules directly and pass the main app's real `tool_catalog` and `llm_config`.
