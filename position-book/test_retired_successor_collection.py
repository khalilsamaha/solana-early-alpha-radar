"""Actual eight-plus-twenty bounded collectors against disposable synthetic data."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import retired_successor_collection as m
import test_retired_exit_successor as contract_tests
from test_expired_exit_evidence import Replies
from test_signed_exit_timing import files
import admission_exit_capture_checks as fixtures
from paired_checks import shift,NOW
from preflight_checks import fake_key


class CollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contract_tests.SuccessorTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):contract_tests.SuccessorTests.tearDownClass.__func__(cls)
    def setUp(self):contract_tests.SuccessorTests.setUp(self)
    def tearDown(self):contract_tests.SuccessorTests.tearDown(self)
    def inputs(self,*,expiry_hook=None,quote_hook=None):
        first,e,b=fixtures.setup(self.c)
        for v in (first,e):shift(v,self.stamp-(NOW+30200),100)
        first['evidence']['blockTime']['result']=self.stamp//1000
        e['capture']['evidence']['blockTime']['result']=self.stamp//1000
        clock=fixtures.Clock();clock.at=self.stamp
        quote=fixtures.Opener(first,e,quote_hook)
        quote.rows[7]['value']['blockhash']=fake_key('successor-connected-new-blockhash')
        return Replies(self.c,self.ctx,expiry_hook),quote,clock
    def observe(self,reads,quote,clock,monotonic=lambda:0,**kw):
        return m.observe(self.c.home,self.c.wallet,self.c.pool,self.expected,self.retired,
            _expiry_opener=reads,_quote_opener=quote,clock=clock,monotonic=monotonic,**kw)

    def test_real_collectors_validate_without_changing_any_journal(self):
        reads,quote,clock=self.inputs();before=files(self.c)
        r=self.observe(reads,quote,clock)
        self.assertEqual(r['state'],'successor-observation-consistent-held',r)
        self.assertEqual(r['networkRequests'],28);self.assertEqual(len(reads.calls),8);self.assertEqual(len(quote.calls),20)
        self.assertEqual(r['binding']['attemptNumber'],2);self.assertGreater(r['timing']['headroomAfterValidationMs'],0)
        for key in ('sourceStateChanged','successorPersisted','signingApproved','executionApproved','transactionsSent','privateKeyAccessed'):
            self.assertFalse(r[key])
        self.assertEqual(files(self.c),before)
        self.assertNotIn('unsignedTransactionBase64',json.dumps(r))
        self.assertNotIn(self.c.exit_wire,json.dumps(r))

    def test_same_producer_integrates_atomic_contract_offline(self):
        reads,quote,clock=self.inputs();producers=[]
        def produce(ctx):
            book=self.c.book()
            try:
                p=m.Collector(self.c.home,book,self.c.wallet,self.c.pool,m.retirement.row(book),clock,lambda:0,
                    expiry_opener=reads,quote_opener=quote)
                producers.append(p);return p(ctx)
            finally:book.close()
        r=m.successor._prepare_from_producer(self.c.home,self.c.wallet,self.c.pool,self.expected,self.retired,
            produce,allow_unsigned_successor=True,clock=clock,monotonic=lambda:0)
        self.assertTrue(r['createdThisRun']);self.assertEqual(r['state'],'unsigned-successor-prepared-held')
        self.assertEqual(producers[0].telemetry()['networkRequests'],28)
        next_reads,next_quote,_=self.inputs()
        r=self.observe(next_reads,next_quote,clock)
        self.assertEqual(r['diagnosticCode'],'successor-already-present');self.assertEqual(r['networkRequests'],0)

    def test_receipt_or_balance_conflict_never_starts_quote(self):
        for mode in ('receipt','balance'):
            def conflict(q,v):
                if mode=='receipt' and q['method']=='getTransaction':return dict(slot=99,transaction=[self.ctx['signedWire'],'base64'])
                if mode=='balance' and q['id']==6:
                    v=deepcopy(v);v['value'][0]['lamports']+=1
                return v
            reads,quote,clock=self.inputs(expiry_hook=conflict);r=self.observe(reads,quote,clock)
            self.assertNotEqual(r['state'],'successor-observation-consistent-held');self.assertEqual(quote.calls,[])
            self.assertEqual(files(self.c),self.saved)

    def test_stop_during_expiry_stops_before_next_request(self):
        def stop(q,v):
            if q['id']==2:(self.c.home/'STOP').touch(mode=0o600)
            return v
        reads,quote,clock=self.inputs(expiry_hook=stop);r=self.observe(reads,quote,clock)
        self.assertEqual(r['diagnosticCode'],'successor-stopped');self.assertEqual(len(reads.calls),2)
        self.assertEqual(quote.calls,[]);self.assertEqual(self.c.path.read_bytes(),self.saved[str(self.c.path)])

    def test_backend_ack_change_and_quote_failure_remain_unavailable(self):
        for mode in ('ack','provider','simulation'):
            for name,data in self.saved.items():Path(name).write_bytes(data);Path(name).chmod(0o600)
            def hook(n,q,rpc):
                if mode=='ack' and n==20:(self.c.path.parent/m.history.backend.ACK).write_text('{}')
                if mode=='provider' and n==3:rpc.rows[0]=TimeoutError('PRIVATE_PROVIDER_DETAIL')
                if mode=='simulation' and n==19:rpc.rows[0]['value']['err']={'private':'PRIVATE_PROVIDER_DETAIL'}
            reads,quote,clock=self.inputs(quote_hook=hook);r=self.observe(reads,quote,clock)
            self.assertNotEqual(r['state'],'successor-observation-consistent-held')
            self.assertNotIn('PRIVATE_PROVIDER_DETAIL',json.dumps(r));self.assertLessEqual(r['networkRequests'],28)
            self.assertEqual(self.c.path.read_bytes(),self.saved[str(self.c.path)])

    def test_source_snapshot_blocks_writer_commit_during_requests(self):
        collisions=[]
        def collide():
            db=sqlite3.connect(self.c.path,timeout=0,isolation_level=None)
            try:
                db.execute('BEGIN IMMEDIATE');db.execute('CREATE TABLE competing_writer (n INTEGER)')
                with self.assertRaises(sqlite3.OperationalError):db.execute('COMMIT')
                db.execute('ROLLBACK');collisions.append(True)
            finally:db.close()
        def eh(q,v):collide();return v
        def qh(n,q,rpc):collide()
        r=self.observe(*self.inputs(expiry_hook=eh,quote_hook=qh))
        self.assertEqual(r['state'],'successor-observation-consistent-held',r)
        self.assertEqual(len(collisions),28);self.assertEqual(files(self.c),self.saved)

    def test_final_validation_expiry_never_returns_success(self):
        reads,quote,clock=self.inputs();original=m.successor.binding
        def slow(*a,**kw):
            value=original(*a,**kw);clock.at+=10000;return value
        with patch.object(m.successor,'binding',side_effect=slow):r=self.observe(reads,quote,clock)
        self.assertEqual(r['diagnosticCode'],'successor-expired-before-return');self.assertIsNone(r['binding'])
        self.assertEqual(files(self.c),self.saved)

    def test_default_uses_fixed_collectors_and_closes_quote_session(self):
        reads,quote,clock=self.inputs();closed=[]
        class Session:
            def open(self,*args,**kw):return quote.open(*args,**kw)
            def close(self):closed.append(True)
            def summary(self):return {'synthetic':True}
        with patch.object(m.capture,'Session',return_value=Session()),patch.object(m.expiry.chain.urllib.request,'build_opener',return_value=reads):
            r=m.observe(self.c.home,self.c.wallet,self.c.pool,self.expected,self.retired,clock=clock,monotonic=lambda:0)
        self.assertEqual(r['state'],'successor-observation-consistent-held',r)
        self.assertEqual(closed,[True]);self.assertEqual(len(reads.calls),8);self.assertEqual(len(quote.calls),20)


    def test_total_budget_stops_after_slow_replay_without_rpc(self):
        reads,quote,clock=self.inputs();original=m.expiry.context;ticks=[0]
        def slow(*a,**kw):
            value=original(*a,**kw);ticks[0]=121;return value
        with patch.object(m.expiry,'context',side_effect=slow):
            r=self.observe(reads,quote,clock,monotonic=lambda:ticks[0])
        self.assertEqual(r['diagnosticCode'],'successor-total-budget')
        self.assertEqual(reads.calls,[]);self.assertEqual(quote.calls,[]);self.assertEqual(files(self.c),self.saved)

    def test_total_budget_stops_between_quote_requests_without_retry(self):
        ticks=[0]
        def slow(n,q,rpc):
            if n==2:ticks[0]=121
        reads,quote,clock=self.inputs(quote_hook=slow)
        r=self.observe(reads,quote,clock,monotonic=lambda:ticks[0])
        self.assertNotEqual(r['state'],'successor-observation-consistent-held')
        self.assertEqual(len(quote.calls),2);self.assertEqual(files(self.c),self.saved)


    def test_snapshot_close_failure_cannot_publish_success(self):
        from contextlib import contextmanager
        original=m.history.lifecycle.admission_read_lock
        @contextmanager
        def fail(path):
            with original(path):yield
            raise sqlite3.OperationalError('PRIVATE_CLOSE_FAILURE')
        with patch.object(m.history.lifecycle,'admission_read_lock',fail):r=self.observe(*self.inputs())
        self.assertEqual(r['state'],'successor-observation-unavailable-held');self.assertIsNone(r['binding'])
        self.assertNotIn('PRIVATE_CLOSE_FAILURE',json.dumps(r));self.assertEqual(files(self.c),self.saved)

    def test_snapshot_close_time_counts_toward_deadline(self):
        from contextlib import contextmanager
        original=m.history.lifecycle.admission_read_lock
        reads,quote,clock=self.inputs()
        @contextmanager
        def slow(path):
            with original(path):yield
            clock.at+=10000
        with patch.object(m.history.lifecycle,'admission_read_lock',slow):r=self.observe(reads,quote,clock)
        self.assertEqual(r['diagnosticCode'],'successor-expired-before-return');self.assertIsNone(r['binding'])
        self.assertEqual(files(self.c),self.saved)


    def test_rpc_timeouts_are_clipped_to_remaining_operation_budget(self):
        reads,quote,clock=self.inputs();original=m.expiry.context;ticks=[0];timeouts=[]
        def slow(*a,**kw):
            value=original(*a,**kw);ticks[0]=119.5;return value
        for opener in (reads,quote):
            old=opener.open
            def limited(request,timeout,old=old):
                timeouts.append(timeout);return old(request,timeout)
            opener.open=limited
        with patch.object(m.expiry,'context',side_effect=slow):
            r=self.observe(reads,quote,clock,monotonic=lambda:ticks[0])
        self.assertEqual(r['state'],'successor-observation-consistent-held',r)
        self.assertEqual(len(timeouts),28);self.assertTrue(all(0<t<=0.5 for t in timeouts))
        self.assertEqual(files(self.c),self.saved)


if __name__=='__main__':unittest.main()
