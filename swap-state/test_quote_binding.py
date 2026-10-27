import copy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from quote_binding import review, VERSION, PROGRAM, MAX_AGE_MS, U64
from state_fixtures import fixture, NOW, change_row, fake_key
from swap_fixtures import edit_wire
from contract import decode


from quote_checks import bundle, run


class BindingTests(unittest.TestCase):
    def blocked(self, b, reason=None, now=NOW):
        r = review(b, now_ms=now)
        self.assertEqual(r['state'], 'unavailable', r)
        self.assertIsNone(r['binding'])
        self.assertFalse(r['executionApproved'])
        if reason:
            self.assertEqual(r['reasons'], [reason])
        return r

    def test_both_pool_orientations_bind_exact_bytes_and_declared_funding(self):
        for reverse in (False, True):
            b = bundle(reverse); before = copy.deepcopy(b)
            r = review(b, now_ms=NOW)
            self.assertEqual(r['state'], 'declared-quote-state-consistent', r)
            self.assertEqual(r['binding']['tokenSpendableAtomic'], '100')
            self.assertEqual(r['binding']['nativeSpendableLamports'], '6000')
            self.assertEqual(r['binding']['rpcMessageFeeLamports'], '5001')
            self.assertEqual(r['binding']['priorityIncludedLamports'], '1')
            self.assertEqual(r['binding']['newAccountRentDebitLamports'], '0')
            self.assertEqual(b, before)
            for k in ('executionApproved', 'signingApproved', 'ledgerUpdated', 'quoteAuthenticityVerified',
                      'reservationsVerified', 'mainnetSupported', 'programDeploymentVerified', 'simulationVerified'):
                self.assertIs(r[k], False)
            for k in ('networkRequests', 'signaturesCreated', 'transactionsSent'):
                self.assertEqual(r[k], 0)

    def test_quote_account_roles_cannot_drift(self):
        for k in ('pool', 'wallet', 'source', 'destination', 'inputMint', 'outputMint'):
            b = bundle(); b['quote'][k] = fake_key('wrong')
            self.blocked(b, 'quote-account-mismatch')

    def test_network_and_program_are_fixed(self):
        for k, v in (('network', 'mainnet-beta'), ('program', fake_key('router'))):
            b = bundle(); b['quote'][k] = v
            self.blocked(b, 'unsupported-route')

    def test_unsigned_message_must_still_match_policy(self):
        b = bundle(); b['capture']['packet']['policy']['amountIn'] = '101'
        self.blocked(b, 'instruction-policy-not-current')
        b = bundle(); edit_wire(b['capture']['packet'], lambda m: m['instructions'].append(m['instructions'][2]))
        self.blocked(b, 'instruction-policy-not-current')

    def test_quote_amounts_and_minimum_bind_instruction(self):
        for k, v in (('inAmount', '101'), ('minimumOutAmount', '191')):
            b = bundle(); b['quote'][k] = v
            self.blocked(b, 'quote-instruction-amount-mismatch')

    def test_minimum_bound_uses_ceil_and_never_exceeds_quote(self):
        b = bundle(); b['quote']['outAmount'] = '201'
        self.blocked(b, 'quote-minimum-outside-bound')  # 190.95 cannot become 190
        b = bundle(); b['quote']['outAmount'] = '189'
        self.blocked(b, 'quote-minimum-outside-bound')
        b = bundle(); b['maxSlippageBps'] = 499
        self.blocked(b, 'quote-minimum-outside-bound')

    def test_strict_amounts_and_slippage_types(self):
        for v in (True, 100, '01', '1e2', '-1', '0', str(U64+1), None):
            b = bundle(); b['quote']['inAmount'] = v
            self.blocked(b, 'invalid-quote-amount')
        for v in (True, -1, 10000, 0.5, '500'):
            b = bundle(); b['maxSlippageBps'] = v
            self.blocked(b, 'invalid-slippage')

    def test_quote_policy_and_capture_have_causal_order(self):
        b = bundle(); b['quote']['receivedAtMs'] = NOW-999
        self.blocked(b, 'quote-policy-capture-order')
        b = bundle(); b['capture']['startedAtMs'] = NOW-1001
        self.blocked(b, 'quote-policy-capture-order')
        b = bundle(); b['quote']['requestedAtMs'] = NOW-1100
        self.blocked(b, 'quote-stale-or-future')

    def test_original_request_age_not_response_or_review_time(self):
        b = bundle(); b['quote']['requestedAtMs'] = NOW-MAX_AGE_MS-1
        self.blocked(b, 'quote-stale-or-future')
        b = bundle(); b['quote']['receivedAtMs'] = NOW+1
        self.blocked(b, 'quote-stale-or-future')
        b = bundle(); b['quote']['requestedAtMs'] = NOW-MAX_AGE_MS
        self.assertEqual(review(b, now_ms=NOW)['state'], 'declared-quote-state-consistent')
        self.blocked(b, 'quote-stale-or-future', now=NOW+1)

    def test_invalid_clock_and_expired_policy(self):
        self.blocked(bundle(), 'invalid-clock', now=True)
        b = bundle(); b['capture']['packet']['policy']['expiresAtMs'] = NOW
        self.blocked(b, 'instruction-policy-not-current')

    def test_state_capture_future_and_too_old(self):
        b = bundle(); b['capture']['finishedAtMs'] = NOW+1
        self.blocked(b, 'capture-stale-or-future')
        b = bundle(); b['capture']['startedAtMs'] = NOW-MAX_AGE_MS-1
        self.blocked(b, 'capture-stale-or-future')

    def test_state_must_include_prior_packet_not_summary(self):
        b = bundle(); b['capture'] = {'state': 'policy-state-consistent'}
        self.blocked(b, 'prior-packet-required')
        b = bundle(); b['capture']['evidence']['fee']['result']['value'] = 9999
        self.blocked(b, 'account-or-message-evidence-rejected')

    def test_token_owner_mint_frozen_missing_and_extensions(self):
        for index, offset, data in ((9,32,decode(fake_key('attacker'))),
                                    (10,0,decode(fake_key('wrong-mint'))), (9,108,b'\x02')):
            b = bundle(); change_row(b['capture'], index, offset, data)
            self.blocked(b, 'account-or-message-evidence-rejected')
        for value in (None, {'owner': 'Token2022'}):
            b = bundle(); b['capture']['evidence']['accounts']['result']['value'][9] = value
            self.blocked(b, 'account-or-message-evidence-rejected')

    def test_delegate_and_close_authority_do_not_pass(self):
        for offset in (72,129):
            b = bundle(); change_row(b['capture'],9,offset,(1).to_bytes(4,'little')+decode(fake_key('other')))
            self.blocked(b, 'account-or-message-evidence-rejected')

    def test_pool_blockers_and_mint_authorities_fail_closed(self):
        b = bundle(); change_row(b['capture'],0,329,b'\x04')
        self.blocked(b, 'pool-eligibility-blocked')
        b = bundle(); change_row(b['capture'],2,0,(1).to_bytes(4,'little')+decode(fake_key('mint-authority')))
        self.blocked(b, 'mint-authority-present')

    def test_quoted_slot_cannot_postdate_account_snapshot(self):
        b = bundle(); b['quote']['contextSlot'] = 102
        self.blocked(b, 'account-state-predates-quote-slot')
        b = bundle(); b['quote']['contextSlot'] = True
        self.blocked(b, 'quote-slot')

    def test_quote_output_needs_reserve_and_destination_space(self):
        b = bundle(); change_row(b['capture'],5,64,(195).to_bytes(8,'little'))
        self.blocked(b, 'quote-output-exceeds-reserve')
        b = bundle(); change_row(b['capture'],10,64,(U64-195).to_bytes(8,'little'))
        self.blocked(b, 'quoted-destination-overflow')

    def test_reserved_tokens_and_native_cannot_be_spent_twice(self):
        b = bundle(); b['reservations']['otherTokenAtomic'] = '901'
        self.blocked(b, 'token-funding-shortfall')
        b = bundle(); b['reservations']['otherNativeLamports'] = '94001'
        self.blocked(b, 'native-funding-shortfall')

    def test_unknown_reservations_never_become_zero(self):
        for k in ('otherTokenAtomic','otherNativeLamports','asOfMs'):
            b = bundle(); b['reservations'][k] = None
            self.blocked(b, 'reservation-evidence-unavailable')

    def test_reservations_bind_source_wallet_mint_and_time(self):
        for k in ('source','wallet','inputMint'):
            b = bundle(); b['reservations'][k] = fake_key('other')
            self.blocked(b, 'reservation-account-mismatch')
        for t in (NOW-499, NOW-MAX_AGE_MS-1):
            b = bundle(); b['reservations']['asOfMs'] = t
            self.blocked(b, 'reservation-stale-or-after-capture')

    def test_evidence_hash_changes_when_known_reservation_changes(self):
        b = bundle(); first = review(b, now_ms=NOW)['binding']
        b['reservations']['otherTokenAtomic'] = '899'
        second = review(b, now_ms=NOW)['binding']
        self.assertNotEqual(first['reservationSha256'], second['reservationSha256'])
        self.assertNotEqual(first['inputSha256'], second['inputSha256'])
        self.assertEqual(first['messageSha256'], second['messageSha256'])

    def test_schema_and_errors_do_not_echo_arbitrary_text(self):
        for section in (None,'quote','reservations'):
            b = bundle(); (b if section is None else b[section])['secret'] = 'sensitive-value'
            self.assertNotIn('sensitive-value', str(self.blocked(b)))
        for b in (None, [], {}, {'format': VERSION}):
            self.blocked(b, 'bundle-schema')

    def test_self_check_reproducible_eight_cases(self):
        self.assertEqual(run(), run())
        self.assertEqual(run()['casesPassed'], 8)

    def test_cli_private_complete_report_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'report.json.gz'
            command = [sys.executable, str(Path(__file__).with_name('quote_cli.py')), '--output', str(out)]
            p = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            raw = out.read_bytes(); r = json.loads(gzip.decompress(raw)); r.pop('capturedAt')
            self.assertEqual(r, run())
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(out.read_bytes(), raw)

    def test_cli_duplicate_keys_no_report_and_stale_input_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp)/'input.json', Path(tmp)/'report.json.gz'
            command = [sys.executable, str(Path(__file__).with_name('quote_cli.py')),
                       '--input', str(src), '--output', str(out)]
            src.write_text('{"format":1,"format":2}')
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertFalse(out.exists())
            b = bundle(); b['quote']['requestedAtMs'] = 1; b['quote']['receivedAtMs'] = 2
            src.write_text(json.dumps(b))
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            r = json.loads(gzip.decompress(out.read_bytes()))
            self.assertEqual(r['state'], 'unavailable')
            self.assertEqual(r['reasons'], ['quote-stale-or-future'])


if __name__ == '__main__':
    unittest.main()
