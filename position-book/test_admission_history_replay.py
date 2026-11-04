"""Exact-row reuse never substitutes for current policy, ownership or freshness."""
import copy
import json
import unittest
from unittest.mock import patch
import pre_sign_admission as admission
import admission_history_replay as m
from unsigned_exit_replacement_checks import case


class HistoryReplayTests(unittest.TestCase):
    def test_exact_rows_reused_results_are_independent_and_sql_still_read(self):
        with case() as c:
            b=c.book();reads=[]
            try:
                b.db.set_trace_callback(reads.append)
                with m.scope() as stats,patch.object(b,'_read_rows',wraps=b._read_rows) as full:
                    first=b.read();expected=copy.deepcopy(first);first[0]['state']='FORGED'
                    second=b.read();self.assertEqual(second,expected)
                    self.assertEqual(full.call_count,1)
                self.assertEqual(len([q for q in reads if q.startswith('SELECT * FROM admission_events')]),2)
                self.assertGreater(stats()['hits'],0)
                self.assertEqual(stats()['sqlReadsSkipped'],0)
            finally:b.close()

    def test_every_chain_column_and_current_policy_invalidate_a_warm_entry(self):
        with case() as c,m.scope():
            b=c.book()
            try:
                b.read();rows=[dict(r) for r in b.db.execute('SELECT * FROM admission_events ORDER BY seq')]
                for name,value in [('seq',99),('at_ms',-1),('value','{}'),('hash','0'*64),('previous_hash','f'*64)]:
                    bad=copy.deepcopy(rows);bad[-1][name]=value
                    with self.subTest(name=name),self.assertRaises((ValueError,KeyError)):
                        m.replay(b.policy,bad,lambda:b._read_rows(bad))
                b.policy=copy.deepcopy(b.policy);b.policy['maximumTotalFeeLamports']='39999'
                with self.assertRaises(ValueError):b.read()
            finally:b.close()

    def test_committed_stop_append_is_visible_after_warm_read(self):
        with case() as c,m.scope():
            b=c.book()
            try:
                before=b.read();b.stop()
                after=b.read();self.assertNotEqual(before,after)
                self.assertEqual(after[0]['state'],'stopped')
            finally:b.close()

    def test_real_rehashed_accounting_tamper_is_not_hidden_by_warm_chain(self):
        import unsigned_exit_replacement as replacement
        with case() as c,m.scope():
            b=c.book()
            try:
                replacement.preparation.original_saved(b,c.clock())
                row=json.loads(b.db.execute('SELECT value FROM admission_entry_accounting').fetchone()[0])
                row['accounting']['ownedAcquiredAtomic']='999999'
                b.db.execute('UPDATE admission_entry_accounting SET value=?,hash=?',
                    (admission.encoded(row),replacement.digest(row)))
                with self.assertRaisesRegex(ValueError,'entry-accounting-source-conflict'):
                    replacement.preparation.original_saved(b,c.clock())
            finally:b.close()

    def test_cap_failure_bypass_cleanup_and_nested_scopes(self):
        # Construct canonical immutable rows with a trusted synthetic validator;
        # this test exercises only storage bounds, not acceptance of real evidence.
        def rows(n=1,text='{}'):
            return [dict(seq=i+1,at_ms=i+1,value=text,previous_hash='',hash=str(i)) for i in range(n)]
        calls=[]
        def compute(r):calls.append(True);return json.loads(r[-1]['value']),len(r),r[-1]['hash'],r[-1]['at_ms']
        with m.scope() as stats:
            r=rows()
            for _ in range(2):m.replay({},r,lambda:compute(r))
            self.assertEqual(len(calls),1)
            with m.scope() as inner:m.replay({},r,lambda:compute(r))
            self.assertEqual(inner()['entries'],0)
            m.replay({},r,lambda:compute(r));self.assertEqual(len(calls),2)
            for i in range(m.MAX_ENTRIES+3):m.replay({'id':i},r,lambda:compute(r))
            self.assertEqual(stats()['entries'],m.MAX_ENTRIES)
            self.assertLessEqual(stats()['retainedBytes'],m.MAX_TOTAL_BYTES)
            for large in (rows(65),rows(text=json.dumps({'x':'a'*(m.MAX_ENTRY_BYTES+1)}))):
                m.replay({},large,lambda:compute(large));m.replay({},large,lambda:compute(large))
            def fail():raise ValueError('original-error')
            for _ in range(2):
                with self.assertRaisesRegex(ValueError,'original-error'):m.replay({'bad':1},r,fail)
            self.assertEqual(stats()['failures'],2)
        self.assertEqual(stats()['entries'],0);self.assertEqual(stats()['retainedBytes'],0)
        self.assertIsNone(m._SCOPE.get())
        for enabled in (False,):
            with m.scope(enabled=enabled):
                with patch.object(m.json,'dumps',side_effect=AssertionError('extra serialization')):
                    self.assertEqual(m.replay({},[],lambda:'original'),'original')

    def test_thread_has_no_inherited_operation_cache(self):
        from concurrent.futures import ThreadPoolExecutor
        with m.scope():
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertIsNone(pool.submit(m._SCOPE.get).result())
        self.assertIsNone(m._SCOPE.get())

    def test_aggregate_byte_budget_and_exception_cleanup(self):
        text=json.dumps({'x':'a'*100000})
        r=[dict(seq=1,at_ms=1,value=text,previous_hash='',hash='a')]
        def compute():return json.loads(text),1,'a',1
        with self.assertRaises(KeyboardInterrupt):
            with m.scope() as stats:
                for i in range(40):m.replay({'id':i},r,compute)
                self.assertLessEqual(stats()['retainedBytes'],m.MAX_TOTAL_BYTES)
                self.assertLess(stats()['entries'],m.MAX_ENTRIES)
                raise KeyboardInterrupt()
        self.assertIsNone(m._SCOPE.get());self.assertEqual(stats()['entries'],0)


if __name__=='__main__':unittest.main()
