"""Retirement denies further sending and preserves every economic commitment."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import exit_retirement as m
from test_expired_exit_evidence import fixture,Replies
from exit_submission_checks import signed_case,submit,FakeRpc
from test_signed_exit_timing import files


class RetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager=signed_case();cls.c=cls.manager.__enter__();cls.c.now+=30000
        cls.ctx=fixture(cls.c);cls.saved=files(cls.c);cls.stamp=cls.c.now
    @classmethod
    def tearDownClass(cls):cls.manager.__exit__(None,None,None)
    def setUp(self):
        self.c.now=self.stamp
        for name,data in self.saved.items():Path(name).write_bytes(data)
    def tearDown(self):
        (self.c.home/'STOP').unlink(missing_ok=True)
        for name,data in self.saved.items():Path(name).write_bytes(data)
    def expected(self):return self.c.exit_state['request']['preparationSha256']
    def retire(self,rpc=None,**kw):
        return m.retire(self.c.home,self.c.wallet,self.c.pool,self.expected(),allow_retire=True,
            opener=rpc or Replies(self.c,self.ctx),clock=lambda:self.c.now,monotonic=lambda:0,**kw)
    def status(self):return m.status(self.c.home,self.c.wallet,self.c.pool,self.expected(),clock=lambda:self.c.now)
    def tables(self):
        db=sqlite3.connect(self.c.path)
        try:
            names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            return {n:db.execute('SELECT * FROM '+n).fetchall() for n in names}
        finally:db.close()
    def rewrite(self,mutate):
        db=sqlite3.connect(self.c.path)
        try:
            v=json.loads(db.execute('SELECT value FROM admission_exit_retirement').fetchone()[0]);mutate(v)
            db.execute('UPDATE admission_exit_retirement SET value=?,hash=?',(m.encoded(v),m.digest(v)));db.commit()
        finally:db.close()

    def test_retire_commit_lifecycle_reopen_and_duplicate_preserve_exact_history_and_holds(self):
        before=self.tables();(self.c.home/'STOP').touch(mode=0o600)
        with patch.object(m.history.backend,'_invoke',side_effect=AssertionError('signer')):
            result=self.retire()
        self.assertEqual(result['state'],'exit-retired-held',result);self.assertTrue(result['createdThisRun'])
        self.assertEqual(result['networkRequests'],8)
        self.assertEqual(result['scopedAccounting'],self.ctx['identity']['scopedAccounting'])
        after=self.tables();self.assertEqual(set(after)-set(before),{m.guard.TABLE})
        self.assertEqual(before,{k:after[k] for k in before})
        for name,data in self.saved.items():
            if Path(name)!=self.c.path:self.assertEqual(Path(name).read_bytes(),data)
        snapshot=files(self.c)
        class NoNetwork:
            def open(self,*a,**kw):raise AssertionError('duplicate RPC')
        duplicate=self.retire(NoNetwork());self.assertFalse(duplicate['createdThisRun']);self.assertEqual(duplicate['networkRequests'],0)
        self.assertEqual(duplicate['retirementSha256'],result['retirementSha256']);self.assertEqual(self.status()['state'],'exit-retired-held')
        self.assertEqual(files(self.c),snapshot)
        lifecycle=m.history.lifecycle.inspect(self.c.home,self.c.wallet,self.c.pool,clock=lambda:self.c.now)
        self.assertTrue(lifecycle['coherent'],lifecycle);self.assertEqual(lifecycle['phase'],'exit-retired-held')
        self.assertEqual(lifecycle['scopedAccounting'],result['scopedAccounting'])
        for key in ('reservationsReleasedThisRun','replacementAuthorized','retryAllowed','executionApproved','nonExecutionProven','receiptEffectsReconciled','privateKeyAccessed','signaturesCreated','transactionsSent'):
            self.assertFalse(result[key])
        for secret in (self.c.exit_wire,self.c.wallet,self.ctx['identity']['signature']):self.assertNotIn(secret,json.dumps(result))

    def test_sender_and_mark_fail_before_rpc_even_with_a_corrupt_marker(self):
        result=self.retire();self.assertEqual(result['state'],'exit-retired-held',result)
        for corrupt in (False,True):
            if corrupt:self.rewrite(lambda r:r.update(contextSha256='0'*64))
            before=files(self.c);rpc=FakeRpc(self.c)
            with self.assertRaisesRegex(ValueError,'retired-or-marker-invalid'):submit(self.c,rpc)
            self.assertEqual(rpc.requests,[])
            book=self.c.book()
            try:
                with self.assertRaisesRegex(ValueError,'retired-or-marker-invalid'):
                    m.history.transport.ExitSubmission(book).mark({},self.c.home,self.c.wallet,self.c.pool,lambda:self.c.now)
                with self.assertRaisesRegex(ValueError,'retired-or-marker-invalid'):
                    m.history.transport.handoff.current(self.c.home,book,self.c.wallet,self.c.pool,lambda:self.c.now)
            finally:book.close()
            self.assertEqual(files(self.c),before)
        self.assertEqual(self.status()['state'],'retirement-unavailable')

    def test_changed_accounts_transaction_present_and_failed_rpc_never_write(self):
        before=files(self.c)
        def changed(q,v):
            if q['method']=='getMultipleAccounts':v=deepcopy(v);v['value'][0]['lamports']+=1
            return v
        def found(q,v):
            if q['method']=='getTransaction':return dict(slot=self.ctx['identity']['minimumContextSlot'],transaction=[self.c.exit_wire,'base64'],meta=dict(err=None),version='legacy')
            return v
        class Failed:
            def open(self,*a,**kw):raise TimeoutError('private detail')
        for rpc in (Replies(self.c,self.ctx,changed),Replies(self.c,self.ctx,found),Failed()):
            result=self.retire(rpc);self.assertEqual(result['state'],'retirement-refused-held',result)
            self.assertEqual(files(self.c),before);self.assertNotIn('private detail',json.dumps(result))

    def test_stale_handoff_or_changed_ack_between_collection_and_writer_refuses(self):
        original=m._persist
        for kind in ('stale','ack'):
            self.setUp();before=files(self.c)
            def changed(*args,**kw):
                if kind=='stale':self.c.now+=10001
                else:(self.c.path.parent/m.history.backend.ACK).write_text('{}')
                return original(*args,**kw)
            with patch.object(m,'_persist',side_effect=changed):result=self.retire()
            self.assertEqual(result['state'],'retirement-refused-held',result)
            self.assertNotIn(m.guard.TABLE,self.tables())
            self.assertEqual(self.c.path.read_bytes(),before[str(self.c.path)])

    def test_write_failure_or_expiry_before_commit_rolls_back(self):
        original=m.write_record
        for kind in ('disk','clock'):
            self.setUp();before=files(self.c)
            def fault(book,r):
                original(book,r)
                if kind=='disk':raise OSError('disk failure')
                self.c.now+=10001
            with patch.object(m,'write_record',side_effect=fault):result=self.retire()
            self.assertEqual(result['state'],'retirement-unconfirmed-held',result)
            self.assertNotIn(m.guard.TABLE,self.tables());self.assertEqual(files(self.c),before)

    def test_semantic_replay_rejects_rehashed_changed_identity_proof_and_times(self):
        result=self.retire();self.assertEqual(result['state'],'exit-retired-held',result);saved=self.c.path.read_bytes()
        mutations=[lambda r:r.update(preparationSha256='0'*64),lambda r:r.update(contextSha256='0'*64),
            lambda r:r['rpcEvidence']['validity']['result'].update(value=True),
            lambda r:r['rpcEvidence']['height'].update(result=self.ctx['lastValidBlockHeight']),
            lambda r:r.update(observedAtMs=r['recordedAtMs']-10001),
            lambda r:r.update(recordedAtMs=self.c.now+1)]
        for mutate in mutations:
            self.c.path.write_bytes(saved);self.rewrite(mutate);before=files(self.c)
            self.assertEqual(self.status()['state'],'retirement-unavailable')
            lifecycle=m.history.lifecycle.inspect(self.c.home,self.c.wallet,self.c.pool,clock=lambda:self.c.now)
            self.assertFalse(lifecycle['coherent']);self.assertIsNone(lifecycle['scopedAccounting'])
            self.assertEqual(files(self.c),before)

    def test_explicit_opt_in_and_exact_preparation_are_required_before_reads(self):
        before=files(self.c);rpc=Replies(self.c,self.ctx)
        with self.assertRaises(ValueError):m.retire(self.c.home,self.c.wallet,self.c.pool,self.expected(),opener=rpc)
        result=m.retire(self.c.home,self.c.wallet,self.c.pool,'0'*64,allow_retire=True,opener=rpc,clock=lambda:self.c.now)
        self.assertEqual(result['state'],'retirement-unavailable');self.assertEqual(rpc.calls,[]);self.assertEqual(files(self.c),before)

    def test_snapshot_projection_replays_retirement_and_retains_held_amounts(self):
        result=self.retire();self.assertEqual(result['state'],'exit-retired-held',result)
        from admission_recovery import retirement_projection
        with m.read_only_journals():
            b=self.c.book()
            try:
                with m.history.lifecycle.admission_read_lock(b.j.path):
                    r=retirement_projection(b,self.c.home,self.c.wallet,self.c.pool,lambda:self.c.now)
                    self.assertEqual(r['recordSha256'],result['retirementSha256'])
                    self.assertEqual(r['scopedAccounting'],result['scopedAccounting'])
            finally:b.close()
        self.rewrite(lambda r:r.update(contextSha256='0'*64))
        with m.read_only_journals():
            b=self.c.book()
            try:
                with m.history.lifecycle.admission_read_lock(b.j.path),self.assertRaises(ValueError):
                    retirement_projection(b,self.c.home,self.c.wallet,self.c.pool,lambda:self.c.now)
            finally:b.close()

    def test_retirement_object_appearing_during_preflight_blocks_send_boundary(self):
        # A malformed object is sufficient to deny; it never grants authority.
        self.c.now=self.c.exit_state['lastAtMs']+1
        def callback(method):
            if method=='getFeeForMessage':
                db=sqlite3.connect(self.c.path)
                try:db.execute('CREATE TABLE admission_exit_retirement (invalid TEXT)');db.commit()
                finally:db.close()
        rpc=FakeRpc(self.c,callback=callback)
        with self.assertRaisesRegex(ValueError,'retired-or-marker-invalid'):submit(self.c,rpc)
        self.assertNotIn('sendTransaction',[q['method'] for q in rpc.requests])
        self.assertNotIn(m.history.transport.BOUNDARY,self.tables())

    def test_lost_local_completion_after_commit_is_unknown_until_read_only_status(self):
        original=m.public
        def lost(*args,**kw):
            value=original(*args,**kw)
            if kw.get('created'):raise OSError('lost local completion')
            return value
        with patch.object(m,'public',side_effect=lost):result=self.retire()
        self.assertEqual(result['state'],'retirement-unconfirmed-held')
        for key in ('recorded','createdThisRun','sourceStateChanged'):self.assertIsNone(result[key])
        before=files(self.c);status=self.status()
        self.assertEqual(status['state'],'exit-retired-held');self.assertEqual(status['networkRequests'],0)
        self.assertFalse(status['createdThisRun']);self.assertEqual(files(self.c),before)

    def test_previous_send_boundary_cannot_be_retired_as_locally_unsent(self):
        self.c.now=self.c.exit_state['lastAtMs']+1
        submit(self.c,FakeRpc(self.c,lost=True));self.c.now+=30000
        before=files(self.c);rpc=Replies(self.c,self.ctx);result=self.retire(rpc)
        self.assertEqual(result['state'],'retirement-unavailable');self.assertEqual(rpc.calls,[])
        self.assertEqual(files(self.c),before)

    def test_cli_cannot_submit_import_reports_or_overwrite_sources(self):
        cli=Path(__file__).with_name('exit_retirement_cli.py')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'source';root.mkdir();out=Path(d)/'out.gz'
            base=[sys.executable,'-E','-s',str(cli),'--directory',str(root),'--wallet','invalid','--pool','invalid','--preparation-sha256','0'*64,'--output',str(out)]
            for extra in (['--action','retire'],['--allow-local-retirement'],['--allow-devnet-submit'],['--report','anything']):
                r=subprocess.run(base+extra,capture_output=True,timeout=10);self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())
            out.write_bytes(b'keep');r=subprocess.run(base,capture_output=True,timeout=10)
            self.assertNotEqual(r.returncode,0);self.assertEqual(out.read_bytes(),b'keep')
            r=subprocess.run(base[:-1]+[str(root/'out.gz')],capture_output=True,timeout=10)
            self.assertNotEqual(r.returncode,0);self.assertFalse((root/'out.gz').exists())


if __name__=='__main__':unittest.main()
