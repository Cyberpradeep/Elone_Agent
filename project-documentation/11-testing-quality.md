# 11 — Testing & Quality Analysis

## 1. Inventory (`backend/tests/`)
| Area | Files |
|---|---|
| Auth / RBAC / tenant / CSRF / CORS (E2E driver in subprocess) | `test_auth_and_cors.py` (1.1k lines, 7 tests) |
| Server-side gates + publish integrity (C3/C4) | `test_c3_c4_server_gates_and_publish_integrity.py` |
| Governance bypass disabled (C1) | `test_governance_bypass_disabled.py` |
| Config validation, cost caps, quarantine purge (H1–H3) | `test_config_cost_quarantine_hardening.py`, `test_dynamic_config.py` |
| Prompt-injection hardening | `test_prompt_injection_hardening.py` |
| DLP / security utilities | `test_security.py` |
| Pipeline integration (mocked LLM) | `test_pipeline_integration.py`, `test_agents_modular.py` |
| VLM traceability + re-ingestion | `test_vlm_traceability_and_reingest.py` (1.3k lines) |
| Governance scorer, retrieval index, tool binding | `test_governance_scorer.py`, `test_retrieval_index.py`, `test_jit_converter_tools.py` |
| msg/1.0 protocol & orchestrator state machine | `test_agent_protocol.py`, `test_msg_protocol_runtime.py`, `test_orchestrator_state.py` |
| Golden set | `test_golden_set.py`, `eval_golden_set.py`, `golden_set/**` |
| LLM evals (DeepEval) | `tests/deepeval/*` (6 test modules + runner) |
| Script-style | `backend/test_standalone.py` (1.1k lines), `test_llm_providers.py` (manual, needs keys) |

No frontend tests, no browser/E2E tests, no load tests, no coverage configuration, no CI.

## 2. What I actually ran (in a throw-away copy of `HEAD` under the session scratchpad — real repo untouched)
Command: `ELONE_ALLOW_INSECURE_DEV_KEY=1 python -m pytest tests -q --ignore=tests/deepeval` (venv python).

| Result | Count |
|---|---|
| passed | **148** |
| failed | **2** |
| skipped | 2 |
| collection errors (deepeval) | 6 modules — `ModuleNotFoundError: deepeval` |

Failures, both **environment-dependent, not logic regressions**:
1. `test_auth_and_cors…test_end_to_end_…` — publish returned 400 `Security configuration missing: 'ELONE_PLAYBOOK_SIGNING_KEY'`. With `ELONE_PLAYBOOK_SIGNING_KEY` exported the whole file passed (7/7). The test *depends on an env var that `.env.example` never mentions* (the author's local `.env` supplies it).
2. `test_governance_bypass_disabled…test_05_mcp_cli_harness…` — MCP harness calls the real validator LLM; with no `MISTRAL_API_KEY` Layer 2 failed closed (this is the intended fail-closed behaviour, but the test is not hermetic).

⇒ README badge "91 passed (100%)" is stale: the suite now has 152 collectable non-DeepEval tests; 148 pass in a clean env, 2 need secrets/keys, and the DeepEval suite cannot run without installing an undeclared dependency.

## 3. Mocking
LLMs are patched in most suites (`patch("gemini_monitor.monitor.check_daily_limit")`, fake `get_llm`, canned planner outputs). Auth tests spawn an isolated Python subprocess with a temp `ELONE_KB_DIR`/auth dir and FastAPI `TestClient`, so real `knowledge_base` is not touched (I confirmed by running in a copy; tests do use temp dirs in 11 files — verify per-test before running on the live tree).

## 4. Coverage assessment
| Critical workflow | Tested? |
|---|---|
| Login / lockout / CSRF / role matrix / tenant & clearance isolation | ✅ strong |
| SoD, gates computed server-side, hash-bound publish | ✅ strong |
| Quarantine & AST block → 0 LLM calls | ✅ (txt path) |
| Config validation | ✅ |
| Prompt-injection (mocked LLM) | ✅ but only deterministic parts really verified |
| DLP evasion via placeholder substrings / PDF API-key silent redaction | ❌ no test (and behaviour is wrong) |
| Published-SOP edit (`PUT canonical`, `sync-playbook`) governance | ❌ only asserts role/tenant 403s and 200 for authorised, not that gates/AST run |
| `/api/plan-preview` secret handling | ❌ |
| Layer-2 fail-open on malformed LLM output | ❌ |
| Concurrency (two ingests, ledger reload races, usage-file races) | ❌ |
| Multi-process deployment | ❌ |
| Frontend | ❌ none |
| OIDC against a real JWKS | 🟡 unit-level only via injected `jwk_client` |
| Real LLM end-to-end | 🟡 only manual/DeepEval |

## 5. Linting, formatting, CI, monitoring
- **Linting/formatting**: none configured (no ruff/flake8/black/mypy config; the code carries `# pyrefly: ignore` comments, implying a Pyrefly IDE checker). One `DeprecationWarning: invalid escape sequence '\W'` in `utils/security.py:757` docstring.
- **CI/CD**: none (no `.github/`, GitLab, etc.).
- **Error monitoring**: none (no Sentry/OTel). Errors printed to console / returned in responses; `auth_events.jsonl` is the only structured security log.
- Skill files under `.agents/` (code-reviewer, agent-eval-tracer, security-audit) are *developer aids*, not part of the product.

## 6. Reliability risks surfaced by testing/reading
- Test hermeticity (needs keys/env), undeclared dev deps (`deepeval`, `uvicorn`).
- Large single-file test drivers executed in subprocesses make failures hard to localise (assertion line numbers refer to a generated temp file).
- No regression test for the 2026-11-12 findings listed in [13](13-gaps-and-recommendations.md).

## 7. How to run (verified commands)
```powershell
cd backend
$env:ELONE_ALLOW_INSECURE_DEV_KEY="1"; $env:ELONE_PLAYBOOK_SIGNING_KEY="any-long-test-string"
..\venv\Scripts\python.exe -m pytest tests -q --ignore=tests\deepeval
```
(Run it from a copy if you worry about runtime files; the suite is designed to use temp dirs but I did not audit every test.)
