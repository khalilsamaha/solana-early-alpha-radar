import json
import hashlib
import math
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
import canonical_replay as m


class CanonicalReplayTests(unittest.TestCase):
    def test_exact_bytes_and_type_distinctions(self):
        samples = [None, True, 1, False, 0, '', 'é\n\\"😀', [], {},
                   {'z': [True, 1, None], 'a': {'é': 'x'}}, [1, 2], [2, 1]]
        with m.scope() as stats:
            for value in samples:
                wanted = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
                self.assertEqual(m.digest(value), wanted)
                self.assertEqual(m.digest(value), wanted)
            self.assertEqual(stats()['hits'], len(samples))
            self.assertEqual(m.digest({'b': 2, 'a': 1}), m.digest({'a': 1, 'b': 2}))

    def test_equal_copies_hit_but_mutated_content_does_not(self):
        value = {'a': [{'b': 'before'}], 'x': [1, 2]}
        with m.scope() as stats:
            first = m.digest(value)
            self.assertEqual(m.digest(json.loads(json.dumps(value))), first)
            value['a'][0]['b'] = 'after'
            self.assertNotEqual(m.digest(value), first)
            del value['a']; value['x'].reverse()
            self.assertEqual(m.digest(value), m.original(value))
            self.assertEqual(stats()['hits'], 1)

    def test_unsupported_values_preserve_original_behavior(self):
        class Text(str): pass
        class Mapping(dict): pass
        cyclic = []; cyclic.append(cyclic)
        for value in (1.5, -0.0, math.nan, math.inf, (1, 2), {1: 'x'},
                      {'x': 1, 2: 'y'}, {'x': Text('y')}, Mapping(a=1),
                      {1, 2}, cyclic, 2**300):
            with self.subTest(kind=type(value)), m.scope() as stats:
                try:
                    expected = m.original(value)
                except (ValueError, TypeError) as exc:
                    with self.assertRaises(type(exc)) as caught: m.digest(value)
                    self.assertEqual(str(caught.exception), str(exc))
                else:
                    self.assertEqual(m.digest(value), expected)
                self.assertEqual(stats()['entries'], 0)
                self.assertEqual(stats()['ineligibleBypasses'], 1)

    def test_traversal_and_entry_bounds_bypass_without_changing_result(self):
        nested = 1
        for _ in range(50): nested = [nested]
        for value in (nested, [0] * (m.MAX_NODES + 1), 'x' * m.MAX_ENTRY_BYTES):
            with m.scope() as stats:
                self.assertEqual(m.digest(value), m.original(value))
                self.assertEqual(stats()['entries'], 0)

    def test_capacity_bounds_and_retained_bytes(self):
        with patch.object(m, 'MAX_ENTRIES', 2), m.scope() as stats:
            for i in range(5): self.assertEqual(m.digest({'n': i}), m.original({'n': i}))
            self.assertEqual(stats()['entries'], 2)
            self.assertEqual(stats()['evictions'], 3)
        with patch.object(m, 'MAX_BYTES', 3000), m.scope() as stats:
            for i in range(10): m.digest({'n': i})
            self.assertLessEqual(stats()['retainedBytes'], 3000)
            self.assertGreater(stats()['evictions'], 0)
        self.assertEqual(stats()['retainedBytes'], 0)
        self.assertEqual(stats()['entries'], 0)

    def test_nested_scopes_disabled_default_and_failure_cleanup(self):
        value = {'x': 1}
        with patch.object(m, 'original', wraps=m.original) as compute:
            m.digest(value); m.digest(value)
            self.assertEqual(compute.call_count, 2)
        with m.scope() as outer:
            m.digest(value)
            with m.scope() as inner:
                m.digest(value)
                self.assertEqual(inner()['hits'], 0)
            with m.scope(enabled=False): m.digest(value)
            m.digest(value)
            self.assertEqual(outer()['hits'], 1)
        with self.assertRaisesRegex(ValueError, 'scope-test'):
            with m.scope() as failed:
                m.digest(value)
                raise ValueError('scope-test')
        self.assertEqual(failed()['entries'], 0)
        self.assertIsNone(m._SCOPE.get())

    def test_threads_do_not_inherit_active_reuse(self):
        with m.scope() as stats:
            m.digest({'x': 1})
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertIsNone(pool.submit(m._SCOPE.get).result())
            self.assertEqual(stats()['hits'], 0)

    def test_computation_failure_is_never_retained(self):
        with m.scope() as stats, patch.object(m, 'original', side_effect=ValueError('test')):
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, 'test'): m.digest({'x': 1})
            self.assertEqual(stats()['entries'], 0)
            self.assertEqual(stats()['failures'], 2)

    def test_computation_uses_immutable_snapshot_despite_external_mutation(self):
        value = {'x': 1}
        original = m.original
        def change(v):
            output = original(v)
            value['x'] += 1
            return output
        with m.scope() as stats, patch.object(m, 'original', change):
            self.assertEqual(m.digest(value), original({'x': 1}))
            self.assertEqual(m.digest(value), original({'x': 2}))
            self.assertEqual(stats()['entries'], 2)
            self.assertEqual(value, {'x': 3})

    def test_counter_report_contains_no_evidence(self):
        @m.operation
        def observe():
            m.digest({'PRIVATE_SENTINEL': 'PRIVATE_VALUE'})
            return {'state': 'done'}
        result = observe()
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertFalse(result['canonicalDigestReplay']['reusesValidationOrAuthorization'])
        self.assertIsNone(m._SCOPE.get())

    def test_equal_large_copies_share_storage_and_keep_distinct_record_hashes(self):
        value='X'*(1024*1024)
        expected=[m.original({'account':value,'record':i}) for i in range(24)]
        with m.scope() as stats:
            for _ in range(2):
                for i in range(24):
                    copy=value.encode().decode()
                    self.assertIsNot(copy,value)
                    self.assertEqual(m.digest({'account':copy,'record':i}),expected[i])
            self.assertEqual(stats()['hits'],24)
            self.assertEqual(stats()['sharedStrings'],1)
            self.assertEqual(stats()['sharedStringReferences'],24)
            self.assertLess(stats()['retainedBytes'],2*1024*1024)
            entries,_=m._SCOPE.get()
            held=[entry[2][0] for entry in entries.values()]
            self.assertTrue(all(s is held[0] for s in held))
        self.assertEqual(stats()['sharedStrings'],0)
        self.assertEqual(stats()['sharedStringBytes'],0)

    def test_eviction_releases_last_reference_and_counts_repeated_fields_once(self):
        a='A'*5000;b='B'*5000
        with patch.object(m,'MAX_ENTRIES',2),m.scope() as stats:
            m.digest({'a':a,'again':a})
            self.assertEqual(stats()['sharedStringReferences'],1)
            m.digest({'a':a,'tag':2})
            self.assertEqual(stats()['sharedStringReferences'],2)
            m.digest({'b':b})
            self.assertEqual(stats()['sharedStrings'],2)
            m.digest({'small':True})
            self.assertEqual(stats()['sharedStrings'],1)
            values,_=m._SCOPE.get()
            self.assertNotIn(a,values.strings)
            m.digest({'last':False})
            self.assertEqual(stats()['sharedStrings'],0)

    def test_sharing_preserves_per_input_size_limit_and_changed_content(self):
        text='a'*5000
        with m.scope() as stats:
            first=m.digest({'x':text})
            changed={'x':text[:-1]+'b'}
            self.assertNotEqual(first,m.digest(changed))
            self.assertEqual(m.digest(changed),m.original(changed))
            with patch.object(m,'MAX_ENTRY_BYTES',7000):
                repeated={'x':text,'y':text}
                self.assertEqual(m.digest(repeated),m.original(repeated))
                self.assertEqual(stats()['ineligibleBypasses'],1)
            self.assertEqual(stats()['entries'],2)

    def test_shared_storage_is_within_byte_budget_through_churn(self):
        with patch.object(m,'MAX_BYTES',14000),m.scope() as stats:
            for i in range(60):
                value={'x':chr(65+i%3)*5000,'i':i}
                self.assertEqual(m.digest(value),m.original(value))
                self.assertLessEqual(stats()['retainedBytes'],14000)
                values,_=m._SCOPE.get()
                # Every pool object has actual retained users; every retained
                # large atom is the exact same immutable object as in the pool.
                for s,(stored,refs,_) in values.strings.items():
                    users=[atom for _,_,atoms in values.values() for atom in atoms if atom==s]
                    self.assertEqual(len(users),refs)
                    self.assertTrue(all(atom is stored for atom in users))
            self.assertGreater(stats()['evictions'],0)
        self.assertEqual(stats()['retainedBytes'],0)

    def test_failed_large_computation_and_nested_scope_do_not_retain_strings(self):
        text='x'*5000
        with m.scope() as outer:
            m.digest(text)
            with m.scope() as inner:
                with patch.object(m,'original',side_effect=ValueError('failed')):
                    with self.assertRaises(ValueError):m.digest(text)
                self.assertEqual(inner()['sharedStrings'],0)
            self.assertEqual(outer()['sharedStrings'],1)
            self.assertEqual(m.digest(text),m.original(text))
            self.assertEqual(outer()['hits'],1)

    def test_last_user_eviction_recalculates_shared_cost_before_admission(self):
        text='x'*5000
        with patch.object(m,'MAX_BYTES',8536),m.scope() as stats:
            m.digest({'a':text})
            self.assertEqual(stats()['entries'],1)
            # Fits if the existing shared allocation is ignored, but cannot fit
            # after its last retained user is evicted. Never undercount it.
            value={'a':text,'b':text}
            self.assertEqual(m.digest(value),m.original(value))
            self.assertEqual(stats()['entries'],0)
            self.assertEqual(stats()['retainedBytes'],0)
            self.assertEqual(stats()['sharedStrings'],0)
            self.assertEqual(stats()['capacityBypasses'],1)

    def test_unicode_and_escaping_share_exact_content_only(self):
        values=['é'*5000,'😀'*5000,('"\\\n\t')*2000]
        with m.scope() as stats:
            for s in values:
                self.assertEqual(m.digest({s:s}),m.original({s:s}))
                self.assertEqual(m.digest({s.encode().decode():s.encode().decode()}),m.original({s:s}))
            self.assertEqual(stats()['sharedStrings'],3)
            self.assertEqual(stats()['hits'],3)

    def test_exact_hit_compares_current_content_without_rebuilding_snapshot(self):
        value={'format':'test','body':{'x':[1,True,None,'x'*5000]}}
        with m.scope() as stats,patch.object(m,'frozen',wraps=m.frozen) as freeze:
            first=m.digest(value)
            self.assertEqual(m.digest(json.loads(json.dumps(value))),first)
            self.assertEqual(freeze.call_count,1)
            value['body']['x'][0]=True
            self.assertNotEqual(m.digest(value),first)
            self.assertEqual(freeze.call_count,2)
            value['body']['x'][-1]='y'*5000
            self.assertEqual(m.digest(value),m.original(value))
            self.assertEqual(freeze.call_count,3)
            self.assertEqual(stats()['hits'],1)

    def test_candidate_index_collision_never_substitutes_full_content_equality(self):
        samples=[{'format':'test','body':x} for x in
                 [True,1,False,0,None,'',[],{},[1],[True],{'a':1},{'a':True}]]
        with m.scope() as stats:
            for v in samples:self.assertEqual(m.digest(v),m.original(v))
            for v in reversed(samples):self.assertEqual(m.digest(v),m.original(v))
            self.assertEqual(stats()['computations'],len(samples))
            self.assertEqual(stats()['hits'],len(samples))

    def test_same_mutable_object_mutations_and_cycles_cannot_hit_prior_snapshot(self):
        class Text(str):pass
        class Mapping(dict):pass
        v={'body':{'value':[1]}}
        with m.scope() as stats:
            m.digest(v)
            for item in [1.0,Text('x'),Mapping(a=1),(1,)]:
                v['body']['value']=item
                self.assertEqual(m.digest(v),m.original(v))
            v['body']['value']=v
            with self.assertRaises(ValueError):m.digest(v)
            self.assertEqual(stats()['hits'],0)

    def test_list_size_change_during_comparison_cannot_accept_partial_zip(self):
        for change in ('shrink','grow'):
            with self.subTest(change=change),m.scope() as stats:
                value={'body':[1,2]};first=m.digest(value);original=m.exact_match;changed=[]
                def mutate(v,k):
                    result=original(v,k)
                    if type(v) is int and v==1 and not changed:
                        changed.append(True)
                        if change=='shrink':value['body'].pop()
                        else:value['body'].append(3)
                    return result
                with patch.object(m,'exact_match',mutate):actual=m.digest(value)
                self.assertEqual(actual,m.original(value))
                self.assertNotEqual(actual,first)
                self.assertEqual(stats()['hits'],0)

    def test_bucket_indexes_are_bounded_evicted_and_cleared_with_entries(self):
        with patch.object(m,'MAX_ENTRIES',2),m.scope() as stats:
            values,_=m._SCOPE.get()
            for i in range(20):
                v={'format':str(i),'body':[i]}
                self.assertEqual(m.digest(v),m.original(v))
                self.assertEqual(sum(len(keys) for keys in values.buckets.values()),len(values))
                self.assertTrue(all(key in values for keys in values.buckets.values() for key in keys))
            self.assertEqual(stats()['evictions'],18)
        self.assertFalse(values.buckets)
        self.assertFalse(values.strings)

    def test_wide_roots_and_non_builtin_keys_keep_existing_lookup_behavior(self):
        class Text(str):pass
        for v in ({str(i):i for i in range(33)}, {'x'*129:1}, {Text('body'):1}):
            with m.scope():
                self.assertIsNone(m.bucket(v))
                self.assertEqual(m.digest(v),m.original(v))
                self.assertEqual(m.digest(v),m.original(v))



if __name__ == '__main__': unittest.main()
