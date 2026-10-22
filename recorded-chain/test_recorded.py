import base64
import copy
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from recorded_capture import Client, GENESIS, SYSTEM, collect, project_transaction, loads
from recorded_checks import synthetic, self_check
from recorded_cli import read
from review import review
from wire import verify_wire, verify_signed_message
from reconcile import digest

ROOT = Path(__file__).resolve().parent


class FakeOpener:
    def __init__(self, values): self.values, self.calls = values, []
    def open(self, request, timeout):
        payload = json.loads(request.data)
        self.calls.append((request, timeout, payload))
        value = self.values[len(self.calls) - 1]
        if isinstance(value, Exception): raise value
        if isinstance(value, bytes): return io.BytesIO(value)
        return io.BytesIO(json.dumps({'jsonrpc': '2.0', 'id': payload['id'], 'result': value}).encode())


def values(sample=True):
    c = synthetic(); e = c['evidence']
    discovery = [{'signature': c['signature'], 'slot': 100, 'err': None, 'confirmationStatus': 'finalized', 'memo': 'PRIVATE-MARKER'}]
    return [GENESIS['devnet']] + ([discovery] if sample else []) + [e[k]['result'] for k in
        ('transactionJson', 'transactionBase64', 'signatureStatus')] + [GENESIS['devnet']]


