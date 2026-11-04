"""Diagnostic failures remain visible without leaking raw evidence or becoming passes."""
import gzip,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import continuation_diagnostics as d
import continuation_exit_checks as checks

class DiagnosticsTests(unittest.TestCase):
    def test_nested_failure_retains_exact_phase_and_no_private_exception(self):
        r={}
        with self.assertRaises(ValueError):
            with d.phase(r,'connected-rehearsal'):
                with d.phase(r,'replacement-preparation'):
                    raise ValueError('private signed wire /home/private key')
        self.assertEqual(r['failedPhase'],'replacement-preparation')
        self.assertEqual(len(r['diagnosticPhases']),2)
        self.assertTrue(all(not v['completed'] for v in r['diagnosticPhases']))
        self.assertNotIn('/home/private',json.dumps(r))
        self.assertTrue(r['diagnosticPhases'][1]['codeLocations'])
        self.assertTrue(all(set(v)=={'module','function','line'} for v in r['diagnosticPhases'][1]['codeLocations']))
        self.assertNotIn(str(Path(__file__).parent),json.dumps(r))
        self.assertEqual(r['diagnosticPhases'][1]['diagnosticCode'],'unclassified')

    def test_foreign_traceback_locations_are_not_exported(self):
        with tempfile.TemporaryDirectory() as folder:
            code=compile("raise ValueError('secret')",str(Path(folder)/'private.py'),'exec')
            try:exec(code,{})
            except ValueError as exc:rows=d.locations(exc)
        self.assertTrue(all(r['module']!='private.py' for r in rows))
        self.assertNotIn(folder,json.dumps(rows))

    def test_known_expiry_and_observations_only_export_allowlisted_fields(self):
        r={}
        with self.assertRaises(ValueError):
            with d.phase(r,'original-preparation') as row:
                row['observation']=d.observation(dict(state='unavailable',diagnosticCode='exit-capture-expired',
                    networkRequests=20,createdThisRun=False,privateKey='secret',signedTransactionBase64='secret'))
                raise ValueError('original-not-prepared')
        row=r['diagnosticPhases'][0]
        self.assertEqual(row['diagnosticCode'],'original-not-prepared')
        self.assertEqual(row['observation'],dict(state='unavailable',diagnosticCode='exit-capture-expired',networkRequests=20,createdThisRun=False))
        self.assertNotIn('secret',json.dumps(r))
        self.assertEqual(d.observation(dict(state={'secret':'value'},diagnosticCode=['secret'],networkRequests=True,createdThisRun=1)),dict(state='unclassified',diagnosticCode='unclassified'))
        self.assertEqual(d.observation(None),dict(resultType='non-object'))

    def test_original_preparation_failure_exposes_collector_reason(self):
        from types import SimpleNamespace
        import admission_exit_capture_checks
        fixture=SimpleNamespace(collect=lambda:None,settle=lambda:{'accounting':{}},
            e={'costInputs':{'baseline':{}}},home='/disposable',wallet='fixture',pool='fixture')
        r={'cases':{}}
        with patch.object(checks,'exit_inputs',return_value=(None,None)), \
             patch.object(admission_exit_capture_checks,'Opener',return_value=None), \
             patch.object(checks.m.collection,'collect_and_prepare',return_value={
                 'state':'unavailable','diagnosticCode':'exit-capture-expired','networkRequests':20}):
            with self.assertRaisesRegex(ValueError,'original-not-prepared'):checks.connected(fixture,r)
        self.assertEqual(r['failedPhase'],'original-preparation')
        self.assertEqual(r['diagnosticPhases'][-1]['observation']['diagnosticCode'],'exit-capture-expired')
        self.assertEqual(r['diagnosticPhases'][-1]['observation']['networkRequests'],20)

    def test_phase_and_clock_bounds_are_diagnostic_only(self):
        r={};ticks=iter((2,1))
        with d.phase(r,'entry-collection',monotonic=lambda:next(ticks)):pass
        self.assertTrue(r['diagnosticPhases'][0]['completed'])
        self.assertIsNone(r['diagnosticPhases'][0]['elapsedMs'])
        with self.assertRaises(ValueError):
            with d.phase(r,'private-phase'):pass
        r={'diagnosticPhases':[{}]*32}
        with self.assertRaises(ValueError):
            with d.phase(r,'entry-collection'):pass

    def test_runner_setup_failure_publishes_failure_not_null_stage(self):
        import test_fresh_exit
        class Fixture:
            @classmethod
            def setUpClass(cls):raise ValueError('private setup failure')
            @classmethod
            def tearDownClass(cls):pass
        with patch.object(test_fresh_exit,'ActualBackendTests',Fixture),patch.object(checks,'fault_checks',return_value={'prior':'passed'}):
            r=checks.run()
        self.assertEqual(r['state'],'review-required')
        self.assertEqual(r['failedPhase'],'fixture-class-setup')
        self.assertEqual(r['casesPassed'],1)
        self.assertTrue(r['temporaryLedgersRemoved'])
        self.assertNotIn('private setup failure',json.dumps(r))

    def test_cli_publishes_safe_failure_report_and_exits_nonzero(self):
        import continuation_exit_cli as cli
        r=dict(state='review-required',casesPassed=11,integrationElapsedMs=None,failedPhase='replacement-preparation',diagnosticPhases=[])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.gz'
            with patch.object(cli,'run',return_value=r),patch('sys.argv',['check','--output',str(path)]),patch('builtins.print'):
                with self.assertRaises(SystemExit) as exc:cli.main()
            self.assertEqual(exc.exception.code,2)
            self.assertEqual(json.load(gzip.open(path))['failedPhase'],'replacement-preparation')
            self.assertEqual(path.stat().st_mode&0o777,0o600)

if __name__=='__main__':unittest.main()
