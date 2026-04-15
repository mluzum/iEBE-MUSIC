#!/usr/bin/env python3
"""Build script smoke checks (syntax-level)."""

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


class BuildScriptSmokeTests(unittest.TestCase):
    def _bash_syntax_check(self, rel_path):
        script_path = REPO_ROOT / rel_path
        result = subprocess.run(
            ["bash", "-n", str(script_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"bash -n failed for {rel_path}: {result.stderr}",
        )

    def test_get_code_packages_shell_syntax(self):
        self._bash_syntax_check("codes/get_code_packages.sh")

    def test_compile_code_packages_shell_syntax(self):
        self._bash_syntax_check("codes/compile_code_packages.sh")


if __name__ == "__main__":
    unittest.main()