class ReviewTests(unittest.TestCase):
    def test_nine_synthetic_cases(self):
        self.assertEqual(self_check()['casesPassed'], 9)

    def test_recorded_devnet_bytes_verify_offline_and_leave_lookup_unknown(self):
        c = json.loads((ROOT / 'devnet-recorded-fixture.json').read_text())
        with patch('socket.socket', side_effect=AssertionError('no network')):
            result = review(c)
        self.assertEqual(result['state'], 'signed-message-consistent-lookup-unverified')
        self.assertEqual(result['wireSha256'], 'b2d81cfe11a665e78da18e59f82b157f95fec52ab695e8190f6054e83705b29c')
        self.assertTrue(result['signatureVerified']); self.assertTrue(result['wireAndJsonMatched'])
        self.assertTrue(result['rpcClusterIdentityMatched']); self.assertTrue(result['rpcFinalized'])
        self.assertEqual(result['lookupResolution'], 'unverified-rpc-addresses')
        wire = c['evidence']['transactionBase64']['result']['transaction'][0]
        with self.assertRaisesRegex(ValueError, 'lookup'): verify_wire(wire)

    def test_journal_identity_hash_preserved_from_prior_release(self):
        from selfcheck import fixture
        p, _ = fixture()
        w = verify_wire(p['signedTransactionBase64'])
        self.assertEqual(digest({'intent': p['intent'], 'wire': w}),
            '553f73921fc7c272a8505ce014b653341d0eff84d65ddf104102538ab91060a9')

    def test_both_genesis_responses_must_match(self):
        for key in ('genesisBefore', 'genesisAfter'):
            c = synthetic(); c['evidence'][key]['result'] = GENESIS['mainnet-beta']
            with self.subTest(key=key): self.assertEqual(review(c)['reason'], 'network-genesis-mismatch')

    def test_genesis_missing_does_not_claim_identity(self):
        c = synthetic(); c['evidence']['genesisAfter'] = {'state': 'http-error', 'httpStatus': 429}
        r = review(c)
        self.assertEqual(r['state'], 'unknown'); self.assertFalse(r['rpcClusterIdentityMatched'])

    def test_missing_history_and_provisional_are_unknown(self):
        for key in ('transactionJson', 'transactionBase64'):
            c = synthetic(); c['evidence'][key]['result'] = None
            self.assertEqual(review(c)['state'], 'unknown')
        for status in (None, 'confirmed', 'processed'):
            c = synthetic()
            if status is None: c['evidence']['signatureStatus']['result']['value'] = [None]
            else: c['evidence']['signatureStatus']['result']['value'][0]['confirmationStatus'] = status
            self.assertEqual(review(c)['state'], 'unknown')

    def test_slot_version_and_status_disagreement(self):
        for key in ('slot', 'version'):
            c = synthetic(); c['evidence']['transactionBase64']['result'][key] = 1
            self.assertEqual(review(c)['state'], 'mismatch')
        c = synthetic(); c['evidence']['signatureStatus']['result']['value'][0]['err'] = 'AccountNotFound'
        self.assertEqual(review(c)['reason'], 'status-error-disagreement')

    def test_metadata_differences_are_not_hidden(self):
        for key, value in (('fee', 1), ('preBalances', []), ('postTokenBalances', []), ('innerInstructions', None)):
            c = synthetic(); c['evidence']['transactionBase64']['result']['meta'][key] = value
            self.assertEqual(review(c)['reason'], 'cross-encoding-metadata-disagreement')

    def test_signed_bytes_and_json_message_must_agree(self):
        for field, value in (('recentBlockhash', SYSTEM), ('instructions', [])):
            c = synthetic(); c['evidence']['transactionJson']['result']['transaction']['message'][field] = value
            self.assertNotEqual(review(c)['state'], 'signed-transaction-consistent')

    def test_tampered_signature_is_not_verified(self):
        c = synthetic(); b = c['evidence']['transactionBase64']['result']['transaction']
        raw = bytearray(base64.b64decode(b[0])); raw[1] ^= 1; b[0] = base64.b64encode(raw).decode()
        r = review(c)
        self.assertEqual(r['reason'], 'invalid-ed25519-signature'); self.assertFalse(r['signatureVerified'])

    def test_changed_lookup_reference_breaks_wire_json_match(self):
        c = json.loads((ROOT / 'devnet-recorded-fixture.json').read_text())
        message = c['evidence']['transactionJson']['result']['transaction']['message']
        message['addressTableLookups'][0]['accountKey'] = SYSTEM
        r = review(c)
        self.assertEqual(r['reason'], 'wire-json-message-disagreement')

    def test_changed_resolved_address_cannot_be_claimed_verified(self):
        c = json.loads((ROOT / 'devnet-recorded-fixture.json').read_text())
        for key in ('transactionJson', 'transactionBase64'):
            c['evidence'][key]['result']['meta']['loadedAddresses']['writable'][0] = '11111111111111111111111111111112'
        r = review(c)
        self.assertEqual(r['lookupResolution'], 'unverified-rpc-addresses')
        self.assertFalse(r['executionApproved']); self.assertFalse(r['intentProven'])

    def test_missing_tokens_stay_unavailable_not_zero(self):
        c = synthetic()
        for key in ('transactionJson', 'transactionBase64'):
            c['evidence'][key]['result']['meta'].pop('preTokenBalances')
        r = review(c)
        self.assertEqual(r['state'], 'signed-transaction-consistent')
        self.assertEqual(r['tokenEvidence'], 'unavailable')

    def test_invalid_native_values_rejected_in_both_encodings(self):
        for value in (True, -1, 2**64, 1.5, '1'):
            c = synthetic()
            for key in ('transactionJson', 'transactionBase64'):
                c['evidence'][key]['result']['meta']['preBalances'][0] = value
            self.assertEqual(review(c)['state'], 'invalid-input')

    def test_discovery_is_bound_to_same_signature_slot_and_account(self):
        c = collect(sample=True, opener=FakeOpener(values()))
        self.assertEqual(review(c)['state'], 'signed-transaction-consistent')
        for field, value in (('signature', synthetic('create')['signature']), ('slot', 99), ('err', 'AccountNotFound')):
            b = copy.deepcopy(c); b['evidence']['discovery']['result'][0][field] = value
            self.assertEqual(review(b)['state'], 'mismatch')

    def test_failure_is_identity_result_not_successful_trade(self):
        r = review(synthetic('failed'))
        self.assertEqual(r['state'], 'signed-transaction-consistent')
        self.assertEqual(r['transactionOutcome'], 'rpc-reported-failure')
        self.assertFalse(r['intentProven']); self.assertFalse(r['executionApproved'])

    def test_original_evidence_not_mutated_and_output_omits_instructions(self):
        c = synthetic(); before = copy.deepcopy(c); result = review(c)
        self.assertEqual(c, before)
        for key in ('transaction', 'meta', 'instructions', 'signedTransactionBase64'): self.assertNotIn(key, result)

    def test_missing_or_timed_out_crypto_runtime_preserves_unknown_report(self):
        for error in (subprocess.TimeoutExpired('node', 5), OSError('PRIVATE'), ValueError('node-runtime-unavailable')):
            with patch('review.verify_signed_message', side_effect=error):
                result = review(synthetic())
            self.assertEqual(result['state'], 'unknown')
            self.assertEqual(result['reason'], 'signature-verifier-unavailable')
            self.assertNotIn('PRIVATE', json.dumps(result))

    def test_malformed_and_unsupported_are_not_passes(self):
        for c in (None, {}, {'format': 'other'}, {'format': 'recorded-chain-capture-1'}):
            self.assertEqual(review(c)['state'], 'invalid-input')
        c = synthetic(); c['evidence']['transactionBase64']['result']['transaction'][1] = 'base58'
        self.assertEqual(review(c)['state'], 'unsupported')


