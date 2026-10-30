"""
Unit Test Integration for Golden Test Set Benchmark (Section 19.2)
=================================================================
Executes the 16-case Golden Test Set evaluation and asserts 100% pass rate.
"""

import os
import sys
import unittest

# Ensure backend root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from tests.eval_golden_set import run_golden_set_evaluation


class TestGoldenSetBenchmark(unittest.TestCase):
    """Executes Section 19.2 Golden Test Set Benchmark across all 4 categories."""

    def test_run_all_golden_cases(self):
        manifest_path = os.path.join(os.path.dirname(__file__), "golden_set", "manifest.json")
        all_passed, report = run_golden_set_evaluation(manifest_path)
        
        total = report["total_cases"]
        passed = report["passed_cases"]
        pass_rate = report["pass_rate_pct"]
        
        self.assertEqual(
            passed,
            total,
            f"Golden set benchmark failures: only {passed}/{total} ({pass_rate:.1f}%) passed! Failed cases: "
            + str([r["id"] for r in report["results"] if not r["passed"]])
        )
        self.assertTrue(all_passed)


if __name__ == "__main__":
    unittest.main()

