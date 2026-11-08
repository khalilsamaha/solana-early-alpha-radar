"""Explicit nested computational reuse with bounded ownership and fresh inputs."""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import successor_execution as execution

s=execution.signing
SPECS=((s.canonical_replay,'_reuse_canonical_scope','canonicalDigestReplay'),
       (s.serialization_replay,'_reuse_serialization_scope','canonicalTextReplay'),
       (s.encoding_replay,'_reuse_encoding_scope','encodingReplay'),
       (s.admission_history_replay,'_reuse_history_scope','admissionHistoryReplay'))


def compute(m,value):
    if m is s.canonical_replay:return m.digest(value)
    if m is s.serialization_replay:return m.encoded(value)
    if m is s.encoding_replay:return m.replay('encode',str(value).encode(),lambda:str(value))
    row=dict(seq=1,at_ms=1,value=json.dumps(value),previous_hash='',hash='fixture')
    return m.replay({'policy':1},[row],lambda:(json.loads(row['value']),1,'fixture',1))


class ScopeOwnershipTests(unittest.TestCase):
    def test_explicit_child_joins_exact_owner_default_child_remains_isolated(self):
        for m,flag,key in SPECS:
            with self.subTest(module=m.__name__):
                @m.operation
                def child():
                    compute(m,{'n':1});return {}
                with m.scope() as stats:
                    compute(m,{'n':1});owner=m._SCOPE.get()
                    isolated=child()[key];self.assertEqual(isolated['hits'],0)
                    joined=child(**{flag:True})[key];self.assertEqual(joined['hits'],1)
                    self.assertIs(m._SCOPE.get(),owner)
                    self.assertEqual(stats()['entries'],1)
                    with ThreadPoolExecutor(1) as executor:self.assertIsNone(executor.submit(m._SCOPE.get).result())
                self.assertIsNone(m._SCOPE.get())

    def test_failure_never_clears_parent_and_owner_clears_on_exception(self):
        for m,flag,_ in SPECS:
            with self.subTest(module=m.__name__):
                @m.operation
                def failed():
                    compute(m,{'n':1});raise ValueError('fixture-failure')
                with self.assertRaisesRegex(ValueError,'outer-failure'):
                    with m.scope() as stats:
                        owner=m._SCOPE.get()
                        with self.assertRaisesRegex(ValueError,'fixture-failure'):failed(**{flag:True})
                        self.assertIs(m._SCOPE.get(),owner);self.assertEqual(stats()['entries'],1)
                        compute(m,{'n':1});self.assertEqual(stats()['hits'],1)
                        raise ValueError('outer-failure')
                self.assertEqual(stats()['entries'],0);self.assertIsNone(m._SCOPE.get())

    def test_changed_mutable_inputs_are_recomputed_inside_joined_scope(self):
        for m,flag,_ in SPECS:
            with self.subTest(module=m.__name__):
                value={'n':1}
                @m.operation
                def child():return {'value':compute(m,value)}
                with m.scope():
                    old=child(**{flag:True})['value'];value['n']=2
                    new=child(**{flag:True})['value'];self.assertNotEqual(old,new)
                self.assertIsNone(m._SCOPE.get())

    def test_invalid_reuse_flags_rejected_before_computation(self):
        for m,flag,_ in SPECS:
            @m.operation
            def child():self.fail('body reached')
            for v in (1,None,'yes'):
                with self.assertRaisesRegex(ValueError,'computation-scope-mode'):child(**{flag:v})

    def test_joined_scope_keeps_original_capacity_limits(self):
        for m,flag,key in SPECS:
            @m.operation
            def child(n):return {'value':compute(m,{'n':n})}
            with self.subTest(module=m.__name__),patch.object(m,'MAX_ENTRIES',1),m.scope() as stats:
                for n in range(5):
                    result=child(n,**{flag:True});self.assertLessEqual(stats()['entries'],1)
                    self.assertEqual(result[key]['maximumEntries'],1)
