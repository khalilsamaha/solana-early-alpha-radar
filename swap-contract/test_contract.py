import base64
import copy
import gzip
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from contract import (validate, PROGRAM, TOKEN, COMPUTE, NATIVE, U64, DISCRIMINATOR,
                      b58, decode_wire, decode, POLICY_ROLES)
from swap_fixtures import NOW, fixture, edit_wire, instruction_data, fake_key
from swap_checks import run


class ContractTests(unittest.TestCase):
    def rejected(self, packet, reason=None, now=NOW):
        result = validate(packet, now_ms=now)
        self.assertEqual(result['state'], 'rejected', result)
        if reason:
            self.assertEqual(result['reason'], reason)
        self.assertFalse(result['signingApproved'])
        self.assertFalse(result['executionApproved'])
        return result

    def test_legacy_and_v0_match_without_claiming_signing_or_state_verification(self):
        for version in ('legacy', 0):
            p = fixture(version); original = copy.deepcopy(p)
            r = validate(p, now_ms=NOW)
            self.assertEqual(r['state'], 'instruction-policy-match')
            self.assertEqual(r['priorityFeeLamports'], '1')
            self.assertEqual(r['validUntilExclusiveMs'], NOW + 9501)
            self.assertEqual(r['messageVersion'], version)
            self.assertEqual(p, original)
            for key in ('signingApproved', 'executionApproved', 'accountStateVerified', 'clusterVerified',
                        'blockhashValidityVerified', 'deployedProgramVerified', 'feeAssertionVerified',
                        'priorPolicyProven', 'simulationVerified', 'ledgerUpdated'):
                self.assertIs(r[key], False, key)

    def test_anchor_instruction_discriminator_is_frozen(self):
        self.assertEqual(DISCRIMINATOR.hex(), '8fbe5adac41e33de')

    def test_all_account_roles_are_bound_individually(self):
        for role in POLICY_ROLES:
            with self.subTest(role=role):
                p = fixture(); p['policy']['accounts'][role] = fake_key('replacement')
                self.rejected(p)

    def test_role_aliases_rejected_even_when_policy_and_message_agree(self):
        p = fixture(); p['policy']['accounts']['inputVault'] = p['policy']['accounts']['source']
        self.rejected(p, 'role-alias')

    def test_native_token_system_and_program_roles_rejected(self):
        for reserved in (NATIVE, TOKEN, COMPUTE, PROGRAM, '11111111111111111111111111111111'):
            p = fixture(); p['policy']['accounts']['inputMint'] = reserved
            self.rejected(p, 'reserved-role-key')

    def test_invalid_public_key_is_sanitized(self):
        for value in ('0'*44, '1'*33, 'x', None, {}, 7):
            p = fixture(); p['policy']['accounts']['wallet'] = value
            self.rejected(p, 'invalid-public-key')

    def test_amounts_are_positive_canonical_u64_strings(self):
        for field in ('amountIn', 'minimumAmountOut'):
            for value in ('0', '-1', '01', '1.0', '', str(U64+1), '9'*10000, 100, True, None):
                p = fixture(); p['policy'][field] = value
                self.rejected(p)

    def test_exact_amounts_and_minimum_not_quote_label(self):
        for offset in (8, 16):
            p = fixture(); raw = bytearray(decode(decode_wire(p['unsignedTransactionBase64'])[4]['transaction']['message']['instructions'][2]['data']))
            raw[offset] += 1
            instruction_data(p, 2, bytes(raw))
            self.rejected(p, 'input-amount-mismatch' if offset == 8 else 'minimum-output-mismatch')

    def test_large_amounts_do_not_use_floating_point(self):
        p = fixture(); p['policy']['amountIn'] = str(U64); p['policy']['minimumAmountOut'] = str(U64-1)
        instruction_data(p, 2, DISCRIMINATOR + struct.pack('<QQ', U64, U64-1))
        r = validate(p, now_ms=NOW)
        self.assertEqual(r['state'], 'instruction-policy-match')
        self.assertEqual(r['amountIn'], str(U64))

    def test_extra_instruction_and_account_are_rejected(self):
        p = edit_wire(fixture(), lambda m: m['instructions'].append({'programIdIndex': 0, 'accounts': [0], 'data': ''}))
        self.rejected(p, 'instruction-count')
        def extra(m):
            m['accountKeys'].append(fake_key('unused'))
            m['header']['numReadonlyUnsignedAccounts'] += 1
        self.rejected(edit_wire(fixture(), extra), 'unexpected-or-missing-account')

    def test_compute_order_duplicates_tags_and_lengths(self):
        for index, data in ((0,b'\x01'+bytes(4)), (0,b'\x02'+bytes(3)),
                            (1,b'\x02'+bytes(8)), (1,b'\x03'+bytes(9))):
            self.rejected(instruction_data(fixture(), index, data))
        def duplicate(m):
            m['instructions'][1] = copy.deepcopy(m['instructions'][0])
        self.rejected(edit_wire(fixture(), duplicate), 'compute-price-instruction')
        self.rejected(edit_wire(fixture(), lambda m: m['instructions'].reverse()), 'compute-instruction-contract')

    def test_compute_instructions_cannot_reference_accounts(self):
        self.rejected(edit_wire(fixture(), lambda m: m['instructions'][0].update(accounts=[0])), 'compute-instruction-contract')

    def test_compute_units_and_price_caps(self):
        for units in (0, 300001, 1400001):
            self.rejected(instruction_data(fixture(), 0, struct.pack('<BI', 2, units)), 'compute-budget-exceeded')
        self.rejected(instruction_data(fixture(), 1, struct.pack('<BQ', 3, 11)), 'compute-budget-exceeded')
        for value in (0, 1400001, True, 1.5, '300000'):
            p = fixture(); p['policy']['maxComputeUnits'] = value
            self.rejected(p, 'invalid-compute-cap')

    def test_priority_fee_ceiling_and_zero(self):
        for units, price, expected in ((200000, 0, '0'), (200000, 5, '1'), (200001, 5, '2')):
            p = instruction_data(fixture(), 0, struct.pack('<BI', 2, units))
            instruction_data(p, 1, struct.pack('<BQ', 3, price))
            self.assertEqual(validate(p, now_ms=NOW)['priorityFeeLamports'], expected)
        p = fixture(); p['policy']['maxPriorityFeeLamports'] = '0'
        self.rejected(p, 'priority-fee-exceeded')

    def test_priority_multiplication_large_integer_and_cap(self):
        p = fixture(); p['policy'].update(maxComputeUnits=1400000, maxMicroLamportsPerCU=str(U64),
            maxPriorityFeeLamports=str(U64), maxTotalFeeLamports=str(U64))
        instruction_data(p, 0, struct.pack('<BI', 2, 1400000))
        instruction_data(p, 1, struct.pack('<BQ', 3, U64))
        self.rejected(p, 'priority-fee-exceeded')

    def test_total_fee_bounds_and_binding(self):
        p = fixture(); p['feeAssertion']['lamports'] = '6001'
        self.rejected(p, 'total-fee-outside-bounds')
        p = instruction_data(fixture(), 1, struct.pack('<BQ', 3, 10)); p['feeAssertion']['lamports'] = '1'
        self.rejected(p, 'total-fee-outside-bounds')
        p = edit_wire(fixture(), lambda m: m['instructions'][1].update(data=b58(struct.pack('<BQ',3,2))), rebind_fee=False)
        self.rejected(p, 'fee-message-mismatch')
        p = fixture(); p['policy']['maxPriorityFeeLamports'] = '6001'
        self.rejected(p, 'inconsistent-fee-caps')

    def test_invalid_fee_assertions_and_caps(self):
        for field in ('maxMicroLamportsPerCU', 'maxPriorityFeeLamports', 'maxTotalFeeLamports'):
            for value in (None, True, -1, '01', str(U64+1)):
                p = fixture(); p['policy'][field] = value
                self.rejected(p)
        for value in ('0', None, 5001, '1.5', str(U64+1)):
            p = fixture(); p['feeAssertion']['lamports'] = value
            self.rejected(p, 'invalid-fee-assertion')

    def test_policy_clock_and_expiry_boundaries(self):
        self.rejected(fixture(), 'policy-expired-or-future', now=NOW-1001)
        self.rejected(fixture(), 'policy-expired-or-future', now=NOW+14000)
        p = fixture(); p['policy']['expiresAtMs'] += 1
        self.rejected(p, 'policy-expired-or-future')
        for bad in (True, -1, None, 1.1, 2**53):
            self.rejected(fixture(), 'invalid-clock', now=bad)

    def test_fee_age_and_policy_order(self):
        p = fixture(); p['policy']['issuedAtMs'] = NOW-11000; p['policy']['expiresAtMs'] = NOW+4000
        p['feeAssertion']['observedAtMs'] = NOW-10000
        self.assertEqual(validate(p, now_ms=NOW)['state'], 'instruction-policy-match')
        p['feeAssertion']['observedAtMs'] -= 1
        self.rejected(p, 'fee-assertion-stale-or-future')
        for value in (NOW+1, NOW-1001):
            p = fixture(); p['feeAssertion']['observedAtMs'] = value
            self.rejected(p, 'fee-assertion-stale-or-future')

    def test_blockhash_match_not_chain_liveness_claim(self):
        p = fixture(); p['policy']['blockhash'] = fake_key('other-blockhash')
        self.rejected(p, 'blockhash-mismatch')

    def test_swap_program_discriminator_and_length(self):
        self.rejected(edit_wire(fixture(), lambda m: m['instructions'][2].update(programIdIndex=m['accountKeys'].index(TOKEN))), 'swap-program-mismatch')
        for data in (bytes(24), DISCRIMINATOR+bytes(15), DISCRIMINATOR+bytes(17)):
            self.rejected(instruction_data(fixture(), 2, data), 'unsupported-swap-instruction')

    def test_all_swap_account_indices_and_count(self):
        for index in range(13):
            def change(m):
                m['instructions'][2]['accounts'][index] = m['accountKeys'].index(COMPUTE)
            self.rejected(edit_wire(fixture(), change), 'swap-account-role-mismatch')
        for accounts in ([], [0]*12, [0]*14):
            self.rejected(edit_wire(fixture(), lambda m: m['instructions'][2].update(accounts=accounts)), 'swap-account-role-mismatch')

    def test_write_permissions_cannot_expand_or_shrink(self):
        for shift in (-1, 1):
            def change(m):
                m['header']['numReadonlyUnsignedAccounts'] += shift
            self.rejected(edit_wire(fixture(), change), 'writable-privilege-mismatch')

    def test_signed_extra_signer_and_duplicate_keys(self):
        self.rejected(edit_wire(fixture(), lambda m: None, signatures=[bytes([3])*64]), 'requires-one-unsigned-signature')
        p = edit_wire(fixture(), lambda m: m['header'].update(numRequiredSignatures=2), signatures=[bytes(64),bytes(64)])
        self.rejected(p, 'requires-one-unsigned-signature')
        self.rejected(edit_wire(fixture(), lambda m: m['accountKeys'].__setitem__(1,m['accountKeys'][0])), 'malformed-or-unsupported-wire')

    def test_lookup_table_even_unused_is_unsupported(self):
        p = edit_wire(fixture(0), lambda m: m.update(addressTableLookups=[
            {'accountKey': fake_key('lookup'), 'writableIndexes': [], 'readonlyIndexes': []}]))
        self.rejected(p, 'lookup-tables-unsupported')

    def test_malformed_wire_version_trailing_bytes_index_and_shortvec(self):
        p = fixture(); raw = base64.b64decode(p['unsignedTransactionBase64'])
        malformed = (raw+b'\0', raw[:-1], b'\x81\x00'+raw[1:], raw[:65]+b'\x81'+raw[65:])
        for data in malformed:
            q = fixture(); q['unsignedTransactionBase64'] = base64.b64encode(data).decode()
            self.rejected(q, 'malformed-or-unsupported-wire')
        for data in ('!', 'a'*2000, None, 123):
            q = fixture(); q['unsignedTransactionBase64'] = data
            self.rejected(q, 'malformed-or-unsupported-wire')
        self.rejected(edit_wire(fixture(), lambda m: m['instructions'][2].update(programIdIndex=255)), 'malformed-or-unsupported-wire')

    def test_strict_schema_and_network_for_policy_and_fee(self):
        for section in (None, 'policy', 'feeAssertion'):
            p = fixture(); d = p if section is None else p[section]; d['unexpected'] = 'not exported'
            self.rejected(p)
        for section in ('policy', 'feeAssertion'):
            p = fixture(); p[section]['network'] = 'mainnet-beta'
            self.rejected(p)
        for packet in (None, [], {'format': 'anything'}):
            self.rejected(packet, 'packet-schema')

    def test_self_check_is_deterministic_and_expected_count(self):
        self.assertEqual(run(), run())
        self.assertEqual(run()['casesPassed'], 12)

    def test_cli_complete_private_report_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'check.json.gz'
            command = [sys.executable, str(Path(__file__).with_name('cli.py')), '--output', str(path)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            raw = path.read_bytes()
            report = json.loads(gzip.decompress(raw)); report.pop('capturedAt')
            self.assertEqual(report, run())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(raw, path.read_bytes())

    def test_cli_rejects_duplicate_json_keys_without_partial_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'input.json', Path(tmp)/'output.json.gz'
            source.write_text('{"format":"x","format":"y"}')
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('cli.py')),
                '--input', str(source), '--output', str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
