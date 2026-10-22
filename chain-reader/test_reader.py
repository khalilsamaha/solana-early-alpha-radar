import copy
import gzip
import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from reader import reconcile, fetch, rpc, base58, MAX_BYTES, NoRedirect
from fixtures import fixture, SIGNATURE, WALLET, MINT, ACCOUNT


class ReaderTests(unittest.TestCase):
    def result(self, b):
        r = reconcile(b, SIGNATURE, WALLET, MINT)
        self.assertFalse(r['executionApproved'])
        self.assertFalse(r['resubmitAllowed'])
        self.assertFalse(r['ledgerUpdated'])
        return r

    def test_finalized_legacy_exact_amounts_and_fee(self):
        r = self.result(fixture())
        self.assertEqual(r['state'], 'finalized-success')
        self.assertEqual(r['nativeBalance']['deltaLamports'], '-5000')
        self.assertEqual(r['tokenBalance']['deltaAtomic'], '123456')
        self.assertEqual(r['tokenBalance']['decimals'], 6)

    def test_v0_account_order_includes_loaded_addresses(self):
        b = fixture(); tx = b['transaction']['result']; tx['version'] = 0
        tx['transaction']['message']['accountKeys'] = [WALLET]
        tx['meta']['loadedAddresses'] = {'writable': [ACCOUNT], 'readonly': []}
        self.assertEqual(self.result(b)['tokenBalance']['accounts'][0]['account'], ACCOUNT)
        del tx['meta']['loadedAddresses']
        self.assertEqual(self.result(b)['state'], 'inconsistent-or-unsupported-evidence')

    def test_null_never_proves_failed_or_expired(self):
        b = fixture(); b['signatureStatus']['result']['value'] = [None]; b['transaction']['result'] = None
        self.assertEqual(self.result(b)['state'], 'not-found-unknown')
        b = fixture(); b['transaction']['result'] = None
        self.assertEqual(self.result(b)['state'], 'finalized-transaction-unavailable')

    def test_confirmation_is_provisional_even_if_confirmations_null(self):
        b = fixture(); s = b['signatureStatus']['result']['value'][0]
        s.update(confirmationStatus='confirmed', confirmations=None)
        r = self.result(b)
        self.assertEqual(r['state'], 'provisional-or-unconfirmed')
        self.assertIsNone(r['tokenBalance'])

    def test_failed_transaction_preserves_fee_evidence(self):
        b = fixture(); error = {'InstructionError': [0, 'InvalidArgument']}
        b['signatureStatus']['result']['value'][0]['err'] = error
        tx = b['transaction']['result']; tx['meta']['err'] = error
        tx['meta']['postTokenBalances'] = copy.deepcopy(tx['meta']['preTokenBalances'])
        r = self.result(b)
        self.assertEqual(r['state'], 'finalized-failed')
        self.assertEqual(r['nativeBalance']['transactionFeeLamports'], '5000')
        self.assertEqual(r['tokenBalance']['deltaAtomic'], '0')

    def test_mismatched_signature_slot_or_failure_rejects_balances(self):
        for mutate in (lambda tx: tx.update(slot=101),
                       lambda tx: tx['transaction'].update(signatures=['1' * 64]),
                       lambda tx: tx['meta'].update(err={'x': 1}),
                       lambda tx: tx.update(version=1)):
            b = fixture(); mutate(b['transaction']['result']); r = self.result(b)
            self.assertEqual(r['state'], 'inconsistent-or-unsupported-evidence')
            self.assertIsNone(r['nativeBalance'])

    def test_missing_owner_and_account_creation_remain_unknown(self):
        for change in ('owner', 'creation', 'closure'):
            b = fixture(); m = b['transaction']['result']['meta']
            if change == 'owner': del m['preTokenBalances'][0]['owner']
            if change == 'creation': m['preTokenBalances'] = []
            if change == 'closure': m['postTokenBalances'] = []
            r = self.result(b)
            self.assertEqual(r['state'], 'finalized-success')
            self.assertIsNone(r['tokenBalance']['deltaAtomic'])

    def test_duplicate_accounts_decimals_and_overflow_rejected(self):
        for change in ('duplicate', 'decimals', 'amount'):
            b = fixture(); m = b['transaction']['result']['meta']
            if change == 'duplicate': m['preTokenBalances'] *= 2
            if change == 'decimals': m['postTokenBalances'][0]['uiTokenAmount']['decimals'] = True
            if change == 'amount': m['postTokenBalances'][0]['uiTokenAmount']['amount'] = str(2**64)
            self.assertEqual(self.result(b)['state'], 'inconsistent-or-unsupported-evidence')

    def test_wallet_must_be_required_signer(self):
        b = fixture(); keys = b['transaction']['result']['transaction']['message']['accountKeys']
        keys.reverse()
        self.assertEqual(self.result(b)['state'], 'wallet-not-a-required-signer')

    def test_transport_failure_has_no_balance_inference(self):
        b = fixture(); b['transaction'] = {'state': 'network-error'}
        self.assertEqual(self.result(b)['state'], 'rpc-evidence-unavailable')

    def test_rpc_only_two_read_methods_fixed_finality_and_no_credentials(self):
        class Transport:
            calls = []
            def open(self, req, timeout):
                payload = json.loads(req.data); self.calls.append((req, payload, timeout))
                return io.BytesIO(json.dumps({'jsonrpc': '2.0', 'id': payload['id'], 'result': None}).encode())
        transport = Transport(); fetch('devnet', SIGNATURE, transport)
        self.assertEqual([c[1]['method'] for c in transport.calls], ['getSignatureStatuses', 'getTransaction'])
        self.assertEqual(transport.calls[1][1]['params'][1], {'commitment': 'finalized', 'encoding': 'json', 'maxSupportedTransactionVersion': 0})
        for req, _, timeout in transport.calls:
            self.assertEqual(req.full_url, 'https://api.devnet.solana.com')
            self.assertEqual(timeout, 10)
            self.assertIsNone(req.get_header('Authorization'))
        with self.assertRaises(ValueError): rpc('devnet', 'sendTransaction', [], 1, transport)
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def test_byte_cap_wrong_id_and_provider_messages_sanitized(self):
        class Transport:
            def __init__(self, body): self.body = body
            def open(self, req, timeout): return io.BytesIO(self.body)
        for body, state in [(b' ' * (MAX_BYTES + 1), 'response-too-large'),
                            (b'{"jsonrpc":"2.0","id":2,"result":null}', 'invalid-rpc-envelope'),
                            (b'{"jsonrpc":"2.0","id":1,"error":{"message":"arbitrary provider text"}}', 'rpc-error')]:
            r = rpc('devnet', 'getTransaction', [], 1, Transport(body))
            self.assertEqual(r, {'state': state})

    def test_identifiers_are_byte_validated(self):
        for invalid, size in [('NightFloat', 32), ('0' * 64, 64), (WALLET, 64), ('1' * 33, 32)]:
            with self.assertRaises(ValueError): base58(invalid, size)

    def test_offline_cli_is_private_atomic_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json.gz'
            args = [sys.executable, str(Path(__file__).with_name('run.py')), '--output', str(path)]
            subprocess.run(args, check=True, capture_output=True)
            r = json.loads(gzip.decompress(path.read_bytes()))
            self.assertEqual(r['rpcRequestsAttempted'], 0)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)


if __name__ == '__main__':
    unittest.main()
