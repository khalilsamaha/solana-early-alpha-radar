import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import container_boundary as c
from capture import CaptureError


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r1-boundary-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.consumer = c.Consumer(self.root)
        self.ipc = self.root / 'ipc'; self.ipc.mkdir(mode=0o700)
        with patch.object(c.os, 'getuid', return_value=self.root.stat().st_uid), \
             patch.object(c.os, 'geteuid', return_value=1000), \
             patch.object(c.os, 'getgid', return_value=1000), \
             patch.object(c.os, 'getegid', return_value=1000):
            # Command generation needs the fixed accepted host UID; safe_directory
            # is tested separately against real filesystem owners.
            with patch.object(c, 'safe_directory', side_effect=lambda x: Path(x)), \
                 patch.object(c.os, 'getuid', return_value=1000):
                self.args = self.consumer.create_args(self.ipc)

    def row(self, **updates):
        return {'id': 'a' * 64, 'image': c.IMAGE, 'label': self.consumer.token,
            'user': '1000:1000', 'network': 'none', 'readonly': True, 'privileged': False,
            'restart': 'no', 'memory': 128 * 1024**2, 'pids': 32, 'caps': ['ALL'],
            'swap': 128 * 1024**2, 'cpus': 1000000000, 'init': True, 'logging': 'none',
            'security': ['no-new-privileges:true'], 'running': False, 'exit_code': 0,
            'mounts': [{'Destination': '/r1-code', 'Source': str(self.consumer.code), 'Type': 'bind', 'RW': False},
                       {'Destination': '/r1-ipc', 'Source': str(self.ipc), 'Type': 'bind', 'RW': False}], **updates}

    def test_fixed_image_no_pull_no_network_and_no_restart(self):
        for value in ('--pull=never', '--network=none', '--restart=no', '--read-only', '--init',
                      '--user=1000:1000', '--cap-drop=ALL', '--no-healthcheck', '--log-driver=none', c.IMAGE):
            self.assertIn(value, self.args)
        for forbidden in ('--env-file', '--privileged', '--publish', '--volumes-from'):
            self.assertNotIn(forbidden, self.args)
        self.assertEqual(self.args[self.args.index(c.IMAGE) + 1], '-i')
        self.assertIn('--entrypoint=/usr/bin/env', self.args)

    def test_only_reviewed_source_and_socket_directories_mounted_read_only(self):
        mounts = [self.args[i+1] for i,a in enumerate(self.args) if a == '--mount']
        self.assertEqual(len(mounts), 2)
        self.assertTrue(all(m.endswith(',readonly') for m in mounts))
        files = {str(p.relative_to(self.consumer.code)) for p in self.consumer.code.rglob('*') if p.is_file()}
        self.assertEqual(files, set(c.CODE_FILES))
        self.assertNotIn('.env', files)

    def test_staged_sources_exactly_match_repository(self):
        for name, expected in self.consumer.code_pins.items():
            self.assertEqual(c.digest((c.REPO/name).read_bytes()), expected)

    def test_wrong_uid_rejected_before_create(self):
        with patch.object(c.os, 'getuid', return_value=0):
            with self.assertRaises(CaptureError): self.consumer.create_args(self.ipc)

    def test_paths_cannot_inject_mount_arguments(self):
        p = self.root / 'bad,readonly=false'; p.mkdir(mode=0o700)
        with self.assertRaises(CaptureError): c.safe_directory(p)
        p = self.root / 'link'; p.symlink_to(self.ipc)
        with self.assertRaises(CaptureError): c.safe_directory(p)

    def test_public_socket_directory_rejected(self):
        self.ipc.chmod(0o755)
        with self.assertRaises(CaptureError): c.safe_directory(self.ipc)

    def test_exact_isolation_passes_but_modified_fields_fail(self):
        self.consumer.isolation(self.row())
        for change in ({'network':'host'}, {'user':'root'}, {'readonly':False}, {'privileged':True},
                       {'restart':'always'}, {'memory':0}, {'pids':0}, {'caps':[]}, {'security':[]}):
            with self.subTest(change=change), self.assertRaises(CaptureError):
                self.consumer.isolation(self.row(**change))

    def test_extra_or_writable_or_wrong_mounts_rejected(self):
        for change in ('RW', 'Source', 'extra'):
            row = self.row()
            if change == 'extra': row['mounts'].append(dict(row['mounts'][0]))
            elif change == 'RW': row['mounts'][0]['RW'] = True
            else: row['mounts'][0]['Source'] = '/production'
            with self.assertRaises(CaptureError): self.consumer.isolation(row)

    def test_unowned_container_never_removed(self):
        self.consumer.attempted = True
        with patch.object(self.consumer, 'command', return_value=json.dumps(self.row(label='wrong')).encode()) as command:
            with self.assertRaises(CaptureError): asyncio.run(self.consumer.cleanup())
            self.assertEqual(command.call_count, 1)
            self.assertEqual(command.call_args.args[0], 'inspect')

    def test_uncertain_create_reconciles_own_name_before_removal(self):
        self.consumer.attempted = True
        with patch.object(self.consumer, 'command', side_effect=[json.dumps(self.row()).encode(), ('a'*64+'\n').encode()]) as command:
            asyncio.run(self.consumer.cleanup())
        self.assertEqual(command.call_args_list[0].args[-1], self.consumer.name)
        self.assertEqual(command.call_args_list[1].args, ('rm','--force','--volumes','a'*64))
        self.assertTrue(self.consumer.removed)

    def test_wrong_id_or_image_rejected(self):
        self.consumer.cid = 'a'*64
        for change in ({'id':'b'*64}, {'image':'sha256:'+'b'*64}):
            with patch.object(self.consumer, 'command', return_value=json.dumps(self.row(**change)).encode()):
                with self.assertRaises(CaptureError): self.consumer.identify(self.consumer.cid)

    def test_removal_daemon_failure_is_not_success(self):
        self.consumer.attempted = True
        with patch.object(self.consumer, 'command', side_effect=[json.dumps(self.row()).encode(), RuntimeError('withheld')]):
            with self.assertRaises(RuntimeError): asyncio.run(self.consumer.cleanup())
        self.assertFalse(self.consumer.removed)

    def test_removal_response_must_match_exact_id(self):
        self.consumer.attempted = True
        with patch.object(self.consumer, 'command', side_effect=[json.dumps(self.row()).encode(), b'wrong\n']):
            with self.assertRaises(CaptureError): asyncio.run(self.consumer.cleanup())
        self.assertFalse(self.consumer.removed)

    def test_cleanup_is_idempotent_and_never_removes_before_attempt(self):
        with patch.object(self.consumer, 'command') as command:
            asyncio.run(self.consumer.cleanup())
            self.consumer.attempted = self.consumer.removed = True
            asyncio.run(self.consumer.cleanup())
            command.assert_not_called()

    def test_no_automatic_restart(self):
        self.consumer.attempted = True
        with self.assertRaises(CaptureError): asyncio.run(self.consumer.start(self.ipc/'discovery.sock', self.root))

    def test_bad_isolation_never_starts_container(self):
        async def run():
            with patch.object(c.host, 'trusted_local_docker'), \
                 patch.object(self.consumer, 'create_args', return_value=self.args), \
                 patch.object(self.consumer, 'command', side_effect=[b'a'*64, json.dumps(self.row(network='host')).encode()]), \
                 patch.object(c.asyncio, 'create_subprocess_exec', new_callable=AsyncMock) as launch:
                with self.assertRaises(CaptureError): await self.consumer.start(self.ipc/'discovery.sock', self.root)
                launch.assert_not_called()
        asyncio.run(run())

    def test_cancellation_waits_for_dispatched_daemon_operation(self):
        import threading
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        def operation():
            entered.set(); release.wait(2); finished.set()
        async def run():
            task = asyncio.create_task(self.consumer.operation(operation))
            while not entered.is_set(): await asyncio.sleep(0.001)
            task.cancel(); await asyncio.sleep(0)
            self.assertFalse(task.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError): await task
            self.assertTrue(finished.is_set())
        asyncio.run(run())

    def test_failed_cleanup_is_not_automatically_retried(self):
        self.consumer.attempted = True
        with patch.object(self.consumer, 'command', side_effect=RuntimeError('withheld')) as call:
            with self.assertRaises(RuntimeError): asyncio.run(self.consumer.cleanup())
            with self.assertRaises(CaptureError): asyncio.run(self.consumer.cleanup())
            self.assertEqual(call.call_count, 1)

    def test_real_node_fixture_refuses_missing_endpoint_without_direct_fallback(self):
        import shutil, subprocess
        result = subprocess.run([shutil.which('node'), str(c.REPO / 'r1-data/shared_scanner_fixture.mjs'),
            'unix', str(self.ipc / 'discovery.sock')], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5,
            env={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout), {'tokens':0,'creations':0,'discovery_gaps':0,
            'sources':[], 'upstream_connections_opened':0})

    def test_existing_output_directory_never_receives_a_failure_report(self):
        import contextlib, io
        import check_container
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check_container.main(['--offline-only','--output-directory',str(self.root)]), 1)
        self.assertFalse((self.root / 'report.json').exists())
