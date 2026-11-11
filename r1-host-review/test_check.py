import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import check as c


def metadata(**updates):
    return {"id": "a" * 64, "image": "sha256:" + "b" * 64, "pid": 321,
        "running": True, "started": "2026-11-11T10:00:00.000000000Z", "health": "healthy",
        "user": "node", "init": True, "readonly_rootfs": True, "privileged": False,
        "userns_mode": "", "restart_policy": "unless-stopped", **updates}


def process(pid, **updates):
    return {"pid": pid, "start_ticks": 100, "uid": [1000] * 4, "gid": [1000] * 4,
            "user_namespace": "user:[123]", **updates}


class HostReviewTests(unittest.TestCase):
    def observation(self, *, metas=None, identities=None, child_sets=None):
        metas = metas or [metadata(), metadata()]
        with patch.object(c, 'trusted_local_docker'), patch.object(c, 'inspect', side_effect=metas), \
             patch.object(c, 'process_identity', side_effect=identities or (lambda pid: process(pid))), \
             patch.object(c, 'children', side_effect=child_sets or [[322], [322]]), \
             patch.object(c, 'in_container', return_value=True), \
             patch.object(c, 'namespace', return_value='user:[123]'), \
             patch.object(c.os, 'getuid', return_value=1000), patch.object(c.os, 'geteuid', return_value=1000), \
             patch.object(c.os, 'getgid', return_value=1000), patch.object(c.os, 'getegid', return_value=1000):
            return c.observe(Path('/unused/private/config'))

    def test_stable_same_uid_observation_never_authorizes_rollout(self):
        r = self.observation()
        self.assertTrue(r['same_uid_and_namespace_observed'])
        self.assertEqual(r['main_process']['pid'], 322)
        self.assertEqual(r['findings'], [])
        self.assertFalse(r['production_ipc_peer_verified'])
        self.assertFalse(r['process_executable_verified'])

    def test_changed_container_identity_rejects_mixed_snapshot(self):
        with self.assertRaisesRegex(c.ReviewError, 'changed'):
            self.observation(metas=[metadata(), metadata(id='c' * 64)])

    def test_pid_reuse_is_detected_by_start_ticks(self):
        with self.assertRaisesRegex(c.ReviewError, 'changed'):
            self.observation(identities=[process(321), process(322), process(321, start_ticks=101)])

    def test_child_replacement_is_rejected(self):
        with self.assertRaisesRegex(c.ReviewError, 'changed'):
            self.observation(child_sets=[[322], [323]])

    def test_ambiguous_or_missing_child_never_guesses_scanner_pid(self):
        for ids in ([], [322, 323]):
            with self.subTest(ids=ids), self.assertRaisesRegex(c.ReviewError, 'ambiguous'):
                self.observation(child_sets=[ids])

    def test_uid_and_namespace_mismatch_are_explicit(self):
        r = self.observation(identities=lambda pid: process(pid, uid=[1001] * 4, user_namespace='user:[456]'))
        self.assertFalse(r['same_uid_and_namespace_observed'])
        self.assertIn('scanner-host-uid-mismatch', r['findings'])
        self.assertIn('user-namespace-mismatch', r['findings'])

    def test_non_init_container_observes_main_pid_without_child_guess(self):
        r = self.observation(metas=[metadata(init=False)] * 2)
        self.assertEqual(r['main_process']['pid'], 321)
        self.assertEqual(r['process_selection'], 'container-main-pid')

    def test_stopped_container_does_not_probe_pid_zero(self):
        with self.assertRaisesRegex(c.ReviewError, 'not-running'):
            self.observation(metas=[metadata(running=False, pid=0)])

    def test_unknown_health_and_hardening_never_look_ready(self):
        r = self.observation(metas=[metadata(health=None, readonly_rootfs=False)] * 2)
        self.assertIn('container-health-not-confirmed', r['findings'])
        self.assertIn('container-hardening-differs', r['findings'])

    def test_inspect_command_is_fixed_local_allowlisted_and_read_only(self):
        with patch.object(c, 'bounded_command', return_value=json.dumps(metadata()).encode()) as call:
            self.assertEqual(c.inspect(Path('/private/empty')), metadata())
        command = call.call_args.args[0]
        self.assertEqual(command, [c.DOCKER, '--config', '/private/empty', '--host', 'unix:///run/docker.sock',
            'inspect', '--type', 'container', '--format', c.FORMAT, c.TARGET])
        for forbidden in ('.Env', '.Cmd', '.Entrypoint', '.Mounts', '.Labels'):
            self.assertNotIn(forbidden, c.FORMAT)
        self.assertEqual(set(c.ENV), {'PATH', 'LANG', 'LC_ALL'})

    def test_extra_fields_and_duplicate_keys_are_rejected(self):
        rows = [json.dumps(metadata(Env=['DO-NOT-EXPORT'])).encode(), b'{"id":"a","id":"b"}',
                json.dumps(metadata(pid=True)).encode(), json.dumps(metadata(image='secret')).encode()]
        for raw in rows:
            with patch.object(c, 'bounded_command', return_value=raw), self.assertRaisesRegex(c.ReviewError, '^metadata-invalid$'):
                c.inspect(Path('/private'))

    def test_proc_identity_parses_numeric_fields_without_exporting_names(self):
        status = 'Name:\tDO-NOT-EXPORT\nUid:\t1000 1000 1000 1000\nGid:\t1000 1000 1000 1000\n'
        stat = '321 (name with ) chars) ' + ' '.join(['S'] + ['0'] * 18 + ['12345'])
        with patch.object(c, 'read_proc', side_effect=[status, stat]), patch.object(c, 'namespace', return_value='user:[1]'):
            r = c.process_identity(321)
        self.assertEqual(r['start_ticks'], 12345)
        self.assertNotIn('DO-NOT-EXPORT', json.dumps(r))

    def test_proc_duplicate_uid_is_rejected(self):
        with patch.object(c, 'read_proc', return_value='Uid: 1 1 1 1\nUid: 1 1 1 1\nGid: 1 1 1 1\n'):
            with self.assertRaises(c.ReviewError): c.process_identity(321)

    def test_cgroup_binding_requires_exact_container_id_not_pid_number_alone(self):
        with patch.object(c, 'read_proc', return_value='0::/system.slice/docker-' + 'a' * 64 + '.scope\n'):
            self.assertTrue(c.in_container(321, 'a' * 64))
            self.assertFalse(c.in_container(321, 'b' * 64))
        with patch.object(c, 'read_proc', return_value='0::/\n'):
            self.assertFalse(c.in_container(321, 'a' * 64))

    def test_subprocess_output_is_capped_and_child_reaped(self):
        with self.assertRaisesRegex(c.ReviewError, 'output-limit'):
            c.bounded_command([sys.executable, '-c', 'import sys; sys.stdout.write("x"*20000)'])

    def test_command_deadline_kills_and_reaps_stalled_child(self):
        original = c.subprocess.Popen
        started = []
        def start(*args, **kwargs):
            p = original(*args, **kwargs)
            started.append(p)
            return p
        with patch.object(c.subprocess, 'Popen', side_effect=start), \
             patch.object(c.time, 'monotonic', side_effect=[100, 105]):
            with self.assertRaisesRegex(c.ReviewError, '^docker-timeout$'):
                c.bounded_command([sys.executable, '-c', 'import time; time.sleep(10)'])
        self.assertIsNotNone(started[0].returncode)
        self.assertTrue(started[0].stdout.closed)

    def test_subprocess_failure_and_stderr_are_not_returned(self):
        with self.assertRaisesRegex(c.ReviewError, '^docker-inspect-unavailable$'):
            c.bounded_command([sys.executable, '-c', 'import sys; print("DO-NOT-EXPORT",file=sys.stderr); sys.exit(1)'])

    def test_subprocess_does_not_inherit_credentials_or_remote_docker_context(self):
        with patch.dict(os.environ, {'PUMPPORTAL_API_KEY': 'fixture', 'DOCKER_HOST': 'tcp://fixture:123',
                                     'DOCKER_CONTEXT': 'remote-fixture'}):
            raw = c.bounded_command([sys.executable, '-c', 'import json,os;print(json.dumps(dict(os.environ)))'])
        self.assertEqual(json.loads(raw), c.ENV)

    def test_atomic_report_refuses_existing_output_and_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'report.json'
            c.write_report(p, {'value': 1})
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError): c.write_report(p, {'value': 2})
            link = Path(t) / 'link'; link.symlink_to(p)
            with self.assertRaises(FileExistsError): c.write_report(link, {'value': 3})
            self.assertEqual(json.loads(p.read_text()), {'value': 1})

    def test_unavailable_host_writes_sanitized_blocked_report_without_retry(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'report.json'
            with patch.object(c, 'run_tests', return_value={'run':1,'failures':0,'errors':0,'skipped':0}), \
                 patch.object(c, 'observe', side_effect=RuntimeError('DO-NOT-EXPORT')) as observe, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(['--output',str(path),'--observe-local-container']), 0)
            self.assertEqual(observe.call_count, 1)
            r = json.loads(path.read_text())
            self.assertEqual(r['status'], 'host-identity-unavailable-rollout-blocked')
            self.assertFalse(r['production_modified']); self.assertFalse(r['live_launch_authorized'])
            self.assertNotIn('DO-NOT-EXPORT', path.read_text())

    def test_arguments_cannot_select_other_container_or_command(self):
        with tempfile.TemporaryDirectory() as t, contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(c.main(['--output',str(Path(t)/'report.json'),'--observe-local-container',
                                     '--container','DO-NOT-EXPORT']), 1)
            self.assertNotIn('DO-NOT-EXPORT', err.getvalue())
