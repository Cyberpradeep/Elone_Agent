"""M4 (settings half): model names and limits come from config/settings.json, not from code."""
import os
import re
import sys
import json
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings as cfg
from config import llm_config

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLES = ("execution_planning", "planning_validation", "vlm_image_analysis")
MODEL_ENV = ("PLANNING_PROVIDER", "PLANNING_MODEL", "VALIDATION_PROVIDER", "VALIDATION_MODEL",
             "VLM_PROVIDER", "VLM_MODEL", "GROQ_MODEL")


def _clean_env():
    return {k: v for k, v in os.environ.items() if k not in MODEL_ENV}


class TestModelsComeFromSettings(unittest.TestCase):
    def tearDown(self):
        cfg.settings.reload()

    def test_role_map_matches_settings_file(self):
        with open(cfg.SETTINGS_JSON_PATH, encoding="utf-8") as f:
            file_models = json.load(f)["llm_models"]
        with patch.dict(os.environ, _clean_env(), clear=True):
            cfg.settings.reload()
            for role in ROLES:
                self.assertEqual(llm_config.ROLE_PROVIDER_MAP[role]["provider"], file_models[role]["provider"])
                self.assertEqual(llm_config.ROLE_PROVIDER_MAP[role]["model"], file_models[role]["model"])
                self.assertEqual(llm_config.ROLE_PROVIDER_MAP[role]["fallbacks"], file_models[role]["fallbacks"])

    def test_changing_settings_changes_the_model_in_use(self):
        same_object = llm_config.ROLE_PROVIDER_MAP
        llm_config.apply_llm_models({
            "execution_planning": {"provider": "Groq", "model": "some-new-model", "fallbacks": []},
        })
        self.assertIs(llm_config.ROLE_PROVIDER_MAP, same_object)  # importers stay current
        self.assertEqual(same_object["execution_planning"],
                         {"provider": "groq", "model": "some-new-model", "fallbacks": []})

    def test_env_overrides_still_win(self):
        env = dict(_clean_env(), PLANNING_MODEL="env-planner", VLM_PROVIDER="OpenRouter",
                   VLM_MODEL="env-vlm", GROQ_MODEL="env-groq")
        with patch.dict(os.environ, env, clear=True):
            cfg.settings.reload()
            m = llm_config.ROLE_PROVIDER_MAP
            self.assertEqual(m["execution_planning"]["model"], "env-planner")
            self.assertEqual(m["vlm_image_analysis"]["provider"], "openrouter")
            self.assertEqual(m["vlm_image_analysis"]["model"], "env-vlm")
            groq_fallbacks = [fb for r in ROLES for fb in m[r]["fallbacks"] if fb["provider"] == "groq"]
            self.assertTrue(groq_fallbacks)
            self.assertTrue(all(fb["model"] == "env-groq" for fb in groq_fallbacks))

    def test_env_values_are_not_written_back_to_the_file(self):
        with patch.dict(os.environ, dict(_clean_env(), PLANNING_MODEL="env-planner"), clear=True):
            cfg.settings.reload()
            self.assertNotEqual(cfg.settings._file_config["llm_models"]["execution_planning"]["model"], "env-planner")

    def test_unknown_role_and_provider_are_rejected(self):
        with self.assertRaises(ValueError):
            llm_config.get_llm("no_such_role")
        llm_config.apply_llm_models({"execution_planning": {"provider": "nope", "model": "x"}})
        with self.assertRaises(ValueError):
            llm_config.get_llm("execution_planning")

    def test_no_model_names_hardcoded_in_role_mapping(self):
        with open(os.path.join(BACKEND_DIR, "config", "llm_config.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("codestral", src)
        self.assertNotIn("nemotron", src)
        self.assertIsNone(re.search(r'os\.environ\.get\("(PLANNING|VALIDATION|VLM)_', src))


class TestLimitsComeFromSettings(unittest.TestCase):
    def tearDown(self):
        cfg.settings.reload()

    def _with(self, section, values):
        cfg.settings._cached_config.setdefault(section, {}).update(values)

    def test_shipped_files_and_defaults_define_every_new_key(self):
        sources = [cfg._DEFAULT_CONFIG]
        for p in (cfg.SETTINGS_JSON_PATH, cfg.CONFIG_FILE_PATH):
            with open(p, encoding="utf-8") as f:
                sources.append(json.load(f))
        for d in sources:
            for key in ("upload_chunk_bytes", "max_uncompressed_zip_mb", "max_zip_compression_ratio"):
                self.assertIn(key, d["file_upload"])
            self.assertIn("max_agent_calls_per_job", d["governance"])
            self.assertEqual(set(d["link_scraper"]), {"max_output_chars", "max_redirect_hops", "timeout_seconds"})
            self.assertIn("usd_to_inr_rate", d["cost"])
            self.assertIn("max_output_tokens", d["llm_limits"])
            for role in ROLES:
                self.assertIn("fallbacks", d["llm_models"][role])

    def test_output_token_cap_is_read_from_settings(self):
        self._with("llm_limits", {"max_output_tokens": {"groq": 777}})
        self.assertEqual(llm_config._max_output_tokens("groq", 2048), 777)
        self.assertEqual(llm_config._max_output_tokens("mistral", 999), 999)  # unlisted -> caller default

    def test_currency_rate_is_read_from_settings(self):
        from gemini_monitor.cost_calculator import calculate_cost
        self._with("cost", {"usd_to_inr_rate": 100.0})
        out = calculate_cost("gemini-2.5-flash", input_tokens=1_000_000, output_tokens=0)
        self.assertAlmostEqual(out["total_cost_inr"], out["total_cost_usd"] * 100.0, places=4)

    def test_scraper_and_upload_limits_are_read_from_settings(self):
        self._with("link_scraper", {"max_redirect_hops": 7, "timeout_seconds": 3})
        self._with("file_upload", {"upload_chunk_bytes": 131072})
        self.assertEqual(cfg.settings.scrape_max_redirect_hops, 7)
        self.assertEqual(cfg.settings.scrape_timeout_seconds, 3.0)
        self.assertEqual(cfg.settings.upload_chunk_bytes, 131072)

    def test_new_keys_are_not_editable_through_the_api(self):
        for body in ({"llm_limits": {"max_output_tokens": {"groq": 1}}},
                     {"link_scraper": {"max_redirect_hops": 99}},
                     {"cost": {"usd_to_inr_rate": 1}},
                     {"file_upload": {"upload_chunk_bytes": 1}}):
            _, errs = cfg.validate_config_updates(body)
            self.assertTrue(errs, body)


if __name__ == "__main__":
    unittest.main()
