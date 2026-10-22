import copy
import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from reconcile import reconcile, binding, TOKEN, NATIVE, SYSTEM
from intent_fixtures import fixture, pub, encode
from intent_cli import read


class IntentTests(unittest.TestCase):
    def check(self, bundle, state, reason=None):
        r = reconcile(bundle)
        self.assertEqual(r['state'], state, r)
        if reason: self.assertEqual(r['reason'], reason)
        self.assertFalse(r['executionApproved']); self.assertFalse(r['resubmitAllowed']); self.assertFalse(r['ledgerUpdated'])
        self.assertEqual(r['networkRequests'], 0)
        return r

    def tx(self, bundle): return bundle['rpcEvidence']['transaction']['result']

    def test_exact_input_minimum_output_and_fee(self):
        r = self.check(fixture(), 'balance-consistent-with-bound-message')
        self.assertEqual(r['tokenAccounts']['source']['deltaAtomic'], '-100')
        self.assertEqual(r['tokenAccounts']['destination']['deltaAtomic'], '200')
        self.assertEqual(r['native']['walletDeltaLamports'], '-5000')

    def test_creation_requires_funding_initialization_and_native_reconciliation(self):
        r = self.check(fixture('create'), 'balance-consistent-with-bound-message')
        self.assertEqual(r['native']['rentSpentLamports'], '2039280')
        self.assertEqual(r['native']['walletDeltaLamports'], '-2044280')
        self.assertEqual(r['tokenAccounts']['destination']['preAtomic'], '0')

    def test_closure_requires_explicit_refund_destination(self):
        r = self.check(fixture('close'), 'balance-consistent-with-bound-message')
        self.assertEqual(r['native']['rentRefundedLamports'], '2039280')
        b = fixture('close'); self.tx(b)['meta']['innerInstructions'][0]['instructions'][-1]['accounts'][1] = 5
        self.check(b, 'unknown', 'closure-instruction-unproven')

    def test_missing_creation_instruction_does_not_infer_zero(self):
        b = fixture('create'); self.tx(b)['meta']['innerInstructions'][0]['instructions'].pop(0)
        self.check(b, 'unknown', 'creation-instructions-unproven')

    def test_wrong_creation_owner_and_reversed_order(self):
        b = fixture('create'); ops = self.tx(b)['meta']['innerInstructions'][0]['instructions']
        ops[1]['data'] = encode(bytes([18]) + bytes([99]) * 32)
        self.check(b, 'mismatch', 'creation-owner-or-space-mismatch')
        b = fixture('create'); ops = self.tx(b)['meta']['innerInstructions'][0]['instructions']; ops[0], ops[1] = ops[1], ops[0]
        self.check(b, 'mismatch', 'creation-order-mismatch')

    def test_creation_rent_cap_and_balance_mismatch(self):
        b = fixture('create'); b['intent']['maximumRentLamports'] = '1'
        self.check(b, 'mismatch', 'rent-cap-exceeded')
        b = fixture('create'); self.tx(b)['meta']['postBalances'][2] += 1
        self.check(b, 'mismatch', 'creation-rent-mismatch')

    def test_missing_side_on_existing_account_is_unknown(self):
        b = fixture(); self.tx(b)['meta']['postTokenBalances'].pop(0)
        self.check(b, 'unknown', 'existing-account-balance-missing')

    def test_failed_receipt_reconciles_only_fee_and_unchanged_tokens(self):
        for lifecycle in ('existing', 'create', 'close'):
            r = self.check(fixture(lifecycle, failed=True), 'finalized-failure-fee-only')
            self.assertEqual(r['native']['walletDeltaLamports'], '-5000')
            self.assertEqual(r['native']['rentSpentLamports'], '0')

    def test_failed_receipt_cannot_change_token_balances(self):
        b = fixture(failed=True); self.tx(b)['meta']['postTokenBalances'][0]['uiTokenAmount']['amount'] = '999'
        self.check(b, 'mismatch', 'failed-transaction-changed-account')

    def test_missing_confirmed_and_rpc_failures_stay_unknown(self):
        for state in ('null', 'confirmed', 'network'):
            b = fixture()
            if state == 'null':
                b['rpcEvidence']['signatureStatus']['result']['value'] = [None]
                b['rpcEvidence']['transaction']['result'] = None
            if state == 'confirmed': b['rpcEvidence']['signatureStatus']['result']['value'][0]['confirmationStatus'] = 'confirmed'
            if state == 'network': b['rpcEvidence']['transaction'] = {'state': 'network-error'}
            self.check(b, 'unknown', 'chain-evidence-not-finalized-and-consistent')

    def test_different_signature_or_wallet_never_pass(self):
        b = fixture(); b['intent']['signature'] = encode(bytes([3]) * 64)
        self.check(b, 'unknown')
        b = fixture(); b['intent']['wallet'] = pub(99)
        self.check(b, 'unknown')

    def test_message_binding_catches_blockhash_instruction_and_key_mutation(self):
        mutations = [lambda m: m.update(recentBlockhash=pub(99)),
                     lambda m: m['instructions'][0].update(data='3'),
                     lambda m: m['instructions'][0]['accounts'].reverse()]
        for mutate in mutations:
            b = fixture(); mutate(self.tx(b)['transaction']['message'])
            self.check(b, 'mismatch', 'prepared-message-mismatch')

    def test_network_and_prior_time_disagreements(self):
        b = fixture(); b['network'] = 'mainnet-beta'
        self.check(b, 'mismatch', 'network-label-mismatch')
        b = fixture(); b['capturedAtMs'] = b['intent']['preparedAtMs'] - 1
        self.check(b, 'invalid-input', 'evidence-before-intent')

    def test_input_partial_fill_and_minimum_output(self):
        b = fixture(); self.tx(b)['meta']['postTokenBalances'][0]['uiTokenAmount']['amount'] = '901'
        self.check(b, 'mismatch', 'input-amount-mismatch')
        b = fixture(); b['intent']['minimumOutputAtomic'] = '201'
        self.check(b, 'mismatch', 'minimum-output-not-met')

    def test_native_debit_and_fee_cap(self):
        b = fixture(); self.tx(b)['meta']['postBalances'][0] -= 1
        self.check(b, 'mismatch', 'unexplained-native-wallet-change')
        b = fixture(); b['intent']['maximumFeeLamports'] = '4999'
        self.check(b, 'mismatch', 'fee-cap-exceeded')

    def test_prepared_native_and_token_balances_must_match(self):
        b = fixture(); b['intent']['walletPreLamports'] = '9999999'
        self.check(b, 'mismatch', 'wallet-prebalance-mismatch')
        b = fixture(); b['intent']['source']['preAmountAtomic'] = '1001'
        self.check(b, 'mismatch', 'token-prebalance-mismatch')

    def test_missing_token_program_and_wrong_owner(self):
        b = fixture(); del self.tx(b)['meta']['preTokenBalances'][0]['programId']
        self.check(b, 'unknown', 'token-identity-unavailable')
        b = fixture(); self.tx(b)['meta']['postTokenBalances'][0]['owner'] = pub(99)
        self.check(b, 'mismatch', 'token-account-identity-mismatch')

    def test_declared_mint_program_and_decimals_must_match_both_sides(self):
        for field, value in (('mint', pub(99)), ('programId', pub(99)), ('decimals', 9)):
            b = fixture(); row = self.tx(b)['meta']['postTokenBalances'][1]
            if field == 'decimals': row['uiTokenAmount']['decimals'] = value
            else: row[field] = value
            self.check(b, 'mismatch', 'token-account-identity-mismatch')

    def test_unrelated_wallet_token_debit_detected(self):
        b = fixture(); meta = self.tx(b)['meta']
        for field in ('preTokenBalances','postTokenBalances'): meta[field][2]['owner'] = b['intent']['wallet']
        self.check(b, 'mismatch', 'unexpected-wallet-token-change')

    def test_token_2022_and_wrapped_native_explicitly_unsupported(self):
        b = fixture(); b['intent']['source']['programId'] = pub(99)
        self.check(b, 'unsupported', 'token-program-not-supported')
        b = fixture(); b['intent']['source']['mint'] = NATIVE
        self.check(b, 'unsupported', 'wrapped-native-not-supported')

    def test_approval_operation_not_treated_as_transfer(self):
        b = fixture(); self.tx(b)['meta']['innerInstructions'][0]['instructions'][0]['data'] = encode(bytes([4]) + (100).to_bytes(8,'little'))
        self.check(b, 'unsupported', 'unsupported-token-account-operation')

    def test_malformed_transfer_layout_not_accepted(self):
        b = fixture(); self.tx(b)['meta']['innerInstructions'][0]['instructions'][0]['data'] = encode(bytes([3]))
        self.check(b, 'unsupported', 'unsupported-token-account-operation')

    def test_system_change_to_existing_token_account_not_accepted(self):
        b = fixture(); tx = self.tx(b)
        tx['meta']['innerInstructions'][0]['instructions'][0]['programIdIndex'] = tx['transaction']['message']['accountKeys'].index(SYSTEM)
        self.check(b, 'unsupported', 'unsupported-token-account-operation')

    def test_missing_inner_instructions_and_duplicate_groups(self):
        b = fixture(); self.tx(b)['meta']['innerInstructions'] = None
        self.check(b, 'unknown', 'inner-instructions-unavailable')
        b = fixture(); self.tx(b)['meta']['innerInstructions'] *= 2
        self.check(b, 'unknown', 'inner-instructions-unavailable')

    def test_v0_binding_preserves_loaded_keys_and_rejects_replacement(self):
        b = fixture(); tx = self.tx(b); message = tx['transaction']['message']
        last = message['accountKeys'].pop(); tx['version'] = 0
        message['header']['numReadonlyUnsignedAccounts'] -= 1
        message['addressTableLookups'] = [{'accountKey': pub(30), 'readonlyIndexes': [1], 'writableIndexes': []}]
        tx['meta']['loadedAddresses'] = {'writable': [], 'readonly': [last]}
        b['intent']['messageSha256'] = binding(tx)[0]
        self.check(b, 'balance-consistent-with-bound-message')
        tx['meta']['loadedAddresses']['readonly'][0] = pub(31)
        self.check(b, 'mismatch', 'prepared-message-mismatch')

    def test_strict_atomic_schema_and_unsupported_fields(self):
        for value in (100, True, '01', str(2**64), '-1'):
            b = fixture(); b['intent']['inputAtomic'] = value
            self.check(b, 'invalid-input')
        b = fixture(); b['intent']['allowSubmit'] = True
        self.check(b, 'invalid-input', 'invalid-intent-schema')

    def test_no_rpc_calls_and_input_evidence_unchanged(self):
        b = fixture(); before = copy.deepcopy(b)
        with patch('reader.fetch', side_effect=AssertionError('No RPC')):
            self.check(b, 'balance-consistent-with-bound-message')
        self.assertEqual(b, before)

    def test_duplicate_keys_nonfinite_and_oversize_input_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'input.json.gz'
            for raw in (b'{"intent":1,"intent":2}', b'{"x":NaN}', b' ' * (4 * 1024 * 1024 + 1)):
                p.write_bytes(gzip.compress(raw))
                with self.assertRaises(ValueError): read(p)

    def test_selfcheck_cli_and_report_are_private_and_exclusive(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'report.json.gz'
            args = [sys.executable, str(Path(__file__).with_name('intent_cli.py')), '--output', str(p)]
            subprocess.run(args, check=True, capture_output=True)
            r = json.loads(gzip.decompress(p.read_bytes()))
            self.assertEqual(len(r['cases']), 6); self.assertEqual(r['networkRequests'], 0)
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(subprocess.run(args,capture_output=True).returncode, 0)

    def test_cli_reads_supplied_evidence_without_publishing_raw_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'source.json'; output = root/'report.json.gz'
            b = fixture(); b['rpcEvidence']['transaction']['result']['meta']['logMessages'] = ['arbitrary excluded text']
            source.write_text(json.dumps(b))
            subprocess.run([sys.executable, str(Path(__file__).with_name('intent_cli.py')), '--input', str(source), '--output', str(output)], check=True,capture_output=True)
            raw = gzip.decompress(output.read_bytes()); self.assertNotIn(b'arbitrary excluded text',raw)
            self.assertEqual(json.loads(raw)['state'], 'balance-consistent-with-bound-message')


if __name__ == '__main__': unittest.main()
