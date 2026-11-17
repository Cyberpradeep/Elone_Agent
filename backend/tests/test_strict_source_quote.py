import unittest
from pydantic import ValidationError

from schemas.okf_schema import OKFStepModel, OKFPlaybookModel
from agents.a2_structuring.canonical_builder import build_canonical_sop_from_draft


class TestStrictSourceQuoteMandate(unittest.TestCase):
    def test_okf_step_model_requires_source_quote(self):
        """OKFStepModel rejects steps when source_quote is completely omitted."""
        invalid_step = {
            "step_number": 1,
            "sop_step_description": "Restart the print spooler",
            "step_type": "command",
            "command": "Restart-Service spooler",
        }
        with self.assertRaises(ValidationError) as ctx:
            OKFStepModel.model_validate(invalid_step)
        self.assertIn("source_quote", str(ctx.exception))

    def test_okf_step_model_rejects_empty_or_whitespace_source_quote(self):
        """OKFStepModel rejects empty or whitespace-only source_quote."""
        for empty_val in ("", "   ", "\t\n"):
            step = {
                "step_number": 1,
                "sop_step_description": "Restart the print spooler",
                "step_type": "command",
                "command": "Restart-Service spooler",
                "source_quote": empty_val,
            }
            with self.assertRaises(ValidationError) as ctx:
                OKFStepModel.model_validate(step)
            self.assertIn("source_quote", str(ctx.exception))

    def test_okf_step_model_rejects_trivial_single_word_quote(self):
        """OKFStepModel rejects quotes with fewer than 2 words (must be 5-25 words copied verbatim)."""
        step = {
            "step_number": 1,
            "sop_step_description": "Restart the print spooler",
            "step_type": "command",
            "command": "Restart-Service spooler",
            "source_quote": "Restart",
        }
        with self.assertRaises(ValidationError) as ctx:
            OKFStepModel.model_validate(step)
        self.assertIn("too short", str(ctx.exception))

    def test_okf_step_model_normalizes_quote_aliases(self):
        """OKFStepModel recognizes common LLM alias keys (quote, quote_text, verbatim_quote)."""
        for alias in ("quote", "quote_text", "verbatim_quote", "sourceQuote"):
            step = {
                "step_number": 1,
                "sop_step_description": "Restart the print spooler",
                "step_type": "command",
                "command": "Restart-Service spooler",
                alias: "Restart the print spooler service now",
            }
            model = OKFStepModel.model_validate(step)
            self.assertEqual(model.source_quote, "Restart the print spooler service now")

    def test_canonical_builder_fails_immediately_when_step_missing_quote(self):
        """Canonical builder MUST raise ValueError immediately if source_quote is missing (no fallback to line 1)."""
        draft_without_quote = {
            "frontmatter": {
                "sop_id": "SOP-TEST-NO-QUOTE",
                "title": "Unsafe Hallucinated SOP",
                "steps": [
                    {
                        "step_number": 1,
                        "sop_step_description": "Disable local Windows Defender firewall",
                        "command": "Set-NetFirewallProfile -Enabled False",
                        # NO source_quote provided!
                    }
                ],
            }
        }
        raw_doc_text = "Standard Corporate Maintenance SOP\n1. Check system date."

        with self.assertRaises(ValueError) as ctx:
            build_canonical_sop_from_draft(draft_without_quote, raw_text=raw_doc_text)

        err_msg = str(ctx.exception)
        self.assertIn("Missing required verbatim 'source_quote'", err_msg)
        self.assertIn("Disable local Windows Defender firewall", err_msg)

    def test_canonical_builder_succeeds_with_verbatim_quote(self):
        """Canonical builder retains the exact source_quote without fuzzy borrowing."""
        draft = {
            "frontmatter": {
                "sop_id": "SOP-TEST-VALID",
                "title": "Corporate Maintenance SOP",
                "steps": [
                    {
                        "step_number": 1,
                        "sop_step_description": "Flush local DNS cache",
                        "command": "ipconfig /flushdns",
                        "source_quote": "Flush the local DNS resolver cache",
                    }
                ],
            }
        }
        raw_doc_text = (
            "Corporate Maintenance SOP\n"
            "Flush the local DNS resolver cache to clear stale network records."
        )
        canonical = build_canonical_sop_from_draft(draft, raw_text=raw_doc_text)
        self.assertEqual(len(canonical["steps"]), 1)
        self.assertEqual(canonical["steps"][0]["quote"], "Flush the local DNS resolver cache")
        self.assertTrue(canonical["steps"][0]["verified"])


if __name__ == "__main__":
    unittest.main()

