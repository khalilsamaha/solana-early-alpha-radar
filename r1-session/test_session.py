import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import session as s
import fixtures
from capture import CaptureError, Limits
from measurement import replay


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r1-session-test-')
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_node_exit_cannot_hide_missing_discovery_or_a_second_upstream(self):
        good = {'tokens': 1, 'creations': 1, 'discovery_gaps': 1, 'upstream_connections_opened': 0}
        fixtures.validate_node(good)
        for key, value in (('tokens', 0), ('creations', 0), ('discovery_gaps', 0),
                           ('upstream_connections_opened', 1)):
            with self.assertRaises(CaptureError): fixtures.validate_node({**good, key: value})

    async def test_immediate_first_frame_is_captured_and_every_worker_joins(self):
        result = await fixtures.exercise(self.root/'normal', messages=7)
        receipt = result['receipt']
        measured = replay(self.root/'normal/control/capture', self.root/'normal/control/session.jsonl')
        self.assertEqual(measured['messages_counted'], 7)
        self.assertEqual(measured['selected_creations'], 1)
        self.assertEqual(measured['local_sends_completed'], 1)
        self.assertEqual(measured['session_outcome'], 'capture-stopped')
        self.assertEqual(receipt['owner']['upstream_attempts'], 1)
        self.assertTrue(receipt['capture_thread_joined'])
        self.assertEqual(result['discovery']['frames'], 1)
        self.assertFalse(receipt['live_launch_authorized'])

    async def test_transport_and_cleanup_failures_are_retained_without_retry(self):
        for mode in ('cleanup-failure', 'send-failure', 'provider-failure', 'operator-stop'):
            with self.subTest(mode=mode):
                result = await fixtures.exercise(self.root/mode, mode)
                self.assertEqual(result['upstream_attempts'], 1)
                self.assertNotEqual(result['receipt']['research']['outcome'], 'capture-stopped')
                self.assertTrue(result['receipt']['capture_thread_joined'])
                raw = b''.join(p.read_bytes() for p in (self.root/mode).rglob('*') if p.is_file())
                self.assertNotIn(fixtures.SECRET.encode(), raw)

    async def test_idle_session_expires_without_reconnect_or_paid_watch(self):
        result = await fixtures.exercise(self.root/'idle', 'idle')
        self.assertEqual(result['receipt']['research']['outcome'], 'capture-stopped')
        self.assertEqual(len(result['receipt']['owner']['commands']), 2)
        measured = replay(self.root/'idle/control/capture', self.root/'idle/control/session.jsonl')
        self.assertEqual(measured['stop_reason'], 'deadline')
        self.assertEqual(measured['messages_counted'], 0)

    async def test_no_peer_means_no_upstream_and_no_completed_marker(self):
        ipc = self.root/'ipc'; ipc.mkdir(mode=0o700)
        called = []
        async def factory():
            called.append(True)
            raise AssertionError()
        bound = asyncio.Event()
        class WaitingServer(fixtures.TestServer):
            async def start(self):
                bound.set()
        with patch.object(s, 'Server', WaitingServer):
            task = asyncio.create_task(s.run(self.root/'control', ipc, factory))
            try:
                await asyncio.wait_for(bound.wait(), 2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                if not task.done(): task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertFalse(called)
        self.assertTrue((self.root/'control/admission.json').exists())
        self.assertFalse((self.root/'control/stopped.json').exists())
        self.assertFalse((ipc/'discovery.sock').exists())

    async def test_existing_attempt_cannot_be_reused_even_after_success(self):
        await fixtures.exercise(self.root/'normal')
        ipc = self.root/'ipc'; ipc.mkdir(mode=0o700)
        async def factory():
            raise AssertionError('must not run')
        with self.assertRaises(FileExistsError):
            await s.run(self.root/'normal/control', ipc, factory)

    async def test_invalid_limits_fail_before_admission(self):
        ipc = self.root/'ipc'; ipc.mkdir(mode=0o700)
        for limits in (replace(Limits(), seconds=True), replace(Limits(), active_watches=3),
                       replace(Limits(), daily_watches=25), replace(Limits(), raw_bytes=8388609)):
            with self.assertRaises(CaptureError):
                await s.run(self.root/'control', ipc, None, limits)
        self.assertFalse((self.root/'control').exists())

    async def test_source_drift_refuses_completed_marker(self):
        before = s.pins()
        with patch.object(s, 'pins', side_effect=[before, {}]):
            with self.assertRaises(CaptureError):
                await fixtures.exercise(self.root/'drift')
        self.assertFalse((self.root/'drift/control/stopped.json').exists())

    async def test_cancel_active_capture_joins_worker_without_completion(self):
        task = asyncio.create_task(fixtures.exercise(self.root/'cancel', 'idle'))
        try:
            async with asyncio.timeout(2):
                while not (self.root/'cancel/control/session.jsonl').exists():
                    if task.done(): await task
                    await asyncio.sleep(0.002)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        finally:
            if not task.done(): task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertFalse((self.root/'cancel/control/stopped.json').exists())
        self.assertFalse(any(t.name == 'r1-capture' and t.is_alive() for t in threading.enumerate()))

    async def test_failed_factory_joins_waiting_worker_without_completion(self):
        ipc = self.root/'ipc'; ipc.mkdir(mode=0o700)
        async def failed(): raise OSError(fixtures.SECRET)
        with patch.object(s, 'Server', fixtures.TestServer):
            with self.assertRaises(CaptureError): await s.run(self.root/'failed', ipc, failed)
        self.assertFalse((self.root/'failed/stopped.json').exists())
        self.assertFalse(any(t.name == 'r1-capture' and t.is_alive() for t in threading.enumerate()))


if __name__ == '__main__':
    unittest.main()