class TransportTests(unittest.TestCase):
    def test_exact_six_read_requests_sample_no_credentials_or_send(self):
        fake = FakeOpener(values()); c = collect(sample=True, opener=fake)
        self.assertEqual(c['rpcRequestsAttempted'], 6)
        self.assertEqual([r[2]['method'] for r in fake.calls], ['getGenesisHash', 'getSignaturesForAddress',
            'getTransaction', 'getTransaction', 'getSignatureStatuses', 'getGenesisHash'])
        for req, timeout, _ in fake.calls:
            self.assertEqual(req.full_url, 'https://api.devnet.solana.com')
            self.assertEqual(req.method, 'POST'); self.assertEqual(timeout, 10)
            self.assertIsNone(req.get_header('Authorization'))
        self.assertEqual(fake.calls[1][2]['params'], [SYSTEM, {'limit': 1, 'commitment': 'finalized'}])
        self.assertNotIn('PRIVATE-MARKER', json.dumps(c))

    def test_explicit_signature_uses_five_and_no_discovery(self):
        fake = FakeOpener(values(False))
        c = collect(signature=synthetic()['signature'], opener=fake)
        self.assertEqual(c['rpcRequestsAttempted'], 5)
        self.assertEqual(c['evidence']['discovery']['state'], 'not-requested')

    def test_wrong_cluster_stops_before_discovery(self):
        fake = FakeOpener([GENESIS['mainnet-beta']]); c = collect(sample=True, opener=fake)
        self.assertEqual(c['rpcRequestsAttempted'], 1)
        self.assertEqual(review(c)['reason'], 'network-genesis-mismatch')

    def test_http_429_and_network_error_stop_without_retry(self):
        for error in (urllib.error.HTTPError('https://example.invalid', 429, 'PRIVATE', {}, None), urllib.error.URLError('PRIVATE')):
            fake = FakeOpener([error]); c = collect(sample=True, opener=fake)
            self.assertEqual(c['rpcRequestsAttempted'], 1); self.assertNotIn('PRIVATE', json.dumps(c))

    def test_provider_error_and_wrong_id_are_sanitized(self):
        for raw in (b'{"jsonrpc":"2.0","id":1,"error":{"message":"PRIVATE"}}',
                    b'{"jsonrpc":"2.0","id":2,"result":"PRIVATE"}',
                    b'{"jsonrpc":"2.0","id":true,"result":"PRIVATE"}'):
            c = collect(sample=True, opener=FakeOpener([raw]))
            self.assertEqual(c['rpcRequestsAttempted'], 1); self.assertNotIn('PRIVATE', json.dumps(c))

    def test_duplicate_keys_nonfinite_and_byte_caps(self):
        for raw in (b'{"id":1,"id":2}', b'{"a":NaN}'):
            with self.assertRaises(ValueError): loads(raw)
        with patch('recorded_capture.MAX_RESPONSE', 16):
            c = collect(sample=True, opener=FakeOpener([b'X' * 17]))
        self.assertEqual(c['evidence']['genesisBefore']['state'], 'response-too-large')

    def test_discovery_empty_or_excessive_does_not_select_another(self):
        for rows in ([], values()[1] * 2):
            c = collect(sample=True, opener=FakeOpener([GENESIS['devnet'], rows]))
            self.assertEqual(c['rpcRequestsAttempted'], 2); self.assertIsNone(c['signature'])

    def test_failure_mid_capture_stops_further_requests(self):
        v = values(); v[3] = urllib.error.URLError('PRIVATE')
        c = collect(sample=True, opener=FakeOpener(v))
        self.assertEqual(c['rpcRequestsAttempted'], 4)
        self.assertEqual(c['evidence']['signatureStatus']['state'], 'not-requested')

    def test_methods_endpoints_caps_and_inputs_are_bounded(self):
        with self.assertRaises(ValueError): Client('https://example.invalid')
        client = Client('devnet', FakeOpener([GENESIS['devnet']] * 6))
        with self.assertRaises(ValueError): client.request('sendTransaction', [])
        for _ in range(6): client.request('getGenesisHash', [])
        with self.assertRaises(ValueError): client.request('getGenesisHash', [])
        for kwargs in ({'network': 'mainnet-beta', 'sample': True}, {'signature': 'NOT A SIGNATURE'}, {'sample': False}):
            with self.assertRaises(ValueError): collect(**kwargs)

    def test_redirects_and_environment_proxies_disabled(self):
        client = Client('devnet')
        self.assertFalse(any(isinstance(h, urllib.request.ProxyHandler) and h.proxies for h in client.opener.handlers))
        from recorded_capture import NoRedirect
        h = next(h for h in client.opener.handlers if isinstance(h, NoRedirect))
        self.assertIsNone(h.redirect_request(None, None, 302, 'moved', {}, 'https://example.invalid'))

    def test_transaction_projection_removes_logs_and_return_data(self):
        tx = synthetic()['evidence']['transactionJson']['result']
        tx['meta'].update(logMessages=['PRIVATE'], returnData={'data': 'PRIVATE'})
        tx['arbitrary'] = 'PRIVATE'
        self.assertNotIn('PRIVATE', json.dumps(project_transaction(tx)))

    def test_cli_offline_recorded_replay_is_private_and_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'report.json.gz'
            command = [sys.executable, str(ROOT / 'recorded_cli.py'), '--input', str(ROOT / 'devnet-recorded-fixture.json'), '--output', str(output)]
            p = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            with gzip.open(output, 'rt') as f: result = json.load(f)
            self.assertEqual(result['currentRunNetworkRequests'], 0)
            self.assertEqual(result['review']['state'], 'signed-message-consistent-lookup-unverified')
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(read(output), result['capture'])
            previous = output.read_bytes()
            p = subprocess.run(command, capture_output=True)
            self.assertNotEqual(p.returncode, 0); self.assertEqual(output.read_bytes(), previous)


if __name__ == '__main__': unittest.main()
