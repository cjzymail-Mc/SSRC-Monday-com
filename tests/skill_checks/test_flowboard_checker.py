"""Run the full-check wrapper only inside disposable, minimal Git repositories.

No Flowboard product suites, network operations, or real runtime data are used.
Run: python -m unittest discover -s tests/skill_checks -p test_flowboard_checker.py -v
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / ".agents/skills/commit-push-pr/scripts/run-flowboard-checks.ps1"
GIT = shutil.which("git")
PWSH = shutil.which("pwsh")


@unittest.skipUnless(GIT and PWSH and shutil.which("node"), "Git, PowerShell 7 and Node required")
class FlowboardCheckerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="flowboard-checker-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
                        PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Isolated checker test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.put(".gitignore", "__pycache__/\nflowboard.db\nbackups/\n.env\ntemporary/\n")
        self.put("tests/test_product.py", "import unittest\nclass Product(unittest.TestCase):\n    def test_product(self):\n        self.assertEqual(2 + 2, 4)\n")
        self.put("tests/product.test.js", "const test = require('node:test');\nconst assert = require('node:assert/strict');\ntest('product', () => assert.equal(2 + 2, 4));\n")
        self.put("app.py", "VALUE = 1\n")
        self.put("app.js", "const value = 1;\n")

    def put(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def git(self, *args):
        result = subprocess.run([GIT, *args], cwd=self.root, env=self.env,
                                text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def commit_fixture(self):
        self.git("add", "--all")  # Disposable fixture only.
        self.git("commit", "-m", "checker fixture")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def run_checker(self, success=True):
        result = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(SCRIPT)],
                                cwd=self.root, env=self.env, text=True, encoding="utf-8",
                                capture_output=True, timeout=60)
        output = result.stdout + result.stderr
        if success:
            self.assertEqual(result.returncode, 0, output)
            self.assertIn("FLOWBOARD_CHECKS_OK", output)
            self.assertIn("real_data_guard=unchanged", output)
        else:
            self.assertNotEqual(result.returncode, 0, output)
            self.assertNotIn("FLOWBOARD_CHECKS_OK", output)
        return output

    def test_tracked_unicode_spaces_and_tool_exclusions(self):
        self.put("src/名字 with space.py", "VALUE = '有效'\n")
        self.put("src/名字 with space.js", "const value = '有效';\n")
        self.put(".agents/tools/invalid.py", "def broken(\n")
        self.put(".agents/tools/invalid.js", "const = ;\n")
        self.put("tests/skill_checks/test_invalid.py", "def broken(\n")
        self.put("tests/skill_checks/invalid.js", "const = ;\n")
        self.commit_fixture()
        self.put("temporary/untracked.py", "def broken(\n")
        self.put("temporary/untracked.js", "const = ;\n")
        self.put("backups/old.py", "def broken(\n")
        self.put("flowboard.db", "isolated database sentinel\n")
        output = self.run_checker()
        self.assertIn("Python syntax batch (3 tracked files)", output)
        self.assertIn("JavaScript syntax: src/名字 with space.js", output)
        self.assertNotIn("JavaScript syntax: .agents/", output)
        self.assertFalse((self.root / "src/__pycache__").exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_tracked_python_syntax_error_fails_batch(self):
        self.put("src/错误 file.py", "def broken(\n")
        self.commit_fixture()
        output = self.run_checker(success=False)
        self.assertIn("SyntaxError", output)
        self.assertIn("src/错误 file.py", output)

    def test_tracked_javascript_syntax_error_fails(self):
        self.put("src/错误 file.js", "const = ;\n")
        self.commit_fixture()
        output = self.run_checker(success=False)
        self.assertIn("SyntaxError", output)
        self.assertIn("JavaScript syntax: src/错误 file.js", output)

    def test_tracked_historical_source_remains_checked(self):
        self.put("archive/old.py", "def broken(\n")
        self.commit_fixture()
        output = self.run_checker(success=False)
        self.assertIn("archive/old.py", output)
        self.assertIn("SyntaxError", output)

    def test_product_test_failure_is_not_suppressed(self):
        self.put("tests/test_product.py", "import unittest\nclass Product(unittest.TestCase):\n    def test_product(self):\n        self.fail('product sentinel failure')\n")
        self.commit_fixture()
        output = self.run_checker(success=False)
        self.assertIn("product sentinel failure", output)
        self.assertIn("Python full suite failed", output)

    def test_guard_runs_even_when_product_suite_fails(self):
        self.put("tests/test_product.py", "import unittest\nfrom pathlib import Path\nclass Product(unittest.TestCase):\n    def test_product(self):\n        Path('flowboard.db').write_text('changed fixture')\n        self.fail('product sentinel failure')\n")
        self.commit_fixture()
        self.put("flowboard.db", "isolated database sentinel\n")
        output = self.run_checker(success=False)
        self.assertIn("CHECKS_AND_REAL_DATA_GUARD_FAILED", output)
        self.assertIn("REAL_DATA_GUARD_FAILED", output)
        self.assertIn("product sentinel failure", output)


if __name__ == "__main__":
    unittest.main()
