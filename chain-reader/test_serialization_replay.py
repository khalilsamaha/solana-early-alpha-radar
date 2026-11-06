"""Canonical text equivalence, fresh mutable inputs, bounded isolated retention."""
import json
import math
import random
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import serialization_replay as m


def original(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False)


class SerializationTests(unittest.TestCase):
    def test_original_bytes_including_unicode_and_random_nested_inputs(self):
        rng=random.Random(57)
        chars=['a','é','😀','\ud800','\udfff','\x00','\n','"','\\']
        values=[None,True,False,1,0,-123,[],{},'']
        for _ in range(100):
            values.append({'z':[rng.randint(-2**64,2**64),bool(rng.randrange(2)),None],
                           ''.join(rng.choices(chars,k=5)):''.join(rng.choices(chars,k=10))})
        with m.scope() as stats:
            for v in values:
                for _ in range(2):self.assertEqual(m.encoded(v),original(v))
            self.assertGreaterEqual(stats()['hits'],len(values))

    def test_exact_hits_skip_new_snapshots_but_still_detect_nested_mutation(self):
        value={'evidence':{'raw':'x'*5000,'count':1}}
        with m.scope() as stats,patch.object(m,'frozen',wraps=m.frozen) as freeze:
            first=m.encoded(value)
            self.assertEqual(m.encoded(json.loads(first)),first)
            self.assertEqual(freeze.call_count,1)
            value['evidence']['count']=True
            self.assertNotEqual(m.encoded(value),first)
            self.assertEqual(freeze.call_count,2)
            self.assertEqual(stats()['hits'],1)

    def test_mutations_equal_copies_and_type_distinctions(self):
        v={'nested':[1,True,{'a':'x'}]}
        with m.scope() as stats:
            a=m.encoded(v);self.assertEqual(m.encoded(json.loads(a)),a)
            v['nested'][0]=True;self.assertNotEqual(m.encoded(v),a)
            v['nested'][2]['a']='y';self.assertEqual(m.encoded(v),original(v))
            v['nested'].reverse();self.assertEqual(m.encoded(v),original(v))
            self.assertEqual(stats()['hits'],1)

    def test_unsupported_and_invalid_values_keep_original_behavior(self):
        class Text(str):pass
        class Mapping(dict):pass
        cyclic=[];cyclic.append(cyclic)
        for v in (1.5,-0.0,math.inf,math.nan,2**300,(1,2),{1:'x'}, {'a':1,2:'b'},
                  Text('x'),Mapping(a=1),cyclic,{1,2}):
            with self.subTest(kind=type(v)),m.scope() as stats:
                try:wanted=original(v)
                except (TypeError,ValueError) as e:
                    with self.assertRaises(type(e)) as caught:m.encoded(v)
                    self.assertEqual(str(caught.exception),str(e))
                else:self.assertEqual(m.encoded(v),wanted)
                self.assertEqual(stats()['entries'],0)

    def test_default_nested_disabled_and_exception_scopes(self):
        with patch.object(m,'original',wraps=m.original) as compute:
            m.encoded({'a':1});m.encoded({'a':1});self.assertEqual(compute.call_count,2)
        with m.scope() as outer:
            m.encoded({'a':1})
            with m.scope() as inner:
                m.encoded({'a':1});self.assertEqual(inner()['hits'],0)
            with m.scope(enabled=False):m.encoded({'a':1})
            m.encoded({'a':1});self.assertEqual(outer()['hits'],1)
            with ThreadPoolExecutor(1) as executor:self.assertIsNone(executor.submit(m._SCOPE.get).result())
        with self.assertRaisesRegex(ValueError,'test-failure'):
            with m.scope() as failed:
                m.encoded({'large':'x'*5000});raise ValueError('test-failure')
        self.assertEqual(failed()['retainedBytes'],0)
        self.assertEqual(failed()['sharedStrings'],0)
        self.assertIsNone(m._SCOPE.get())

    def test_output_bytes_charged_and_eviction_preserves_results(self):
        v={'large':'x'*50000}
        with m.scope() as stats:
            value=m.encoded(v)
            self.assertGreaterEqual(stats()['retainedBytes'],sys.getsizeof(value)+50000)
        with patch.object(m,'MAX_BYTES',150000),m.scope() as stats:
            for i in range(30):
                v={'large':'x'*50000,'row':i}
                self.assertEqual(m.encoded(v),original(v))
                self.assertLessEqual(stats()['retainedBytes'],150000)
            self.assertGreater(stats()['evictions'],0)
        with patch.object(m,'MAX_ENTRIES',2),m.scope() as stats:
            for i in range(10):m.encoded({'row':i})
            self.assertEqual(stats()['entries'],2)
            self.assertEqual(stats()['evictions'],8)

    def test_entry_and_traversal_caps_preserve_output_without_retention(self):
        nested=1
        for _ in range(50):nested=[nested]
        for v in (nested,[0]*8193,'x'*(16*1024*1024)):
            with m.scope() as stats:
                self.assertEqual(m.encoded(v),original(v))
                self.assertEqual(stats()['entries'],0)
        with patch.object(m,'MAX_BYTES',10),m.scope() as stats:
            self.assertEqual(m.encoded({'x':'y'}),original({'x':'y'}))
            self.assertEqual(stats()['entries'],0)
            self.assertEqual(stats()['capacityBypasses'],1)

    def test_mutable_input_not_retained_or_serialized_after_snapshot(self):
        v={'x':1};compute=m.original
        def mutate(item):
            v['x']+=1
            return compute(item)
        with m.scope(),patch.object(m,'original',mutate):
            self.assertEqual(m.encoded(v),'{"x":1}')
            self.assertEqual(m.encoded(v),'{"x":2}')

    def test_failures_never_retained_and_public_summary_has_no_content(self):
        with m.scope() as stats,patch.object(m,'original',side_effect=ValueError('fixed')):
            for _ in range(2):
                with self.assertRaises(ValueError):m.encoded({'x':1})
            self.assertEqual(stats()['entries'],0);self.assertEqual(stats()['failures'],2)
        @m.operation
        def observed():
            m.encoded({'PRIVATE_SENTINEL':'PRIVATE_VALUE'});return {'state':'complete'}
        value=observed()['canonicalTextReplay']
        self.assertEqual(m.summary(dict(value,secret='PRIVATE_VALUE')),value)
        self.assertNotIn('PRIVATE',json.dumps(value))
        for k,v in [('calls',True),('retainedBytes',m.MAX_BYTES+1),('entries',129),('version','x')]:
            self.assertIsNone(m.summary(dict(value,**{k:v})))
        self.assertIsNone(m._SCOPE.get())


if __name__=='__main__':unittest.main()
