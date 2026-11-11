import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from capture import Capture, Limits, verify
from test_capture import Clock, frame
from transport import run_session


class Wire:
    def __init__(self, clock, events=()):
        self.clock = clock
        self.events = list(events)
        self.sent = []
        self.aborted = 0
        self.closed = 0

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def recv(self):
        if not self.events:
            raise ConnectionError("SENSITIVE-UPSTREAM-ERROR")
        event = self.events.pop(0)
        if isinstance(event, int):
            self.clock.advance(event)
            raise TimeoutError()
        if isinstance(event, BaseException):
            raise event
        return event

    def abort(self):
        self.aborted += 1

    async def close(self):
        self.closed += 1


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.clock = Clock()
        self.opens = 0

    def tearDown(self):
        self.temp.cleanup()

    def capture(self, **kw):
        return Capture(self.root / "capture", Limits(sample_modulus=1, **kw),
                       wall=lambda: self.clock.wall, monotonic=lambda: self.clock.mono)

    async def run_wire(self, c, wire, **kw):
        async def factory():
            self.opens += 1
            return wire
        return await run_session(c, factory, **kw)

    async def test_single_connection_subscribes_only_selected_token(self):
        wire = Wire(self.clock, [frame(), frame(mint="3" * 32), frame("buy")])
        with self.capture(active_watches=1) as c:
            result = await self.run_wire(c, wire)
        self.assertEqual(self.opens, 1)
        self.assertEqual([x["method"] for x in wire.sent], ["subscribeNewToken", "subscribeMigration", "subscribeTokenTrade"])
        self.assertEqual(wire.sent[-1]["keys"], ["1" * 31 + "2"])
        self.assertEqual((wire.aborted, wire.closed), (1, 1))
        self.assertEqual(result["outcome"], "transport-failed")
        self.assertNotIn("SENSITIVE", str(result))
        self.assertEqual(verify(self.root / "capture")["stop_reason"], "transport-gap")

    async def test_final_message_never_triggers_new_paid_subscription(self):
        wire = Wire(self.clock, [frame(), frame("buy")])
        with self.capture(messages=1) as c:
            result = await self.run_wire(c, wire)
        self.assertEqual(len(wire.sent), 2)
        self.assertEqual(len(wire.events), 1)
        self.assertEqual(result["outcome"], "capture-stopped")

    async def test_silence_deadline_closes_without_waiting_for_trade(self):
        wire = Wire(self.clock, [20])
        with self.capture(seconds=10) as c:
            await self.run_wire(c, wire)
        self.assertEqual(verify(self.root / "capture")["stop_reason"], "deadline")
        self.assertEqual(wire.aborted, 1)

    async def test_expiry_and_migration_unsubscribe(self):
        wire = Wire(self.clock, [frame(), 2, frame(mint="3" * 32), frame("migration", mint="3" * 32)])
        with self.capture(watch_seconds=1) as c:
            await self.run_wire(c, wire)
        ends = [x for x in wire.sent if x["method"] == "unsubscribeTokenTrade"]
        self.assertEqual(ends, [{"method": "unsubscribeTokenTrade", "keys": ["1" * 31 + "2"]},
                                {"method": "unsubscribeTokenTrade", "keys": ["3" * 32]}])

    async def test_duplicate_creation_does_not_duplicate_subscription(self):
        wire = Wire(self.clock, [frame(), frame(), frame("buy")])
        with self.capture() as c:
            await self.run_wire(c, wire)
        self.assertEqual(sum(x["method"] == "subscribeTokenTrade" for x in wire.sent), 1)

    async def test_provider_error_closes_without_leaking_payload(self):
        wire = Wire(self.clock, [b'{"error":"DO-NOT-STORE"}'])
        with self.capture() as c:
            result = await self.run_wire(c, wire)
        self.assertNotIn("DO-NOT-STORE", str(result))
        self.assertNotIn(b"DO-NOT-STORE", (self.root / "capture" / "ticks.db").read_bytes())
        self.assertEqual(verify(self.root / "capture")["stop_reason"], "provider-error")

    async def test_stopped_capture_never_opens_wire(self):
        wire = Wire(self.clock)
        with self.capture(messages=1) as c:
            c.receive(frame())
            result = await self.run_wire(c, wire)
        self.assertEqual(self.opens, 0)
        self.assertEqual(result["connections_opened"], 0)

    async def test_existing_evidence_cannot_silently_start_new_network_session(self):
        wire = Wire(self.clock)
        with self.capture() as c:
            c.receive(frame())
            result = await self.run_wire(c, wire)
        self.assertEqual(self.opens, 0)
        self.assertEqual(result["outcome"], "transport-failed")

    async def test_send_timeout_stops_and_aborts(self):
        wire = Wire(self.clock)
        async def hang(payload):
            await asyncio.Future()
        wire.send = hang
        with self.capture() as c:
            result = await self.run_wire(c, wire, send_seconds=0.01)
        self.assertEqual((wire.aborted, result["outcome"]), (1, "transport-failed"))

    async def test_cleanup_failure_is_not_hidden(self):
        wire = Wire(self.clock, [frame()])
        async def fail():
            raise RuntimeError("SECRET")
        wire.close = fail
        with self.capture(messages=1) as c:
            result = await self.run_wire(c, wire)
        self.assertEqual(result["outcome"], "transport-cleanup-failed")
        self.assertNotIn("SECRET", str(result))

    async def test_cancellation_closes_and_records_gap(self):
        wire = Wire(self.clock, [asyncio.CancelledError()])
        with self.capture() as c:
            with self.assertRaises(asyncio.CancelledError):
                await self.run_wire(c, wire)
        self.assertEqual((wire.aborted, wire.closed), (1, 1))
        self.assertEqual(verify(self.root / "capture")["gaps"], 1)

    async def test_real_receive_wait_is_bounded_and_network_unavailable(self):
        wire = Wire(self.clock)
        async def silent():
            self.clock.advance(1)
            await asyncio.Future()
        wire.recv = silent
        # Creating the test event loop precedes the socket prohibition.
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            with self.capture(seconds=2) as c:
                await self.run_wire(c, wire, poll_seconds=0.01)
        self.assertEqual(verify(self.root / "capture")["stop_reason"], "deadline")
