import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "report.json"

    def tearDown(self):
        self.temp.cleanup()

    def call(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = check.main(args)
        return code, stdout.getvalue() + stderr.getvalue()

    def test_existing_output_and_symlink_are_preserved(self):
        self.path.write_text("preserve")
        code, _ = self.call(["--output", str(self.path)])
        self.assertEqual(code, 1)
        self.assertEqual(self.path.read_text(), "preserve")
        link = self.path.parent / "link"
        link.symlink_to(self.path)
        code, _ = self.call(["--output", str(link)])
        self.assertEqual(code, 1)
        self.assertTrue(link.is_symlink())

    def test_invalid_arguments_never_echo_possible_credentials(self):
        code, text = self.call(["--output", str(self.path), "--api-key", "SENSITIVE-KEY"])
        self.assertEqual(code, 1)
        self.assertNotIn("SENSITIVE-KEY", text)
        self.assertFalse(self.path.exists())

    def test_failure_never_echoes_exception_or_writes_pass_report(self):
        with patch.object(check, "run_checks", side_effect=RuntimeError("SENSITIVE-KEY")):
            code, text = self.call(["--output", str(self.path)])
        self.assertEqual(code, 1)
        self.assertNotIn("SENSITIVE-KEY", text)
        self.assertFalse(self.path.exists())

    def test_success_is_private_synthetic_and_live_blocked(self):
        # Stub recursion only: the real runner executes this suite externally.
        with patch.object(check, "run_checks", return_value={"run": 1, "failures": 0, "errors": 0, "skipped": 0}):
            code, _ = self.call(["--output", str(self.path)])
        self.assertEqual(code, 0)
        report = json.loads(self.path.read_text())
        self.assertEqual(report["status"], "offline-core-passed-live-blocked")
        self.assertFalse(report["paid_collection_enabled"])
        self.assertFalse(report["credentials_loaded"])
        self.assertFalse(report["network_used"])
        self.assertTrue(report["synthetic_only"])
        self.assertFalse(report["evidence"]["off_machine_restore_verified"])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_rehearsal_still_runs_without_any_network(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            self.assertTrue(check.rehearsal()["local_restore_replay_passed"])


if __name__ == "__main__":
    unittest.main()
