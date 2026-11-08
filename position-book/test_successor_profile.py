"""Diagnostics preserve control flow, scope and private output boundaries."""
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import successor_profile as p
import successor_profile_cli as cli


class ProfileTests(unittest.TestCase):
    def test_nested_wall_cpu_accounting_and_deadline(self):
        ticks = iter((0, 1000000, 4000000, 10000000))
        cpus = iter((0, 1000000, 2000000, 4000000))
        walls = iter((100, 101, 104, 110))
        profile = p.Profile(tick=lambda: next(ticks), cpu=lambda: next(cpus), wall=lambda: next(walls))
        with profile.measure('execution'):
            with profile.measure('submit'):
                pass
        result = profile.report(109)
        outer, child = result['spans']
        self.assertEqual((outer['elapsedMs'], outer['exclusiveMs']), (10, 7))
        self.assertEqual((outer['threadCpuMs'], outer['exclusiveThreadCpuMs']), (4, 3))
        self.assertEqual(child['parentIndex'], 0)
        self.assertEqual(outer['headroomAtEndMs'], -1)
        self.assertEqual(result, profile.report(109))

    def test_exception_and_result_preserved_without_payload(self):
        profile = p.Profile()
        marker = object()
        self.assertIs(p.timed(lambda: marker, profile, 'submit')(), marker)
        def fail():
            raise ValueError('PRIVATE_KEY_OR_SQL')
        with self.assertRaisesRegex(ValueError, 'PRIVATE_KEY_OR_SQL'):
            p.timed(fail, profile, 'submit')()
        result = profile.report()
        self.assertEqual(result['stageTotals']['submit']['incomplete'], 1)
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertEqual(profile.stack, [])

    def test_span_cap_and_invalid_stage_do_not_skip_work(self):
        profile = p.Profile()
        seen = []
        with patch.object(p, 'MAX_SPANS', 1):
            with profile.measure('execution'):
                with profile.measure('submit'):
                    seen.append(1)
        with profile.measure('PRIVATE_PATH'):
            seen.append(2)
        result = profile.report()
        self.assertEqual(seen, [1, 2])
        self.assertEqual(len(result['spans']), 1)
        self.assertFalse(result['valid'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_bad_diagnostic_clock_does_not_replace_application_result(self):
        ticks = iter((10, 9))
        profile = p.Profile(tick=lambda: next(ticks))
        self.assertEqual(p.timed(lambda: 7, profile, 'submit')(), 7)
        result = profile.report()
        self.assertFalse(result['valid'])
        self.assertIsNone(result['spans'][0]['elapsedMs'])

    def test_transaction_commit_rollback_suppression_and_enter_failure(self):
        for mode in ('commit', 'rollback', 'suppress', 'enter-failure'):
            with self.subTest(mode=mode):
                profile = p.Profile()
                events = []
                @contextmanager
                def original(self):
                    events.append('enter')
                    if mode == 'enter-failure':
                        raise OSError('enter')
                    try:
                        yield 3
                    except ValueError:
                        events.append('rollback')
                        if mode != 'suppress':
                            raise
                    else:
                        events.append('commit')
                def run():
                    with p.transaction(original, profile)(None) as value:
                        self.assertEqual(value, 3)
                        if mode in ('rollback', 'suppress'):
                            raise ValueError('payload')
                if mode == 'rollback':
                    with self.assertRaises(ValueError): run()
                elif mode == 'enter-failure':
                    with self.assertRaises(OSError): run()
                else:
                    run()
                self.assertEqual(events, ['enter'] if mode == 'enter-failure' else
                                 ['enter', 'commit' if mode == 'commit' else 'rollback'])
                self.assertEqual(profile.stack, [])

    def test_instrumentation_and_phase_patch_restore_after_exception(self):
        import successor_execution_checks as checks
        original = checks.m._collect_sign_submit
        phase = checks.fixture.phase
        def fail():
            report = {'phases': []}
            with checks.fixture.phase(report, 'fixture-class-setup'):
                self.assertIs(checks.m._collect_sign_submit, original)
            with checks.fixture.phase(report, 'collection-signing-preflight-single-send'):
                self.assertIsNot(checks.m._collect_sign_submit, original)
                raise ValueError('fixture')
        with patch.object(checks, 'run', fail):
            with self.assertRaises(ValueError): p.run()
        self.assertIs(checks.fixture.phase, phase)
        self.assertIs(checks.m._collect_sign_submit, original)
        self.assertFalse(p._lock.locked())

    def test_partial_diagnostic_is_not_timing_acceptance(self):
        import successor_execution_checks as checks
        def fake():
            report = {'phases': [], 'state': 'review-required', 'integration': {'originalDeadlineMs': 1}}
            with checks.fixture.phase(report, 'collection-signing-preflight-single-send'):
                with self.assertRaises(ValueError):
                    checks.m._collect_sign_submit('/unused', 'w', 'p', 'a'*64, 'b'*64)
            return report
        with patch.object(checks, 'run', fake):
            result = p.run()
        self.assertEqual(result['state'], 'diagnostic-collected')
        self.assertFalse(result['timingAcceptance'])
        self.assertFalse(result['fullAcceptanceSuiteRun'])
        self.assertFalse(result['executionApproved'])
        self.assertEqual(result['profile']['stageTotals']['execution']['incomplete'], 1)

    def test_busy_refusal_and_missing_phase(self):
        import successor_execution_checks as checks
        with p._lock:
            with self.assertRaisesRegex(ValueError, 'offline-profile-busy'): p.run()
        with patch.object(checks, 'run', return_value={'state': 'review-required'}):
            self.assertEqual(p.run()['state'], 'diagnostic-incomplete')

    def test_runtime_output_accepts_only_version_and_commit_shapes(self):
        with patch.object(cli.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='PRIVATE/PATH')):
            result = cli.runtime()
        self.assertIsNone(result['node'])
        self.assertIsNone(result['sourceCommit'])
        self.assertTrue(result['workingTreeDirty'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_cli_refuses_operational_arguments_and_existing_outputs(self):
        script = str(Path(cli.__file__).resolve())
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)/'report.gz'
            for flag in ('--directory', '--wallet', '--rpc-endpoint', '--allow-devnet-submit'):
                r = subprocess.run([sys.executable, '-B', script, '--output', str(output), flag, 'unused'], capture_output=True)
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse(output.exists())
            output.write_bytes(b'preserved')
            r = subprocess.run([sys.executable, '-B', script, '--output', str(output)], capture_output=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(output.read_bytes(), b'preserved')
            link = Path(root)/'link.gz'
            link.symlink_to(output)
            r = subprocess.run([sys.executable, '-B', script, '--output', str(link)], capture_output=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(output.read_bytes(), b'preserved')


if __name__ == '__main__':
    unittest.main()
