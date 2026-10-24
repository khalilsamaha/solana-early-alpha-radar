"""Real orchestration, disposable signers and synthetic RPC; no funded wallet access."""
import copy
import json
import os
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
import spend_guard as guard
import swap_submission as submit
import test_swap_submission as forward
import test_reverse_swap as reverse
import test_controlled_swap as setup


class EntrySpendingCase(unittest.TestCase):
    setUpClass = classmethod(setup.ControlledSwapCase.setUpClass.__func__)
    tearDownClass = classmethod(setup.ControlledSwapCase.tearDownClass.__func__)
    setUp = setup.ControlledSwapCase.setUp
    tearDown = setup.ControlledSwapCase.tearDown
    prepare = forward.SwapSubmissionCase.prepare

    def start(self, **kw):
        self.prepare(); t = forward.Transport(self.home, **kw)
        return submit.execute(self.home, self.wallet, self.pool, opener=t, sleeper=lambda _:None), t

    def summary(self):
        with guard.Guard(self.home) as g: return g.summary()

    def test_reservation_precedes_signer_and_boundary_precedes_send(self):
        self.prepare(); t = forward.Transport(self.home)
        signer = setup.swap.invoke_signer; original_open = t.open
        def signing(*args, **kw):
            s = self.summary()
            self.assertEqual(s['heldEntryPrincipalAtomic'],'1000')
            self.assertEqual(s['reservedFeeLamports'],'20000')
            self.assertFalse(s['legs']['entry']['signedIdentityBound'])
            return signer(*args, **kw)
        def opening(req, timeout=None):
            q=json.loads(req.data)
            if q['method']=='sendTransaction':
                s=self.summary(); self.assertIsNotNone(s['legs']['entry']['boundaryAtMs'])
                self.assertEqual(s['confirmedFeeLamports'],'0')
            return original_open(req,timeout)
        t.open=opening
        with patch.object(setup.swap,'invoke_signer',side_effect=signing):
            r=submit.execute(self.home,self.wallet,self.pool,opener=t,sleeper=lambda _:None)
        s=r['spendingGuard']; self.assertTrue(s['pretradeBudgetEnforced'])
        self.assertEqual(s['state'],'open'); self.assertEqual(s['confirmedFeeLamports'],'5000')
        self.assertEqual(s['reservedFeeLamports'],'10000'); self.assertEqual(s['lastReconciledAcquiredAtomic'],'990')

    def test_insufficient_roundtrip_fee_reserve_blocks_before_signing(self):
        self.prepare(); t=forward.Transport(self.home)
        t.rows[self.wallet]['lamports']=15000
        with patch.object(setup.swap,'invoke_signer',side_effect=AssertionError('must not sign')):
            r=submit.execute(self.home,self.wallet,self.pool,opener=t,sleeper=lambda _:None)
        self.assertFalse((self.home/submit.CHILD/'signed.json').exists())
        self.assertFalse(any(q['method']=='sendTransaction' for q in t.calls))
        self.assertEqual(r['state'],'preparation-incomplete')

    def test_unknown_then_recovery_keeps_and_reconciles_once(self):
        r,t=self.start(pending=True); s=r['spendingGuard']
        self.assertEqual(s['heldEntryPrincipalAtomic'],'1000'); self.assertEqual(s['reservedFeeLamports'],'20000')
        t.change=lambda q,v:2001 if q['method']=='getBlockHeight' else v; t.calls.clear()
        r=submit.recover(self.home,self.wallet,opener=t,sleeper=lambda _:None)
        self.assertEqual(r['state'],'expired-outcome-unknown'); self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000')
        t.change=None;t.pending=False;t.calls.clear()
        r=submit.recover(self.home,self.wallet,opener=t,sleeper=lambda _:None)
        n=r['spendingGuard']['eventCount']; self.assertEqual(r['spendingGuard']['confirmedFeeLamports'],'5000')
        again=submit.recover(self.home,self.wallet,opener=t)
        self.assertEqual(again['spendingGuard']['eventCount'],n)
        self.assertFalse(any(q['method']=='sendTransaction' for q in t.calls))

    def test_actual_process_death_after_budget_commit_preserves_boundary(self):
        self.prepare()
        code = """
import os,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
import test_swap_submission as fixture
import swap_submission as s
from pool_fixtures import BASE
home=Path(sys.argv[2]); wallet=sys.argv[3]; pool=sys.argv[4]
original=s.write_new
baseline=dict(BASE,network='devnet',kind='observed-devnet-deployment',observedAtMs=0)
def killed(path,value):
    if path.name=='submission-boundary.json':os._exit(77)
    original(path,value)
with patch('preflight.BASELINE',baseline),patch('preflight_capture.BASELINE',baseline),patch.object(s,'write_new',side_effect=killed):
    s.execute(home,wallet,pool,opener=fixture.Transport(home),sleeper=lambda _:None)
"""
        run=subprocess.run([sys.executable,'-c',code,str(Path(__file__).parent),str(self.home),self.wallet,self.pool],capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,77,run.stderr)
        self.assertIsNotNone(self.summary()['legs']['entry']['boundaryAtMs'])
        self.assertEqual(self.summary()['reservedFeeLamports'],'20000')
        t=forward.Transport(self.home)
        submit.execute(self.home,self.wallet,self.pool,opener=t)
        submit.recover(self.home,self.wallet,opener=t)
        self.assertEqual(t.calls,[])

    def test_event_cap_rolls_back_settlement_and_recovery_can_finish(self):
        r,t=self.start(pending=True); before=self.summary();t.pending=False
        with patch.object(guard,'MAX_EVENTS',before['eventCount']),self.assertRaisesRegex(ValueError,'event-cap'):
            submit.recover(self.home,self.wallet,opener=t,sleeper=lambda _:None)
        self.assertEqual(self.summary(),before)
        r=submit.recover(self.home,self.wallet,opener=t)
        self.assertEqual(r['spendingGuard']['confirmedFeeLamports'],'5000')

    def test_entry_failure_only_consumes_confirmed_fee(self):
        r,_=self.start(failure=True);s=r['spendingGuard']
        self.assertEqual(s['state'],'entry-failed');self.assertEqual(s['heldEntryPrincipalAtomic'],'0')
        self.assertEqual(s['reservedFeeLamports'],'0');self.assertEqual(s['confirmedFeeLamports'],'5000')
        self.assertEqual(s['lastReconciledAcquiredAtomic'],'0')

    def test_crash_after_reservation_before_marker_keeps_hold(self):
        self.prepare();t=forward.Transport(self.home);write=submit.write_new
        def crash(path,value):
            if path.name==guard.MARKER: raise KeyboardInterrupt('power loss')
            write(path,value)
        with patch.object(submit,'write_new',side_effect=crash), self.assertRaises(KeyboardInterrupt):
            submit.execute(self.home,self.wallet,self.pool,opener=t,sleeper=lambda _:None)
        r=submit.status(self.home,self.wallet)
        self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000')
        self.assertFalse(r['spendingGuard']['reservationMarkerPresent'])
        t.calls.clear();submit.execute(self.home,self.wallet,self.pool,opener=t)
        self.assertEqual(t.calls,[])

    def test_crash_after_guard_boundary_before_file_never_retries(self):
        self.prepare();t=forward.Transport(self.home);write=submit.write_new
        def crash(path,value):
            if path.name=='submission-boundary.json':raise KeyboardInterrupt('power loss')
            write(path,value)
        with patch.object(submit,'write_new',side_effect=crash),self.assertRaises(KeyboardInterrupt):
            submit.execute(self.home,self.wallet,self.pool,opener=t,sleeper=lambda _:None)
        self.assertIsNotNone(self.summary()['legs']['entry']['boundaryAtMs'])
        self.assertFalse((self.home/submit.CHILD/'submission-boundary.json').exists())
        t.calls.clear();r=submit.recover(self.home,self.wallet,opener=t,sleeper=lambda _:None)
        self.assertEqual(t.calls,[]);self.assertEqual(r['spendingGuard']['heldEntryPrincipalAtomic'],'1000')

    def test_final_receipt_before_accounting_crash_reconciles_on_recovery(self):
        self.prepare();t=forward.Transport(self.home)
        with patch.object(guard.Guard,'reconcile',side_effect=KeyboardInterrupt('power loss')), self.assertRaises(KeyboardInterrupt):
            submit.execute(self.home,self.wallet,self.pool,opener=t,sleeper=lambda _:None)
        self.assertEqual(self.summary()['reservedFeeLamports'],'20000')
        t.calls.clear(); r=submit.recover(self.home,self.wallet,opener=t)
        self.assertEqual(t.calls,[]);self.assertEqual(r['spendingGuard']['confirmedFeeLamports'],'5000')

    def test_lost_signer_ack_keeps_reservation_without_resigning(self):
        self.prepare();t=forward.Transport(self.home);signer=setup.swap.invoke_signer
        def lost(*a,**kw):signer(*a,**kw);raise OSError('lost ack')
        with patch.object(setup.swap,'invoke_signer',side_effect=lost):r=submit.execute(self.home,self.wallet,self.pool,opener=t)
        self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000')
        self.assertFalse(r['spendingGuard']['legs']['entry']['signedIdentityBound'])
        t.calls.clear();submit.recover(self.home,self.wallet,opener=t);self.assertEqual(t.calls,[])

    def test_quarantine_retains_unresolved_reservations(self):
        def change(q,v):
            if q['method']=='getTransaction' and v:v['meta']['postBalances'][1]+=1
            return v
        r,_=self.start(change=change);s=r['spendingGuard']
        self.assertEqual(s['state'],'quarantined');self.assertFalse(s['accountingUsable'])
        self.assertEqual(s['heldEntryPrincipalAtomic'],'1000');self.assertEqual(s['reservedFeeLamports'],'20000')

    def test_budget_store_missing_or_marker_removed_fails_closed(self):
        r,_=self.start();path=self.home/guard.NAME; saved=path.read_bytes();path.unlink()
        with self.assertRaises(ValueError):submit.recover(self.home,self.wallet)
        path.write_bytes(saved);path.chmod(0o600)
        (self.home/submit.CHILD/guard.MARKER).unlink()
        with self.assertRaisesRegex(ValueError,'marker-missing'):submit.status(self.home,self.wallet)

    def test_budget_event_corruption_refused(self):
        self.start()
        with sqlite3.connect(self.home/guard.NAME) as db:db.execute("UPDATE spending_events SET event_hash='invalid' WHERE seq=1")
        with self.assertRaisesRegex(ValueError,'integrity'):submit.status(self.home,self.wallet)

    def test_legacy_completed_receipt_not_relabelled_as_budgeted(self):
        self.start();child=self.home/submit.CHILD
        (child/guard.MARKER).unlink();(self.home/guard.NAME).unlink()
        p=child/'execution.json';v=json.loads(p.read_text());v.pop('spendingGuardVersion');p.write_text(json.dumps(v))
        r=submit.status(self.home,self.wallet)
        self.assertEqual(r['state'],'finalized-success');self.assertFalse(r['spendingGuard']['pretradeBudgetEnforced'])


