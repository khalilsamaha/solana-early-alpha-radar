import contextlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import capture as c
import handoff as h
from test_capture import frame


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.capture = self.root/"capture"
        with c.Capture(self.capture, c.Limits(messages=2, sample_modulus=1)) as source:
            source.receive(frame())
            source.receive(frame("buy"))
        self.original = (self.capture/"ticks.db").read_bytes()
        self.export = self.root/"export"
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            self.report = h.export_capture(self.capture, self.export)
        self.bundle = self.export/"capture.zip"
        self.raw = self.bundle.read_bytes()

    def tearDown(self): self.tmp.cleanup()

    def rebuild(self, changes=None, extra=None, compression=zipfile.ZIP_STORED):
        with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
            members = {name: archive.read(name) for name in h.MEMBERS}
        if changes: members = changes(members)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, data in [*members.items(), *(extra or [])]:
                entry = zipfile.ZipInfo(name)
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | 0o600) << 16
                entry.compress_type = compression
                archive.writestr(entry, data)
        return output.getvalue()

    def try_restore(self, raw, name="changed"):
        package = self.root/(name+".zip")
        c.exclusive_file(package, raw)
        return h.restore_capture(package, c.digest(raw), self.root/name)

    def test_export_is_deterministic_private_and_preserves_source(self):
        self.assertEqual((self.capture/"ticks.db").read_bytes(), self.original)
        again = h.export_capture(self.capture, self.root/"again")
        self.assertEqual(again["bundle_sha256"], self.report["bundle_sha256"])
        self.assertEqual(self.raw, (self.root/"again/capture.zip").read_bytes())
        self.assertEqual(set(p.name for p in self.export.iterdir()), {"capture.zip", "report.json"})
        self.assertEqual(self.export.stat().st_mode & 0o777, 0o700)
        for path in self.export.iterdir(): self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
            self.assertEqual(set(archive.namelist()), set(h.MEMBERS))
            self.assertTrue(all(e.compress_type == zipfile.ZIP_STORED for e in archive.infolist()))

    def test_copied_bundle_restores_exact_bytes_and_replay_without_remote_claim(self):
        transferred = self.root/"returned.zip"
        c.exclusive_file(transferred, self.raw)
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            report = h.restore_capture(transferred, self.report["bundle_sha256"], self.root/"restore")
        self.assertEqual((self.root/"restore/restored/ticks.db").read_bytes(), self.original)
        self.assertEqual(report["capture"], self.report["capture"])
        self.assertTrue(report["transfer_bytes_match"])
        self.assertTrue(report["source_bundle_preserved"])
        for flag in ("network_used", "credentials_loaded", "remote_upload_performed", "remote_download_verified",
                     "off_machine_restore_verified", "paid_collection_enabled", "profitability_evaluated"):
            self.assertIs(report[flag], False)
        self.assertNotIn("bundle_file", report)

    def test_wrong_missing_or_malformed_expected_digest_stops_before_output(self):
        for value in (None, "", "f"*64, "A"*64, "0"*65):
            with self.assertRaises(c.CaptureError): h.restore_capture(self.bundle, value, self.root/"bad")
        self.assertFalse((self.root/"bad").exists())

    def test_swapped_valid_capture_cannot_match_original_receipt(self):
        other = self.root/"other"
        with c.Capture(other, c.Limits(messages=1)) as source: source.receive(frame(mint="3"*32))
        h.export_capture(other, self.root/"other-export")
        with self.assertRaises(c.CaptureError):
            h.restore_capture(self.root/"other-export/capture.zip", self.report["bundle_sha256"], self.root/"restore")
        self.assertFalse((self.root/"restore").exists())

    def test_manifest_and_sqlite_replay_tampering_rejected_even_with_new_package_digest(self):
        for i, kind in enumerate(("report", "database", "duplicate-json", "version-bool")):
            def change(members):
                manifest = json.loads(members["manifest.json"])
                if kind == "report": manifest["report"]["raw_rows"] += 1
                elif kind == "database": members["ticks.db"] = b"not-sqlite"; manifest["database_sha256"] = c.digest(members["ticks.db"])
                elif kind == "version-bool": manifest["version"] = True
                if kind == "duplicate-json":
                    members["manifest.json"] = b'{"version":1,"version":1}'
                else: members["manifest.json"] = c.canonical(manifest).encode()
                return members
            with self.assertRaises(Exception): self.try_restore(self.rebuild(change), "bad"+str(i))
            self.assertFalse((self.root/("bad"+str(i))/"report.json").exists())

    def test_path_traversal_unknown_duplicate_members_and_compression_rejected(self):
        variants = [self.rebuild(extra=[("../escape", b"x")]),
                    self.rebuild(extra=[("extra", b"x")]),
                    self.rebuild(compression=zipfile.ZIP_DEFLATED)]
        with patch("warnings.warn"):
            variants.append(self.rebuild(extra=[("ticks.db", b"duplicate")]))
        for i, raw in enumerate(variants):
            with self.assertRaises(c.CaptureError): self.try_restore(raw, "bad"+str(i))
        self.assertFalse((self.root/"escape").exists())

    def test_package_member_and_input_size_caps(self):
        raw = self.rebuild(lambda m: {**m, "manifest.json": b"x"*(h.MAX_MANIFEST+1)})
        with self.assertRaises(c.CaptureError): self.try_restore(raw)
        with patch.object(h, "MAX_PACKAGE", len(self.raw)-1):
            with self.assertRaises(c.CaptureError): h.restore_capture(self.bundle, self.report["bundle_sha256"], self.root/"cap")
        self.assertFalse((self.root/"cap").exists())

    def test_directory_count_and_size_rejected_before_zip_parser_allocation(self):
        end = list(struct.unpack("<4s4H2LH", self.raw[-22:]))
        for field, value in ((3, 65535), (4, 65535), (5, 513), (6, 0), (7, 1)):
            changed = list(end); changed[field] = value
            raw = self.raw[:-22] + struct.pack("<4s4H2LH", *changed)
            with patch.object(h.zipfile, "ZipFile", side_effect=AssertionError("parser must not start")):
                with self.assertRaises(c.CaptureError): h.unpack(raw, self.root/"unpacked")
        self.assertFalse((self.root/"unpacked").exists())

    def test_corrupt_payload_and_symbolic_link_member_never_produce_report(self):
        raw = bytearray(self.raw)
        raw[100] ^= 1
        with self.assertRaises(Exception): self.try_restore(bytes(raw), "crc")
        stream = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.raw)) as original, zipfile.ZipFile(stream, "w") as archive:
            for entry in original.infolist():
                data = original.read(entry)
                if entry.filename == "ticks.db": entry.external_attr = (stat.S_IFLNK | 0o600) << 16
                archive.writestr(entry, data)
        with self.assertRaises(c.CaptureError): self.try_restore(stream.getvalue(), "link")
        for name in ("crc", "link"): self.assertFalse((self.root/name/"report.json").exists())

    def test_symlinks_hardlinks_and_world_readable_inputs_rejected(self):
        alias = self.root/"alias"
        alias.symlink_to(self.export, target_is_directory=True)
        with self.assertRaises(c.CaptureError): h.restore_capture(alias/"capture.zip", self.report["bundle_sha256"], self.root/"restore")
        linked = self.root/"hardlink"
        os.link(self.bundle, linked)
        with self.assertRaises(c.CaptureError): h.restore_capture(self.bundle, self.report["bundle_sha256"], self.root/"restore")
        linked.unlink()
        self.bundle.chmod(0o644)
        with self.assertRaises(c.CaptureError): h.restore_capture(self.bundle, self.report["bundle_sha256"], self.root/"restore")
        self.assertFalse((self.root/"restore").exists())

    def test_existing_outputs_and_alias_parents_never_replace_data(self):
        out = self.root/"keep"; out.mkdir(); (out/"marker").write_text("preserve")
        with self.assertRaises(FileExistsError): h.restore_capture(self.bundle, self.report["bundle_sha256"], out)
        with self.assertRaises(FileExistsError): h.export_capture(self.capture, self.export)
        alias = self.root/"alias"; alias.symlink_to(out, target_is_directory=True)
        with self.assertRaises(c.CaptureError): h.restore_capture(self.bundle, self.report["bundle_sha256"], alias/"nested")
        self.assertEqual((out/"marker").read_text(), "preserve")
        self.assertEqual(self.bundle.read_bytes(), self.raw)

    def test_active_writer_cannot_export_and_failed_export_has_no_pass_report(self):
        with c.Capture(self.root/"active"):
            with self.assertRaises(c.CaptureError): h.export_capture(self.root/"active", self.root/"active-export")
        self.assertFalse((self.root/"active-export/report.json").exists())

    def test_nested_export_destination_cannot_pollute_original_capture(self):
        before = {p.name: p.read_bytes() for p in self.capture.iterdir()}
        for destination in (self.capture, self.capture/"nested"):
            with self.assertRaises(c.CaptureError): h.export_capture(self.capture, destination)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.capture.iterdir()})
        self.assertEqual(c.verify(self.capture), self.report["capture"])

    def test_source_change_during_export_prevents_pass(self):
        original = h.package
        def change(archive):
            raw = original(archive)
            with (self.capture/"ticks.db").open("ab") as out: out.write(b"changed")
            return raw
        with patch.object(h, "package", side_effect=change):
            with self.assertRaises(c.CaptureError): h.export_capture(self.capture, self.root/"changed")
        self.assertFalse((self.root/"changed/report.json").exists())

    def test_rehearsal_preserves_restart_gap_and_never_claims_off_machine_success(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            result = h.rehearse(self.root/"rehearsal")
        self.assertEqual(result["status"], "offline-handoff-rehearsal-passed-live-blocked")
        self.assertEqual((result["capture"]["messages"], result["capture"]["gaps"], result["capture"]["restarts"]), (4,1,1))
        self.assertTrue(result["synthetic_only"])
        self.assertFalse(result["off_machine_restore_verified"])
        self.assertTrue(result["remote_round_trip_pending"])

    def test_cli_arguments_and_failure_text_do_not_leak_secrets(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.assertEqual(h.main(["restore", "--bundle", "SENSITIVE-PATH"]), 1)
            with patch.object(h, "rehearse", side_effect=RuntimeError("SECRET")):
                self.assertEqual(h.main(["rehearse", "--output-directory", str(self.root/"failed")]), 1)
        self.assertNotIn("SENSITIVE", out.getvalue())
        self.assertNotIn("SECRET", out.getvalue())

    def test_cli_export_and_restore_round_trip(self):
        with contextlib.redirect_stdout(io.StringIO()), patch("socket.socket", side_effect=AssertionError("network forbidden")):
            self.assertEqual(h.main(["export", "--capture", str(self.capture), "--output-directory", str(self.root/"cli-export")]), 0)
            self.assertEqual(h.main(["restore", "--bundle", str(self.root/"cli-export/capture.zip"), "--expected-sha256", self.report["bundle_sha256"], "--output-directory", str(self.root/"cli-restore")]), 0)
