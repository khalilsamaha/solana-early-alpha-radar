"""Versioned durable exit-attempt admission and unresolved-exposure accounting."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from book import Book, validate_policy
from exit_budget_checks import policy, entry, exit_leg, run
from position_fixtures import package, registration, clock, policy as legacy_policy

HERE=Path(__file__).resolve().parent


class ExitBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'budget.positions.sqlite'
        self.b=Book(self.path,policy(),clock)
    def tearDown(self):self.b.close();self.tmp.cleanup()
    def reopen(self):self.b.close();self.b=Book(self.path,clock=clock)
    def reset(self,p):self.b.close();self.path.unlink();self.b=Book(self.path,p,clock)
    def empty(self):
        for table in ('intents','legs','positions'):
            self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)

    def test_portable_contract_no_network(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):r=run()
        self.assertEqual(r['casesPassed'],14)
        self.assertTrue(r['temporaryLedgersRemoved'])
        for k in ('executionApproved','liveSenderIntegrated','automaticRetryAllowed','roundTripFundingEstablished'):self.assertFalse(r[k])

    def test_schema_explicit_version_attempts_and_policy_immutable(self):
        for bad in (None,0,4,True,1.5,'2'):
            p=policy();p['maximumExitAttempts']=bad
            with self.assertRaises(ValueError):validate_policy(p)
        for format in ('position-book-policy-1','position-book-policy-3'):
            p=policy();p['format']=format
            with self.assertRaises(ValueError):validate_policy(p)
        p=policy();p.pop('maximumExitAttempts')
        with self.assertRaises(ValueError):validate_policy(p)
        for attempts in (1,2,3):validate_policy(policy(attempts))
        with self.assertRaisesRegex(ValueError,'immutable-policy-conflict'):Book(self.path,policy(3),clock)
        with self.assertRaisesRegex(ValueError,'immutable-policy-conflict'):Book(self.path,legacy_policy(),clock)
        self.reopen();self.assertEqual(self.b.policy['maximumExitAttempts'],2)

    def test_entry_reserves_all_attempts_not_only_expected_fee(self):
        for attempts in (1,2,3):
            self.reset(policy(attempts));s=self.b.reserve('p','entry',registration(package(),'buy'))
            self.assertEqual(s['reservedFeeLamports'],str(10000*(1+attempts)))
            self.assertEqual(s['positionExitBudgets'][0]['futureExitFeeHeldLamports'],str(10000*attempts))
            self.assertTrue(s['feeReserveCovered']);self.assertEqual(s['feesSpentLamports'],'0')

    def test_native_and_cumulative_shortfall_roll_back_every_table(self):
        p=policy();p['maximumTotalFeeLamports']='29999';self.reset(p)
        with self.assertRaisesRegex(ValueError,'cumulative-fee-limit'):self.b.reserve('p','entry',registration(package(),'buy'))
        self.empty()
        p=policy(3);p.update(maximumLegFeeLamports='4000000',maximumTotalFeeLamports='13000000');self.reset(p)
        with self.assertRaisesRegex(ValueError,'native-fee-reserve'):self.b.reserve('p','entry',registration(package(),'buy'))
        self.empty()

    def test_failure_consumes_fee_once_and_keeps_exact_remaining_exit_allowance(self):
        entry(self.b);self.assertEqual(self.b.status()['reservedFeeLamports'],'20000')
        s=exit_leg(self.b,failed=True)
        self.assertEqual((s['feesSpentLamports'],s['reservedFeeLamports']),('10000','10000'))
        self.assertEqual(s,self.b.observe('exit',package('exit',failed=True)))
        self.reopen();self.assertEqual(self.b.status(),s)
        self.assertEqual(s['positions'][0]['quantity'],'200')
        self.assertEqual(s['positions'][0]['pnl'],None)
        self.assertEqual(s['cumulativeGrossLossAtomic'],'0')
        s=exit_leg(self.b,'retry');self.assertEqual(s['reservedFeeLamports'],'0')
        self.assertEqual(s['feesSpentLamports'],'15000');self.assertEqual(s['cumulativeGrossLossAtomic'],'20')
        self.assertEqual(s['lastReconciledQuoteAtomic'],'980')

    def test_attempt_cap_blocks_another_exit_even_with_plenty_of_cash(self):
        self.reset(policy(1));entry(self.b);s=exit_leg(self.b,failed=True)
        self.assertTrue(s['positionExitBudgets'][0]['exitAttemptsExhausted'])
        self.assertTrue(s['positionExitBudgets'][0]['furtherExitRegistrationBlocked'])
        self.assertGreater(int(s['lastReconciledNativeLamports']),10000)
        self.assertEqual(s['positions'][0]['state'],'open')
        with self.assertRaisesRegex(ValueError,'exit-attempt-cap'):self.b.reserve('p','exit',registration(package('retry'),'retry'))
        self.assertEqual(self.b.exit_attempts('p'),1)
        self.assertIsNone(self.b.db.execute("SELECT 1 FROM intents WHERE id='retry'").fetchone())
        self.reopen();self.assertEqual(s,self.b.status())

    def test_all_failed_attempts_remain_open_without_inventing_a_close(self):
        entry(self.b);exit_leg(self.b,failed=True);s=exit_leg(self.b,'retry',failed=True)
        self.assertEqual(s['positions'][0]['state'],'open');self.assertEqual(s['positions'][0]['quantity'],'200')
        self.assertEqual(s['principalExposureAtomic'],'100');self.assertEqual(s['reservedFeeLamports'],'0')
        self.assertTrue(s['positionExitBudgets'][0]['exitAttemptsExhausted'])
        self.assertEqual(s['feesSpentLamports'],'15000')
        # Distinct declared intent, same already-used signature is rejected before quota reuse.
        with self.assertRaises(ValueError):self.b.reserve('p','exit',registration(package('retry'),'renamed'))
        self.assertEqual(self.b.exit_attempts('p'),2)

    def test_pending_attempt_counts_once_survives_unknown_and_reopen(self):
        entry(self.b);reg=registration(package('exit'),'exit')
        s=self.b.reserve('p','exit',reg);self.assertEqual(s,self.b.reserve('p','exit',reg))
        self.assertEqual(self.b.exit_attempts('p'),1)
        self.b.boundary('exit');s=self.b.observe('exit',package('exit',unknown=True))
        self.assertEqual(s['reservedFeeLamports'],'20000')
        self.assertEqual(s['positionExitBudgets'][0]['futureExitFeeHeldLamports'],'10000')
        self.reopen();self.assertEqual(s,self.b.status())
        with self.assertRaises(ValueError):self.b.boundary('exit')
        self.assertEqual(s,self.b.status())

    def test_process_death_after_boundary_keeps_future_exit_capacity(self):
        self.b.reserve('p','entry',registration(package(),'buy'))
        code="from book import Book;from position_fixtures import clock;import os,sys;b=Book(sys.argv[1],clock=clock);b.boundary('buy');os._exit(79)"
        r=subprocess.run([sys.executable,'-c',code,str(self.path)],cwd=HERE)
        self.assertEqual(r.returncode,79);self.reopen();s=self.b.status()
        self.assertEqual(s['positions'][0]['state'],'entry-unknown')
        self.assertEqual(s['reservedFeeLamports'],'30000')
        self.assertEqual(s['reservedQuoteAtomic'],'100')

    def test_receipt_rollback_keeps_budget_and_attempt_counts(self):
        entry(self.b);self.b.reserve('p','exit',registration(package('exit'),'exit'));self.b.boundary('exit')
        before=self.b.status()
        with patch('journal.MAX_EVENTS',1):
            with self.assertRaisesRegex(ValueError,'journal-event-cap'):self.b.observe('exit',package('exit',failed=True))
        self.assertEqual(self.b.status(),before);self.assertEqual(self.b.exit_attempts('p'),1)

    def test_quarantine_retains_unknown_principal_and_future_caps(self):
        self.b.reserve('p','entry',registration(package(),'buy'));self.b.boundary('buy')
        s=self.b.observe('buy',{'state':'finalized-success'})
        self.assertTrue(s['quarantined']);self.assertFalse(s['accountingUsable']);self.assertFalse(s['feeReserveCovered'])
        self.assertEqual(s['reservedQuoteAtomic'],'100');self.assertEqual(s['reservedFeeLamports'],'30000')
        self.reopen();self.assertEqual(s,self.b.status())
        with self.assertRaises(ValueError):self.b.reserve('p','exit',registration(package('exit'),'exit'))

    def test_two_readers_cannot_allocate_extra_exit_after_quota_used(self):
        self.reset(policy(1));entry(self.b);exit_leg(self.b,failed=True)
        other=Book(self.path,clock=clock)
        try:
            for book in (self.b,other):
                with self.assertRaisesRegex(ValueError,'exit-attempt-cap'):book.reserve('p','exit',registration(package('retry'),'retry'))
            self.assertEqual(other.exit_attempts('p'),1)
        finally:other.close()

    def test_legacy_status_shape_unchanged_and_existing_book_not_migrated(self):
        self.reset(legacy_policy());s=self.b.reserve('p','entry',registration(package(),'buy'))
        self.assertEqual(s['format'],'position-book-status-1');self.assertNotIn('maximumExitAttempts',s)
        self.assertEqual(s['reservedFeeLamports'],'20000')
        with self.assertRaisesRegex(ValueError,'immutable-policy-conflict'):Book(self.path,policy(),clock)
        self.reopen();self.assertEqual(self.b.status(),s)

    def test_cli_exclusive_private_output_and_no_live_options(self):
        cli=HERE/'exit_budget_cli.py'
        out=Path(self.tmp.name)/'check.gz';cmd=[sys.executable,'-E','-s',str(cli),'--output',str(out)]
        r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
        before=out.read_bytes();report=json.loads(gzip.decompress(before))
        self.assertEqual(report['casesPassed'],14);self.assertEqual(out.stat().st_mode&0o777,0o600)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),before)
        for arg in ('--directory','--allow-devnet-submit','--simulate-devnet','--execute'):
            target=Path(self.tmp.name)/'absent.gz'
            r=subprocess.run([sys.executable,str(cli),'--output',str(target),arg],capture_output=True)
            self.assertNotEqual(r.returncode,0);self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
