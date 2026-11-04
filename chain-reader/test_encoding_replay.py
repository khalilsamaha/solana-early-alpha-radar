"""Exact conversion equivalence; reuse never becomes evidence approval."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'intent-journal'))
import wire
import reconcile
import reader
import encoding_replay as m


def outcome(fn, *args):
    try:
        return ('value', fn(*args))
    except Exception as exc:
        return ('error', type(exc), str(exc), getattr(exc, 'reason', None))


class EncodingTests(unittest.TestCase):
    def test_canonical_and_leading_zero_inputs_match_uncached_implementations(self):
        rng = random.Random(42)
        values = [b'', bytes(32), bytes(64), b'\0\0\x01']
        values += [rng.randbytes(n) for n in range(1, 66)]
        with m.scope() as stats:
            for raw in values:
                expected = wire._b58(raw)
                for _ in range(2):
                    self.assertEqual(wire.b58(raw), expected)
                    self.assertEqual(reconcile.decode(expected), reconcile._decode(expected))
                    for size in (32, 64):
                        self.assertEqual(outcome(reader.base58, expected, size),
                                         outcome(reader._base58, expected, size))
            self.assertGreater(stats()['hits'], 0)
            self.assertLessEqual(stats()['entries'], m.MAX_ENTRIES)

    def test_errors_wrong_lengths_noncanonical_inputs_and_subclasses_match(self):
        class Text(str): pass
        class Bytes(bytes): pass
        values = [None, [], {}, 12, True, '', '0', 'O', 'I', 'l', 'é', '1'*91,
                  '1'*1801, '1'*31, '1'*32, '1'*64, '1'*65, Text('1'*32)]
        with m.scope():
            for value in values:
                for _ in range(2):
                    self.assertEqual(outcome(reconcile.decode, value), outcome(reconcile._decode, value))
                    for size in (32, 64, True, None, 0, 33):
                        self.assertEqual(outcome(reader.base58, value, size), outcome(reader._base58, value, size))
            for raw in (None, [], {}, bytearray(b'a'), Bytes(b'a'), bytes(100)):
                self.assertEqual(outcome(wire.b58, raw), outcome(wire._b58, raw))

    def test_exact_input_kind_and_expected_length_are_separate(self):
        with m.scope() as stats:
            self.assertEqual(reader.base58('1'*32, 32), '1'*32)
            with self.assertRaises(ValueError): reader.base58('1'*32, 64)
            self.assertEqual(reconcile.decode('1'*32), bytes(32))
            self.assertEqual(wire.b58(bytes(32)), '1'*32)
            self.assertEqual(reader.base58('1'*64, 64), '1'*64)
            self.assertEqual(stats()['entries'], 4)
            self.assertEqual(stats()['failures'], 1)
            self.assertEqual(stats()['hits'], 0)

    def test_failed_computations_are_not_cached(self):
        with m.scope() as stats, patch.object(reconcile, '_decode', wraps=reconcile._decode) as compute:
            for _ in range(2):
                with self.assertRaises(reconcile.EvidenceError): reconcile.decode('0')
            self.assertEqual(compute.call_count, 2)
            self.assertEqual(stats()['entries'], 0)
            self.assertEqual(stats()['failures'], 2)

    def test_bound_bypasses_without_eviction_or_semantic_change(self):
        with m.scope() as stats:
            for i in range(m.MAX_ENTRIES):
                self.assertEqual(wire.b58(i.to_bytes(32, 'big')), wire._b58(i.to_bytes(32, 'big')))
            overflow = (m.MAX_ENTRIES+1).to_bytes(32, 'big')
            with patch.object(wire, '_b58', wraps=wire._b58) as compute:
                wire.b58(overflow);wire.b58(overflow);wire.b58(bytes(32))
                self.assertEqual(compute.call_count, 2)
            self.assertEqual(stats()['entries'], m.MAX_ENTRIES)
            self.assertEqual(stats()['capacityBypasses'], 2)
            self.assertEqual(stats()['hits'], 1)

    def test_no_scope_is_uncached_and_nested_scope_is_independent(self):
        raw = bytes(32)
        with patch.object(wire, '_b58', wraps=wire._b58) as compute:
            wire.b58(raw);wire.b58(raw)
            self.assertEqual(compute.call_count, 2)
            with m.scope() as outer:
                wire.b58(raw)
                with m.scope() as inner:
                    wire.b58(raw);wire.b58(raw)
                    self.assertEqual(inner()['hits'], 1)
                self.assertEqual(inner()['entries'], 0)
                wire.b58(raw)
                self.assertEqual(outer()['hits'], 1)
                with m.scope(enabled=False): wire.b58(raw);wire.b58(raw)
                self.assertEqual(outer()['hits'], 1)
            self.assertEqual(outer()['entries'], 0)
            wire.b58(raw)
            self.assertEqual(compute.call_count, 7)
        self.assertIsNone(m._SCOPE.get())

    def test_exception_cleanup_threads_and_report_do_not_leak_values(self):
        secret = bytes(range(32))
        with self.assertRaises(KeyboardInterrupt):
            with m.scope() as stats:
                wire.b58(secret)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    self.assertIsNone(pool.submit(m._SCOPE.get).result())
                report = stats();report['entries'] = 999
                self.assertEqual(stats()['entries'], 1)
                self.assertNotIn(wire._b58(secret), str(stats()))
                raise KeyboardInterrupt()
        self.assertIsNone(m._SCOPE.get());self.assertEqual(stats()['entries'], 0)

    def test_only_bounded_immutable_results_are_stored(self):
        with m.scope() as stats:
            for value in ({}, [], bytearray(b'a'), 'a'*91):
                for _ in range(2): self.assertIs(m.replay('encode', b'a', lambda:value), value)
            for kind, value in (([], b'a'), ('unknown', b'a'), ('encode', b'a'*65)):
                self.assertEqual(m.replay(kind, value, lambda:'ok'), 'ok')
            self.assertEqual(stats()['entries'], 0)
            self.assertEqual(stats()['ineligibleBypasses'], 3)

    def test_operation_scopes_report_and_cleanup_without_authorization(self):
        @m.operation
        def operation(fail=False):
            wire.b58(bytes(32));wire.b58(bytes(32))
            if fail: raise RuntimeError('failure')
            return dict(state='original')
        for _ in range(2):
            result = operation()
            self.assertEqual(result['state'], 'original')
            self.assertEqual(result['encodingReplay']['computations'], 1)
            self.assertEqual(result['encodingReplay']['hits'], 1)
            self.assertFalse(result['encodingReplay']['storesStateOrAuthorization'])
        with self.assertRaises(RuntimeError): operation(True)
        self.assertIsNone(m._SCOPE.get())

    def test_encoding_hits_do_not_replace_signature_authentication(self):
        import base64, json
        fixtures = json.loads(Path(wire.__file__).with_name('public-fixtures.json').read_text())
        signed = fixtures['existing']['signedTransactionBase64']
        original = wire.subprocess.run
        with m.scope() as stats, patch.object(wire.subprocess, 'run', wraps=original) as verifier:
            wire.verify_wire(signed);wire.verify_wire(signed)
            raw = bytearray(base64.b64decode(signed));raw[1] ^= 1
            with self.assertRaisesRegex(ValueError, 'invalid-ed25519-signature'):
                wire.verify_wire(base64.b64encode(raw).decode())
            self.assertEqual(verifier.call_count, 3)
            self.assertGreater(stats()['hits'], 0)

    def test_current_clocks_and_mutated_policy_are_still_revalidated(self):
        # Identifier reuse must never reuse an enclosing policy decision.
        from copy import deepcopy
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'swap-contract'))
        import contract, swap_fixtures
        packet = swap_fixtures.fixture()
        now = swap_fixtures.NOW
        with m.scope():
            self.assertEqual(contract._validate(packet, now)['state'], 'instruction-policy-match')
            with self.assertRaises(contract.Rejected): contract._validate(packet, packet['policy']['expiresAtMs'])
            changed = deepcopy(packet);changed['policy']['amountIn'] = '999999'
            with self.assertRaises(contract.Rejected): contract._validate(changed, now)
            changed = deepcopy(packet);changed['policy']['accounts']['wallet'] = '1'*32
            with self.assertRaises(contract.Rejected): contract._validate(changed, now)


if __name__ == '__main__': unittest.main()
