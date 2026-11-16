import asyncio
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import common as c
import separated_session as s
import session_evidence as e
import fixtures
from capture import Limits, lock
from provider_wire import Wire, secret_variants


async def exercise(root, mode='normal', messages=4):
    ipc = root/'ipc'; ipc.mkdir(mode=0o700)
    events = {k: asyncio.Event() for k in
              ('shutdown', 'research_done', 'endpoint_ready', 'peer_ready', 'upstream_ready', 'admitted')}
    events['admitted'].set()
    peer = fixtures.Peer(mode, messages)
    async def factory():
        peer.frames.put_nowait(peer.event('create'))
        return Wire(peer, secret_variants(fixtures.SECRET))
    result = await s.run(root/'control', ipc, factory, Limits(messages=messages, seconds=1, sample_modulus=1),
                         **events, service_seconds=1, server_factory=fixtures.TestServer)
    return result


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.ipc = self.root/'ipc'; self.ipc.mkdir(mode=0o700)
        self.events = {k: asyncio.Event() for k in
                      ('shutdown', 'research_done', 'endpoint_ready', 'peer_ready', 'upstream_ready', 'admitted')}
        self.calls = 0

    async def factory(self):
        self.calls += 1
        raise AssertionError('connection must not be attempted')

    async def run_session(self, **overrides):
        options = {**self.events, 'service_seconds': 1, 'setup_seconds': 1,
                   'server_factory': fixtures.TestServer, **overrides}
        return await s.run(self.root/'control', self.ipc, self.factory,
                           Limits(seconds=1), **options)

    async def test_stop_before_setup_creates_no_attempt_or_connection(self):
        self.events['shutdown'].set()
        with self.assertRaisesRegex(c.CaptureError, 'stopped-before'):
            await self.run_session()
        self.assertFalse((self.root/'control').exists())
        self.assertEqual(self.calls, 0)

    async def test_stop_while_awaiting_admission_never_connects(self):
        task = asyncio.create_task(self.run_session())
        await asyncio.wait_for(self.events['peer_ready'].wait(), 1)
        self.events['shutdown'].set()
        with self.assertRaisesRegex(c.CaptureError, 'stopped-during'):
            await asyncio.wait_for(task, 1)
        self.assertEqual(self.calls, 0)
        self.assertFalse((self.root/'control/stopped.json').exists())
        receipt = await asyncio.to_thread(e.export, self.root/'control', self.root/'partial')
        self.assertEqual(receipt['assessment']['classification'], 'quarantined-incomplete-evidence')

    async def test_stop_cancels_inflight_connect_and_joins_capture(self):
        connecting, cancelled = asyncio.Event(), asyncio.Event()
        async def factory():
            connecting.set()
            try: await asyncio.Future()
            finally: cancelled.set()
        self.events['admitted'].set()
        task = asyncio.create_task(s.run(self.root/'control', self.ipc, factory, Limits(seconds=1),
            **self.events, service_seconds=1, server_factory=fixtures.TestServer))
        await asyncio.wait_for(connecting.wait(), 1)
        self.events['shutdown'].set()
        with self.assertRaises(c.CaptureError): await asyncio.wait_for(task, 2)
        self.assertTrue(cancelled.is_set())
        import threading
        self.assertFalse(any(t.name == 'r1-capture' and t.is_alive() for t in threading.enumerate()))
        self.assertFalse((self.root/'control/stopped.json').exists())

    async def test_one_setup_deadline_includes_admission(self):
        with self.assertRaisesRegex(c.CaptureError, 'setup-deadline'):
            await self.run_session()
        self.assertEqual(self.calls, 0)

    async def test_invalid_phase_budget_rejects_before_creation(self):
        for budget in (0, True, 31, None):
            with self.assertRaises(c.CaptureError): await self.run_session(setup_seconds=budget)
        self.assertFalse((self.root/'control').exists())


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.root = Path(cls.temp.name)
        os.umask(0o077)
        asyncio.run(exercise(cls.root))
        cls.report = e.export(cls.root/'control', cls.root/'export')
        cls.raw = (cls.root/'export/evidence.zip').read_bytes()

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_closed_run_roundtrip_has_no_synthetic_origin_requirement(self):
        result = e.restore(self.root/'export/evidence.zip', self.report['sha256'], self.root/'restore')
        self.assertEqual(result, self.report['assessment'])
        self.assertEqual(result['classification'], 'closed-clean-session-evidence')
        self.assertEqual(result['replayed']['capture']['raw_rows'], 4)
        self.assertFalse(result['provider_origin_attested'])
        self.assertFalse(result['production_handoff_verified'])

    def test_cleanup_failure_remains_failed_after_export_and_independent_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); asyncio.run(exercise(root, 'cleanup-failure'))
            report = e.export(root/'control', root/'export')
            assessment = e.restore(root/'export/evidence.zip', report['sha256'], root/'restored')
            self.assertEqual(assessment['classification'], 'closed-failed-session-evidence')
            self.assertEqual(assessment['local_session_outcome'], 'transport-cleanup-failed')

    def test_distinct_data_volume_not_fixed_fixture_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); asyncio.run(exercise(root, messages=7))
            report = e.export(root/'control', root/'export')
            self.assertNotEqual(report['sha256'], self.report['sha256'])
            self.assertEqual(report['assessment']['replayed']['capture']['raw_rows'], 7)

    def test_missing_stop_and_rollback_bytes_are_quarantined_without_repair(self):
        data, _ = e.verify(self.raw, self.report['sha256'])
        for changed in ({k: v for k, v in data.items() if k != 'stopped.json'},
                        {**data, 'capture-journal': b'original interrupted rollback bytes'}):
            before = copy.deepcopy(changed)
            assessment = e.assess(changed)
            self.assertEqual(assessment['classification'], 'quarantined-incomplete-evidence')
            self.assertEqual(changed, before)

    def test_rehashed_false_receipts_cannot_claim_complete(self):
        data, _ = e.verify(self.raw, self.report['sha256'])
        for field, value in (('capture_thread_joined', False), ('billing_cutoff_verified', True),
                             ('retirement_sha256', '0'*64)):
            changed = dict(data); stopped = e.row(changed['stopped.json']); stopped[field] = value
            changed['stopped.json'] = c.raw(stopped)
            self.assertEqual(e.assess(changed)['classification'], 'quarantined-incomplete-evidence')

    def test_extra_owner_send_cannot_hide_after_retirement(self):
        data, _ = e.verify(self.raw, self.report['sha256'])
        stopped = e.row(data['stopped.json'])
        stopped['owner']['commands'].append(stopped['owner']['commands'][-1])
        data['stopped.json'] = c.raw(stopped)
        self.assertEqual(e.assess(data)['classification'], 'quarantined-incomplete-evidence')

    def test_checksum_trailer_and_oversized_directory_refused(self):
        for raw, sha in ((self.raw, '0'*64), (self.raw+b'x', c.digest(self.raw+b'x'))):
            with self.assertRaises(c.CaptureError): e.verify(raw, sha)

    def test_live_lock_refuses_snapshot_without_writing_output(self):
        fd = lock(self.root/'control')
        try:
            with self.assertRaises(c.CaptureError): e.export(self.root/'control', self.root/'locked-export')
        finally: os.close(fd)
        self.assertFalse((self.root/'locked-export').exists())

    def test_source_bytes_are_unchanged_by_export_and_replay(self):
        control = self.root/'control'
        before = {p.relative_to(control): p.read_bytes() for p in control.rglob('*') if p.is_file()}
        e.export(control, self.root/'another-export')
        self.assertEqual(before, {p.relative_to(control): p.read_bytes() for p in control.rglob('*') if p.is_file()})

    def test_failed_output_receipt_never_overwrites_source(self):
        with patch.object(e.c, 'exclusive_file', side_effect=OSError):
            with self.assertRaises(OSError): e.export(self.root/'control', self.root/'failed-export')
        self.assertTrue((self.root/'control/stopped.json').exists())
