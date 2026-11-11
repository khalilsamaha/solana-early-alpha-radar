import contextlib
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import capture as c
import measurement as m
import session_bundle as b
import test_measurement as fixtures
from transport import run_session


class BundleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.capture = self.root / "capture"
        self.journal = self.root / "session.jsonl"
        clock = fixtures.Clock()
        wire = fixtures.Wire(clock, [fixtures.frame(), fixtures.frame("buy"), fixtures.frame("sell"), fixtures.frame("migration")])
        async def factory(): return wire
        with m.Journal(self.journal, wall=lambda: clock.wall, monotonic=lambda: clock.mono) as journal:
            with c.Capture(self.capture, c.Limits(messages=4, sample_modulus=1),
                           wall=lambda: clock.wall, monotonic=lambda: clock.mono) as capture:
                result = await run_session(capture, factory, journal=journal)
        self.assertEqual(result["outcome"], "capture-stopped")

    def tearDown(self):
        self.tmp.cleanup()

    def export(self):
        result = b.export_session(self.capture, self.journal, self.root / "export")
        return result, self.root / "export/session.zip"

    def store(self, raw, name="modified.zip"):
        path = self.root / name
        c.exclusive_file(path, raw)
        return path

    def zip_variant(self, contents, *, compression=zipfile.ZIP_STORED, name=None, mode=stat.S_IFREG | 0o600):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=compression) as archive:
            for key, raw in contents.items():
                entry = zipfile.ZipInfo(name if key == "session.jsonl" and name else key,
                                        date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = mode << 16
                entry.compress_type = compression
                archive.writestr(entry, raw)
        return output.getvalue()

    def test_export_restore_pair_preserves_exact_inputs_and_measurements(self):
        originals = ((self.capture / "ticks.db").read_bytes(), self.journal.read_bytes())
        exported, path = self.export()
        restored = b.restore_session(path, exported["bundle_sha256"], self.root / "restore")
        self.assertEqual(restored["capture"], exported["capture"])
        self.assertEqual(restored["measurement"], exported["measurement"])
        self.assertEqual(originals, ((self.capture / "ticks.db").read_bytes(), self.journal.read_bytes()))
        self.assertEqual(originals[0], (self.root / "restore/capture-restore/restored/ticks.db").read_bytes())
        self.assertEqual(originals[1], (self.root / "restore/session.jsonl").read_bytes())
        for key in ("network_used", "credentials_loaded", "paid_collection_enabled", "remote_upload_performed",
                    "remote_download_verified", "off_machine_restore_verified"):
            self.assertFalse(restored[key])
        for p in (self.root / "restore").rglob("*"):
            self.assertEqual(p.stat().st_mode & 0o777, 0o700 if p.is_dir() else 0o600)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_package_is_deterministic_and_three_fixed_members(self):
        _, path = self.export()
        contents, binding = b.unpack(path.read_bytes())
        self.assertEqual(set(contents), {"capture.zip", "session.jsonl", "binding.json"})
        self.assertEqual(b.pack(contents), path.read_bytes())
        again = b.export_session(self.capture, self.journal, self.root / "export-again")
        self.assertEqual(again["bundle_sha256"], c.digest(path.read_bytes()))
        self.assertEqual(binding["measurement"]["local_sends_completed"], 3)

    def test_external_digest_required_before_extraction(self):
        _, path = self.export()
        for i, checksum in enumerate((None, "", "0" * 64, "SYNTHETIC-SECRET")):
            out = self.root / f"restore-{i}"
            with self.assertRaises(c.CaptureError): b.restore_session(path, checksum, out)
            self.assertFalse(out.exists())

    def test_missing_journal_and_substituted_journal_cannot_export(self):
        other = self.root / "other"
        with c.Capture(other, c.Limits(messages=1)) as capture:
            capture.receive(fixtures.frame())
        with self.assertRaises(c.CaptureError):
            b.export_session(other, self.journal, self.root / "bad-export")
        self.assertFalse((self.root / "bad-export").exists())
        with self.assertRaises(FileNotFoundError):
            b.export_session(self.capture, self.root / "missing", self.root / "bad-export")

    def test_changed_payload_cannot_hide_behind_original_binding(self):
        _, path = self.export()
        contents, _ = b.unpack(path.read_bytes())
        contents["session.jsonl"] = contents["session.jsonl"] + b" \n"
        raw = b.pack(contents)
        altered = self.store(raw)
        with self.assertRaises(c.CaptureError):
            b.restore_session(altered, c.digest(raw), self.root / "bad-restore")
        self.assertFalse((self.root / "bad-restore").exists())

    def test_rebound_journal_corruption_is_rejected_by_replay(self):
        _, path = self.export()
        contents, binding = b.unpack(path.read_bytes())
        contents["session.jsonl"] = contents["session.jsonl"][:-1]
        binding["journal_sha256"] = c.digest(contents["session.jsonl"])
        contents["binding.json"] = c.canonical(binding).encode()
        raw = b.pack(contents)
        altered = self.store(raw)
        with self.assertRaises(c.CaptureError):
            b.restore_session(altered, c.digest(raw), self.root / "bad-restore")
        self.assertFalse((self.root / "bad-restore/report.json").exists())
        self.assertEqual(altered.read_bytes(), raw)

    def test_forged_measurement_or_capture_claim_is_recomputed(self):
        _, path = self.export()
        for i, key in enumerate(("measurement", "capture")):
            contents, binding = b.unpack(path.read_bytes())
            if key == "measurement": binding[key]["provider_acknowledged_subscriptions"] = 1
            else: binding[key]["raw_rows"] = 0
            contents["binding.json"] = c.canonical(binding).encode()
            raw = b.pack(contents)
            altered = self.store(raw, f"modified-{i}.zip")
            with self.assertRaises(c.CaptureError):
                b.restore_session(altered, c.digest(raw), self.root / f"bad-restore-{i}")
            self.assertFalse((self.root / f"bad-restore-{i}/report.json").exists())

    def test_unsafe_zip_members_compression_and_trailers_are_rejected(self):
        _, path = self.export()
        raw = path.read_bytes()
        contents, _ = b.unpack(raw)
        cases = [raw + b"trailer", b"prefix" + raw,
                 self.zip_variant(contents, name="../outside"),
                 self.zip_variant(contents, mode=stat.S_IFLNK | 0o600),
                 self.zip_variant(contents, compression=zipfile.ZIP_DEFLATED),
                 self.zip_variant(dict(contents, extra=b"x")),
                 self.zip_variant({k:v for k,v in contents.items() if k != "session.jsonl"})]
        for altered in cases:
            with self.assertRaises(c.CaptureError): b.unpack(altered)
        self.assertFalse((self.root / "outside").exists())

    def test_directory_and_total_size_caps_precede_zip_parser(self):
        _, path = self.export()
        raw = path.read_bytes()
        end = list(struct.unpack("<4s4H2LH", raw[-22:]))
        end[3] = end[4] = 65535
        altered = raw[:-22] + struct.pack("<4s4H2LH", *end)
        with patch.object(b.zipfile, "ZipFile", side_effect=AssertionError("must reject first")):
            with self.assertRaises(c.CaptureError): b.unpack(altered)
            with patch.object(b, "MAX_PACKAGE", len(raw) - 1):
                with self.assertRaises(c.CaptureError): b.unpack(raw)

    def test_old_source_binding_is_not_silently_accepted_by_new_reader(self):
        _, path = self.export()
        with patch.object(b, "source_pins", return_value={}):
            with self.assertRaises(c.CaptureError): b.unpack(path.read_bytes())

    def test_existing_outputs_symlink_and_nested_export_are_preserved(self):
        exported, path = self.export()
        with self.assertRaises(FileExistsError): self.export()
        out = self.root / "existing"
        out.mkdir(mode=0o700)
        (out / "preserve").write_text("preserve")
        with self.assertRaises(FileExistsError): b.restore_session(path, exported["bundle_sha256"], out)
        self.assertEqual((out / "preserve").read_text(), "preserve")
        alias = self.root / "alias.zip"
        alias.symlink_to(path)
        with self.assertRaises(c.CaptureError): b.restore_session(alias, exported["bundle_sha256"], self.root / "restored")
        with self.assertRaises(c.CaptureError): b.export_session(self.capture, self.journal, self.capture / "nested")
        self.assertFalse((self.capture / "nested").exists())

    def test_failed_report_write_cannot_claim_success_or_delete_inputs(self):
        original = (self.capture / "ticks.db").read_bytes(), self.journal.read_bytes()
        write = c.exclusive_file
        def fail(path, raw):
            if path == self.root / "export/report.json":
                raise OSError("SYNTHETIC-SECRET")
            return write(path, raw)
        with patch.object(c, "exclusive_file", side_effect=fail):
            with self.assertRaises(OSError): self.export()
        self.assertFalse((self.root / "export/report.json").exists())
        self.assertEqual(original, ((self.capture / "ticks.db").read_bytes(), self.journal.read_bytes()))

    def test_cli_failures_are_sanitized_and_no_live_mode_exists(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), contextlib.redirect_stdout(output):
            result = b.main(["restore", "--bundle", "SYNTHETIC-SECRET", "--expected-sha256", "0" * 64,
                             "--output-directory", str(self.root / "output")])
            self.assertEqual(result, 1)
            self.assertEqual(b.main(["--live", "SYNTHETIC-SECRET"]), 1)
        self.assertNotIn("SYNTHETIC-SECRET", output.getvalue())
        self.assertFalse((self.root / "output").exists())


if __name__ == "__main__":
    unittest.main()
