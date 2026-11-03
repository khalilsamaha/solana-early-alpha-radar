"""Full offline host profile, safe failure reports and monotonic measurement."""
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import lifecycle_rehearsal as m


class RehearsalTests(unittest.TestCase):
    def test_full_cli_connected_path_and_private_nonoperational_report(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz'
            cmd=[sys.executable,'-E','-s',str(Path(__file__).with_name('lifecycle_rehearsal_cli.py')),'--output',str(out)]
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            raw=out.read_bytes();r=json.loads(gzip.decompress(raw))
            self.assertEqual(r['state'],'offline-rehearsal-passed');self.assertEqual(r['casesPassed'],9)
            self.assertEqual(list(r['timings'][i]['stage'] for i in range(7)),list(m.STAGES))
            self.assertTrue(all(x['completed'] and x['elapsedMs']>=0 for x in r['timings']))
            self.assertEqual(r['entry']['syntheticSendAttempts'],1);self.assertEqual(r['exit']['syntheticSendAttempts'],1)
            self.assertTrue(r['temporaryLedgersRemoved']);self.assertTrue(r['originalSourceUnchanged'])
            self.assertEqual(r['recovery']['repeatNetworkRequests'],0);self.assertEqual(r['realNetworkRequests'],0)
            for key in ('productionWalletAccessed','productionLedgerUpdated','executionApproved','fundsAvailableForNewEntry',
                        'nextCycleAuthorized','runtimeIntegrated','measuredProviderLatency','measuredFinalityLatency','timingApproval'):
                self.assertIs(r[key],False)
            for forbidden in ('signedTransactionBase64','privateKey','requestSha256','wallet','pool','rpcEvidence'):
                self.assertNotIn('"'+forbidden+'"',gzip.decompress(raw).decode())
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(raw,out.read_bytes())
            for flag in ('--directory','--wallet','--pool','--execute','--allow-devnet-submit','--action'):
                target=Path(d)/'absent.gz'
                self.assertNotEqual(subprocess.run(cmd[:-1]+[str(target),flag],capture_output=True).returncode,0)
                self.assertFalse(target.exists())
    def test_cli_retains_incomplete_report_and_returns_failure_exit(self):
        import lifecycle_rehearsal_cli as cli
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'failed.gz';report=m.base()
            report.update(diagnosticCode='rehearsal-original-expiry',failedStage='exit-collection-sign-send')
            with patch.object(sys,'argv',['cli','--output',str(out)]),patch.object(cli,'run',return_value=report):
                self.assertEqual(cli.main(),2)
            saved=json.loads(gzip.decompress(out.read_bytes()))
            self.assertEqual(saved['state'],'review-required');self.assertEqual(saved['diagnosticCode'],'rehearsal-original-expiry')
            self.assertEqual(out.stat().st_mode&0o777,0o600)
    def test_stage_failure_keeps_duration_and_no_exception_text(self):
        ticks=iter([1,2]);mtr=m.Measurements(lambda:next(ticks))
        with self.assertRaisesRegex(OSError,'PRIVATE'):
            with mtr.stage('entry-receipt-accounting'):raise OSError('PRIVATE')
        self.assertEqual(mtr.rows,[dict(stage='entry-receipt-accounting',elapsedMs=1000,completed=False)])
        self.assertNotIn('PRIVATE',json.dumps(mtr.rows))
    def test_invalid_stage_never_enters(self):
        with self.assertRaises(ValueError):
            with m.Measurements().stage('arbitrary private text'):self.fail('entered')
    def test_regressing_or_nonfinite_clock_never_reports_success(self):
        for end in (0,float('nan'),float('inf'),True,None):
            ticks=iter([1,end]);mtr=m.Measurements(lambda:next(ticks))
            with self.assertRaises(ValueError):
                with mtr.stage('fixture-setup'):pass
            self.assertIsNone(mtr.rows[0]['elapsedMs']);self.assertFalse(mtr.rows[0]['completed'])
    def test_clock_regression_between_stages_refuses_work(self):
        ticks=iter([10,11,10]);mtr=m.Measurements(lambda:next(ticks))
        with mtr.stage('fixture-setup'):pass
        with self.assertRaises(ValueError):
            with mtr.stage('entry-collection-sign-send'):self.fail('regressed stage entered')
        self.assertEqual(len(mtr.rows),1)
    def test_leg_projection_never_turns_failed_or_late_send_into_success(self):
        good=dict(state='submission-unknown',signerAcknowledgmentValidated=True,sendRequestsThisRun=1,
                  completedWithinOriginalDeadline=True,networkRequests=25)
        self.assertEqual(m.leg(good)['syntheticSendAttempts'],1)
        for key,value in [('state','rpc-acknowledged'),('signerAcknowledgmentValidated',False),('sendRequestsThisRun',2),
                          ('completedWithinOriginalDeadline',False),('networkRequests',26)]:
            with self.assertRaises(ValueError):m.leg(dict(good,**{key:value}))
    def test_partial_setup_failure_removes_temporary_keys_and_publishes_only_sanitized_failure(self):
        import test_fresh_entry as source
        paths=[]
        def broken(cls):
            p=Path(tempfile.mkdtemp())/'signer.pk8';p.write_bytes(b'PRIVATE');paths.append(p)
            raise OSError('PRIVATE')
        with patch.object(source.FullSourceEntryTests,'setUpClass',classmethod(broken)), \
             patch.object(source.FullSourceEntryTests,'tearDownClass',classmethod(lambda cls:None)):
            r=m.run()
        self.assertEqual(r['state'],'review-required');self.assertEqual(r['failedStage'],'fixture-setup')
        self.assertEqual(r['casesPassed'],0);self.assertTrue(r['temporaryLedgersRemoved'])
        self.assertTrue(paths);self.assertTrue(all(not p.exists() for p in paths));self.assertNotIn('PRIVATE',json.dumps(r))
    def test_cleanup_failure_cannot_leave_success_claim(self):
        import test_fresh_entry as source
        def setup(cls):cls.test_key=b'PRIVATE'
        def instance(obj):obj.home=Path(tempfile.mkdtemp())
        def cleanup(cls):raise OSError('PRIVATE')
        with patch.object(source.FullSourceEntryTests,'setUpClass',classmethod(setup)), \
             patch.object(source.FullSourceEntryTests,'setUp',instance), \
             patch.object(source.FullSourceEntryTests,'tearDown',lambda obj:None), \
             patch.object(source.FullSourceEntryTests,'tearDownClass',classmethod(cleanup)), \
             patch.object(m,'_exercise',lambda *args:None):r=m.run()
        self.assertEqual(r['state'],'review-required');self.assertEqual(r['diagnosticCode'],'temporary-cleanup-incomplete')
        self.assertTrue(r['temporaryLedgersRemoved']);self.assertNotIn('PRIVATE',json.dumps(r))


if __name__=='__main__':unittest.main()
