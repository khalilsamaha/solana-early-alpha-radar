from contextlib import ExitStack, contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import readiness as r
import readiness_diagnostics as d
from test_readiness import config

SECRET = 'SECRET-MUST-NOT-ESCAPE'


@contextmanager
def fixture():
    with ExitStack() as stack:
        with patch.object(d, 'command', return_value=json.dumps(config()).encode()):
            configuration = r.configuration(Path('/unused'))
        identity = {'pid': 123, 'start_ticks': 100, 'uid': [1000] * 4}
        metadata = {'id': configuration['container_id'], 'image': configuration['image'],
                    'started': configuration['started'], 'mounts': []}
        patches = (
            (r, 'pins', {'fixture.py': 'a' * 64}),
            (r.i.host, 'trusted_local_docker', None),
            (r, 'configuration', configuration), (r, 'census', ['a' * 64]),
            (r.i, 'observe', {'identity_observation': {'main_process': identity}, 'metadata': metadata}),
            (r, 'dotenv_presence', {'observed': True, 'present': False, 'contents_read': False}),
            (r, 'storage', {'available': True, 'space_reserved': False, 'retention_approved': False}),
            (r.i, 'metadata', metadata), (r.i.host, 'process_identity', identity),
        )
        mocks = {name: stack.enter_context(patch.object(module, name, return_value=value))
                 for module, name, value in patches}
        yield mocks


