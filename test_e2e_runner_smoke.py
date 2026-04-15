#!/usr/bin/env python3
"""Smoke tests for the end-to-end test runner script."""

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
RUNNER = REPO_ROOT / "run_full_stack_tests.sh"


class E2ERunnerSmokeTests(unittest.TestCase):
    def test_runner_exists(self):
        self.assertTrue(RUNNER.exists(), msg=f"Runner script missing: {RUNNER}")

    def test_runner_has_valid_shell_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(RUNNER)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"Shell syntax check failed: {result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
