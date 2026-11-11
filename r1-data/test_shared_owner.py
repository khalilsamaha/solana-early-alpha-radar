import asyncio
import json
import unittest

from capture import CaptureError, canonical
from shared_owner import Owner
from test_capture import frame


class FakeWire:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.sent = []
        self.aborted = False
        self.fail_method = None

    async def send(self, raw):
        row = json.loads(raw)
        self.sent.append(row)
        if row["method"] == self.fail_method:
            raise RuntimeError("DO-NOT-EXPORT-KEY")

    async def recv(self):
        return await self.incoming.get()

    def abort(self):
        self.aborted = True

    async def close(self):
        self.abort()


class SharedOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.wire = FakeWire()
        self.opens = 0
        async def factory():
            self.opens += 1
            return self.wire
        self.owner = Owner(factory)
        await self.owner.start()

    async def asyncTearDown(self):
        await self.owner.close()

    async def wait_for(self, condition):
        async with asyncio.timeout(2):
            while not condition():
                await asyncio.sleep(0.001)

    async def subscribe(self, lease):
        await lease.send(canonical({"method": "subscribeTokenTrade", "keys": ["1" * 31 + "2"]}))

    async def test_one_factory_free_subscriptions_once_and_no_reconnect(self):
        self.assertEqual([x["method"] for x in self.wire.sent], ["subscribeNewToken", "subscribeMigration"])
        with self.assertRaises(CaptureError):
            await self.owner.start()
        self.assertEqual(self.opens, 1)

    async def test_normal_stop_unsubscribes_and_discovery_continues(self):
        lease = self.owner.attach(10)
        await self.subscribe(lease)
        report = await lease.finish()
        self.assertEqual(report["outcome"], "unsubscribed")
        self.assertFalse(self.wire.aborted)
        self.assertFalse(report["billing_cutoff_verified"])
        await self.wire.incoming.put(frame())
        data = await asyncio.wait_for(self.owner.discovery.recv(), 1)
        self.assertEqual(json.loads(data)["seq"], 1)
        self.assertEqual(self.opens, 1)
        self.assertEqual(self.wire.sent[-1]["method"], "unsubscribeTokenTrade")

    async def test_terminal_lease_never_rearms_or_resubscribes(self):
        lease = self.owner.attach(10)
        await lease.finish()
        with self.assertRaises(CaptureError):
            self.owner.attach(10)
        with self.assertRaises(CaptureError):
            await self.subscribe(lease)
        self.assertEqual(len(self.wire.sent), 2)

    async def test_deadline_runs_without_capture_worker_progress(self):
        lease = self.owner.attach(0.05)
        await self.subscribe(lease)
        await self.wait_for(lambda: lease.cleanup is not None)
        self.assertEqual(lease.cleanup["reason"], "deadline")
        self.assertTrue(lease.cleanup["discovery_continues"])
        self.assertFalse(self.owner.watches)

    async def test_missing_worker_heartbeat_retires_before_long_lease_deadline(self):
        lease = self.owner.attach(10)
        await self.subscribe(lease)
        await asyncio.sleep(2.1)
        self.assertEqual(lease.cleanup["reason"], "worker-unresponsive")
        self.assertTrue(lease.cleanup["discovery_continues"])
        self.assertFalse(self.owner.watches)

    async def test_heartbeat_cannot_extend_original_deadline(self):
        lease = self.owner.attach(0.04)
        original = lease.until
        await lease.heartbeat()
        await self.wait_for(lambda: lease.cleanup is not None)
        self.assertEqual(lease.until, original)
        self.assertEqual(lease.cleanup["reason"], "deadline")

    async def test_deadline_while_send_queued_never_sends_late_subscribe(self):
        lease = self.owner.attach(0.03)
        async with self.owner.lock:
            task = asyncio.create_task(self.subscribe(lease))
            await asyncio.sleep(0.05)
        with self.assertRaises(CaptureError):
            await task
        await lease.finish()
        self.assertEqual(len(self.wire.sent), 2)

    async def test_failed_cleanup_aborts_upstream_and_cannot_claim_continuity(self):
        lease = self.owner.attach(10)
        await self.subscribe(lease)
        self.wire.fail_method = "unsubscribeTokenTrade"
        result = await lease.finish()
        self.assertEqual(result["outcome"], "upstream-aborted")
        self.assertFalse(result["discovery_continues"])
        self.assertTrue(self.wire.aborted)
        self.assertNotIn("DO-NOT-EXPORT", str(self.owner.receipt()))

    async def test_uncertain_subscribe_is_remembered_and_aborts(self):
        lease = self.owner.attach(10)
        self.wire.fail_method = "subscribeTokenTrade"
        with self.assertRaises(CaptureError):
            await self.subscribe(lease)
        await lease.finish()
        self.assertEqual(self.owner.commands[-1]["state"], "uncertain")
        self.assertTrue(self.owner.watches)
        self.assertTrue(self.wire.aborted)

    async def test_research_overflow_retires_paid_watches_but_preserves_discovery(self):
        lease = self.owner.attach(10)
        await self.subscribe(lease)
        for _ in range(65):
            await self.wire.incoming.put(b'{"message":"accepted"}')
        await self.wait_for(lambda: lease.cleanup is not None)
        self.assertEqual(lease.cleanup["reason"], "research-overflow")
        self.assertTrue(lease.cleanup["discovery_continues"])
        self.assertFalse(self.owner.watches)

    async def test_discovery_overflow_aborts_instead_of_silent_loss(self):
        for _ in range(65):
            await self.wire.incoming.put(frame())
        await self.wait_for(lambda: self.owner.closed)
        self.assertTrue(self.wire.aborted)
        with self.assertRaises(CaptureError):
            await self.owner.discovery.recv()

    async def test_only_discovery_is_forwarded_and_unknown_fields_are_removed(self):
        await self.wire.incoming.put(frame("buy"))
        await self.wire.incoming.put(frame(secret="NEVER-FORWARD"))
        data = await asyncio.wait_for(self.owner.discovery.recv(), 1)
        self.assertNotIn(b"NEVER-FORWARD", data)
        self.assertEqual(json.loads(data)["event"]["txType"], "create")
        self.assertTrue(self.owner.discovery.queue.empty())

    async def test_invalid_raw_and_provider_errors_are_sanitized(self):
        await self.wire.incoming.put(b'{"error":"SECRET"}')
        await self.wait_for(lambda: self.owner.closed)
        self.assertNotIn("SECRET", str(self.owner.receipt()))

    async def test_research_cannot_send_free_account_or_trading_commands(self):
        lease = self.owner.attach(10)
        with self.assertRaises(CaptureError):
            await lease.send('{"method":"subscribeAccountTrade","keys":["SECRET"]}')
        await lease.finish()
        self.assertEqual(len(self.wire.sent), 2)
        self.assertNotIn("SECRET", str(self.owner.receipt()))

    async def test_cleanup_has_reserved_command_capacity(self):
        lease = self.owner.attach(10)
        await self.subscribe(lease)
        self.owner.commands += [{"state": "completed"}] * (1023 - len(self.owner.commands))
        result = await lease.finish()
        self.assertEqual(result["outcome"], "unsubscribed")
        self.assertEqual(len(self.owner.commands), 1024)

    async def test_research_bridge_refuses_capture_on_owner_loop(self):
        lease = self.owner.attach(10)
        with self.assertRaises(CaptureError):
            await lease.remote("recv")

    async def test_oversized_frame_aborts(self):
        await self.wire.incoming.put(b'x' * 65537)
        await self.wait_for(lambda: self.owner.closed)
        self.assertTrue(self.wire.aborted)

    async def test_discovery_byte_cap_is_independent_of_frame_cap(self):
        for _ in range(24):
            await self.wire.incoming.put(frame(name='x' * 60000))
        await self.wait_for(lambda: self.owner.closed)
        self.assertLess(self.owner.sequence, 24)
