import copy
import gzip
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from book import Book
from position_fixtures import package, registration, policy, clock
from position_checks import run

HERE=Path(__file__).resolve().parent


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.positions.sqlite'
        self.b=Book(self.path,policy(),clock)
    def tearDown(self):
        self.b.close();self.temp.cleanup()
    def entry(self):
        self.b.reserve('p','entry',registration(package(),'buy'));self.b.boundary('buy')
        return self.b.observe('buy',package())
    def exit(self, failed=False):
        self.b.reserve('p','exit',registration(package('exit'),'sell'));self.b.boundary('sell')
        return self.b.observe('sell',package('exit',failed=failed))
    def reopen(self):
        self.b.close();self.b=Book(self.path,clock=clock)

    def test_selfcheck_offline(self):
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            r=run()
        self.assertEqual(r['casesPassed'],10);self.assertEqual(r['networkRequests'],0)
    def test_fee_only_entry_failure_releases_reservation(self):
        self.b.reserve('p','entry',registration(package(),'buy'));self.b.boundary('buy')
        r=self.b.observe('buy',package(failed=True))
        self.assertEqual(r['lastReconciledQuoteAtomic'],'1000');self.assertEqual(r['lastReconciledNativeLamports'],'9995000')
        self.assertEqual(r['reservedFeeLamports'],'0');self.assertEqual(r['principalExposureAtomic'],'0')
    def test_full_roundtrip(self):
        r=self.entry();self.assertEqual(r['reservedFeeLamports'],'10000')
        r=self.exit();self.assertEqual(r['lastReconciledQuoteAtomic'],'980')
        self.assertEqual(r['feesSpentLamports'],'10000');self.assertEqual(r['cumulativeGrossLossAtomic'],'20')
        self.assertEqual(r['positions'][0]['pnl'],'-20');self.assertEqual(r['principalExposureAtomic'],'0')
    def test_unknowns_not_free_cash_or_failed(self):
        self.b.reserve('p','entry',registration(package(),'buy'));self.b.boundary('buy')
        r=self.b.observe('buy',package(unknown=True));self.reopen()
        self.assertEqual(r,self.b.status('p'));self.assertEqual(r['reservedQuoteAtomic'],'100')
        with self.assertRaises(ValueError):self.b.boundary('buy')
        self.b.observe('buy',package());self.b.reserve('p','exit',registration(package('exit'),'sell'));self.b.boundary('sell')
        r=self.b.observe('sell',package('exit',unknown=True));self.reopen()
        self.assertEqual(r,self.b.status('p'));self.assertEqual(r['principalExposureAtomic'],'100')
        with self.assertRaises(ValueError):self.b.reserve('p','exit',registration(package('retry'),'retry'))
    def test_duplicate_register_and_receipt_no_counter_reset(self):
        self.entry();self.b.reserve('p','entry',registration(package(),'buy'))
        before=self.b.status();count=self.b.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        self.b.observe('buy',package());self.assertEqual(before,self.b.status())
        self.assertEqual(count,self.b.db.execute('SELECT COUNT(*) FROM events').fetchone()[0])
        self.exit();before=self.b.status();self.b.observe('buy',package());self.assertEqual(before,self.b.status())
    def test_changed_capture_context_same_final_outcome(self):
        self.entry();p=package();p['bundle']['capturedAtMs']+=100
        p['bundle']['rpcEvidence']['signatureStatus']['result']['context']['slot']+=20
        before=self.b.status();self.b.observe('buy',p);self.assertEqual(before,self.b.status())
    def test_unknown_cannot_erase_final(self):
        self.entry();before=self.b.status();self.b.observe('buy',package(unknown=True));self.assertEqual(before,self.b.status())
    def test_conflicting_final_quarantine_sticky(self):
        self.entry();r=self.b.observe('buy',package(failed=True));self.assertTrue(r['quarantined'])
        self.reopen();self.b.observe('buy',package());self.assertTrue(self.b.status()['quarantined'])
        with self.assertRaises(ValueError):self.b.reserve('p','exit',registration(package('exit'),'sell'))
    def test_forged_summary_cannot_advance(self):
        self.b.reserve('p','entry',registration(package(),'buy'));self.b.boundary('buy')
        r=self.b.observe('buy',{'state':'signed-token-accounting-consistent','tokenAccounts':{}})
        self.assertTrue(r['quarantined']);self.assertEqual(r['lastReconciledQuoteAtomic'],'1000')
    def test_mutated_wire_or_intent_quarantines(self):
        for kind in ('wire','intent'):
            with tempfile.TemporaryDirectory() as d:
                b=Book(Path(d)/'x.positions.sqlite',policy(),clock)
                b.reserve('p','entry',registration(package(),'buy'));b.boundary('buy');p=package()
                if kind=='wire':p['signedTransactionBase64']='AAAA'
                else:p['bundle']['intent']['inputAtomic']='99'
                self.assertTrue(b.observe('buy',p)['quarantined']);b.close()
    def test_exit_slot_must_follow_entry(self):
        self.entry();self.b.reserve('p','exit',registration(package('exit'),'sell'));self.b.boundary('sell')
        p=package('exit');p['bundle']['rpcEvidence']['transaction']['result']['slot']=100
        p['bundle']['rpcEvidence']['signatureStatus']['result']['value'][0]['slot']=100
        self.assertTrue(self.b.observe('sell',p)['quarantined'])
    def test_stop_survives_reopen_allows_exit(self):
        self.entry();self.b.stop_entries();self.reopen();self.assertTrue(self.b.status()['entriesStopped'])
        self.assertEqual(self.exit()['positions'][0]['state'],'closed')
    def test_stop_blocks_prepared_entry_boundary(self):
        self.b.reserve('p','entry',registration(package(),'buy'));self.b.stop_entries()
        with self.assertRaisesRegex(ValueError,'entries-stopped'):self.b.boundary('buy')
        self.assertEqual(self.b.status()['reservedQuoteAtomic'],'100')
    def test_stale_boundary_rolls_back_and_keeps_reservation(self):
        self.b.reserve('p','entry',registration(package(),'buy'))
        self.b.j.clock=lambda:clock()+6000
        with self.assertRaisesRegex(ValueError,'stale-intent'):self.b.boundary('buy')
        self.assertEqual(self.b.j.row('buy')['state'],'prepared')
    def test_clock_regression_rejected(self):
        self.entry();self.b.j.clock=lambda:clock()-1
        with self.assertRaisesRegex(ValueError,'local-clock-regressed'):self.b.reserve('p','exit',registration(package('exit'),'sell'))
    def test_immutable_policy_and_wrong_book(self):
        p=policy();p['maximumPrincipalAtomic']='99'
        with self.assertRaises(ValueError):Book(self.path,p,clock)
        from journal import Journal
        other=Path(self.temp.name)/'other.positions.sqlite';j=Journal(other);j.close()
        with self.assertRaises(sqlite3.OperationalError):Book(other,policy(),clock)
    def test_failed_reservation_rolls_back_intent_and_position(self):
        p=package();p['bundle']['intent']['inputAtomic']='101'
        with self.assertRaisesRegex(ValueError,'principal-limit'):self.b.reserve('p','entry',registration(p,'buy'))
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM intents').fetchone()[0],0)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM positions').fetchone()[0],0)
    def test_source_and_native_continuity(self):
        self.entry()
        for field in ('native','quote','quantity','asset'):
            p=package('exit');i=p['bundle']['intent']
            if field=='native':i['walletPreLamports']='9995001'
            if field=='quote':i['destination']['preAmountAtomic']='899'
            if field=='quantity':i['inputAtomic']='199'
            if field=='asset':i['source']['decimals']=5
            with self.assertRaises(ValueError):self.b.reserve('p','exit',registration(p,'sell'))
        self.assertEqual(self.b.status('p')['positions'][0]['state'],'open')
    def test_rent_and_unknown_lifecycles_rejected(self):
        for kind in ('rent','lifecycle','mainnet'):
            p=package();i=p['bundle']['intent']
            if kind=='rent':i['maximumRentLamports']='1'
            elif kind=='lifecycle':i['destination']['lifecycle']='create'
            else:i['network']='mainnet-beta'
            with self.assertRaises(ValueError):self.b.reserve('p','entry',registration(p,'buy'))
    def test_fee_budget_reserves_entry_and_exit(self):
        self.b.close();self.path.unlink();p=policy();p['maximumTotalFeeLamports']='19999';self.b=Book(self.path,p,clock)
        with self.assertRaisesRegex(ValueError,'cumulative-fee-limit'):self.b.reserve('p','entry',registration(package(),'buy'))
    def test_failed_exit_fee_cap_does_not_reset(self):
        self.b.close();self.path.unlink();p=policy();p['maximumTotalFeeLamports']='20000';self.b=Book(self.path,p,clock)
        self.entry();self.exit(failed=True)
        self.b.reserve('p','exit',registration(package('retry'),'retry'));self.b.boundary('retry')
        r=self.b.observe('retry',package('retry',failed=True));self.assertEqual(r['feesSpentLamports'],'15000')
        p=package('exit');p['bundle']['intent']['walletPreLamports']='9985000'
        # An already used signed identity cannot be relabelled for another attempt.
        with self.assertRaises(ValueError):self.b.reserve('p','exit',registration(p,'retry2'))
    def test_loss_limit_persists(self):
        self.entry();self.exit(failed=True)
        self.b.reserve('p','exit',registration(package('retry'),'retry'));self.b.boundary('retry');self.b.observe('retry',package('retry'))
        self.reopen()
        with self.assertRaisesRegex(ValueError,'gross-loss-limit'):self.b.reserve('p2','entry',registration(package('entry2'),'buy2'))
    def test_signature_reuse_and_active_position_limit(self):
        self.entry()
        with self.assertRaises(ValueError):self.b.reserve('other','entry',registration(package(),'buy2'))
        p=package('entry2');p['bundle']['intent']['walletPreLamports']='9995000'
        with self.assertRaisesRegex(ValueError,'active-position-limit'):self.b.reserve('other','entry',registration(p,'buy2'))
    def test_file_security(self):
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        other=Path(self.temp.name)/'link.positions.sqlite';os.link(self.path,other)
        with self.assertRaises(ValueError):Book(other,clock=clock)
        other.unlink();other.symlink_to(self.path)
        with self.assertRaises(ValueError):Book(other,clock=clock)
    def test_event_cap_rollback_does_not_partially_apply_receipt(self):
        self.b.reserve('p','entry',registration(package(),'buy'));self.b.boundary('buy');before=self.b.status()
        with patch('journal.MAX_EVENTS',2):
            with self.assertRaisesRegex(ValueError,'journal-event-cap'):self.b.observe('buy',package())
        self.assertEqual(before,self.b.status())
    def test_two_connections_cannot_reserve_twice(self):
        other=Book(self.path,clock=clock)
        self.b.reserve('p','entry',registration(package(),'buy'))
        p=package('entry2');p['bundle']['intent']['walletPreLamports']='10000000'
        try:
            with self.assertRaisesRegex(ValueError,'active-position-limit'):other.reserve('p2','entry',registration(p,'buy2'))
            self.assertEqual(other.db.execute('SELECT COUNT(*) FROM intents').fetchone()[0],1)
        finally:other.close()
    def test_process_death_before_commit_rolls_back_boundary(self):
        self.b.reserve('p','entry',registration(package(),'buy'))
        code="from book import Book;from position_fixtures import clock;import os,sys;b=Book(sys.argv[1],clock=clock);b.db.execute('BEGIN IMMEDIATE');b.boundary('buy');os._exit(79)"
        r=subprocess.run([sys.executable,'-c',code,str(self.path)],cwd=HERE)
        self.assertEqual(r.returncode,79);self.reopen();self.assertEqual(self.b.status('p')['positions'][0]['state'],'entry-prepared')
    def test_process_death_after_commit_recovery_never_resends(self):
        self.b.reserve('p','entry',registration(package(),'buy'))
        code="from book import Book;from position_fixtures import clock;import os,sys;b=Book(sys.argv[1],clock=clock);b.boundary('buy');os._exit(79)"
        r=subprocess.run([sys.executable,'-c',code,str(self.path)],cwd=HERE)
        self.assertEqual(r.returncode,79);self.reopen()
        self.assertEqual(self.b.status('p')['positions'][0]['state'],'entry-unknown')
        with self.assertRaises(ValueError):self.b.boundary('buy')
        self.assertEqual(self.b.observe('buy',package())['positions'][0]['state'],'open')
    def test_failed_exit_cannot_replay_an_earlier_slot(self):
        self.entry();self.exit(failed=True)
        self.b.reserve('p','exit',registration(package('retry'),'retry'));self.b.boundary('retry')
        p=package('retry');p['bundle']['rpcEvidence']['transaction']['result']['slot']=119
        p['bundle']['rpcEvidence']['signatureStatus']['result']['value'][0]['slot']=119
        self.assertTrue(self.b.observe('retry',p)['quarantined'])
    def test_fee_capacity_after_failed_exit_is_explicit_and_enforced(self):
        self.b.close();self.path.unlink();p=policy();p['maximumTotalFeeLamports']='20000';self.b=Book(self.path,p,clock)
        self.entry();self.exit(failed=True)
        self.b.reserve('p','exit',registration(package('retry'),'retry'));self.b.boundary('retry')
        r=self.b.observe('retry',package('retry',failed=True))
        self.assertFalse(r['feeReserveCovered']);self.assertEqual(r['feeBudgetRemainingLamports'],'5000')
        p=package('entry2');i=copy.deepcopy(package('retry')['bundle']['intent'])
        i['signature']=p['bundle']['intent']['signature'];i['messageSha256']=p['bundle']['intent']['messageSha256']
        i['walletPreLamports']='9985000';p['bundle']['intent']=i
        with self.assertRaisesRegex(ValueError,'cumulative-fee-limit'):self.b.reserve('p','exit',registration(p,'retry2'))
        self.assertEqual(self.b.status('p')['positions'][0]['state'],'open')
    def test_observation_requires_prior_boundary(self):
        self.b.reserve('p','entry',registration(package(),'buy'))
        with self.assertRaisesRegex(ValueError,'boundary-required'):self.b.observe('buy',package())

    def test_cli_private_report_no_overwrite(self):
        out=Path(self.temp.name)/'report.json.gz'
        args=[sys.executable,str(HERE/'cli.py'),'--output',str(out)]
        self.assertEqual(subprocess.run(args,capture_output=True).returncode,0)
        self.assertEqual(out.stat().st_mode&0o777,0o600)
        before=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(before))['casesPassed'],10)
        self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0);self.assertEqual(before,out.read_bytes())


if __name__=='__main__':unittest.main()
