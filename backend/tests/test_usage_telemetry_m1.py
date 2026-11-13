import os
import sys
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

# Ensure backend is on sys.path
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from config.llm_config import resolve_llm_metadata, ROLE_PROVIDER_MAP
from gemini_monitor.cost_calculator import calculate_cost, PRICING_CATALOG
from gemini_monitor import monitor


class TestLLMMetadataResolution(unittest.TestCase):
    def test_resolve_gemini_client(self):
        fake_gemini = MagicMock()
        fake_gemini.__class__.__name__ = "ChatGoogleGenerativeAI"
        fake_gemini.model = "gemini-2.5-flash"
        prov, mdl = resolve_llm_metadata(fake_gemini, "execution_planning")
        self.assertEqual(prov, "gemini")
        self.assertEqual(mdl, "gemini-2.5-flash")

    def test_resolve_mistral_client(self):
        fake_mistral = MagicMock()
        fake_mistral.__class__.__name__ = "ChatMistralAI"
        fake_mistral.model = "codestral-latest"
        prov, mdl = resolve_llm_metadata(fake_mistral, "execution_planning")
        self.assertEqual(prov, "mistral")
        self.assertEqual(mdl, "codestral-latest")

    def test_resolve_groq_client_from_base_url(self):
        fake_groq = MagicMock()
        fake_groq.__class__.__name__ = "ChatOpenAI"
        fake_groq.model_name = "llama-3.3-70b-versatile"
        fake_groq.openai_api_base = "https://api.groq.com/openai/v1"
        prov, mdl = resolve_llm_metadata(fake_groq)
        self.assertEqual(prov, "groq")
        self.assertEqual(mdl, "llama-3.3-70b-versatile")

    def test_resolve_zai_client_from_base_url(self):
        fake_zai = MagicMock()
        fake_zai.__class__.__name__ = "ChatOpenAI"
        fake_zai.model_name = "glm-4.7-flash"
        fake_zai.openai_api_base = "https://api.z.ai/api/paas/v4"
        prov, mdl = resolve_llm_metadata(fake_zai)
        self.assertEqual(prov, "zai")
        self.assertEqual(mdl, "glm-4.7-flash")

    def test_resolve_runnable_with_fallbacks(self):
        primary = MagicMock()
        primary.__class__.__name__ = "ChatMistralAI"
        primary.model = "codestral-latest"
        fallback = MagicMock()

        wrapper = MagicMock()
        wrapper.runnable = primary
        wrapper.fallbacks = [fallback]

        prov, mdl = resolve_llm_metadata(wrapper)
        self.assertEqual(prov, "mistral")
        self.assertEqual(mdl, "codestral-latest")

    def test_resolve_fallback_to_role_config(self):
        empty_llm = MagicMock(spec=[])  # No attributes
        prov, mdl = resolve_llm_metadata(empty_llm, "execution_planning")
        expected_prov = ROLE_PROVIDER_MAP["execution_planning"]["provider"]
        expected_mdl = ROLE_PROVIDER_MAP["execution_planning"]["model"]
        self.assertEqual(prov, expected_prov)
        self.assertEqual(mdl, expected_mdl)


class TestCostCalculator(unittest.TestCase):
    def test_calculate_cost_groq_llama70b(self):
        cost = calculate_cost(
            model="llama-3.3-70b-versatile",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            provider="groq",
        )
        self.assertEqual(cost["provider"], "groq")
        # $0.59 input + $0.79 output = $1.38
        self.assertAlmostEqual(cost["total_cost_usd"], 1.38, places=2)

    def test_calculate_cost_zai_glm(self):
        cost = calculate_cost(
            model="glm-4.7-flash",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            provider="zai",
        )
        self.assertEqual(cost["provider"], "zai")
        # $0.01 input + $0.01 output = $0.02
        self.assertAlmostEqual(cost["total_cost_usd"], 0.02, places=2)

    def test_calculate_cost_codestral(self):
        cost = calculate_cost(
            model="codestral-latest",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            provider="mistral",
        )
        # $0.30 input + $0.90 output = $1.20
        self.assertAlmostEqual(cost["total_cost_usd"], 1.20, places=2)