class ReadinessReportTests(unittest.TestCase):
    def collect(self):
        return r.collect(Path('/unused-config'), Path('/unused-storage'))

    def test_complete_observation_has_all_stages_without_activation(self):
        with fixture():
            report = self.collect()
        self.assertEqual(report['status'], 'deployment-inputs-observed-rollout-pending')
        self.assertEqual([row['stage'] for row in report['stages']], list(d.STAGES))
        self.assertTrue(all(row['status'] == 'completed' for row in report['stages']))
        self.assertNotIn('failure', report)
        for field in ('activation_authorized', 'automatic_resume_allowed', 'raw_diagnostics_exported',
                      'provider_connection_opened', 'production_modified'):
            self.assertIs(report[field], False)

    def test_each_stage_failure_preserves_position_and_never_runs_later_stages(self):
        original = d.Trace.run
        for index, stage in enumerate(d.STAGES):
            with self.subTest(stage=stage), fixture():
                def injected(trace, name, function, *args):
                    if name == stage:
                        def fail():
                            raise RuntimeError(SECRET)
                        return original(trace, name, fail)
                    return original(trace, name, function, *args)
                with patch.object(d.Trace, 'run', injected):
                    report = self.collect()
                self.assertNotIn('observation', report)
                self.assertEqual(report['status'], 'deployment-inputs-unavailable')
                self.assertEqual(report['failure']['stage'], stage)
                self.assertEqual(report['failure']['code'], 'observation-unavailable')
                self.assertEqual([row['status'] for row in report['stages']],
                                 ['completed'] * index + ['unavailable'] +
                                 ['not-run'] * (len(d.STAGES) - index - 1))
                self.assertEqual(report['observation_attempted'], index > 0)
                self.assertNotIn(SECRET, json.dumps(report))

    def test_recognized_docker_failure_has_safe_code_and_no_second_attempt(self):
        with fixture() as mocks:
            mocks['configuration'].side_effect = r.i.host.ReviewError('docker-template-unavailable')
            report = self.collect()
            self.assertEqual(mocks['configuration'].call_count, 1)
            mocks['observe'].assert_not_called()
            mocks['census'].assert_not_called()
        self.assertEqual(report['failure']['stage'], 'configuration-before')
        self.assertEqual(report['failure']['code'], 'docker-template-unavailable')

    def test_actual_configuration_parser_failure_has_pinned_source_location(self):
        with fixture() as mocks, patch.object(d, 'command', return_value=b'{}'):
            mocks['configuration'].side_effect = ACTUAL_CONFIGURATION
            report = self.collect()
        self.assertEqual(report['failure']['code'], 'readiness-configuration-shape')
        # check() raises inside the source-pinned intake module; no host path/locals.
        self.assertEqual(report['failure']['site']['source'], 'r1-production-review/intake.py')
        self.assertIsInstance(report['failure']['site']['line'], int)
        self.assertNotIn('/workspace', json.dumps(report))

    def test_source_drift_discards_otherwise_successful_observation(self):
        with fixture() as mocks:
            mocks['pins'].side_effect = [{'a.py': 'a' * 64}, {'a.py': 'b' * 64}]
            report = self.collect()
        self.assertNotIn('observation', report)
        self.assertEqual(report['failure']['stage'], 'source-after')
        self.assertEqual(report['failure']['code'], 'readiness-source-changed')

    def test_configuration_and_process_drift_stay_unavailable(self):
        for target, stage, changes in (
            ('configuration', 'configuration-consistency', [None, {'different': True}]),
            ('metadata', 'process-consistency', [{'different': True}]),
        ):
            with self.subTest(target=target), fixture() as mocks:
                if changes[0] is None:
                    changes = [mocks[target].return_value, *changes[1:]]
                mocks[target].side_effect = changes
                report = self.collect()
            self.assertNotIn('observation', report)
            self.assertEqual(report['failure']['stage'], stage)

    def test_optional_storage_unknown_is_retained_not_declared_available(self):
        with fixture() as mocks:
            mocks['storage'].return_value = {'available': False, 'reason': 'filesystem-observation-unavailable'}
            report = self.collect()
        self.assertIn('observation', report)
        self.assertFalse(report['observation']['proposed_storage']['available'])
        self.assertIn('proposed-storage-filesystem-unavailable', report['observation']['findings'])

    def test_missing_stop_settings_produce_findings_without_claiming_effective_defaults(self):
        with fixture() as mocks:
            mocks['configuration'].return_value.update(standard_term_signal=None, stop_timeout_seconds=None)
            report = self.collect()
        self.assertIn('observation', report)
        self.assertIn('stop-signal-unconfirmed', report['observation']['findings'])
        self.assertIn('stop-timeout-unconfirmed', report['observation']['findings'])
        self.assertIs(report['activation_authorized'], False)

    def test_exception_messages_and_custom_stringification_never_escape(self):
        class SensitiveError(Exception):
            def __str__(self):
                raise AssertionError('must not stringify')
        for error, expected in ((SensitiveError(SECRET), 'observation-unavailable'),
                                (PermissionError(SECRET), 'permission-denied'),
                                (KeyError(SECRET), 'required-field-unavailable'),
                                (ValueError('context-fields:' + SECRET), 'value-invalid')):
            with self.subTest(error=type(error).__name__), fixture() as mocks:
                mocks['configuration'].side_effect = error
                report = self.collect()
            self.assertEqual(report['failure']['code'], expected)
            self.assertNotIn(SECRET, json.dumps(report))

    def test_failed_cli_preserves_private_archive_and_nonzero_result(self):
        with tempfile.TemporaryDirectory() as tmp, fixture() as mocks:
            out = Path(tmp) / 'results'
            mocks['configuration'].side_effect = RuntimeError(SECRET)
            with patch('sys.argv', ['readiness.py', '--output', str(out), '--storage-root', tmp]), \
                 redirect_stdout(io.StringIO()) as output:
                old_umask = os.umask(0o077)
                try:
                    result = r.main()
                finally:
                    os.umask(old_umask)
            self.assertEqual(result, 1)
            raw = (out / 'report.json').read_bytes()
            with zipfile.ZipFile(out / 'production-readiness.zip') as archive:
                self.assertEqual(archive.namelist(), ['report.json'])
                self.assertEqual(raw, archive.read('report.json'))
            self.assertEqual((out / 'report.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual((out / 'production-readiness.zip').stat().st_mode & 0o777, 0o600)
            self.assertNotIn(SECRET, raw.decode() + output.getvalue())

    def test_trace_refuses_automatic_stage_retry(self):
        trace = d.Trace()
        trace.run('source-before', lambda: None)
        with self.assertRaises(ValueError):
            trace.run('source-before', lambda: None)

    def test_private_config_cleanup_failure_revokes_success(self):
        @contextmanager
        def broken_cleanup(*args, **kwargs):
            yield '/unused-config'
            raise PermissionError(SECRET)
        with tempfile.TemporaryDirectory() as tmp, fixture():
            out = Path(tmp) / 'results'
            with patch('sys.argv', ['readiness.py', '--output', str(out), '--storage-root', tmp]), \
                 patch.object(r, 'collect', return_value={'observation': {'accepted': False},
                     'status': 'deployment-inputs-observed-rollout-pending'}), \
                 patch.object(r.tempfile, 'TemporaryDirectory', side_effect=broken_cleanup), \
                 patch.object(r.i.host, 'write_report') as write, \
                 patch.object(r.zipfile, 'ZipFile'), redirect_stdout(io.StringIO()):
                old_umask = os.umask(0o077)
                try:
                    result = r.main()
                finally:
                    os.umask(old_umask)
            report = write.call_args.args[1]
            self.assertEqual(result, 1)
            self.assertNotIn('observation', report)
            self.assertEqual(report['failure']['stage'], 'private-client-configuration')
            self.assertNotIn(SECRET, json.dumps(report))


ACTUAL_CONFIGURATION = r.configuration


class BoundedCommandTests(unittest.TestCase):
    def run_child(self, body, *, deadline=1):
        # Disposable local executable stands in for Docker; no daemon/socket used.
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / 'fake-docker'
            executable.write_text('#!/usr/bin/python3\n' + body + '\n')
            executable.chmod(0o700)
            children = []
            real_popen = subprocess.Popen
            def launch(*args, **kwargs):
                process = real_popen(*args, **kwargs)
                children.append(process)
                return process
            try:
                with patch.object(d.i.host, 'DOCKER', str(executable)), \
                     patch.object(d, 'COMMAND_SECONDS', deadline), \
                     patch.object(d.subprocess, 'Popen', side_effect=launch):
                    return d.command(Path(tmp), 'ps', '--no-trunc', '--format', '{{.ID}}')
            finally:
                self.assertEqual(len(children), 1)
                self.assertIsNotNone(children[0].poll())
                self.assertTrue(children[0].stdout.closed)
                self.assertTrue(children[0].stderr.closed)

    def test_success_returns_stdout_only(self):
        result = self.run_child(f'import os\nos.write(1, b"ok\\n")\nos.write(2, b"{SECRET}")')
        self.assertEqual(result, b'ok\n')

    def test_failures_export_only_constant_classifications(self):
        for message, code in (
            ('template parsing error: ' + SECRET, 'docker-template-unavailable'),
            ('template parsing error: map has no entry for key "StopTimeout" ' + SECRET,
             'docker-template-field-unavailable-StopTimeout'),
            ('template parsing error: can\'t evaluate field StopSignal in type foo ' + SECRET,
             'docker-template-field-unavailable-StopSignal'),
            ('template parsing error: map has no entry for key "SECRET"', 'docker-template-unavailable'),
            ('permission denied ' + SECRET, 'docker-permission-denied'),
            ('No such container: ' + SECRET, 'docker-target-unavailable'),
            (SECRET, 'docker-inspect-unavailable'),
        ):
            with self.subTest(code=code), self.assertRaisesRegex(d.i.host.ReviewError, '^' + code + '$'):
                self.run_child(f'import os\nos.write(1, b"{SECRET}")\nos.write(2, {message.encode()!r})\nraise SystemExit(1)')

    def test_stdout_and_stderr_are_independently_bounded(self):
        for fd, code in ((1, 'docker-output-limit'), (2, 'docker-diagnostic-limit')):
            with self.subTest(fd=fd), self.assertRaisesRegex(d.i.host.ReviewError, '^' + code + '$'):
                self.run_child(f'import os,time\nos.write({fd}, b"x"*20000)\ntime.sleep(10)')

    def test_open_pipe_timeout_kills_and_reaps_child(self):
        with self.assertRaisesRegex(d.i.host.ReviewError, '^docker-timeout$'):
            self.run_child('import time\ntime.sleep(10)', deadline=0.15)

    def test_closed_pipes_do_not_escape_process_deadline(self):
        with self.assertRaisesRegex(d.i.host.ReviewError, '^docker-timeout$'):
            self.run_child('import os,time\nos.close(1)\nos.close(2)\ntime.sleep(10)', deadline=0.15)

    def test_mutating_commands_refused_before_process_launch(self):
        with patch.object(d.subprocess, 'Popen') as launch:
            for args in (('restart', d.i.host.TARGET), ('exec', d.i.host.TARGET, 'env'),
                         ('inspect', '--type', 'container', '--format', '{{json .}}', 'other')):
                with self.assertRaises(ValueError):
                    d.command(Path('/unused'), *args)
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
