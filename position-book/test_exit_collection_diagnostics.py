"""Bounded telemetry and actual failed/successful read-only collections."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import exit_collection_diagnostics as d


class DiagnosticsTests(unittest.TestCase):
    def test_phase_measurements_include_last_phase_and_do_not_supply_deadline(self):
        with patch.object(d.time,'perf_counter_ns',side_effect=[0,1000000,4000000]):
            t=d.Timing();t.mark('pool');r=t.finish()
        self.assertEqual(r['elapsedMs'],4)
        self.assertEqual(r['stages'],[dict(stage='admission',elapsedMs=1),dict(stage='pool',elapsedMs=3)])
        self.assertNotIn('validUntilExclusiveMs',r)

    def test_bad_timing_is_unavailable_not_zero_or_a_raised_exception(self):
        for ticks in ([10,9],[0,OSError('PRIVATE')],[0,10**30],[False,10],[0,float('nan')]):
            with patch.object(d.time,'perf_counter_ns',side_effect=ticks):
                self.assertIsNone(d.Timing().finish())

    def test_projection_withholds_private_arbitrary_and_invalid_data(self):
        raw=dict(state='PRIVATE',stage='PRIVATE',diagnosticCode='PRIVATE',networkRequests=21,
                 collectionTiming={'version':d.VERSION,'elapsedMs':float('nan')},evidence='PRIVATE')
        r=d.summary(raw);self.assertNotIn('PRIVATE',json.dumps(r));self.assertIsNone(r['networkRequests'])
        self.assertIsNone(r['collectionTiming']);self.assertIsNone(d.summary([]))
        for n in (True,-1,10**500,float('inf')):self.assertFalse(d.number(n))
        raw.update(state={},stage=[],diagnosticCode={});self.assertIsInstance(d.summary(raw),dict)

    def test_projection_bounds_stage_rows_and_is_idempotent(self):
        raw=dict(state='unavailable',stage='simulation',diagnosticCode='exit-capture-simulation',networkRequests=20,
            collectionTiming=dict(version=d.VERSION,elapsedMs=12,
                stages=[dict(stage='pool',elapsedMs=10,private='PRIVATE')]),private='PRIVATE')
        r=d.summary(raw);self.assertEqual(d.summary(r),r);self.assertNotIn('PRIVATE',json.dumps(r))
        for rows in ([dict(stage='PRIVATE',elapsedMs=1)], [dict(stage='pool',elapsedMs=True)],
                     [dict(stage='pool',elapsedMs=1)]*9):
            raw['collectionTiming']['stages']=rows;self.assertIsNone(d.summary(raw)['collectionTiming'])

    def test_real_continuation_collection_failure_survives_both_wrappers_without_signing(self):
        from preserved_exit_checks import case
        import fresh_exit as fresh
        import controlled_continuation as controlled
        with case() as c:
            before=c.path.read_bytes()
            def hook(n,body,rpc):
                if n==19:rpc.rows[0]['value']['err']={'PRIVATE':'never export'}
            c.rpc.hook=hook
            def refuse(*a):raise AssertionError('signing must not occur')
            raw=fresh._run(c.home,c.wallet,c.pool,signer_adapter=refuse,collection_opener=c.rpc,
                clock=c.clock,monotonic=lambda:0,_continuation_expected=(c.expected,c.current))
            self.assertEqual(raw['collectionDiagnostic']['stage'],'simulation')
            self.assertEqual(raw['collectionDiagnostic']['diagnosticCode'],'exit-capture-simulation')
            self.assertEqual(raw['collectionRequests'],19);self.assertEqual(raw['senderRequests'],0)
            self.assertEqual(raw['signerInvocationAttempts'],0);self.assertEqual(before,c.path.read_bytes())
            with patch.object(controlled,'EXECUTE',return_value=raw):
                public=controlled.execute(c.home,c.wallet,c.pool,expected_original_sha256=c.expected,
                    expected_current_sha256=c.current,allow_unsigned_continuation=True,
                    allow_private_key_signing=True,allow_devnet_submit=True)
            self.assertEqual(public['collectionDiagnostic'],raw['collectionDiagnostic'])
            self.assertEqual(controlled.exit_code(public),2)
            self.assertNotIn('PRIVATE',json.dumps(public));self.assertIsNone(public['preparation'])

    def test_read_only_success_reports_all_eight_phases_without_state_changes(self):
        from preserved_exit_checks import case
        with case() as c:
            before=c.path.read_bytes();r=c.observe()
            self.assertEqual(r['state'],'preserved-exit-observation-complete',r)
            t=r['collectionTiming'];self.assertEqual([p['stage'] for p in t['stages']],list(d.STAGES))
            self.assertAlmostEqual(sum(p['elapsedMs'] for p in t['stages']),t['elapsedMs'],delta=.01)
            self.assertEqual(r['networkRequests'],20);self.assertEqual(before,c.path.read_bytes())
            self.assertFalse(r['preparationPersisted']);self.assertFalse(r['privateKeyAccessed'])

    def test_read_only_success_retains_same_guards_and_no_telemetry_clock_dependency(self):
        from preserved_exit_checks import case
        with case() as c:
            before=c.path.read_bytes()
            with patch.object(d.time,'perf_counter_ns',side_effect=OSError('PRIVATE')):
                r=c.observe()
            self.assertEqual(r['state'],'preserved-exit-observation-complete',r)
            self.assertIsNone(r['collectionTiming']);self.assertEqual(r['networkRequests'],20)
            self.assertEqual(before,c.path.read_bytes());self.assertFalse(r['preparationPersisted'])
            self.assertGreater(r['observationTiming']['headroomAfterValidationMs'],0)

if __name__=='__main__':unittest.main()
