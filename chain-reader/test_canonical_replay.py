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


if __name__ == '__main__': unittest.main()
