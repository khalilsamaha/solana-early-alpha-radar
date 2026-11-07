"""Retired-exit review cannot grant an execution or spending capability."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import retired_exit_replan as m
from exit_submission_checks import signed_case
from test_expired_exit_evidence import fixture,Replies
from test_signed_exit_timing import files


class ReplanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager=signed_case();cls.c=cls.manager.__enter__();cls.c.now+=30000
        cls.ctx=fixture(cls.c);cls.expected=cls.c.exit_state['request']['preparationSha256']
        r=m.retirement.retire(cls.c.home,cls.c.wallet,cls.c.pool,cls.expected,
            allow_retire=True,opener=Replies(cls.c,cls.ctx),clock=lambda:cls.c.now,monotonic=lambda:0)
        if r['state']!='exit-retired-held':raise AssertionError(r)
        cls.retired=r['retirementSha256'];cls.saved=files(cls.c);cls.stamp=cls.c.now
    @classmethod
    def tearDownClass(cls):cls.manager.__exit__(None,None,None)
    def setUp(self):
        self.c.now=self.stamp
        for name,data in self.saved.items():Path(name).write_bytes(data)
    def tearDown(self):
        (self.c.home/'STOP').unlink(missing_ok=True)
        for name,data in self.saved.items():Path(name).write_bytes(data)
    def inspect(self,rpc=None,expected=None,mono=lambda:0):
        return m.inspect(self.c.home,self.c.wallet,self.c.pool,self.expected,expected or self.retired,
            opener=rpc or Replies(self.c,self.ctx),clock=lambda:self.c.now,monotonic=mono)

    def test_consistent_review_binds_retirement_and_preserves_all_source_bytes(self):
        with patch.object(m.history.backend,'_invoke',side_effect=AssertionError('no signer')):
            r=self.inspect()
        self.assertEqual(r['state'],'retired-exit-review-consistent-held',r)
        self.assertEqual(r['identity']['retirementSha256'],self.retired)
        self.assertEqual(r['networkRequests'],8);self.assertEqual(r['blockingReasons'],[])
        self.assertEqual(r['scopedAccounting'],self.ctx['identity']['scopedAccounting'])
        self.assertEqual(r['budget']['quantityAtomic'],self.ctx['identity']['scopedAccounting']['ownedAcquiredHeldAtomic'])
        self.assertEqual(r['budget']['proposedMaximumFeeLamports'],'10000')
        self.assertEqual(r['budget']['conservativeRemainingAttemptSlots'],1)
        for k in ('sourceStateChanged','privateKeyAccessed','signaturesCreated','transactionsSent',
                  'reservationsReleasedThisRun','replacementAuthorized','executionApproved','nonExecutionProven'):
            self.assertFalse(r[k])
        for secret in (self.c.exit_wire,self.c.wallet,self.ctx['identity']['signature']):self.assertNotIn(secret,json.dumps(r))
        self.assertEqual(files(self.c),self.saved)

    def test_missing_wrong_or_rehashed_retirement_stops_before_rpc(self):
        rpc=Replies(self.c,self.ctx);r=self.inspect(rpc,expected='0'*64)
        self.assertEqual(r['diagnosticCode'],'replan-retirement-mismatch');self.assertEqual(rpc.calls,[])
        db=sqlite3.connect(self.c.path)
        try:
            old=json.loads(db.execute('SELECT value FROM admission_exit_retirement').fetchone()[0])
            old['contextSha256']='0'*64
            db.execute('UPDATE admission_exit_retirement SET value=?,hash=?',(m.retirement.encoded(old),m.digest(old)));db.commit()
        finally:db.close()
        r=self.inspect();self.assertEqual(r['state'],'retired-exit-review-unavailable');self.assertEqual(r['networkRequests'],0)
        db=sqlite3.connect(self.c.path)
        try:db.execute('DROP TABLE admission_exit_retirement');db.commit()
        finally:db.close()
        r=self.inspect();self.assertEqual(r['state'],'retired-exit-review-unavailable');self.assertEqual(r['networkRequests'],0)

    def test_observation_cannot_regress_below_retirement_height(self):
        db=sqlite3.connect(self.c.path)
        try:
            old=json.loads(db.execute('SELECT value FROM admission_exit_retirement').fetchone()[0])
            old['rpcEvidence']['height']['result']+=10
            expected=m.digest(old)
            db.execute('UPDATE admission_exit_retirement SET value=?,hash=?',(m.retirement.encoded(old),expected));db.commit()
        finally:db.close()
        before=files(self.c);r=self.inspect(expected=expected)
        self.assertEqual(r['state'],'retired-exit-review-blocked',r)
        self.assertIn('account-or-height-regressed-since-retirement',r['blockingReasons'])
        self.assertEqual(files(self.c),before)

    def test_external_account_change_blocks_even_when_it_adds_funds(self):
        def change(q,v):
            if q['method']=='getMultipleAccounts':v['value'][0]['lamports']+=1
            return v
        r=self.inspect(Replies(self.c,self.ctx,change))
        self.assertEqual(r['state'],'retired-exit-review-blocked',r)
        self.assertIn('wallet-account-changed',r['blockingReasons']);self.assertFalse(r['replacementAuthorized'])
        self.assertEqual(files(self.c),self.saved)

    def test_returned_signature_or_transaction_requires_reconciliation(self):
        for method in ('getSignatureStatuses','getTransaction'):
            with self.subTest(method=method):
                def returned(q,v):
                    if q['method']!=method:return v
                    slot=self.ctx['identity']['minimumContextSlot']+11
                    if method=='getSignatureStatuses':
                        v['value']=[dict(slot=slot,err=None,confirmations=None,confirmationStatus='finalized')];return v
                    return dict(slot=slot,transaction=[self.ctx['signedWire'],'base64'])
                r=self.inspect(Replies(self.c,self.ctx,returned))
                self.assertEqual(r['state'],'retired-exit-review-blocked',r)
                self.assertFalse(r['replacementAuthorized']);self.assertFalse(r['reservationsReleasedThisRun'])
        self.assertEqual(files(self.c),self.saved)

    def test_stop_remains_a_blocker_and_is_never_cleared(self):
        (self.c.home/'STOP').touch(mode=0o600)
        r=self.inspect();self.assertIn('stop-requested',r['blockingReasons'])
        self.assertEqual(r['state'],'retired-exit-review-blocked');self.assertTrue((self.c.home/'STOP').exists())

    def test_stale_provider_and_failed_transport_remain_unavailable(self):
        def stale(q,v):return self.c.now//1000-31 if q['method']=='getBlockTime' else v
        r=self.inspect(Replies(self.c,self.ctx,stale))
        self.assertEqual(r['state'],'retired-exit-review-unavailable');self.assertIsNone(r['budget'])
        class Broken:
            def open(self,*a,**kw):raise TimeoutError('private provider detail')
        r=self.inspect(Broken());self.assertEqual(r['networkRequests'],1)
        self.assertNotIn('private provider detail',json.dumps(r));self.assertEqual(files(self.c),self.saved)

    def test_backend_ack_mutation_during_rpc_invalidates_review(self):
        def corrupt(q,v):
            if q['id']==8:(self.c.path.parent/m.history.backend.ACK).write_text('{}')
            return v
        r=self.inspect(Replies(self.c,self.ctx,corrupt))
        self.assertEqual(r['state'],'retired-exit-review-unavailable');self.assertIsNone(r['observation'])
        self.assertEqual(self.c.path.read_bytes(),self.saved[str(self.c.path)])

    def test_shared_read_lock_excludes_commits_during_all_rpc_calls(self):
        checked=[]
        def collision(q,v):
            db=sqlite3.connect(self.c.path,timeout=0,isolation_level=None)
            try:
                db.execute('BEGIN IMMEDIATE')
                with self.assertRaises(sqlite3.OperationalError):db.execute('COMMIT')
                db.execute('ROLLBACK');checked.append(q['method'])
            finally:db.close()
            return v
        r=self.inspect(Replies(self.c,self.ctx,collision))
        self.assertEqual(r['state'],'retired-exit-review-consistent-held',r)
        self.assertEqual(checked,list(m.expiry.ORDER));self.assertEqual(files(self.c),self.saved)

    def test_slow_local_replay_does_not_age_new_observation(self):
        original=m.expiry.context;ticks=[0];calls=[]
        def slow(*a,**kw):
            value=original(*a,**kw);self.c.now+=25000;ticks[0]+=25;calls.append(1);return value
        def fresh(q,v):return self.c.now//1000 if q['method']=='getBlockTime' else v
        with patch.object(m.expiry,'context',side_effect=slow):
            r=self.inspect(Replies(self.c,self.ctx,fresh),mono=lambda:ticks[0])
        self.assertEqual(r['state'],'retired-exit-review-consistent-held',r);self.assertEqual(len(calls),1)
        self.assertEqual(files(self.c),self.saved)

    def test_total_and_network_deadlines_do_not_publish_partial_readiness(self):
        original=m.expiry.context;ticks=[0]
        def slow(*a,**kw):value=original(*a,**kw);ticks[0]=121;return value
        with patch.object(m.expiry,'context',side_effect=slow):r=self.inspect(mono=lambda:ticks[0])
        self.assertEqual(r['networkRequests'],0);self.assertEqual(r['diagnosticCode'],'replan-operation-budget')
        ticks[0]=0
        def delay(q,v):ticks[0]=31;return v
        r=self.inspect(Replies(self.c,self.ctx,delay),mono=lambda:ticks[0])
        self.assertEqual(r['state'],'retired-exit-review-unavailable');self.assertEqual(r['networkRequests'],1)
        self.assertEqual(files(self.c),self.saved)

    def test_budget_cannot_reset_retired_slot_or_increase_fees(self):
        policy=dict(maximumExitAttempts=1,maximumTotalFeeLamports='30000',maximumExitFeeLamports='10000')
        a=deepcopy(self.ctx['identity']['scopedAccounting'])
        b=m.budget(policy,a);self.assertIn('conservative-attempt-cap-exhausted',b['blockers'])
        self.assertEqual(b['conservativeRemainingAttemptSlots'],0)
        a['feeHeldLamports']='9999';b=m.budget(policy,a)
        self.assertIn('reserved-exit-fee-cap-not-covered',b['blockers']);self.assertEqual(b['proposedMaximumFeeLamports'],'9999')
        a['feeHeldLamports']='30000'
        with self.assertRaisesRegex(ValueError,'fee-conservation'):m.budget(policy,a)
        a=deepcopy(self.ctx['identity']['scopedAccounting']);a['unusedFeeReleasedLamports']='1'
        with self.assertRaisesRegex(ValueError,'held-accounting'):m.budget(policy,a)

    def test_cli_rejects_execution_import_and_output_inside_private_source(self):
        cli=Path(__file__).with_name('retired_exit_replan_cli.py')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out.gz';root=Path(d)/'source';root.mkdir()
            args=[sys.executable,'-E','-s',str(cli),'--directory',str(root),'--wallet','invalid',
                '--pool','invalid','--preparation-sha256','0'*64,'--retirement-sha256','0'*64,'--output',str(out)]
            for flag in ('--allow-devnet-submit','--allow-private-key-signing','--artifact','--action'):
                p=subprocess.run(args+[flag],capture_output=True,timeout=10)
                self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())
            out.write_bytes(b'keep');p=subprocess.run(args,capture_output=True,timeout=10)
            self.assertNotEqual(p.returncode,0);self.assertEqual(out.read_bytes(),b'keep')
            p=subprocess.run(args[:-1]+[str(root/'out.gz')],capture_output=True,timeout=10)
            self.assertNotEqual(p.returncode,0);self.assertFalse((root/'out.gz').exists())


if __name__=='__main__':unittest.main()
