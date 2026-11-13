"""L1: no `except ...: pass` may silently swallow an error in application code."""
import os
import ast
import sys
import logging
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"venv", "__pycache__", "tests", "knowledge_base", ".git"}
SKIP_FILES = {"test_standalone.py", "test_llm_providers.py"}
ALLOW_MARK = "intentionally silent"


def _silent_handlers():
    found = []
    for dp, dn, fn in os.walk(BACKEND_DIR):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for name in fn:
            if not name.endswith(".py") or name in SKIP_FILES:
                continue
            path = os.path.join(dp, name)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            lines = src.splitlines()
            for node in ast.walk(ast.parse(src)):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    if ALLOW_MARK in lines[node.body[0].lineno - 1]:
                        continue
                    found.append(f"{os.path.relpath(path, BACKEND_DIR)}:{node.lineno}")
    return found


class TestNoSilentExceptions(unittest.TestCase):
    def test_no_except_pass_in_application_code(self):
        self.assertEqual(
            _silent_handlers(), [],
            "Log the error (or mark the line '# intentionally silent: <why>').",
        )


class TestSuppressedErrorsAreLogged(unittest.TestCase):
    def test_corrupt_upload_manifest_is_reported(self):
        from api import context as ctx
        with tempfile.TemporaryDirectory() as td:
            bad = os.path.join(td, "manifest.json")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("{ this is not json")
            with patch.object(ctx, "MANIFEST_PATH", bad), \
                 self.assertLogs("api.context", level="WARNING") as logs:
                self.assertEqual(ctx.read_manifest(), {})  # still non-fatal
        self.assertIn("read_manifest", logs.output[0])
        self.assertIn("JSONDecodeError", logs.output[0])

    def test_failed_auth_audit_write_is_reported(self):
        from auth import dependencies as dep
        with patch.object(dep.os, "makedirs", side_effect=OSError("disk full")), \
             self.assertLogs("auth.dependencies", level="WARNING") as logs:
            dep.log_auth_event("login_failed", identity="someone@test")
        self.assertIn("NOT written to the audit log", logs.output[0])
        self.assertIn("disk full", logs.output[0])

    def test_bad_env_number_is_only_a_debug_note(self):
        from config import settings as cfg
        try:
            with patch.dict(os.environ, {"MAX_PAGE_COUNT": "not-a-number"}), \
                 self.assertLogs("config.settings", level="DEBUG") as logs:
                cfg.settings.reload()
            self.assertTrue(any(
                r.levelno == logging.DEBUG and "keeping default" in r.getMessage()
                for r in logs.records
            ))
        finally:
            cfg.settings.reload()


if __name__ == "__main__":
    unittest.main()
