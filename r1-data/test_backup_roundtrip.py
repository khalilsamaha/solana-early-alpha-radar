import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import backup_roundtrip as b


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.source = self.root/"handoff"
        r = b.h.rehearse(self.source)
        self.bundle = self.source/"export/capture.zip"
        self.report = self.source/"report.json"
        self.raw = self.bundle.read_bytes(); self.report_raw = self.report.read_bytes()
        self.patches = [patch.object(b, "EXPECTED_BUNDLE", r["bundle_sha256"]),
                        patch.object(b, "EXPECTED_REPORT", b.h.c.digest(self.report_raw)),
                        patch.object(b, "BUNDLE_BYTES", len(self.raw)),
                        patch.object(b, "trusted_programs")]
        for p in self.patches: p.start()
        self.calls = []; self.remote = {}; self.fail_at = None; self.returned = None
        self.metadata = b"radar-b2: b2\n"
        self.output = self.root/"roundtrip"

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def process(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if len(self.calls) == self.fail_at:
            raise subprocess.TimeoutExpired(command, 40, output=b"SECRET", stderr=b"SECRET")
        if "listremotes" in command:
            return subprocess.CompletedProcess(command, 0, self.metadata)
        if "rcat" in command:
            target = command[command.index("rcat")+1]
            self.remote[target] = kwargs["input"]
            return subprocess.CompletedProcess(command, 0, None)
        target = command[command.index("cat")+1]
        return subprocess.CompletedProcess(command, 0, self.remote[target] if self.returned is None else self.returned)

    def run_backup(self):
        with patch.object(b.subprocess, "run", side_effect=self.process), patch("socket.socket", side_effect=AssertionError("network forbidden")):
            return b.run(self.bundle, self.report, self.output)

    def test_exact_round_trip_private_restoration_and_no_production_claim(self):
        report = self.run_backup()
        self.assertEqual(report["status"], "synthetic-backup-roundtrip-passed-live-blocked")
        self.assertEqual([c["operation"] for c in report["calls"]], ["backend", "upload", "download"])
        self.assertTrue(report["configured_backend_b2"])
        self.assertTrue(report["remote_download_verified"])
        self.assertTrue(report["downloaded_capture_replayed"])
        self.assertEqual((self.output/"downloaded.zip").read_bytes(), self.raw)
        self.assertEqual(report["capture"], json.loads(self.report_raw)["capture"])
        self.assertEqual(self.bundle.read_bytes(), self.raw)
        self.assertEqual(self.report.read_bytes(), self.report_raw)
        self.assertEqual((self.output/"report.json").stat().st_mode & 0o777, 0o600)
        self.assertFalse(report["production_backup_coverage_verified"])
        self.assertFalse(report["ongoing_retention_verified"])
        self.assertEqual(report["remote_deletions"], 0)

    def test_privileged_command_uses_stdin_no_local_paths_and_scrubbed_environment(self):
        self.run_backup()
        for command, kw in self.calls:
            self.assertEqual(command[:6], [b.SUDO, "-n", b.TIMEOUT, "--signal=TERM", "--kill-after=2s", "40s"])
            self.assertIn(b.RCLONE, command)
            self.assertEqual(command[command.index("--config")+1], b.CONFIG)
            self.assertEqual(command[command.index("--retries")+1], "1")
            self.assertEqual(command[command.index("--low-level-retries")+1], "1")
            self.assertEqual(kw["env"], b.ENV)
            self.assertEqual(kw["stderr"], subprocess.DEVNULL)
            self.assertLessEqual(kw["timeout"], 44)
            self.assertNotIn(str(self.root), " ".join(command))
            self.assertNotIn("shell", kw)
            self.assertFalse(any(x in command for x in ("sync", "delete", "purge", "config")))
        self.assertEqual(self.calls[1][1]["input"], self.raw)
        self.assertEqual(self.calls[1][1]["stdout"], subprocess.DEVNULL)
        self.assertEqual(self.calls[2][0][-2:], ["--count", str(len(self.raw)+1)])

    def test_unknown_wrong_duplicate_or_oversized_backend_metadata_stops_before_upload(self):
        for i, metadata in enumerate((b"other: b2\n", b"radar-b2: local\n", b"radar-b2: b2\nradar-b2: b2\n", b"x"*4097)):
            self.metadata = metadata; self.calls = []; self.output = self.root/("out"+str(i))
            result = self.run_backup()
            self.assertEqual(result["status"], "synthetic-backup-roundtrip-unavailable")
            self.assertEqual(len(self.calls), 1)
            self.assertFalse(result["remote_object_may_exist"])
            self.assertFalse(result["configured_backend_b2"])

    def test_failure_at_each_stage_keeps_sanitized_report_without_retry_or_delete(self):
        for stage in (1, 2, 3):
            self.calls = []; self.fail_at = stage; self.output = self.root/("stage"+str(stage))
            result = self.run_backup()
            self.assertEqual(len(self.calls), stage)
            self.assertEqual(result["status"], "synthetic-backup-roundtrip-unavailable")
            self.assertFalse(result["remote_download_verified"])
            self.assertEqual(result["remote_object_may_exist"], stage >= 2)
            self.assertNotIn("SECRET", (self.output/"report.json").read_text())

    def test_changed_truncated_and_extra_download_bytes_never_pass(self):
        for i, raw in enumerate((self.raw[:-1], self.raw+b"x", b"x"*len(self.raw), self.raw+b"xx")):
            self.returned = raw; self.calls = []; self.output = self.root/("bad"+str(i))
            result = self.run_backup()
            self.assertTrue(result["remote_upload_completed"])
            self.assertFalse(result["remote_download_verified"])
            self.assertEqual(result["status"], "synthetic-backup-roundtrip-unavailable")
            self.assertFalse((self.output/"downloaded.zip").exists())

    def test_wrong_report_or_package_never_calls_privileged_process(self):
        self.report.write_bytes(self.report_raw+b" ")
        with patch.object(b.subprocess, "run", side_effect=AssertionError("must not execute")):
            with self.assertRaises(b.h.c.CaptureError): b.run(self.bundle, self.report, self.output)
        self.assertFalse(self.output.exists())
        self.report.write_bytes(self.report_raw); self.bundle.write_bytes(b"x"*len(self.raw))
        with self.assertRaises(b.h.c.CaptureError): self.run_backup()
        self.assertEqual(self.calls, [])

    def test_existing_output_preserved_before_privileged_process(self):
        self.output.mkdir(); (self.output/"keep").write_text("preserve")
        with self.assertRaises(FileExistsError): self.run_backup()
        self.assertEqual(self.calls, [])
        self.assertEqual((self.output/"keep").read_text(), "preserve")

    def test_method_sequence_scope_digest_and_deadline_cannot_expand(self):
        transfer = b.Transfer()
        target = b.PREFIX+"handoff-"+"a"*32+"-"+b.EXPECTED_BUNDLE[:12]+".zip"
        with self.assertRaises(b.h.c.CaptureError): transfer.run("upload", target, self.raw)
        with patch.object(b.subprocess, "run", side_effect=self.process):
            transfer.run("backend")
            for operation, remote, payload in (("delete", target, None), ("upload", "other:path", self.raw),
                                                ("upload", target, b"bad")):
                with self.assertRaises(b.h.c.CaptureError): transfer.run(operation, remote, payload)
            transfer.run("upload", target, self.raw)
            with self.assertRaises(b.h.c.CaptureError): transfer.run("download", target+"extra")
            transfer.run("download", target)
            with self.assertRaises(b.h.c.CaptureError): transfer.run("backend")
        self.assertEqual(len(self.calls), 3)
        expired = b.Transfer(); expired.deadline = 0
        with self.assertRaises(b.h.c.CaptureError): expired.run("backend")
        self.assertEqual(expired.calls, [])

    def test_failed_process_stops_client_and_nonzero_exit_never_succeeds(self):
        transfer = b.Transfer()
        with patch.object(b.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"SECRET")) as process:
            with self.assertRaises(b.h.c.CaptureError): transfer.run("backend")
            with self.assertRaises(b.h.c.CaptureError): transfer.run("backend")
        self.assertEqual(process.call_count, 1)
        self.assertNotIn("SECRET", str(transfer.calls))

    def test_missing_program_preserves_offline_preflight_and_failure_report(self):
        with patch.object(b, "trusted_programs", side_effect=FileNotFoundError("SECRET")):
            result = self.run_backup()
        self.assertEqual(result["calls"], [])
        self.assertFalse(result["backup_credentials_access_attempted"])
        self.assertTrue((self.output/"preflight/report.json").exists())
        self.assertEqual(result["status"], "synthetic-backup-roundtrip-unavailable")

    def test_live_cli_flag_required_and_argument_errors_sanitized(self):
        args = ["--bundle", str(self.bundle), "--handoff-report", str(self.report), "--output-directory", str(self.output)]
        text = io.StringIO()
        with contextlib.redirect_stdout(text), contextlib.redirect_stderr(text), patch.object(b, "run") as run:
            self.assertEqual(b.main(args), 1)
            self.assertEqual(b.main(args+["--round-trip-b2", "--api-key", "SECRET"]), 1)
        run.assert_not_called()
        self.assertNotIn("SECRET", text.getvalue())

    def test_cli_retains_diagnostic_unavailable_instead_of_false_pass(self):
        self.fail_at = 2
        with patch.object(b.subprocess, "run", side_effect=self.process), contextlib.redirect_stdout(io.StringIO()):
            code = b.main(["--bundle", str(self.bundle), "--handoff-report", str(self.report),
                           "--output-directory", str(self.output), "--round-trip-b2"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((self.output/"report.json").read_text())["status"], "synthetic-backup-roundtrip-unavailable")
