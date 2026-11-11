import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from source_probe import collect, discover_database, main

NOW = 1_800_000_000_000


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "radar.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, n=3, *, oversized=False, future=False, index=True):
        db = sqlite3.connect(self.path)
        try:
            db.execute("CREATE TABLE launch_registry(mint TEXT PRIMARY KEY,received_at INTEGER,data TEXT)")
            db.execute("CREATE TABLE events(data TEXT)")
            db.execute("INSERT INTO events VALUES('PRIVATE-OUTCOME')")
            if index:
                db.execute("CREATE INDEX launch_registry_received ON launch_registry(received_at)")
            for i in range(n):
                at = NOW + 100 if future else NOW - i
                row = {"version": "launch-registry-1", "source": "pumpportal:create",
                       "receivedAt": at, "availableAt": at,
                       "fields": {"signature": "PRIVATE-SIGNATURE", "slotReported": None,
                                  "traderReported": "PRIVATE-WALLET", "virtualSolReservesReported": "30"}}
                db.execute("INSERT INTO launch_registry VALUES(?,?,?)", (str(i), at, "x" * 5000 if oversized else json.dumps(row)))
            db.commit()
        finally:
            db.close()

    def test_read_only_presence_counts_and_no_raw_values(self):
        self.fixture()
        before = self.path.read_bytes()
        result = collect(self.path, now_ms=NOW)
        self.assertEqual(result["status"], "creation-metadata-observed")
        self.assertEqual(result["valid_records"], 3)
        self.assertEqual(result["field_nonnull"]["signature"], 3)
        self.assertEqual(result["field_absent_or_null"]["slotReported"], 3)
        self.assertFalse(result["outcomes_read"])
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertFalse(result["source_complete"])
        self.assertEqual(before, self.path.read_bytes())

    def test_sample_is_bounded_at_128(self):
        self.fixture(200)
        result = collect(self.path, now_ms=NOW)
        self.assertEqual(result["rows_sampled"], 128)

    def test_missing_database_is_not_created(self):
        result = collect(self.path, now_ms=NOW)
        self.assertEqual(result["status"], "source-metadata-unavailable")
        self.assertFalse(self.path.exists())

    def test_missing_index_does_not_fall_back_to_full_scan(self):
        self.fixture(index=False)
        self.assertEqual(collect(self.path, now_ms=NOW)["status"], "source-metadata-unavailable")

    def test_future_clock_and_old_records_do_not_claim_recent_evidence(self):
        self.fixture(future=True)
        self.assertEqual(collect(self.path, now_ms=NOW)["status"], "source-metadata-unavailable")
        self.path.unlink()
        self.fixture()
        result = collect(self.path, now_ms=NOW + 2 * 86_400_000)
        self.assertEqual(result["status"], "creation-metadata-insufficient")
        self.assertEqual(result["rows_sampled"], 0)

    def test_oversized_record_not_exported(self):
        self.fixture(oversized=True)
        result = collect(self.path, now_ms=NOW)
        self.assertEqual(result["oversized_records"], 3)
        self.assertEqual(result["valid_records"], 0)

    def test_view_and_symlink_rejected(self):
        self.fixture()
        link = self.root / "link.sqlite"
        link.symlink_to(self.path)
        self.assertEqual(collect(link, now_ms=NOW)["status"], "source-metadata-unavailable")
        db = sqlite3.connect(self.path)
        try:
            db.execute("DROP TABLE launch_registry")
            db.execute("CREATE VIEW launch_registry AS SELECT data FROM events")
            db.commit()
        finally:
            db.close()
        self.assertEqual(collect(self.path, now_ms=NOW)["status"], "source-metadata-unavailable")

    def test_deadline_failure_never_promotes_partial_result(self):
        self.fixture()
        result = collect(self.path, now_ms=NOW, seconds=0.0000001)
        self.assertEqual(result["status"], "source-metadata-unavailable")

    def test_malformed_record_counted_separately(self):
        self.fixture()
        db = sqlite3.connect(self.path)
        try:
            db.execute("UPDATE launch_registry SET data='{}' WHERE mint='0'")
            db.commit()
        finally:
            db.close()
        result = collect(self.path, now_ms=NOW)
        self.assertEqual((result["valid_records"], result["invalid_records"]), (2, 1))

    def test_unavailable_report_saved_without_leaking_path_or_credentials(self):
        out = self.root / "report.json"
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--database", str(self.root / "PRIVATE-KEY"), "--output", str(out)])
        self.assertEqual(code, 0)
        self.assertNotIn("PRIVATE-KEY", out.read_text() + stdout.getvalue() + stderr.getvalue())
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(out.read_text())["status"], "source-metadata-unavailable")

    def test_existing_report_preserved(self):
        out = self.root / "report.json"
        out.write_text("preserve")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--database", str(self.path), "--output", str(out)]), 1)
        self.assertEqual(out.read_text(), "preserve")

    def test_docker_discovery_is_local_and_never_inspects_environment(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                return SimpleNamespace(returncode=0, stdout=b"a" * 64 + b"\n")
            return SimpleNamespace(returncode=0, stdout=json.dumps({"running": True, "sources": [str(self.root)]}).encode())
        path = discover_database(self.root, runner)
        self.assertEqual(path, self.path)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(a[:3] == ["docker", "--host", "unix:///var/run/docker.sock"] for a in calls))
        self.assertIn("label=com.docker.compose.project.working_dir=" + str(self.root), calls[0])
        self.assertIn("--format", calls[1])
        self.assertNotIn(".Config.Env", " ".join(calls[1]))
        self.assertNotIn("compose", calls[0])

    def test_ambiguous_container_does_not_choose_arbitrarily(self):
        def runner(*args, **kwargs):
            return SimpleNamespace(returncode=0, stdout=b"a" * 64 + b"\n" + b"b" * 64)
        with self.assertRaises(Exception):
            discover_database(self.root, runner)

    def test_discovery_failure_still_produces_unavailable_report(self):
        out = self.root / "report.json"
        with patch("source_probe.discover_database", side_effect=RuntimeError("SECRET")):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--project", str(self.root), "--output", str(out)]), 0)
        result = json.loads(out.read_text())
        self.assertEqual(result["discovery_status"], "local-data-mount-unavailable")
        self.assertEqual(result["status"], "source-metadata-unavailable")
        self.assertNotIn("SECRET", out.read_text())

    def test_wrong_or_stopped_mount_never_opens_database(self):
        count = 0
        def runner(*args, **kwargs):
            nonlocal count
            count += 1
            return SimpleNamespace(returncode=0, stdout=b"a" * 64 if count == 1 else b'{"running":false,"sources":[]}')
        with self.assertRaises(Exception):
            discover_database(self.root, runner)

    def test_project_cli_publishes_source_counts_and_code_pins(self):
        self.fixture()
        out = self.root / "source.json"
        with patch("source_probe.discover_database", return_value=self.path):
            with patch("source_probe.time.time_ns", return_value=NOW * 1_000_000):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--project", str(self.root), "--output", str(out)]), 0)
        result = json.loads(out.read_text())
        self.assertEqual(result["status"], "creation-metadata-observed")
        self.assertEqual(result["discovery_status"], "local-data-mount-found")
        self.assertEqual(result["valid_records"], 3)
        self.assertEqual(set(result["source_sha256"]), {"source_probe.py", "capture.py"})
        self.assertFalse(result["live_activation_allowed"])
        self.assertNotIn("PRIVATE", out.read_text())