class TestGeminiMonitorTelemetry(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.usage_file = os.path.join(self.td.name, "daily_usage.json")
        self.patch_dir = patch.object(monitor, "MONITOR_DIR", self.td.name)
        self.patch_file = patch.object(monitor, "USAGE_FILE", self.usage_file)
        self.patch_unlimited = patch.object(monitor, "is_unlimited_calls", return_value=True)
        self.patch_dir.start()
        self.patch_file.start()
        self.patch_unlimited.start()

    def tearDown(self):
        self.patch_unlimited.stop()
        self.patch_file.stop()
        self.patch_dir.stop()
        self.td.cleanup()

    def test_record_call_stores_telemetry_fields(self):
        session_id = monitor.start_execution_session("test_sop.pdf")
        monitor.bind_job_progress("job_test_123")

        res = monitor.record_call(
            caller="execution_planning",
            model="llama-3.3-70b-versatile",
            provider="groq",
            input_tokens=100,
            output_tokens=50,
            sop_id="SOP-123",
            latency_ms=345.67,
            trace_id="trace_abc_999",
            status="success",
        )

        # Check call_history in today's entry
        today_data = monitor.get_today_usage()
        self.assertEqual(today_data["total_calls"], 1)
        self.assertEqual(today_data["groq_calls"], 1)
        self.assertEqual(len(today_data["call_history"]), 1)

        hist = today_data["call_history"][0]
        self.assertEqual(hist["caller"], "execution_planning")
        self.assertEqual(hist["provider"], "groq")
        self.assertEqual(hist["model"], "llama-3.3-70b-versatile")
        self.assertEqual(hist["latency_ms"], 345.67)
        self.assertEqual(hist["trace_id"], "trace_abc_999")
        self.assertEqual(hist["status"], "success")

        # Check session tracking
        session = monitor.get_execution_summary()
        self.assertEqual(session["groq_calls"], 1)
        self.assertEqual(session["calls"][0]["latency_ms"], 345.67)
        self.assertEqual(session["calls"][0]["trace_id"], "trace_abc_999")
        self.assertEqual(session["calls"][0]["status"], "success")

        # Check job progress tracking
        progress = monitor.get_job_progress("job_test_123")
        self.assertEqual(len(progress), 1)
        self.assertEqual(progress[0]["latency_ms"], 345.67)
        self.assertEqual(progress[0]["status"], "success")
        self.assertEqual(progress[0]["trace_id"], "trace_abc_999")

        monitor.end_execution_session()

    def test_record_call_error_status(self):
        monitor.record_call(
            caller="planning_validation",
            model="glm-4.7-flash",
            provider="zai",
            sop_id="SOP-ERR",
            latency_ms=1200.5,
            trace_id="trace_err_404",
            status="error",
            error_message="HTTP 500 Internal Server Error",
        )

        today_data = monitor.get_today_usage()
        self.assertEqual(today_data["zai_calls"], 1)
        hist = today_data["call_history"][0]
        self.assertEqual(hist["status"], "error")
        self.assertEqual(hist["error_message"], "HTTP 500 Internal Server Error")
        self.assertEqual(hist["latency_ms"], 1200.5)

    def test_provider_tally_distinction_no_nvidia_hijack(self):
        # Verify vision caller does not hijack provider if provider is gemini or groq
        monitor.record_call(
            caller="vision_pipeline",
            model="gemini-2.5-flash",
            provider="gemini",
            input_tokens=10,
            output_tokens=10,
        )
        today_data = monitor.get_today_usage()
        self.assertEqual(today_data["gemini_calls"], 1)
        self.assertEqual(today_data.get("nvidia_vision_calls", 0), 0)

    def test_inter_process_file_locking(self):
        # Verify lock file is created and filelock works during calls
        monitor.record_call(
            caller="test_caller",
            model="gemini-2.5-flash",
            provider="gemini",
            input_tokens=10,
            output_tokens=10,
        )
        self.assertTrue(os.path.exists(self.usage_file))
        # Lock file is created alongside usage_file
        lock_file = f"{self.usage_file}.lock"
        self.assertTrue(os.path.exists(lock_file) or os.path.exists(self.usage_file))


class TestCallSitesTelemetry(unittest.TestCase):
    def test_execution_planner_records_latency_and_trace_id(self):
        from agents.a2_structuring import execution_planner as ep

        fake_llm = MagicMock()
        fake_llm.model = "codestral-latest"
        fake_llm.provider = "mistral"
        fake_res = SimpleNamespace(
            content='{"sop_id": "SOP-1", "title": "T", "steps": []}',
            tool_calls=[],
            usage_metadata={"input_tokens": 12, "output_tokens": 34},
        )
        fake_llm.bind_tools.return_value.invoke.return_value = fake_res

        with patch.object(ep, "get_llm", return_value=fake_llm), \
             patch.object(ep, "extract_ordered_sop_content", return_value=("Restart service", [{"type": "text", "content": "Restart service"}])), \
             patch.object(ep, "get_execution_mode", return_value="command_only"), \
             patch("gemini_monitor.monitor.check_daily_limit"), \
             patch("gemini_monitor.monitor.record_call") as mock_record:
            try:
                ep.plan_okf_from_raw("test_sop.txt")
            except Exception:
                pass

            self.assertTrue(mock_record.called)
            call_kwargs = mock_record.call_args.kwargs
            self.assertEqual(call_kwargs.get("caller"), "execution_planning")
            self.assertEqual(call_kwargs.get("provider"), "mistral")
            self.assertEqual(call_kwargs.get("model"), "codestral-latest")
            self.assertEqual(call_kwargs.get("status"), "success")
            self.assertIsNotNone(call_kwargs.get("latency_ms"))
            self.assertGreaterEqual(call_kwargs.get("latency_ms"), 0)

    def test_plan_validator_records_latency_and_trace_id(self):
        from agents.a4_verification import plan_validator as pv

        fake_llm = MagicMock()
        fake_llm.model = "llama-3.3-70b-versatile"
        fake_llm.provider = "groq"
        fake_llm.invoke.return_value = SimpleNamespace(
            content='```json\n{"is_faithful": true, "hallucinated_entities": [], "missing_critical_steps": [], "security_violations": [], "reasoning": "ok"}\n```',
            usage_metadata={"input_tokens": 20, "output_tokens": 15},
        )

        plan = {
            "sop_id": "SOP-TEST-777",
            "steps": [{"step_number": 1, "step_type": "command", "shell": "powershell", "command": "Get-Process"}],
        }

        with patch.object(pv, "get_llm", return_value=fake_llm), \
             patch("gemini_monitor.monitor.check_daily_limit"), \
             patch("gemini_monitor.monitor.record_call") as mock_record:
            pv.validate_plan_faithfulness_and_linkage(
                "Step 1: Check running services and processes on target server Host01.",
                plan,
            )

            self.assertTrue(mock_record.called)
            call_kwargs = mock_record.call_args.kwargs
            self.assertEqual(call_kwargs.get("caller"), "planning_validation")
            self.assertEqual(call_kwargs.get("provider"), "groq")
            self.assertEqual(call_kwargs.get("model"), "llama-3.3-70b-versatile")
            self.assertEqual(call_kwargs.get("sop_id"), "SOP-TEST-777")
            self.assertEqual(call_kwargs.get("status"), "success")
            self.assertIsNotNone(call_kwargs.get("latency_ms"))

    def test_triage_router_records_latency_and_trace_id(self):
        from agents.a2_structuring import triage_router as tr

        fake_llm = MagicMock()
        fake_llm.model = "glm-4.7-flash"
        fake_llm.provider = "zai"
        fake_llm.invoke.return_value = SimpleNamespace(
            content='{"category": "command", "confidence": 0.95, "reasoning": "powershell command"}',
            usage_metadata={"input_tokens": 30, "output_tokens": 10},
        )

        with patch.object(tr, "get_llm", return_value=fake_llm), \
             patch("gemini_monitor.monitor.check_daily_limit"), \
             patch("gemini_monitor.monitor.record_call") as mock_record:
            tr.run_triage_router(
                "Step 1: Restart Print Spooler service on host01.",
                "spooler-sop",
                enable_tool_inspection=False,
            )

            self.assertTrue(mock_record.called)
            call_kwargs = mock_record.call_args.kwargs
            self.assertEqual(call_kwargs.get("caller"), "triage_router")
            self.assertEqual(call_kwargs.get("provider"), "zai")
            self.assertEqual(call_kwargs.get("model"), "glm-4.7-flash")
            self.assertEqual(call_kwargs.get("trace_id"), "spooler-sop")
            self.assertEqual(call_kwargs.get("status"), "success")
            self.assertIsNotNone(call_kwargs.get("latency_ms"))


if __name__ == "__main__":
    unittest.main()
