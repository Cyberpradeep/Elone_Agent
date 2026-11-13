# 10 — AI / LLM Implementation

## 1. What is genuinely AI here
Three LLM roles (defined in `config/llm_config.py → ROLE_PROVIDER_MAP`), used through LangChain chat clients:

| Role | Used by | Default provider/model (code defaults) | Fallbacks |
|---|---|---|---|
| `execution_planning` | `execution_planner.plan_okf_from_raw`, `triage_router` | Mistral `codestral-latest` (`PLANNING_PROVIDER/MODEL` env) | Groq `qwen/qwen3.8-27b` |
| `planning_validation` | `plan_validator` Layer 2 | Mistral `codestral-latest` (`VALIDATION_*` env) | Groq |
| `vlm_image_analysis` | `vlm_extractor.analyze_image_bytes`, scanned-PDF OCR in `document_extractor` | NVIDIA `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (`VLM_*` env) | OpenRouter nemotron free → NVIDIA llama-3.2-11b-vision |

**Three sources of truth disagree** (verified): README says Groq `qwen/qwen3.8-27b` + Z.ai `glm-4.7-flash`; `settings.json` says Mistral codestral + NVIDIA llama-3.2-11b-vision; `llm_config.py` reads only env and defaults to Mistral codestral + NVIDIA nemotron. **Only `llm_config.py`/env decides what is actually called.** `settings.llm_models` is read by a single test and nothing in production. The README's "hot-reload models" claim is therefore not true for models.

Everything else (scoring, quote tracing, gates, retrieval) is **deterministic code**, deliberately outside the LLM.

## 2. Request lifecycle (user upload → model → stored draft)
1. **Extraction** (`document_extractor.extract_ordered_sop_content`): walks DOCX body / PDF blocks in reading order, keeps images inline as segments; applies Unicode/zero-width cleaning and DLP redaction (pdf/docx).
2. **VLM** per image (≤ `max_images_per_sop`, default 15): `validate_and_sanitize_image_bytes` (magic bytes, ≤4096 px, downscale to 1024 JPEG) → VLM prompt `VLM_SUPPORT_PROMPT` → report text + parsed confidence → saved under `logs/images/<slug>/`; report interleaved into the document text with a directive by confidence (≥0.85 passive evidence; ≥0.60 supplementary; else unreliable). Scanned PDFs without text fall back to per-page VLM OCR.
3. **Prompt assembly**: `escape_prompt_delimiters` neutralises any `<untrusted_document_payload>` tag in the document; text is substituted into one of `COMMAND_COT_PROMPT` / `TOOL_COT_PROMPT` / `HYBRID_COT_PROMPT` (`prompts/jit_converter_prompts.py`, ~800 lines with exemplars, a 6-stage CoT mandate, a source-quote mandate, and an injection-defence mandate). With the shipped `execution_mode=command_only` the **command prompt is always used, triage is skipped, and no tools are bound**.
4. **Planner loop** (`plan_okf_from_raw`): up to 3 attempts (temp 0.0 then 0.1); each may do ≤5 tool turns (only if tools bound: `list_available_platforms`, `get_platform_tools`, … — inspection-only, they never call external systems); hard per-job call budget (default 25) raises `RuntimeError`; daily circuit breaker `check_daily_limit` before each call; cancellation checked before each call; token usage recorded via `gemini_monitor.record_call`.
5. **Parsing**: regex fence extraction → `json.loads(strict=False)` → `sanitize_json_text` repair → `ast.literal_eval` → single-quote normaliser; on failure the error is fed back into the next attempt.
6. **Schema**: Pydantic `OKFPlaybookModel`; non-executable/zero-step output returns `is_executable=false` → job `rejected` ("unactionable").
7. **Validation** (`plan_validator`):
   - Layer 1 (no LLM): malicious-pattern scan, placeholder-step detection, `{{entities.*}}` & `{{variables.*}}` linkage, tool schema check, double-quote enforcement for entity placeholders, `source_action_coverage` ledger rules. Fails stop the loop and are fed back.
   - Layer 2 (LLM): `JIT_VALIDATOR_COT_SYSTEM_PROMPT` → JSON `{is_faithful, injection_detected, dropped_commands, hallucinated_commands, …}`. `injection_detected` ⇒ hard fail. Un-faithful verdicts can be *overridden* when every "dropped" claim is explained by the coverage ledger and no safety-keyword claim exists.
8. **Canonical build & scoring** (no LLM): quote localisation, quote verification (±1 line window; VLM-report quotes accepted), completeness, quality Q, confidentiality score/tier.
9. Draft stored, human review (workflow W2/W3 in [09](09-business-workflows.md)).

## 3. Guardrails — implemented vs. not
| Guardrail | Status | Notes |
|---|---|---|
| Input prompt-injection framing + tag escaping | ✅ | `utils/security.escape_prompt_delimiters`; tests in `test_prompt_injection_hardening.py` |
| Regex threat scan on raw text before any LLM call | ✅ (ingest) / ❌ (`/api/plan-preview`, MCP `plan_sop`) | |
| Secret quarantine before LLM | 🟡 | see [08 §4](08-authentication-security.md#dlp) |
| Output schema validation | ✅ | Pydantic |
| Deterministic command blacklist on output | 🟡 | only 10 patterns |
| LLM faithfulness / injection audit | 🟡 | **Fails closed if the call raises; fails open if the reply is unparsable JSON or lacks fields** (`is_faithful` defaults `True`, `injection_detected` defaults `False`; the outer `except parse_err` only rejects on an explicit `"is_faithful": false`). Layer 2 is also skipped when source text < 30 chars. |
| Verbatim quote traceability | ✅ | code, not LLM, locates quotes |
| Human approval, SoD | ✅ | |
| Tool-call safety | ✅ | catalog tools are read-only |
| LLM output → execution | n/a | not executed in this repo |

## 4. Not implemented (despite README wording)
- **No RAG / embeddings / vector DB.** Retrieval is token-substring matching.
- **No conversational memory/context management** — each ingest is a stateless batch call; retry feedback is the only "memory".
- **No AI confidentiality advisory** is passed in production (`ai_advisory` param unused) — "AI floor rule" code exists but is dormant.
- **No evaluation in CI.** DeepEval suites exist (`tests/deepeval/*`: faithfulness, command safety, tiering, adversarial, retrieval relevancy, tool correctness, golden-set runner with `custom_eval_model.py`) but `deepeval` is not installed/required and these modules fail at import in the current venv; they need live LLM keys.
- No per-tenant model selection, no prompt versioning, no response caching.

## 5. Model fallback, retries, cost
- Fallback via LangChain `.with_fallbacks([...])` built in `get_llm` (cached with `lru_cache` — **a changed env/model requires process restart; API config edits do not affect it**). Mistral and Groq clients rotate across multiple API keys. Z.ai builder auto-falls back `glm-4.7-flash → glm-4.5-flash`.
- Timeouts/retries from `settings.governance.llm_timeout_seconds` (120) / `llm_max_retries` (2) applied to each client (`_limits()` is evaluated at client build time, so cached clients ignore later changes).
- Cost accounting (`gemini_monitor`): `record_call` appends to `daily_usage.json` with tokens and USD/INR. Accuracy issues: model id is hard-coded in callers (`"mistral-large-latest"` / `"gemini-3.7-flash"`), the price table has only Gemini/NVIDIA/Mistral-large entries (Groq/Z.ai/codestral are priced as something else), no lock around read-modify-write (lost updates under concurrency), and the quota counts *calls* globally, not per tenant. Local `.env` sets `UNLIMITED_DAILY_CALLS=true`, so the breaker is currently disabled on this machine.
- Hard budget per job: `max_calls_per_job` (default 25) — attempts × tool turns can never exceed it.

## 6. Observability
- Rich console logging (`utils/pipeline_logger.py`): execution plan, validator audit, active models.
- File audit trail: `logs/converter_input/*` (exact enriched text sent to the planner), `logs/parser/*` (redacted), `logs/debug/*_full_debug.log` (phase summary + steps + reasoning + quotes), weekly `logs/<week>.md`.
- No tracing backend (no OpenTelemetry/Langfuse/Phoenix wiring; `.phoenix/` is only in `.gitignore`).

## 7. Evaluation assets
- `tests/golden_set/` — 16 sample SOPs in 4 groups (happy_path, edge_cases, adversarial: prompt injection / live credentials / jailbreak webhook / destructive command, domain_specific) + `manifest.json`; `tests/eval_golden_set.py`, `tests/test_golden_set.py`.
- `tests/deepeval/*` described above.
- Unit/integration tests mock LLM calls (`patch("gemini_monitor.monitor.check_daily_limit")`, fake planners) so the main suite runs offline.

## 8. msg/1.0 agent protocol (parallel implementation)
`schemas/protocol_msg.py` + `orchestrator/bus.py`: TaskMessage/ResultMessage envelopes, artifact store passed by reference, a route matrix (`ALLOWED_ROUTES`), artifact read/write permission matrix, idempotency keys, budgets (30 agent calls, 14 LLM calls per job). Fully implemented and unit-tested (`test_agent_protocol.py`, `test_msg_protocol_runtime.py`, `test_orchestrator_state.py`) but **only driven by `trace_pipeline.py`**, not by the HTTP service. Treat it as a reference/second implementation that may drift from the live route.
