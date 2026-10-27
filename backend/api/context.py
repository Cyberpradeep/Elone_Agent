"""
API Shared Context & Infrastructure Singletons
==============================================
Holds shared singletons for OrchestratorLedger, DownstreamRetrievalIndex,
AgentMessageBus, and filesystem paths.
"""

import os
import sys
import json
from typing import Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from orchestrator.ledger import OrchestratorLedger
from orchestrator.bus import AgentBus as AgentMessageBus
from agents.a6_hub.retrieval_catalog import DownstreamRetrievalIndex

KB_DIR = os.getenv("ELONE_KB_DIR")
if not KB_DIR or not os.path.exists(KB_DIR):
    root_kb = os.path.abspath(os.path.join(PROJECT_ROOT, "knowledge_base"))
    if os.path.exists(root_kb):
        KB_DIR = root_kb
    elif os.path.exists(os.path.join(BASE_DIR, "knowledge_base")):
        KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
    else:
        KB_DIR = root_kb

UPLOADS_DIR = os.path.join(KB_DIR, "_uploads")
SOPS_DIR = os.path.join(KB_DIR, "sops")
PATTERNS_DIR = os.path.join(KB_DIR, "patterns")
LOGS_DIR = os.path.join(KB_DIR, "logs", "debug")
MANIFEST_PATH = os.path.join(UPLOADS_DIR, "_processed_manifest.json")
GOVERNANCE_LEDGER_PATH = os.path.join(UPLOADS_DIR, "_governance_ledger.json")
RETRIEVAL_CATALOG_PATH = os.path.join(UPLOADS_DIR, "_retrieval_catalog.json")
DRAFTS_DIR = os.path.join(UPLOADS_DIR, "_drafts")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(SOPS_DIR, exist_ok=True)
os.makedirs(PATTERNS_DIR, exist_ok=True)
os.makedirs(DRAFTS_DIR, exist_ok=True)

governance_ledger = OrchestratorLedger(ledger_path=GOVERNANCE_LEDGER_PATH)
retrieval_index = DownstreamRetrievalIndex(catalog_path=RETRIEVAL_CATALOG_PATH)
agent_bus = AgentMessageBus()


def read_manifest() -> Dict[str, Any]:
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def parse_yaml_frontmatter(content: str):
    import yaml
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1])
                return fm or {}, parts[2].strip()
            except Exception:
                pass
    return {}, content.strip()
