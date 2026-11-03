"""Diagnostic isolation, bounded output and the complete disposable entry path."""
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import entry_profile as m
import fresh_entry
from fresh_entry_checks import case


class ProfileTests(unittest.TestCase):
    def test_disabled_hooks_do_not_read_clocks_or_change_execution(self):
        with patch.object(m.time, 'time_ns', side_effect=AssertionError('clock')):
            with m.measure('entry-collection'): value = 7
            m.pin_deadline(100); m.record_send_guard(90)
        self.assertEqual(value, 7)

    def test_nested_inclusive_timings_and_original_headroom(self):
        wall = iter([1000,1010,1020,1030]); mono = iter([1,1.01,1.02,1.03])
        p = m.Profile(clock=lambda:next(wall), monotonic=lambda:next(mono))
        with m.capture(p):
            with m.measure('sender-validation'):
                with m.measure('sender-source-replay'): pass
            m.pin_deadline(1100); m.record_send_guard(1040)
        r = p.report(); self.assertTrue(r['valid'])
        self.assertEqual([x['elapsedMs'] for x in r['spans']], [30,10])
        self.assertEqual([x['remainingAtEndMs'] for x in r['spans']], [70,80])
        self.assertEqual(r['sendGuardRemainingMs'],60)
        self.assertEqual(r['spans'][1]['parentStage'],'sender-validation')
        r['spans'].clear(); self.assertEqual(len(p.report()['spans']),2)

    def test_partial_exception_is_not_hidden_or_exported(self):
        p=m.Profile()
        with m.capture(p):
            with self.assertRaisesRegex(OSError,'PRIVATE'):
                with m.measure('send-request'): raise OSError('PRIVATE')
        r=p.report(); self.assertFalse(r['spans'][0]['completed'])
        self.assertNotIn('PRIVATE',json.dumps(r))

    def test_bad_diagnostic_clock_cannot_hide_committed_result(self):
        for value in (float('nan'),float('inf'),-1,True):
            p=m.Profile(clock=lambda:1000,monotonic=lambda:value)
            with m.capture(p):
                with m.measure('commit-send-boundary'): result='durable'
            self.assertEqual(result,'durable');self.assertFalse(p.report()['valid'])
            self.assertIsNone(p.report()['spans'][0]['elapsedMs'])
        p=m.Profile(clock=lambda:(_ for _ in ()).throw(OSError('PRIVATE')))
        with m.capture(p):
            with m.measure('record-send-ack'): result='unknown'
        self.assertEqual(result,'unknown');self.assertNotIn('PRIVATE',json.dumps(p.report()))
        ticks=iter([0,1e308]);p=m.Profile(clock=lambda:1000,monotonic=lambda:next(ticks))
        with m.capture(p),m.measure('sender-open'):pass
        self.assertFalse(p.report()['valid']);self.assertIsNone(p.report()['spans'][0]['elapsedMs'])

    def test_clock_regression_and_deadline_replacement_are_visible(self):
        ticks=iter([2,1]);p=m.Profile(clock=lambda:1000,monotonic=lambda:next(ticks))
        with m.capture(p):
            m.pin_deadline(1100);m.pin_deadline(1200)
            with m.measure('sender-preflight'):pass
        r=p.report();self.assertFalse(r['valid']);self.assertEqual(r['originalDeadlineMs'],1100)
        self.assertEqual(set(r['diagnosticCodes']),{'diagnostic-clock-invalid','diagnostic-deadline-invalid'})

    def test_scope_is_not_reused_nested_or_leaked_after_exception(self):
        p=m.Profile()
        with self.assertRaises(OSError),m.capture(p):
            with self.assertRaises(ValueError),m.capture(m.Profile()):pass
            raise OSError()
        with self.assertRaises(ValueError),m.capture(p):pass
        other=m.Profile()
        with m.capture(other),m.measure('sender-open'):pass
        self.assertEqual(len(other.report()['spans']),1)

    def test_stage_cap_and_invalid_names_never_export_arbitrary_text(self):
        p=m.Profile()
        with m.capture(p):
            with m.measure('PRIVATE-STAGE'):pass
            with m.measure({'PRIVATE':'unhashable'}):pass
            for _ in range(m.MAX_SPANS+1):
                with m.measure('sender-open'):pass
        r=p.report();self.assertEqual(len(r['spans']),m.MAX_SPANS)
        self.assertFalse(r['valid']);self.assertNotIn('PRIVATE-STAGE',json.dumps(r))

    def test_profile_preserves_expiry_after_durable_boundary(self):
        with case() as c:
            p=m.Profile(clock=lambda:c.now,monotonic=lambda:c.mono)
            mark=fresh_entry.submission.Submission.mark
            def expire(book,proof):
                value=mark(book,proof);c.now=c.deadline;return value
            with m.capture(p),patch.object(fresh_entry.submission.Submission,'mark',expire):r=c.run()
            self.assertEqual(r['sendRequestsThisRun'],0)
            self.assertEqual(c.transport()['state'],'submission-unknown')
            self.assertIsNone(p.report()['sendGuardAtMs'])
            rows={x['stage']:x for x in p.report()['spans']}
            self.assertTrue(rows['commit-send-boundary']['completed'])
            self.assertNotIn('send-request',rows)
            self.assertEqual(c.run()['networkRequests'],0)

    def test_lost_response_and_broken_diagnostic_clock_keep_one_send(self):
        with case() as c:
            p=m.Profile(clock=lambda:(_ for _ in ()).throw(ValueError('PRIVATE')))
            with m.capture(p):r=c.run(rpc=c.opener(lost=True))
            self.assertEqual(r['state'],'submission-unknown');self.assertEqual(r['sendRequestsThisRun'],1)
            self.assertFalse(p.report()['valid']);self.assertNotIn('PRIVATE',json.dumps(p.report()))
            self.assertEqual(c.recover()['state'],'entry-effects-observed')
            self.assertEqual(c.run()['networkRequests'],0)

    def test_cli_connected_profile_private_output_and_no_operational_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.gz'
            cmd=[sys.executable,'-E','-s',str(Path(__file__).with_name('entry_profile_cli.py')),'--output',str(path)]
            completed=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
            self.assertEqual(completed.returncode,0,completed.stderr+completed.stdout)
            raw=path.read_bytes();r=json.loads(gzip.decompress(raw))
            self.assertEqual(r['state'],'offline-entry-profile-passed');self.assertEqual(r['casesPassed'],7)
            self.assertEqual(r['signatureVerification']['submission']['verifierProcesses'],0)
            self.assertGreater(r['signatureVerification']['attempt']['verifierProcesses'],0)
            self.assertTrue(r['profile']['valid']);self.assertTrue(r['temporaryLedgersRemoved'])
            self.assertEqual({x['stage'] for x in r['profile']['spans']},m.STAGES)
            self.assertEqual(r['realNetworkRequests'],r['transactionsSent']);self.assertEqual(r['transactionsSent'],0)
            self.assertGreater(r['profile']['sendGuardRemainingMs'],0)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(path.read_bytes(),raw)
            for flag in ('--observe-devnet','--wallet','--directory','--allow-devnet-submit','--allow-private-key-signing'):
                other=Path(directory)/'no.gz'
                self.assertNotEqual(subprocess.run(cmd[:-1]+[str(other),flag],capture_output=True).returncode,0)
                self.assertFalse(other.exists())

    def test_partial_fixture_failure_removes_owned_keys_and_sanitizes_report(self):
        import entry_profile_rehearsal
        from test_fresh_entry import FullSourceEntryTests
        created=[]
        def fail(cls):
            path=Path(tempfile.gettempdir())/'partial-private-key'
            path.write_text('PRIVATE');created.append(path)
            raise OSError('PRIVATE')
        with patch.object(FullSourceEntryTests,'setUpClass',classmethod(fail)), \
             patch.object(FullSourceEntryTests,'tearDownClass',classmethod(lambda cls:None)):
            r=entry_profile_rehearsal.run()
        self.assertEqual(r['state'],'review-required');self.assertEqual(r['casesPassed'],0)
        self.assertTrue(r['temporaryLedgersRemoved']);self.assertFalse(created[0].exists())
        self.assertNotIn('PRIVATE',json.dumps(r));self.assertEqual(r['profile']['spans'],[])

    def test_cli_failure_publishes_partial_diagnostics_and_returns_two(self):
        import entry_profile_cli
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'failed.gz'
            report=dict(format='entry-profile-rehearsal-1',state='review-required',casesPassed=0,
                profile=m.Profile().report())
            with patch.object(sys,'argv',['entry_profile_cli.py','--output',str(path)]), \
                 patch.object(entry_profile_cli,'run',return_value=report):
                self.assertEqual(entry_profile_cli.main(),2)
            self.assertEqual(json.loads(gzip.decompress(path.read_bytes()))['state'],'review-required')
            self.assertEqual(path.stat().st_mode&0o777,0o600)


if __name__=='__main__':unittest.main()
