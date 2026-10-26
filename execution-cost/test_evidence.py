import base64
from copy import deepcopy
import io
import gzip
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from contract import digest
from examples import fixture as cost_fixture
from evidence import (VERSION, COMPUTE, SYSTEM, GENESIS, ENDPOINTS, MAX_RESPONSE,
                      collect, review, message_evidence, validate_input, rpc, NoRedirect)

NOW = 100000
WALLET = 'FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr'


def raw_key(key):
    n = 0
    for char in key:
        n = n * 58 + '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'.index(char)
    return b'\0' * (len(key)-len(key.lstrip('1'))) + n.to_bytes((n.bit_length()+7)//8, 'big')


def wire(*, v0=False, signed=False, limit=200000, price=25000, lookup=False, wallet=WALLET):
    # Deliberately a system transfer, NOT a swap. An acceptable fee envelope must
    # never be promoted to a verified quote/route by the integration.
    message = bytes([1, 0, 2, 3]) + b''.join(map(raw_key, [wallet, COMPUTE, SYSTEM])) + bytes([9])*32
    message += bytes([3, 1, 0, 5, 2]) + struct.pack('<I', limit)
    message += bytes([1, 0, 9, 3]) + struct.pack('<Q', price)
    message += bytes([2, 2, 0, 0, 12]) + struct.pack('<IQ', 2, 1)
    if v0:
        message = b'\x80' + message + (bytes([1])+bytes([3])*32+bytes([1, 0, 0]) if lookup else b'\0')
    return base64.b64encode(b'\x01' + (b'\x01' if signed else b'\0')*64 + message).decode()


def fixture():
    scenario = cost_fixture()
    scenario['nativeSpendableLamports'] = None
    for leg in ('entry', 'exit'):
        scenario['costs'][leg+'PriorityIncludedLamports'] = None
    return dict(format=VERSION, network='mainnet-beta', wallet=WALLET, scenario=scenario,
                entryTransactionBase64=wire(), exitTransactionBase64=wire(v0=True),
                reservations=dict(otherNativeLamports='2000', asOfMs=99000))


class Transport:
    def __init__(self, change=None):
        self.requests = []
        self.change = change or (lambda q, v: v)

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        q = json.loads(request.data)
        if q['method'] == 'getGenesisHash':
            value = GENESIS['devnet' if request.full_url == ENDPOINTS['devnet'] else 'mainnet-beta']
        elif q['method'] == 'getFeeForMessage':
            value = dict(context=dict(slot=100+q['id']), value=10000)
        else:
            value = dict(context=dict(slot=104), value=dict(owner=SYSTEM, executable=False,
                data=['', 'base64'], lamports=10000000, space=0, rentEpoch=2**64-1))
        return io.BytesIO(json.dumps(dict(jsonrpc='2.0', id=q['id'], result=self.change(q, value))).encode())


def captured(p=None, transport=None):
    p = fixture() if p is None else p
    return collect(p, opener=transport or Transport(), clock=lambda: NOW)


class EvidenceTests(unittest.TestCase):
    def test_end_to_end_raw_fee_balance_to_economics_does_not_validate_a_transfer_as_swap(self):
        p = fixture(); original = deepcopy(p); t = Transport()
        c = captured(p, t); r = review(p, c, now_ms=NOW)
        self.assertEqual(r['state'], 'fee-and-native-evidence-consistent', r)
        self.assertEqual(r['economics']['state'], 'modeled-constraints-met')
        self.assertEqual(r['feeAndNativeEvidence']['scenarioSpendableLamports'], '9998000')
        self.assertEqual(r['feeAndNativeEvidence']['messages']['entry']['priorityIncludedLamports'], '5000')
        self.assertEqual(r['economics']['calculation']['nativeReserveLamports'], '30000')
        for key in ('executionApproved', 'signingApproved', 'quoteMessageSemanticsVerified',
                    'reservationsVerified', 'principalBalanceVerified', 'inputAuthenticityVerified',
                    'productionStateChanged', 'modelEvaluated'):
            self.assertIs(r[key], False)
        self.assertEqual(p, original)
        self.assertEqual(len(t.requests), 5)
        requests = [json.loads(request.data) for request, _ in t.requests]
        self.assertEqual([q['method'] for q in requests],
                         ['getGenesisHash', 'getFeeForMessage', 'getFeeForMessage', 'getAccountInfo', 'getGenesisHash'])
        self.assertEqual(requests[2]['params'][1]['minContextSlot'], 102)
        self.assertEqual(requests[3]['params'][1]['minContextSlot'], 103)
        for request, timeout in t.requests:
            self.assertEqual(request.full_url, ENDPOINTS['mainnet-beta'])
            self.assertEqual(timeout, 5)
            self.assertNotIn('Authorization', request.headers)

    def test_devnet_fee_evidence_never_produces_usdc_economics(self):
        p = fixture(); p['network'] = 'devnet'
        r = review(p, captured(p), now_ms=NOW)
        self.assertEqual(r['state'], 'devnet-fee-evidence-only')
        self.assertIsNone(r['economics'])

    def test_unknown_reservations_or_costs_remain_unknown(self):
        for field in ('reservations', 'rent', 'cap'):
            p = fixture()
            if field == 'reservations': p['reservations'] = dict(otherNativeLamports=None, asOfMs=None)
            if field == 'rent': p['scenario']['costs']['rentDebitLamports'] = None
            if field == 'cap': p['scenario']['costs']['entryNetworkFeeCapLamports'] = None
            r = review(p, captured(p), now_ms=NOW)
            self.assertEqual(r['economics']['state'], 'unavailable', r)

    def test_native_shortfall_is_visible_not_a_margin_pass(self):
        p = fixture(); p['reservations']['otherNativeLamports'] = '9999999'
        r = review(p, captured(p), now_ms=NOW)
        self.assertEqual(r['economics']['state'], 'modeled-constraints-not-met')

    def test_fee_above_cap_and_fee_below_priority_are_rejected(self):
        for value in (10001, 4999):
            t = Transport(lambda q, v: dict(v, value=value) if q['method']=='getFeeForMessage' else v)
            r = review(fixture(), captured(transport=t), now_ms=NOW)
            self.assertEqual(r['state'], 'unavailable', r)
            self.assertIsNone(r['economics'])

    def test_reservations_cannot_exceed_native_balance(self):
        p = fixture(); p['reservations']['otherNativeLamports'] = '10000001'
        self.assertEqual(review(p, captured(p), now_ms=NOW)['reasons'], ['other-reservations-exceed-balance'])

    def test_signed_wrong_payer_lookup_and_malformed_messages_stop_before_requests(self):
        for value in (wire(signed=True), wire(wallet=SYSTEM), wire(v0=True, lookup=True), 'not-base64',
                      wire(limit=1400001), wire(limit=0)):
            p = fixture(); p['entryTransactionBase64'] = value; t = Transport()
            with self.assertRaises(ValueError): captured(p, t)
            self.assertEqual(t.requests, [])

    def test_message_change_changes_fee_identity(self):
        a = message_evidence(wire(), WALLET)
        b = message_evidence(wire(price=25001), WALLET)
        self.assertNotEqual(a['messageSha256'], b['messageSha256'])
        self.assertEqual(b['priorityLamports'], '5001')

    def test_caller_cannot_override_derived_balance_or_priority(self):
        for field in ('balance', 'priority'):
            p = fixture()
            if field == 'balance': p['scenario']['nativeSpendableLamports'] = '90000'
            else: p['scenario']['costs']['entryPriorityIncludedLamports'] = '0'
            with self.assertRaises(ValueError): captured(p)

    def test_capture_binds_full_input_including_quotes_and_reservations(self):
        p = fixture(); c = captured(p)
        p['scenario']['sell']['outAmount'] = '11000000'
        self.assertEqual(review(p, c, now_ms=NOW)['reasons'], ['capture-input-mismatch'])

    def test_changed_request_identity_or_row_order_refused(self):
        for mode in ('hash', 'order'):
            c = captured()
            if mode == 'hash': c['observations'][1]['requestSha256'] = '0'*64
            else: c['observations'][1], c['observations'][2] = c['observations'][2], c['observations'][1]
            self.assertEqual(review(fixture(), c, now_ms=NOW)['state'], 'unavailable')

    def test_stale_future_and_reordered_clocks_refused(self):
        for change in (lambda c: c.update(startedAtMs=NOW-10001),
                       lambda c: c.update(finishedAtMs=NOW+1),
                       lambda c: c['observations'][2].update(requestedAtMs=NOW-1)):
            c = captured(); change(c)
            self.assertEqual(review(fixture(), c, now_ms=NOW)['state'], 'unavailable')

    def test_stale_reservations_and_quotes_stop_without_reads(self):
        for field in ('quote', 'reservation'):
            p = fixture(); t = Transport()
            if field == 'quote': p['scenario']['buy']['requestedAtMs'] = 1
            else: p['reservations']['asOfMs'] = NOW-10001
            with self.assertRaises(ValueError): captured(p, t)
            self.assertEqual(t.requests, [])

    def test_genesis_mismatch_stops_and_final_genesis_is_required(self):
        for target, count in ((1, 1), (5, 5)):
            t = Transport(lambda q, v: GENESIS['devnet'] if q['id']==target else v)
            c = captured(transport=t)
            self.assertEqual(c['networkRequests'], count)
            self.assertEqual(review(fixture(), c, now_ms=NOW)['state'], 'unavailable')

    def test_slot_regression_and_null_fee_or_balance_never_become_zero(self):
        for target, field, value in ((3, 'slot', 101), (2, 'value', None), (4, 'value', None),
                                     (2, 'value', True), (2, 'value', -1), (2, 'value', 0)):
            def change(q, v):
                if q['id']==target:
                    if field == 'slot': v['context']['slot'] = value
                    else: v['value'] = value
                return v
            c = captured(transport=Transport(change))
            self.assertEqual(c['networkRequests'], target)
            self.assertEqual(review(fixture(), c, now_ms=NOW)['state'], 'unavailable')

    def test_non_system_wallet_and_account_data_refused(self):
        for field, value in (('owner', COMPUTE), ('executable', True), ('data', ['YQ==', 'base64']),
                             ('lamports', 2**64), ('space', 1)):
            def change(q, v):
                if q['id']==4: v['value'][field] = value
                return v
            c = captured(transport=Transport(change))
            self.assertEqual(review(fixture(), c, now_ms=NOW)['state'], 'unavailable')

    def test_no_arbitrary_provider_fields_exported(self):
        def change(q, v):
            if q['id']==4: v['value']['SECRET'] = 'do-not-export'
            return v
        c = captured(transport=Transport(change))
        self.assertNotIn('do-not-export', json.dumps(c))
        self.assertNotIn('TransactionBase64', json.dumps(review(fixture(), c, now_ms=NOW)))

    def test_deadline_stops_further_reads(self):
        ticks = iter([NOW, NOW, NOW, NOW+10001, NOW+10001])
        t = Transport(); c = collect(fixture(), opener=t, clock=lambda: next(ticks))
        self.assertEqual(c['networkRequests'], 1)
        self.assertEqual(c['stopReason'], 'capture-deadline')

    def test_transport_errors_bad_envelopes_duplicates_and_size_are_bounded(self):
        bodies = [b'{"jsonrpc":"2.0","id":1,"error":{"message":"SECRET"}}',
                  b'{"jsonrpc":"2.0","id":1,"id":1,"result":null}',
                  b'{"jsonrpc":"2.0","id":true,"result":null}',
                  b'{"jsonrpc":"2.0","id":1,"result":NaN}',
                  b'x'*(MAX_RESPONSE+1), b'not json']
        for body in bodies:
            opener = unittest.mock.Mock()
            opener.open.return_value = io.BytesIO(body)
            c = collect(fixture(), opener=opener, clock=lambda: NOW)
            self.assertEqual(c['networkRequests'], 1)
            self.assertEqual(c['stopReason'], 'rpc-evidence-unavailable')
            self.assertNotIn('SECRET', json.dumps(c))
        for error in (TimeoutError('SECRET'), urllib.error.HTTPError('SECRET',429,'SECRET',{},None)):
            opener = unittest.mock.Mock(); opener.open.side_effect = error
            c = collect(fixture(), opener=opener, clock=lambda: NOW)
            self.assertEqual(opener.open.call_count, 1)
            self.assertNotIn('SECRET', json.dumps(c))

    def test_transport_refuses_send_method_and_redirects(self):
        with self.assertRaises(ValueError): rpc('mainnet-beta', 'sendTransaction', [], 1, Transport())
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid'))

    def test_malformed_review_never_returns_positive(self):
        for p in (None, [], {}, dict(fixture(), network=[])):
            self.assertEqual(review(p, {}, now_ms=NOW)['state'], 'unavailable')

    def test_cli_requires_explicit_public_read(self):
        p = subprocess.run([sys.executable, str(Path(__file__).with_name('evidence_run.py')),
                            '--input', '/missing', '--output', '/missing-output'], capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn(b'--allow-public-read', p.stderr)

    def test_noncanonical_compute_budget_and_extra_compute_instructions_rejected(self):
        raw = bytearray(base64.b64decode(wire()))
        # Synthetic wire: signature envelope, header/count, keys, blockhash, ix count.
        first = 65+4+96+32+1
        for offset, byte in ((first+3, 1), (first+8+3, 2), (first+8+12, 1)):
            changed = raw[:]; changed[offset] = byte
            with self.assertRaises(ValueError): message_evidence(base64.b64encode(changed).decode(), WALLET)

    def test_integer_native_balance_above_javascript_safe_range_stays_exact(self):
        amount = 2**63-1
        def change(q, v):
            if q['id']==4: v['value']['lamports'] = amount
            return v
        r = review(fixture(), captured(transport=Transport(change)), now_ms=NOW)
        self.assertEqual(r['feeAndNativeEvidence']['scenarioSpendableLamports'], str(amount-2000))

    def test_replay_later_rechecks_original_freshness_without_refreshing_evidence(self):
        p = fixture(); c = captured(p)
        self.assertEqual(review(p, c, now_ms=NOW+5001)['state'], 'unavailable')
        self.assertEqual(c['startedAtMs'], NOW)

    def test_input_evidence_must_exist_before_capture_begins(self):
        p = fixture(); c = captured(p)
        c['startedAtMs'] = 99499  # before the supplied reverse quote was received
        self.assertEqual(review(p, c, now_ms=NOW)['state'], 'unavailable')

    def test_cli_exclusive_private_report_and_no_raw_message_export(self):
        import evidence_run
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source.json'; target = Path(directory)/'report.json.gz'
            source.write_text(json.dumps(fixture()))
            argv = ['evidence_run', '--input', str(source), '--output', str(target), '--allow-public-read']
            with patch.object(sys, 'argv', argv), patch.object(evidence_run, 'collect', return_value=captured()) as call, \
                 patch.object(evidence_run.time, 'time_ns', return_value=NOW*1000000):
                self.assertEqual(evidence_run.main(), 0)
                self.assertEqual(call.call_count, 1)
                call.reset_mock()
                with self.assertRaises(ValueError): evidence_run.main()
                call.assert_not_called()
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            data = json.loads(gzip.decompress(target.read_bytes()))
            self.assertEqual(data['review'], review(fixture(), data['capture'], now_ms=NOW))
            self.assertNotIn(fixture()['entryTransactionBase64'], json.dumps(data))


if __name__ == '__main__':
    unittest.main()
