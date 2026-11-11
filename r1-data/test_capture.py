import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from capture import (Capture, CaptureError, Limits, canonical, export_capture,
                     restore_capture, verify)


class Clock:
    def __init__(self):
        self.wall = 1_800_000_000_000_000_000
        self.mono = 100_000_000_000

    def advance(self, seconds):
        self.wall += seconds * 1_000_000_000
        self.mono += seconds * 1_000_000_000


def frame(kind="create", mint="1" * 31 + "2", **fields):
    return canonical(dict(txType=kind, mint=mint, signature="2" * 88, **fields)).encode()


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "capture"
        self.clock = Clock()

    def tearDown(self):
        self.temp.cleanup()

    def open(self, **kw):
        limits = kw.pop("limits", Limits(sample_modulus=1))
        return Capture(self.path, limits, wall=lambda: self.clock.wall,
                       monotonic=lambda: self.clock.mono, **kw)

    def test_capture_preserves_exact_raw_and_labels_receive_order_only(self):
        raw = frame(slot=100, vSolInBondingCurve=30.01)
        with self.open() as c:
            self.assertEqual(c.receive(raw), "watch-planned")
            self.assertEqual(c.receive(frame("buy")), "within-planned-watch")
            saved = c.db.execute("SELECT raw FROM events WHERE seq=1").fetchone()[0]
            self.assertEqual(raw, saved)
        r = verify(self.path)
        self.assertEqual(r["raw_rows"], 2)
        for key in ("ledger_order_verified", "initial_state_verified", "subscription_installed",
                    "billing_limit_verified", "profitability_evaluated"):
            self.assertFalse(r[key])

    def test_message_limit_includes_controls_and_never_rearms(self):
        limits = Limits(messages=2, sample_modulus=1)
        with self.open(limits=limits) as c:
            c.receive(b'{"message":"accepted"}')
            c.receive(frame())
            self.assertIsNone(c.receive(frame("buy")))
        with self.open(limits=limits) as c:
            self.assertEqual(c.state["reason"], "message-limit")
            self.assertIsNone(c.receive(frame("buy")))
        self.assertEqual(verify(self.path)["messages"], 2)

    def test_restart_preserves_budget_deadline_and_marks_gap(self):
        limits = Limits(messages=3, sample_modulus=1)
        with self.open(limits=limits) as c:
            c.receive(frame())
            deadline = c.state["deadline_ns"]
        self.clock.advance(5)
        with self.open(limits=limits) as c:
            self.assertEqual(c.state["deadline_ns"], deadline)
            self.assertEqual(c.receive(frame("buy")), "outside-planned-watch")
            c.receive(frame("sell"))
        r = verify(self.path)
        self.assertEqual((r["gaps"], r["restarts"], r["messages"]), (1, 1, 3))

    def test_changed_limits_cannot_reset_budget(self):
        with self.open(limits=Limits(messages=2)) as c:
            c.receive(frame())
        with self.assertRaisesRegex(CaptureError, "limits-changed"):
            self.open(limits=Limits(messages=3))

    def test_unclean_shutdown_cannot_resume(self):
        c = self.open()
        c.receive(frame())
        c._release()  # equivalent durable state to loss of process
        with self.assertRaisesRegex(CaptureError, "unclean-shutdown"):
            verify(self.path)
        with self.open() as restarted:
            self.assertEqual(restarted.state["reason"], "unclean-shutdown")
            self.assertIsNone(restarted.receive(frame("buy")))

    def test_deadline_survives_restart(self):
        limits = Limits(seconds=10)
        with self.open(limits=limits):
            pass
        self.clock.advance(10)
        with self.open(limits=limits) as c:
            self.assertEqual(c.state["reason"], "deadline")
            self.assertIsNone(c.receive(frame()))

    def test_silence_deadline_and_monotonic_elapsed(self):
        with self.open(limits=Limits(seconds=10)) as c:
            self.clock.mono += 10_000_000_000
            self.assertFalse(c.tick())
            self.assertEqual(c.state["reason"], "deadline")

    def test_backward_wall_clock_fails_closed(self):
        with self.open() as c:
            self.clock.wall -= 1
            self.assertIsNone(c.receive(frame()))
            self.assertEqual(c.state["reason"], "clock-regression")

    def test_backward_monotonic_clock_fails_closed(self):
        with self.open() as c:
            self.clock.mono -= 1
            self.assertFalse(c.tick())
            self.assertEqual(c.state["reason"], "clock-regression")

    def test_oversized_frame_is_counted_but_not_written(self):
        with self.open(limits=Limits(frame_bytes=64)) as c:
            c.receive(frame())
        r = verify(self.path)
        self.assertEqual((r["messages"], r["raw_rows"], r["stop_reason"]), (1, 0, "frame-limit"))

    def test_raw_byte_limit_stops_before_overflow(self):
        raw = frame()
        with self.open(limits=Limits(raw_bytes=len(raw) + 1)) as c:
            c.receive(raw)
            c.receive(frame("buy"))
        r = verify(self.path)
        self.assertEqual(r["raw_bytes"], len(raw))
        self.assertEqual(r["stop_reason"], "raw-byte-limit")

    def test_exact_raw_byte_limit_stops_immediately(self):
        raw = frame()
        with self.open(limits=Limits(raw_bytes=len(raw))) as c:
            c.receive(raw)
            self.assertEqual(c.state["reason"], "raw-byte-limit")

    def test_sampling_uses_mint_not_outcome_fields(self):
        limits = Limits(sample_modulus=2, active_watches=32)
        with self.open(limits=limits) as c:
            for last in "23456789ABCDEFGH":
                mint = "1" * 31 + last
                expected = int(hashlib.sha256(mint.encode()).hexdigest(), 16) % 2 == 0
                decision = c.receive(frame(mint=mint, marketCapSol=999999))
                self.assertEqual(decision, "watch-planned" if expected else "sample-excluded")

    def test_active_cap_and_duplicate_creation_have_denominators(self):
        with self.open(limits=Limits(sample_modulus=1, active_watches=1)) as c:
            self.assertEqual(c.receive(frame()), "watch-planned")
            self.assertEqual(c.receive(frame()), "duplicate-create")
            self.assertEqual(c.receive(frame(mint="3" * 32)), "active-cap")
        self.assertEqual(verify(self.path)["mint_decisions"], {"active-cap": 1, "watch-planned": 1})

    def test_daily_cap_after_watch_expires(self):
        with self.open(limits=Limits(sample_modulus=1, daily_watches=1, watch_seconds=1)) as c:
            c.receive(frame())
            self.clock.advance(2)
            self.assertEqual(c.receive(frame(mint="3" * 32)), "daily-cap")

    def test_migration_and_expiry_end_planned_watch(self):
        with self.open() as c:
            c.receive(frame())
            self.assertEqual(c.receive(frame("migration")), "within-planned-watch")
            self.assertEqual(c.receive(frame("sell")), "outside-planned-watch")
            c.receive(frame(mint="3" * 32))
            self.clock.advance(601)
            self.assertEqual(c.receive(frame("buy", mint="3" * 32)), "outside-planned-watch")

    def test_transport_gap_stops_without_claiming_recovery(self):
        with self.open() as c:
            c.receive(frame())
            self.assertFalse(c.gap())
            self.assertIsNone(c.receive(frame("buy")))
        self.assertEqual(verify(self.path)["stop_reason"], "transport-gap")

    def test_provider_errors_are_never_preserved(self):
        with self.open() as c:
            c.receive(b'{"error":"private upstream response DO-NOT-STORE"}')
        self.assertNotIn(b"DO-NOT-STORE", (self.path / "ticks.db").read_bytes())
        self.assertEqual(verify(self.path)["stop_reason"], "provider-error")

    def test_known_secret_and_encoded_variants_are_rejected(self):
        from urllib.parse import quote
        secret = 'sensitive/value"goes-here'
        for index, value in enumerate((secret, quote(secret, safe=""))):
            self.path = self.root / f"secret{index}"
            with self.open(redactions=(secret,)) as c:
                c.receive(frame(name=value))
            self.assertEqual(verify(self.path)["stop_reason"], "credential-in-frame")
            self.assertNotIn(b"sensitive", (self.path / "ticks.db").read_bytes())

    def test_nested_credential_fields_are_rejected(self):
        with self.open() as c:
            c.receive(frame(extra={"api_key": "NEVER-STORE"}))
        self.assertNotIn(b"NEVER-STORE", (self.path / "ticks.db").read_bytes())
        self.assertEqual(verify(self.path)["raw_rows"], 0)

    def test_control_text_discarded_even_without_known_secret(self):
        with self.open() as c:
            self.assertEqual(c.receive(b'{"message":"DO-NOT-STORE"}'), "control-discarded")
        self.assertNotIn(b"DO-NOT-STORE", (self.path / "ticks.db").read_bytes())

    def test_invalid_json_duplicate_keys_and_nonfinite_values_stop(self):
        for index, raw in enumerate((b"{", b"[]", b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b"\xff")):
            self.path = self.root / f"invalid{index}"
            with self.open() as c:
                self.assertIsNone(c.receive(raw))
            self.assertEqual(verify(self.path)["stop_reason"], "invalid-frame")

    def test_missing_identity_and_unknown_event_are_not_silently_accepted(self):
        for index, raw in enumerate((b'{"txType":"buy"}', frame("unknown"))):
            self.path = self.root / f"identity{index}"
            with self.open() as c:
                c.receive(raw)
            self.assertEqual(verify(self.path)["stop_reason"], "invalid-frame")

    def test_one_writer_and_no_export_of_active_session(self):
        with self.open():
            with self.assertRaises(CaptureError):
                self.open()
            with self.assertRaises(CaptureError):
                export_capture(self.path, self.root / "archive")
        self.assertFalse((self.root / "archive").exists())

    def test_permissions_symlinks_and_hardlinks_refused(self):
        with self.open() as c:
            c.receive(frame())
        db = self.path / "ticks.db"
        self.assertEqual(db.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o700)
        os.link(db, self.root / "hardlink")
        with self.assertRaises(CaptureError):
            verify(self.path)
        (self.root / "hardlink").unlink()
        os.chmod(db, 0o644)
        with self.assertRaises(CaptureError):
            verify(self.path)
        os.chmod(db, 0o600)
        link = self.root / "symlink"
        link.symlink_to(self.path, target_is_directory=True)
        with self.assertRaises(CaptureError):
            verify(link)

    def test_database_symlink_and_existing_files_not_overwritten(self):
        self.path.mkdir(mode=0o700)
        target = self.root / "target"
        target.write_bytes(b"preserve")
        (self.path / "ticks.db").symlink_to(target)
        with self.assertRaises(CaptureError):
            self.open()
        self.assertEqual(target.read_bytes(), b"preserve")

    def test_raw_or_chain_tampering_fails_replay(self):
        with self.open() as c:
            c.receive(frame())
        db = sqlite3.connect(self.path / "ticks.db")
        try:
            with db:
                db.execute("UPDATE events SET raw=?", (frame("sell"),))
        finally:
            db.close()
        with self.assertRaisesRegex(CaptureError, "replay-integrity"):
            verify(self.path)

    def test_export_restore_replay_and_source_preservation(self):
        with self.open() as c:
            c.receive(frame())
            c.receive(frame("buy"))
        before = (self.path / "ticks.db").read_bytes()
        manifest = export_capture(self.path, self.root / "archive")
        restored = restore_capture(self.root / "archive", self.root / "restored")
        self.assertEqual(restored, manifest["report"])
        self.assertEqual(before, (self.path / "ticks.db").read_bytes())
        self.assertEqual(before, (self.root / "restored" / "ticks.db").read_bytes())
        with self.assertRaises(FileExistsError):
            export_capture(self.path, self.root / "archive")
        with self.assertRaises(FileExistsError):
            restore_capture(self.root / "archive", self.root / "restored")

    def test_backup_tampering_and_extra_members_rejected(self):
        with self.open() as c:
            c.receive(frame())
        archive = self.root / "archive"
        export_capture(self.path, archive)
        (archive / "extra").write_text("unexpected")
        with self.assertRaisesRegex(CaptureError, "archive-members"):
            restore_capture(archive, self.root / "restored")
        (archive / "extra").unlink()
        with (archive / "ticks.db").open("ab") as out:
            out.write(b"x")
        with self.assertRaisesRegex(CaptureError, "archive-checksum"):
            restore_capture(archive, self.root / "restored")
        self.assertFalse((self.root / "restored").exists())

    def test_invalid_limits_rejected_without_creating_state(self):
        for limits in (Limits(messages=0), Limits(messages=True), Limits(seconds=172801), Limits(raw_bytes=-1)):
            with self.assertRaises(CaptureError):
                self.open(limits=limits)
        self.assertFalse(self.path.exists())

    def test_interrupted_context_stops_and_releases_lock(self):
        with self.assertRaises(RuntimeError):
            with self.open() as c:
                c.receive(frame())
                raise RuntimeError("synthetic")
        with self.open() as c:
            self.assertEqual(c.state["reason"], "interrupted")

    def test_offline_core_works_with_network_disabled(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            with self.open() as c:
                c.receive(frame())
            self.assertEqual(verify(self.path)["raw_rows"], 1)

    def test_storage_full_stops_without_committing_partial_event(self):
        with self.assertRaisesRegex(CaptureError, "storage-error"):
            with self.open() as c:
                pages = c.db.execute("PRAGMA page_count").fetchone()[0]
                c.db.execute(f"PRAGMA max_page_count={pages}")
                c.receive(frame(name="x" * 50_000))
        r = verify(self.path)
        self.assertEqual((r["stop_reason"], r["messages"], r["raw_rows"]), ("storage-error", 1, 0))
        self.assertEqual(r["mint_decisions"], {})

    def test_mint_state_tampering_is_detected(self):
        with self.open() as c:
            c.receive(frame())
        db = sqlite3.connect(self.path / "ticks.db")
        try:
            with db:
                db.execute("UPDATE mints SET decision='sample-excluded'")
        finally:
            db.close()
        with self.assertRaisesRegex(CaptureError, "mint-integrity"):
            verify(self.path)
        with self.assertRaisesRegex(CaptureError, "mint-integrity"):
            self.open()

    def test_gap_boundary_is_retained_for_replay(self):
        with self.open() as c:
            c.receive(frame())
        self.clock.advance(2)
        with self.open() as c:
            c.receive(frame("buy"))
        r = verify(self.path)
        self.assertEqual(r["gap_records"], [{"after_seq": 1, "at_ns": self.clock.wall, "reason": "restart"}])

    def test_repeated_restarts_are_bounded(self):
        with self.open():
            pass
        for _ in range(129):
            with self.open():
                pass
        r = verify(self.path)
        self.assertEqual((r["gaps"], r["stop_reason"]), (128, "gap-limit"))

    def test_restored_completed_budget_does_not_rearm(self):
        limits = Limits(messages=1)
        with self.open(limits=limits) as c:
            c.receive(frame())
        export_capture(self.path, self.root / "archive")
        restore_capture(self.root / "archive", self.root / "restored")
        self.path = self.root / "restored"
        with self.open(limits=limits) as c:
            self.assertIsNone(c.receive(frame("buy")))
            self.assertEqual(c.state["messages"], 1)

    def test_monotonic_regression_after_progress_is_rejected(self):
        with self.open() as c:
            self.clock.advance(5)
            c.tick()
            self.clock.mono -= 1
            self.assertFalse(c.tick())
            self.assertEqual(c.state["reason"], "clock-regression")

    def test_unexpected_database_schema_blocks_resume(self):
        with self.open():
            pass
        db = sqlite3.connect(self.path / "ticks.db")
        try:
            db.execute("CREATE VIEW unexpected AS SELECT 1")
            db.commit()
        finally:
            db.close()
        with self.assertRaisesRegex(CaptureError, "unexpected-schema"):
            self.open()


if __name__ == "__main__":
    unittest.main()
