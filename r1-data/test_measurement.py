import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import capture as c
import measurement as m
from transport import run_session


MINT = "1" * 31 + "2"


def frame(kind="create", mint=MINT):
    return c.canonical({"txType": kind, "mint": mint, "signature": "2" * 88}).encode()


class Clock:
    def __init__(self):
        self.wall = 1_800_000_000_000_000_000
        self.mono = 1_000_000_000
    def advance(self, ns):
        self.wall += ns
        self.mono += ns


class Wire:
    def __init__(self, clock, frames):
        self.clock, self.frames, self.sent = clock, iter(frames), []
        self.aborted = self.closed = False
    async def send(self, command):
        self.sent.append(json.loads(command))
        self.clock.advance(5_000_000)
    async def recv(self):
        try:
            return next(self.frames)
        except StopIteration:
            raise ConnectionError("SYNTHETIC-PRIVATE-ERROR") from None
    def abort(self):
        self.aborted = True
    async def close(self):
        self.closed = True


class MeasurementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clock = Clock()
        self.path = self.root / "session.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def journal(self):
        return m.Journal(self.path, wall=lambda: self.clock.wall, monotonic=lambda: self.clock.mono)

    def capture(self, **kw):
        return c.Capture(self.root / "capture", c.Limits(sample_modulus=1, **kw),
                         wall=lambda: self.clock.wall, monotonic=lambda: self.clock.mono)

    async def exercise(self, frames=None, messages=4, wire=None):
        wire = wire or Wire(self.clock, frames or [frame(), frame("buy"), frame("sell"), frame("migration")])
        async def factory():
            return wire
        with self.journal() as journal, self.capture(messages=messages) as capture:
            result = await run_session(capture, factory, journal=journal)
        return result, wire

    def replay(self):
        return m.replay(self.root / "capture", self.path)

    def records(self):
        return [json.loads(line) for line in self.path.read_bytes().splitlines()]

    def rewrite(self, records):
        previous = c.GENESIS
        for i, record in enumerate(records, 1):
            record.update(seq=i, previous=previous)
            record.pop("sha256", None)
            previous = c.digest(c.canonical(record).encode())
            record["sha256"] = previous
        self.path.write_text("".join(c.canonical(x) + "\n" for x in records))

    async def test_success_measures_monotonic_local_delay_and_binds_capture(self):
        result, wire = await self.exercise()
        before = (self.root / "capture/ticks.db").read_bytes()
        report = self.replay()
        self.assertEqual(result["outcome"], "capture-stopped")
        self.assertTrue(wire.aborted and wire.closed)
        self.assertEqual(report["creation_receive_to_local_send_return_ns"],
                         {"count": 1, "min": 5_000_000, "max": 5_000_000, "sum": 5_000_000})
        self.assertEqual((report["send_intents"], report["local_sends_completed"]), (3, 3))
        self.assertEqual(report["selected_without_completed_subscription_send"], 0)
        self.assertEqual(report["journal_records"], 9)
        self.assertEqual(before, (self.root / "capture/ticks.db").read_bytes())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        for key in ("provider_acknowledged_subscriptions", "external_creation_denominator",
                    "initial_trade_coverage", "billed_events", "data_fees_lamports"):
            self.assertIsNone(report[key])
        self.assertFalse(report["finality_verified"])
        self.assertFalse(report["ledger_order_verified"])

    async def test_forward_wall_adjustment_does_not_inflate_monotonic_delay(self):
        wire = Wire(self.clock, [frame(), frame("buy"), frame("sell"), frame("migration")])
        original = wire.send
        async def jump(command):
            await original(command)
            if json.loads(command)["method"] == "subscribeTokenTrade":
                self.clock.wall += 60_000_000_000
        wire.send = jump
        await self.exercise(wire=wire)
        self.assertEqual(self.replay()["creation_receive_to_local_send_return_ns"]["max"], 5_000_000)

    async def test_final_selected_creation_remains_in_missing_send_denominator(self):
        _, wire = await self.exercise([frame()], messages=1)
        report = self.replay()
        self.assertEqual(report["selected_creations"], 1)
        self.assertEqual(report["selected_without_completed_subscription_send"], 1)
        self.assertEqual(report["creation_receive_to_local_send_return_ns"]["count"], 0)
        self.assertEqual(len(wire.sent), 2)

    async def test_duplicates_and_capacity_exclusions_have_separate_denominators(self):
        wire = Wire(self.clock, [frame(), frame(), frame(mint="3" * 32), frame("buy")])
        async def factory(): return wire
        with self.journal() as journal, self.capture(messages=4, active_watches=1) as capture:
            await run_session(capture, factory, journal=journal)
        report = self.replay()
        self.assertEqual(report["creation_records_observed"], 3)
        self.assertEqual(report["unique_creation_mints_observed"], 2)
        self.assertEqual(report["mint_decisions"], {"watch-planned": 1, "active-cap": 1})
        self.assertEqual(report["selected_creations"], 1)

    async def test_failed_send_preserves_intent_without_claiming_completion(self):
        wire = Wire(self.clock, [frame()])
        original = wire.send
        async def fail(command):
            if json.loads(command)["method"] == "subscribeTokenTrade":
                raise ConnectionError("SYNTHETIC-PRIVATE-ERROR")
            await original(command)
        wire.send = fail
        result, _ = await self.exercise(wire=wire)
        report = self.replay()
        self.assertEqual(result["outcome"], "transport-failed")
        self.assertEqual(report["send_intents_without_completion_or_abandonment"], 1)
        self.assertEqual(report["selected_without_completed_subscription_send"], 1)
        self.assertEqual(report["gaps"], 1)
        self.assertNotIn(b"SYNTHETIC-PRIVATE-ERROR", self.path.read_bytes())

    async def test_intent_write_failure_prevents_paid_command_and_invalidates_evidence(self):
        wire = Wire(self.clock, [frame()])
        async def factory(): return wire
        with self.journal() as journal, self.capture() as capture:
            original = journal.intent
            def fail(command, capture):
                if command["method"] == "subscribeTokenTrade":
                    with patch.object(m.os, "write", side_effect=OSError("SYNTHETIC-PRIVATE-ERROR")):
                        return original(command, capture)
                return original(command, capture)
            journal.intent = fail
            result = await run_session(capture, factory, journal=journal)
        self.assertEqual(result["outcome"], "measurement-failed")
        self.assertEqual(len(wire.sent), 2)
        self.assertTrue(wire.aborted)
        with self.assertRaises(c.CaptureError): self.replay()
        self.assertNotIn(b"SYNTHETIC-PRIVATE-ERROR", self.path.read_bytes())

    async def test_completion_write_failure_never_turns_send_into_success(self):
        wire = Wire(self.clock, [frame()])
        async def factory(): return wire
        with self.journal() as journal, self.capture() as capture:
            original = journal.sent
            def fail(intent):
                if len(wire.sent) == 3:
                    with patch.object(m.os, "fsync", side_effect=OSError("private")):
                        return original(intent)
                return original(intent)
            journal.sent = fail
            result = await run_session(capture, factory, journal=journal)
        self.assertEqual(len(wire.sent), 3)
        self.assertEqual(result["outcome"], "measurement-failed")
        with self.assertRaises(c.CaptureError): self.replay()

    async def test_start_write_failure_opens_no_connection(self):
        opened = []
        async def factory(): opened.append(True); return Wire(self.clock, [])
        with self.journal() as journal, self.capture() as capture:
            with patch.object(m.os, "write", side_effect=OSError("private")):
                result = await run_session(capture, factory, journal=journal)
        self.assertFalse(opened)
        self.assertEqual(result["outcome"], "measurement-failed")

    async def test_cancellation_records_gap_and_uncertain_send(self):
        wire = Wire(self.clock, [])
        async def cancelled(command): raise asyncio.CancelledError()
        wire.send = cancelled
        with self.assertRaises(asyncio.CancelledError): await self.exercise(wire=wire)
        report = self.replay()
        self.assertEqual(report["session_outcome"], "transport-cancelled")
        self.assertEqual(report["gaps"], 1)
        self.assertEqual(report["send_intents_without_completion_or_abandonment"], 1)
        self.assertTrue(wire.aborted and wire.closed)

    async def test_hash_truncation_and_missing_terminal_are_rejected(self):
        await self.exercise()
        original = self.path.read_bytes()
        for raw in (original[:-1], original.replace(b'capture-stopped', b'transport-failed'),
                    b"\n".join(original.splitlines()[:-1]) + b"\n"):
            self.path.write_bytes(raw)
            with self.assertRaises((c.CaptureError, ValueError)): self.replay()
        self.path.write_bytes(original)

    async def test_rehashed_fake_mint_row_and_terminal_cannot_match_capture(self):
        await self.exercise()
        original = self.records()
        for mutation in ("mint", "row", "terminal", "missing-selection", "duplicate-completion"):
            rows = json.loads(json.dumps(original))
            if mutation == "mint":
                next(x for x in rows if x["kind"] == "selected")["payload"]["mint"] = "3" * 32
            elif mutation == "row":
                next(x for x in rows if x["kind"] == "selected")["payload"]["chain_sha256"] = "0" * 64
            elif mutation == "terminal": rows[-1]["payload"]["messages"] = 0
            elif mutation == "missing-selection": rows = [x for x in rows if x["kind"] != "selected"]
            else: rows.insert(-1, dict(rows[-2]))
            self.rewrite(rows)
            with self.assertRaises(c.CaptureError): self.replay()

    async def test_copy_replays_identically_and_other_database_is_rejected(self):
        await self.exercise()
        c.export_capture(self.root / "capture", self.root / "archive")
        c.restore_capture(self.root / "archive", self.root / "restored")
        copied = self.root / "copied.jsonl"
        c.exclusive_file(copied, self.path.read_bytes())
        self.assertEqual(self.replay(), m.replay(self.root / "restored", copied))
        with c.Capture(self.root / "other", c.Limits(messages=1)) as capture:
            capture.receive(frame())
        with self.assertRaises(c.CaptureError): m.replay(self.root / "other", copied)

    async def test_slow_intent_flush_cannot_authorize_send_after_deadline(self):
        wire = Wire(self.clock, [frame()])
        async def factory(): return wire
        with self.journal() as journal, self.capture(seconds=1) as capture:
            original = journal.intent
            def slow(command, capture):
                intent = original(command, capture)
                if command["method"] == "subscribeTokenTrade":
                    self.clock.advance(2_000_000_000)
                return intent
            journal.intent = slow
            result = await run_session(capture, factory, journal=journal)
        self.assertEqual(result["outcome"], "capture-stopped")
        self.assertEqual(len(wire.sent), 2)
        report = self.replay()
        self.assertEqual(report["stop_reason"], "deadline")
        self.assertEqual(report["send_intents_abandoned"], 1)
        self.assertEqual(report["send_intents_without_completion_or_abandonment"], 0)
        self.assertEqual(report["selected_without_completed_subscription_send"], 1)

    async def test_journal_caps_stop_before_next_command(self):
        with patch.object(m, "MAX_RECORDS", 1):
            result, wire = await self.exercise()
        self.assertEqual(result["outcome"], "measurement-failed")
        self.assertEqual(wire.sent, [])
        with self.assertRaises(c.CaptureError): self.replay()

    async def test_journal_rejects_clock_regression_and_does_not_resume(self):
        with self.journal() as journal, self.capture() as capture:
            journal.start(capture)
            self.clock.advance(-1)
            with self.assertRaises(c.CaptureError): journal.intent({"method": "subscribeNewToken"}, capture)
            self.clock.advance(2)
            with self.assertRaises(c.CaptureError): journal.finish("capture-stopped", capture)
        with self.assertRaises(FileExistsError): self.journal()

    async def test_commands_cannot_store_secrets_or_arbitrary_payloads(self):
        with self.journal() as journal, self.capture() as capture:
            journal.start(capture)
            for command in ({"method": "trade", "apiKey": "SYNTHETIC-PRIVATE-ERROR"},
                            {"method": "subscribeTokenTrade", "keys": ["SYNTHETIC-PRIVATE-ERROR"]},
                            {"method": "subscribeNewToken", "extra": "SYNTHETIC-PRIVATE-ERROR"}):
                with self.assertRaises(c.CaptureError): journal.intent(command, capture)
        self.assertNotIn(b"SYNTHETIC-PRIVATE-ERROR", self.path.read_bytes())

    async def test_symlinks_hardlinks_public_and_oversized_input_rejected(self):
        await self.exercise()
        alias = self.root / "alias"
        alias.symlink_to(self.path)
        with self.assertRaises(c.CaptureError): m.replay(self.root / "capture", alias)
        alias.unlink()
        os.link(self.path, alias)
        with self.assertRaises(c.CaptureError): self.replay()
        alias.unlink()
        self.path.chmod(0o644)
        with self.assertRaises(c.CaptureError): self.replay()
        self.path.chmod(0o600)
        with patch.object(m, "MAX_BYTES", 1):
            with self.assertRaises(c.CaptureError): self.replay()


if __name__ == "__main__":
    unittest.main()
