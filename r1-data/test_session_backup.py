import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture as c
import session_backup as b
import supervisor


class SessionBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        run, report = supervisor.rehearse(Path(cls.fixture.name))
        if report['status'] != 'offline-supervisor-passed-live-blocked':
            cls.fixture.cleanup()
            raise AssertionError('synthetic prerequisite failed')
        cls.raw = (run / 'session-export/session.zip').read_bytes()
        cls.receipt = {"status": "offline-session-bundle-passed-live-blocked", "synthetic_only": True,
                       "tests": {"run": 275, "failures": 0, "errors": 0, "skipped": 0},
                       "source_sha256": b.bundle_format.source_pins(), "supervision": report}
        cls.receipt_raw = (c.canonical(cls.receipt) + '\n').encode()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bundle = self.root / 'session.zip'
        self.report = self.root / 'acceptance.json'
        c.exclusive_file(self.bundle, self.raw)
        c.exclusive_file(self.report, self.receipt_raw)
        self.output = self.root / 'roundtrip'
        self.patches = [patch.object(b, 'EXPECTED_BUNDLE', c.digest(self.raw)),
                        patch.object(b, 'BUNDLE_BYTES', len(self.raw)),
                        patch.object(b, 'EXPECTED_REPORT', c.digest(self.receipt_raw)),
                        patch.object(b.transfer, 'trusted_programs')]
        for p in self.patches: p.start()
        self.calls = []
        self.objects = {}
        self.fail_at = None
        self.returned = None
        self.metadata = b'radar-b2: b2\n'

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def process(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if len(self.calls) == self.fail_at:
            raise subprocess.TimeoutExpired(command, 40, output=b'SYNTHETIC-SECRET', stderr=b'SYNTHETIC-SECRET')
        if 'listremotes' in command:
            return subprocess.CompletedProcess(command, 0, self.metadata)
        if 'rcat' in command:
            remote = command[command.index('rcat') + 1]
            self.objects[remote] = kwargs['input']
            return subprocess.CompletedProcess(command, 0, None)
        remote = command[command.index('cat') + 1]
        return subprocess.CompletedProcess(command, 0, self.objects[remote] if self.returned is None else self.returned)

    def run_backup(self):
        with patch.object(b.transfer.subprocess, 'run', side_effect=self.process), \
             patch('socket.socket', side_effect=AssertionError('network forbidden')):
            return b.run(self.bundle, self.report, self.output)

    def test_complete_archive_roundtrip_replays_both_components_without_live_claims(self):
        report = self.run_backup()
        self.assertEqual(report['status'], 'synthetic-session-backup-passed-live-blocked')
        self.assertTrue(report['remote_download_verified'])
        self.assertTrue(report['downloaded_capture_replayed'])
        self.assertTrue(report['downloaded_measurement_replayed'])
        self.assertEqual(report['measurement'], self.receipt['supervision']['worker_receipt']['measurement'])
        self.assertEqual((self.output / 'downloaded.zip').read_bytes(), self.raw)
        self.assertEqual(self.bundle.read_bytes(), self.raw)
        self.assertEqual(self.report.read_bytes(), self.receipt_raw)
        self.assertEqual([x['operation'] for x in report['calls']], ['backend', 'upload', 'download'])
        self.assertTrue(all(x['state'] == 'completed' for x in report['calls']))
        self.assertFalse(report['production_backup_coverage_verified'])
        self.assertFalse(report['ongoing_retention_verified'])
        self.assertFalse(report['paid_feed_activated'])
        self.assertEqual(report['remote_deletions'], 0)
        self.assertEqual(report['transactions_sent'], 0)
        self.assertEqual((self.output / 'report.json').stat().st_mode & 0o777, 0o600)

    def test_commands_keep_fixed_endpoint_stdin_and_bounds(self):
        report = self.run_backup()
        self.assertRegex(report['remote_object'], r'^' + b.transfer.PREFIX + 'session-[0-9a-f]{32}-' + b.EXPECTED_BUNDLE[:12] + r'\.zip$')
        for command, kwargs in self.calls:
            self.assertEqual(command[:6], [b.transfer.SUDO, '-n', b.transfer.TIMEOUT, '--signal=TERM', '--kill-after=2s', '40s'])
            self.assertEqual(command[command.index('--config') + 1], b.transfer.CONFIG)
            self.assertEqual(command[command.index('--retries') + 1], '1')
            self.assertEqual(command[command.index('--low-level-retries') + 1], '1')
            self.assertNotIn(str(self.root), ' '.join(command))
            self.assertNotIn('shell', kwargs)
            self.assertEqual(kwargs['env'], b.transfer.ENV)
            self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
            self.assertLessEqual(kwargs['timeout'], 44)
            self.assertFalse(any(x in command for x in ('sync', 'delete', 'purge', 'config')))
        self.assertEqual(self.calls[1][1]['input'], self.raw)
        self.assertEqual(self.calls[1][1]['stdout'], subprocess.DEVNULL)
        self.assertEqual(self.calls[2][0][-2:], ['--count', str(len(self.raw) + 1)])

    def test_other_archive_or_report_never_reaches_credentials(self):
        self.report.write_bytes(self.receipt_raw + b' ')
        with self.assertRaises(c.CaptureError): self.run_backup()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.output.exists())
        self.report.write_bytes(self.receipt_raw)
        self.bundle.write_bytes(b'x' * len(self.raw))
        with self.assertRaises(c.CaptureError): self.run_backup()
        self.assertEqual(self.calls, [])

    def test_preflight_measurement_mismatch_stops_before_remote_access(self):
        changed = json.loads(self.receipt_raw)
        changed['supervision']['worker_receipt']['measurement']['provider_acknowledged_subscriptions'] = 1
        raw = c.canonical(changed).encode()
        self.report.write_bytes(raw)
        with patch.object(b, 'EXPECTED_REPORT', c.digest(raw)):
            with self.assertRaises(c.CaptureError): self.run_backup()
        self.assertEqual(self.calls, [])
        self.assertTrue((self.output / 'preflight/report.json').exists())
        self.assertFalse((self.output / 'report.json').exists())

    def test_wrong_or_ambiguous_backend_prevents_upload(self):
        for i, metadata in enumerate((b'radar-b2: local\n', b'other: b2\n', b'radar-b2: b2\nradar-b2: b2\n', b'x' * 4097)):
            self.metadata = metadata
            self.calls = []
            self.output = self.root / f'backend-{i}'
            report = self.run_backup()
            self.assertEqual(report['status'], 'synthetic-session-backup-unavailable')
            self.assertEqual(len(self.calls), 1)
            self.assertFalse(report['remote_object_may_exist'])

    def test_each_failure_stage_is_retained_sanitized_without_retry(self):
        for stage in (1, 2, 3):
            self.fail_at = stage
            self.calls = []
            self.output = self.root / f'failed-{stage}'
            report = self.run_backup()
            self.assertEqual(len(self.calls), stage)
            self.assertEqual(report['status'], 'synthetic-session-backup-unavailable')
            self.assertFalse(report['remote_download_verified'])
            self.assertEqual(report['remote_object_may_exist'], stage >= 2)
            self.assertNotIn('SYNTHETIC-SECRET', (self.output / 'report.json').read_text())
            self.assertEqual((self.output / 'source.zip').read_bytes(), self.raw)

    def test_changed_truncated_and_oversized_downloads_never_pass(self):
        for i, raw in enumerate((self.raw[:-1], self.raw + b'x', self.raw + b'xx', b'x' * len(self.raw))):
            self.returned = raw
            self.calls = []
            self.output = self.root / f'bad-{i}'
            report = self.run_backup()
            self.assertTrue(report['remote_upload_completed'])
            self.assertFalse(report['remote_download_verified'])
            self.assertFalse(report['downloaded_measurement_replayed'])
            self.assertFalse((self.output / 'downloaded.zip').exists())

    def test_download_replay_failure_retains_bytes_but_grants_no_pass(self):
        original = b.bundle_format.restore_session
        def fail(path, checksum, output):
            if Path(path).name == 'downloaded.zip': raise c.CaptureError('private')
            return original(path, checksum, output)
        with patch.object(b.bundle_format, 'restore_session', side_effect=fail):
            report = self.run_backup()
        self.assertEqual(report['status'], 'synthetic-session-backup-unavailable')
        self.assertFalse(report['downloaded_capture_replayed'])
        self.assertFalse(report['downloaded_measurement_replayed'])
        self.assertEqual((self.output / 'downloaded.zip').read_bytes(), self.raw)

    def test_profiles_reject_wrong_label_payload_sequence_and_deadline(self):
        client = b.SessionTransfer()
        target = b.transfer.PREFIX + 'session-' + 'a' * 32 + '-' + b.EXPECTED_BUNDLE[:12] + '.zip'
        with self.assertRaises(c.CaptureError): client.run('download', target)
        with patch.object(b.transfer.subprocess, 'run', side_effect=self.process):
            client.run('backend')
            for remote, raw in ((target.replace('session-', 'handoff-'), self.raw), ('other:remote', self.raw), (target, b'bad')):
                with self.assertRaises(c.CaptureError): client.run('upload', remote, raw)
            client.run('upload', target, self.raw)
            with self.assertRaises(c.CaptureError): client.run('download', target + 'extra')
            client.run('download', target)
            with self.assertRaises(c.CaptureError): client.run('backend')
        self.assertEqual(len(self.calls), 3)
        expired = b.SessionTransfer()
        expired.deadline = 0
        with self.assertRaises(c.CaptureError): expired.run('backend')
        old = b.transfer.Transfer()
        self.assertEqual(old.object_label, 'handoff')
        self.assertEqual(old.expected_bundle, b.transfer.EXPECTED_BUNDLE)
        self.assertEqual(old.bundle_bytes, b.transfer.BUNDLE_BYTES)

    def test_existing_output_and_unsafe_input_preserved_without_process(self):
        self.output.mkdir(mode=0o700)
        (self.output / 'keep').write_text('preserve')
        with self.assertRaises(FileExistsError): self.run_backup()
        self.assertEqual((self.output / 'keep').read_text(), 'preserve')
        self.assertEqual(self.calls, [])
        alias = self.root / 'alias.zip'
        alias.symlink_to(self.bundle)
        with self.assertRaises(c.CaptureError): b.run(alias, self.report, self.root / 'new')

    def test_missing_executable_and_nonzero_exit_are_not_passes(self):
        with patch.object(b.transfer, 'trusted_programs', side_effect=FileNotFoundError('SYNTHETIC-SECRET')):
            report = self.run_backup()
        self.assertFalse(report['backup_credentials_access_attempted'])
        self.assertEqual(self.calls, [])
        client = b.SessionTransfer()
        with patch.object(b.transfer.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'SYNTHETIC-SECRET')) as process:
            with self.assertRaises(c.CaptureError): client.run('backend')
            with self.assertRaises(c.CaptureError): client.run('backend')
        self.assertEqual(process.call_count, 1)
        self.assertNotIn('SYNTHETIC-SECRET', str(client.calls))

    def test_cli_explicit_roundtrip_flag_and_diagnostic_status(self):
        args = ['--bundle', str(self.bundle), '--acceptance-report', str(self.report), '--output-directory', str(self.output)]
        text = io.StringIO()
        with contextlib.redirect_stdout(text), contextlib.redirect_stderr(text), patch.object(b, 'run') as run:
            self.assertEqual(b.main(args), 1)
            self.assertEqual(b.main(args + ['--round-trip-b2', '--api-key', 'SYNTHETIC-SECRET']), 1)
        run.assert_not_called()
        self.assertNotIn('SYNTHETIC-SECRET', text.getvalue())
        self.fail_at = 2
        with patch.object(b.transfer.subprocess, 'run', side_effect=self.process), contextlib.redirect_stdout(io.StringIO()):
            code = b.main(args + ['--round-trip-b2'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((self.output / 'report.json').read_text())['status'], 'synthetic-session-backup-unavailable')


if __name__ == '__main__':
    unittest.main()
