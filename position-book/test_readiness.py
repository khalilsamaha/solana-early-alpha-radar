"""Closed synthetic signed journals, unresolved evidence and immutable inspection."""
import copy
import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
import readiness as r
import test_cycles as fixture
from test_cycle_execution import s,binding,BASE


class ReadinessCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.TwoCycleCase.setUpClass.__func__(cls)
        baseline=dict(copy.deepcopy(BASE),network='devnet',kind='observed-devnet-deployment',observedAtMs=0)
        with patch('preflight.BASELINE',baseline),patch('preflight_capture.BASELINE',baseline):
            r.cycles.sync(cls.template,cls.wallet,cls.pool)
    tearDownClass=classmethod(fixture.TwoCycleCase.tearDownClass.__func__)
    setUp=fixture.TwoCycleCase.setUp
    tearDown=fixture.TwoCycleCase.tearDown
    def inspect(self):return r.inspect(self.home,self.wallet,self.pool)
    def files(self):return {str(p.relative_to(self.home)):p.read_bytes() for p in self.home.rglob('*') if p.is_file()}

    def test_closed_consistent_without_keys_rpc_or_source_changes(self):
        before=self.files()
        with patch('core.signer',side_effect=AssertionError('sign')),patch('urllib.request.urlopen',side_effect=AssertionError('network')):
            v=self.inspect()
        self.assertEqual(v['state'],'closed-evidence-consistent');self.assertEqual(v['blockingReasons'],[])
        self.assertEqual(v['unresolvedLegs'],0);self.assertEqual(before,self.files())
        self.assertFalse(v['tradingReady']);self.assertFalse(v['nextCycleAuthorized'])
        self.assertTrue(v['databaseConnectionsReadOnly']);self.assertEqual(v['strategyReadiness'],'not-assessed')

    def test_repeat_inspection_does_not_append_accounting(self):
        before=self.files();a=self.inspect();b=self.inspect()
        self.assertEqual(a,b);self.assertEqual(b['components']['historicalAccounting']['eventCount'],1)
        self.assertEqual(before,self.files())

    def test_stop_reported_not_cleared_and_not_execution_approval(self):
        (self.home/'STOP').touch(mode=0o600);before=self.files();v=self.inspect()
        self.assertEqual(v['state'],'review-required');self.assertTrue(v['stopRequested'])
        self.assertIn('stop-marker-present',v['blockingReasons']);self.assertEqual(before,self.files())

    def test_missing_book_recommends_sync_without_creating_it(self):
        p=self.home/r.cycles.NAME;p.unlink();before=self.files();v=self.inspect()
        self.assertEqual(v['components']['historicalAccounting']['state'],'missing')
        self.assertIn({'action':'run-historical-accounting-sync'},v['nextActions'])
        self.assertFalse(p.exists());self.assertEqual(before,self.files())

    def test_corrupt_book_remains_unchanged_and_reports_invalid(self):
        p=self.home/r.cycles.NAME;p.write_bytes(b'not a database');before=self.files();v=self.inspect()
        self.assertEqual(v['components']['historicalAccounting']['state'],'unavailable-or-invalid')
        self.assertEqual(before,self.files())

    def test_quarantined_book_never_reported_ready(self):
        book=r.cycles.Ledger(self.home,create=False)
        try:book.apply(source_error=True)
        finally:book.close()
        before=self.files();v=self.inspect()
        self.assertEqual(v['components']['historicalAccounting']['state'],'quarantined')
        self.assertEqual(before,self.files())

    def test_lost_receipt_does_not_mutate_book_into_quarantine(self):
        (self.home/binding.CYCLE/s.REVERSE_CHILD/'receipt-evidence.json').unlink()
        before=self.files();v=self.inspect()
        self.assertEqual(v['state'],'review-required');self.assertGreater(v['unresolvedLegs'],0)
        self.assertEqual(before,self.files())

    def test_submission_unknown_directs_only_read_only_recovery(self):
        child=self.home/binding.CYCLE/s.REVERSE_CHILD
        for p in child.glob('observation-*.json'):p.unlink()
        (child/'receipt-evidence.json').unlink();before=self.files();v=self.inspect()
        key=binding.CYCLE+'/exit'
        self.assertEqual(v['components'][key]['state'],'submission-unknown')
        self.assertTrue(v['components'][key]['requiresReadOnlyRecovery'])
        self.assertIn(dict(action='read-only-recovery',cycle=binding.CYCLE,leg='exit'),v['nextActions'])
        self.assertFalse(v['executionApproved']);self.assertEqual(before,self.files())

    def test_damaged_archive_is_visible_and_never_repaired(self):
        p=self.home/binding.CYCLE/'refused-unsigned-entry-v1'/'failure.json';p.write_bytes(p.read_bytes()+b' ')
        before=self.files();v=self.inspect();self.assertEqual(v['state'],'review-required');self.assertEqual(before,self.files())

    def test_spending_sidecar_refused_without_recovery(self):
        p=self.home/binding.CYCLE/(s.spend_guard.NAME+'-journal');p.write_bytes(b'keep');p.chmod(0o600)
        before=self.files();v=self.inspect()
        self.assertEqual(v['components']['spending']['state'],'unavailable-or-invalid');self.assertEqual(before,self.files())

    def test_accounting_sidecar_refused_without_deletion(self):
        p=self.home/(r.cycles.NAME+'-journal');p.write_bytes(b'keep');p.chmod(0o600)
        before=self.files();v=self.inspect()
        self.assertEqual(v['components']['historicalAccounting']['state'],'unavailable-or-invalid');self.assertEqual(before,self.files())

    def test_lock_contention_stops_before_inspection(self):
        with r.cycles.c.source_lock(self.home,self.wallet):
            with self.assertRaises(BlockingIOError):self.inspect()

    def test_report_excludes_signatures_balances_and_raw_errors(self):
        text=json.dumps(self.inspect())
        for child in (self.home/s.CHILD,self.home/binding.CYCLE/s.REVERSE_CHILD):
            signed=json.loads((child/'signed.json').read_text());self.assertNotIn(signed['wire'],text)
            report=s.report(child.parent,self.wallet,reverse=child.name==s.REVERSE_CHILD)
            self.assertNotIn(report['signature'],text)
        self.assertNotIn(self.wallet,text);self.assertNotIn(self.pool,text)

    def test_wrong_wallet_refused_and_wrong_pool_is_not_ready(self):
        from pool_fixtures import fake_key
        before=self.files()
        with self.assertRaises(ValueError):r.inspect(self.home,fake_key('wrong-wallet'),self.pool)
        v=r.inspect(self.home,self.wallet,fake_key('wrong-pool'))
        self.assertEqual(v['state'],'review-required');self.assertEqual(before,self.files())

    def test_standalone_cli_report_and_output_scope(self):
        cli=Path(__file__).with_name('readiness_cli.py');out=Path(self.tmp.name)/'readiness.json.gz'
        args=[sys.executable,'-E','-s',str(cli),'--action','inspect','--directory',str(self.home),'--wallet',self.wallet,'--pool',self.pool]
        before=self.files();result=subprocess.run(args+['--output',str(out)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        with gzip.open(out,'rt') as f:self.assertEqual(json.load(f)['state'],'closed-evidence-consistent')
        bad=self.home/'forbidden-report.json.gz'
        result=subprocess.run(args+['--output',str(bad)],capture_output=True,text=True,timeout=30)
        self.assertNotEqual(result.returncode,0);self.assertFalse(bad.exists());self.assertEqual(before,self.files())

    def test_signed_but_unresolved_and_failed_leg_classification(self):
        for state,unknown,boundary in [('signed-simulated-not-submitted',False,False),('preparation-incomplete',True,False),('submission-unknown',False,True)]:
            v=r.leg_view(dict(state=state,signatureOutcomeUnknown=unknown,submissionBoundaryRecorded=boundary))
            self.assertTrue(v['unresolved']);self.assertTrue(v['requiresReadOnlyRecovery'])
        v=r.leg_view(dict(state='finalized-failure',signatureOutcomeUnknown=False,submissionBoundaryRecorded=True))
        self.assertFalse(v['unresolved']);self.assertTrue(v['receiptFinalized'])


if __name__=='__main__':unittest.main()
