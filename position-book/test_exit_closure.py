import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

import exit_closure as m
from exit_closure_checks import close, status, commit
from exit_balance_checks import signed_case, collect_receipt, apply, FakeRpc, observe

HERE=Path(__file__).resolve().parent

class ExitClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager=signed_case();cls.c=cls.manager.__enter__()
        collect_receipt(cls.c);apply(cls.c);cls.stamp=cls.c.now
        sink=[];r=observe(cls.c,_evidence_sink=sink.append);assert r['balanceReconciliationPassed'],r
        cls.cap=sink[0];cls.before=cls.c.path.read_bytes()
    @classmethod
    def tearDownClass(cls):cls.manager.__exit__(None,None,None)
    def setUp(self):self.c.now=self.stamp;self.c.path.write_bytes(self.before)
    def tearDown(self):
        (self.c.home/'STOP').unlink(missing_ok=True);self.c.now=self.stamp

    def test_portable_cli(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(HERE/'exit_closure_cli.py'),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();v=json.loads(gzip.decompress(raw));self.assertEqual(v['casesPassed'],21)
            self.assertTrue(all(x=='passed' for x in v['cases'].values()));self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertFalse(v['productionReservationsReleased']);self.assertTrue(v['syntheticScopedClosureExercised'])
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
            self.assertNotEqual(subprocess.run(cmd+['--allow-devnet-submit'],capture_output=True).returncode,0)

    def test_writer_exclusion_and_independent_read_only_replay(self):
        original=m.balance.context;calls=[]
        def inspect(book,*a,**kw):
            self.assertTrue(book.j.read_only)
            self.assertEqual(book.db.execute('PRAGMA query_only').fetchone()[0],1)
            db=sqlite3.connect(self.c.path,timeout=0)
            try:
                with self.assertRaises(sqlite3.OperationalError):db.execute('BEGIN IMMEDIATE')
            finally:db.close()
            calls.append(True);return original(book,*a,**kw)
        with patch.object(m.balance,'context',inspect):r=commit(self.c,self.cap)
        self.assertTrue(r['appliedThisRun']);self.assertEqual(len(calls),1)

    def test_monotonic_and_wall_clock_failures_rollback(self):
        for times in ([10],[-1],[0,10],[0,-1],[1,0.5]):
            with self.subTest(times=times):
                ticks=iter(times)
                with self.assertRaisesRegex(ValueError,'closure-monotonic-expired'):
                    m._commit(self.c.home,self.c.wallet,self.c.pool,self.cap,(0,10),clock=lambda:self.c.now,monotonic=lambda:next(ticks))
                self.assertEqual(self.before,self.c.path.read_bytes())
        original=m._insert
        def regression(book,record):original(book,record);self.c.now-=1
        with patch.object(m,'_insert',regression):
            with self.assertRaisesRegex(ValueError,'closure-expired-before-commit'):commit(self.c,self.cap)
        self.assertEqual(self.before,self.c.path.read_bytes())
        self.c.now=self.stamp
        stopped=m.balance.accounting.submission.handoff.stopped;calls=[]
        def slow_stop(*args):
            calls.append(True);result=stopped(*args)
            if len(calls)==2:self.c.now+=m.balance.FRESH_MS
            return result
        with patch.object(m.balance.accounting.submission.handoff,'stopped',slow_stop):
            with self.assertRaisesRegex(ValueError,'closure-expired-before-commit'):commit(self.c,self.cap)
        self.assertEqual(self.before,self.c.path.read_bytes())

    def test_source_change_between_collection_and_commit_is_rejected(self):
        original=m.balance.context
        def changed(*a,**kw):
            ctx=original(*a,**kw);ctx['identity']['sourceLedgerHeadSha256']='0'*64;return ctx
        with patch.object(m.balance,'context',changed):
            with self.assertRaisesRegex(ValueError,'balance-scope'):commit(self.c,self.cap)
        self.assertEqual(self.before,self.c.path.read_bytes())

    def test_collector_failure_after_sink_is_never_committed(self):
        def failed(*a,**kw):
            kw['_evidence_sink'](deepcopy(self.cap))
            return dict(balanceReconciliationPassed=False,networkRequests=4,diagnosticCode='balance-expired')
        with patch.object(m.balance,'collect',failed),patch.object(m,'_commit',side_effect=AssertionError('commit')):
            r=close(self.c)
        self.assertFalse(r['closureRecorded']);self.assertEqual(self.before,self.c.path.read_bytes())

    def test_ambiguous_return_after_commit_recovers_without_rpc(self):
        original=m._commit
        def lost(*a,**kw):original(*a,**kw);raise OSError('lost caller response')
        with patch.object(m,'_commit',lost):
            with self.assertRaises(OSError):close(self.c)
        before=self.c.path.read_bytes()
        with patch.object(m.balance,'collect',side_effect=AssertionError('network')):r=close(self.c)
        self.assertTrue(r['closureRecorded']);self.assertFalse(r['appliedThisRun']);self.assertEqual(r['networkRequests'],0)
        self.assertEqual(before,self.c.path.read_bytes())

    def test_bounded_record_and_future_timestamp(self):
        commit(self.c,self.cap);closed=self.c.path.read_bytes()
        for mode in ('oversize','future','hash','duplicate'):
            with self.subTest(mode=mode):
                self.c.path.write_bytes(closed);b=self.c.book()
                try:
                    v=m.saved(b,self.c.now)
                    if mode=='oversize':b.db.execute('UPDATE admission_exit_closure SET value=?',('x'*(m.MAX_RECORD+1),))
                    elif mode=='hash':b.db.execute("UPDATE admission_exit_closure SET hash='bad'")
                    elif mode=='future':
                        v['recordedAtMs']+=1;b.db.execute('UPDATE admission_exit_closure SET value=?,hash=?',(m.encoded(v),m.digest(v)))
                    else:
                        text=m.encoded(v);b.db.execute('UPDATE admission_exit_closure SET value=?',('{"format":"duplicate",'+text[1:],))
                finally:b.close()
                before=self.c.path.read_bytes()
                with self.assertRaises(ValueError):status(self.c)
                self.assertEqual(before,self.c.path.read_bytes())

    def test_later_receipt_conflict_never_releases_again(self):
        commit(self.c,self.cap);b=self.c.book()
        try:
            t=m.balance.accounting.submission.ExitSubmission(b);ev=deepcopy(t.captures()[0]['rpcEvidence'])
            ev['transaction']['result']['meta']['err']={'InstructionError':[2,'InvalidArgument']}
            ev['signatureStatus']['result']['value'][0]['err']=ev['transaction']['result']['meta']['err']
            t.save_capture(self.c.now,ev)
        finally:b.close()
        before=self.c.path.read_bytes();rpc=FakeRpc(self.c)
        with self.assertRaisesRegex(ValueError,'balance-accounting-required'):close(self.c,rpc)
        self.assertFalse(rpc.requests);self.assertEqual(before,self.c.path.read_bytes())

if __name__=='__main__':unittest.main()
