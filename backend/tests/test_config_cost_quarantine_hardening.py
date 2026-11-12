"""Regression tests for review findings H1 (/api/config), H2 (cost caps, timeouts) and H3 (quarantine hygiene)."""
import os
import sys
import json
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings as cfg
from config.settings import validate_config_updates


def _app():
    from api.routes_governance import governance_router
    app = FastAPI()
    app.include_router(governance_router)
    return TestClient(app)


class TestConfigSchema(unittest.TestCase):
    def test_unknown_section_and_key_rejected(self):
        _, errs = validate_config_updates({"llm_models": {"execution_planning": {"model": "x"}}})
        self.assertTrue(errs)
        _, errs = validate_config_updates({"governance": {"unlimited_daily_calls": True}})
        self.assertTrue(errs)

    def test_range_and_type_enforced(self):
        _, errs = validate_config_updates({"governance": {"min_passing_score": 0}})
        self.assertTrue(errs)
        _, errs = validate_config_updates({"file_upload": {"max_file_size_mb": 5000}})
        self.assertTrue(errs)
        _, errs = validate_config_updates({"governance": {"max_daily_calls": "lots"}})
        self.assertTrue(errs)
        _, errs = validate_config_updates({"governance": {"max_daily_calls": True}})
        self.assertTrue(errs)

    def test_valid_update_passes(self):
        clean, errs = validate_config_updates({"governance": {"min_passing_score": 85, "max_daily_calls": 150}})
        self.assertEqual(errs, [])
        self.assertEqual(clean["governance"]["max_daily_calls"], 150)


class _FakePrincipal:
    identity = "admin@test"
    sub = "admin-1"
    roles = ("admin",)
    tenant_id = "t1"
    clearance = "L3"
    actor_type = "human"


class TestConfigEndpointAdminOnly(unittest.TestCase):
    def setUp(self):
        self.client = _app()

    def test_unauthenticated_caller_denied(self):
        from server import app  # real app: has the auth error handler
        client = TestClient(app)
        with patch("config.settings.update_settings") as upd:
            r = client.post("/api/config", json={"governance": {"min_passing_score": 85}})
        self.assertIn(r.status_code, (401, 403))
        upd.assert_not_called()

    def test_invalid_payload_rejected_and_nothing_saved(self):
        with patch("api.routes_governance.authenticate_request", return_value=_FakePrincipal()),              patch("config.settings.audit_config_change"),              patch("config.settings.update_settings") as upd:
            r = self.client.put("/api/config", json={"governance": {"min_passing_score": 0}})
        self.assertEqual(r.status_code, 422)
        upd.assert_not_called()

    def test_valid_admin_update_applied_and_audited(self):
        with patch("api.routes_governance.authenticate_request", return_value=_FakePrincipal()),              patch("config.settings.audit_config_change") as audit,              patch("config.settings.update_settings", return_value={"ok": 1}) as upd:
            r = self.client.post("/api/config", json={"governance": {"max_daily_calls": 150}})
        self.assertEqual(r.status_code, 200)
        upd.assert_called_once_with({"governance": {"max_daily_calls": 150}})
        self.assertEqual(audit.call_args[0][-1], "applied")


class TestCostDefaults(unittest.TestCase):
    def test_daily_cap_on_by_default(self):
        d = cfg._DEFAULT_CONFIG["governance"]
        self.assertFalse(d["unlimited_daily_calls"])
        self.assertGreater(d["max_daily_calls"], 0)
        self.assertGreater(d["max_calls_per_job"], 0)

    def test_shipped_config_files_have_cap(self):
        for p in (cfg.SETTINGS_JSON_PATH, cfg.CONFIG_FILE_PATH):
            with open(p, encoding="utf-8") as f:
                g = json.load(f)["governance"]
            self.assertFalse(g["unlimited_daily_calls"], p)
            self.assertGreater(g["max_daily_calls"], 0, p)

    def test_clients_get_timeout_and_retries(self):
        from config import llm_config
        lim = llm_config._limits()
        self.assertGreater(lim["timeout"], 0)
        self.assertIn("max_retries", lim)


class TestParserLogRedaction(unittest.TestCase):
    def test_parser_log_never_contains_password(self):
        import tempfile
        from agents.a1_ingestion import document_extractor as de
        with tempfile.TemporaryDirectory() as d, patch.object(de, "LOGS_PARSER_DIR", d):
            path = de._log_parsed_text("vpn.txt", "utf8", "Step 1\nPassword: Hunter2Secret!\nStep 2")
            with open(path, encoding="utf-8") as f:
                self.assertNotIn("Hunter2Secret!", f.read())


if __name__ == "__main__":
    unittest.main()