class ExitSpendingCase(unittest.TestCase):
    setUpClass=classmethod(reverse.ReverseCase.setUpClass.__func__)
    tearDownClass=classmethod(reverse.ReverseCase.tearDownClass.__func__)
    setUp=reverse.ReverseCase.setUp
    tearDown=reverse.ReverseCase.tearDown
    run_exit=reverse.ReverseCase.run_exit

    def test_round_trip_budget_and_background_inventory(self):
        r,t=self.run_exit();s=r['spendingGuard']
        self.assertEqual(s['state'],'closed');self.assertEqual(s['confirmedFeeLamports'],'10000')
        self.assertEqual(s['reservedFeeLamports'],'0');self.assertEqual(s['lastReconciledAcquiredAtomic'],'0')
        with guard.Guard(self.home) as g:
            state=g.read()[0];self.assertEqual(state['legs']['entry']['contract']['destinationBeforeAtomic'],'500000000')
        self.assertEqual(r['roundTrip']['exitInputAtomic'],'998')

    def test_failed_exit_keeps_position_without_automatic_replacement(self):
        r,t=self.run_exit(failure=True);s=r['spendingGuard']
        self.assertEqual(s['state'],'exit-failed-position-open');self.assertEqual(s['lastReconciledAcquiredAtomic'],'998')
        self.assertEqual(s['confirmedFeeLamports'],'10000');t.calls.clear()
        submit.execute_reverse(self.home,self.wallet,self.pool,opener=t);self.assertEqual(t.calls,[])

    def test_unknown_exit_keeps_exact_acquisition_and_fee_reserve(self):
        r,t=self.run_exit(pending=True);s=r['spendingGuard']
        self.assertEqual(s['state'],'exit-unresolved');self.assertEqual(s['lastReconciledAcquiredAtomic'],'998')
        self.assertEqual(s['reservedFeeLamports'],'10000');self.assertEqual(s['confirmedFeeLamports'],'5000')
        t.pending=False;t.calls.clear();r=submit.recover(self.home,self.wallet,opener=t,sleeper=lambda _:None,reverse=True)
        self.assertEqual(r['spendingGuard']['state'],'closed');self.assertFalse(any(q['method']=='sendTransaction' for q in t.calls))

    def test_legacy_entry_cannot_gain_retroactive_exit_budget(self):
        child=self.home/submit.CHILD;(child/guard.MARKER).unlink();(self.home/guard.NAME).unlink()
        p=child/'execution.json';v=json.loads(p.read_text());v.pop('spendingGuardVersion');p.write_text(json.dumps(v))
        t=reverse.ReverseTransport(self.home)
        with self.assertRaises(ValueError):submit.execute_reverse(self.home,self.wallet,self.pool,opener=t)
        self.assertEqual(t.calls,[]);self.assertFalse((self.home/submit.REVERSE_CHILD).exists())

    def test_two_connections_cannot_reserve_another_entry(self):
        child=self.home/submit.CHILD;plan=submit.read(child,'plan.json');capture=submit.read(child,'preflight.json',4*1024*1024)
        with guard.Guard(self.home) as a,guard.Guard(self.home) as b:
            before=a.summary()
            b.j.clock=lambda:a.read()[3]
            with self.assertRaisesRegex(ValueError,'attempt-already-reserved'):b.reserve('entry',plan,capture)
            self.assertEqual(a.summary(),before)

if __name__=='__main__':unittest.main()
