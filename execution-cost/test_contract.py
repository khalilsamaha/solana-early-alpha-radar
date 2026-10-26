import copy
import json
import random
import unittest
from contract import evaluate, U64
from examples import fixture


class CostTests(unittest.TestCase):
    def setUp(self):
        self.p = fixture()

    def run_case(self):
        return evaluate(self.p, now_ms=100000)

    def test_exact_costs_and_quote_change(self):
        r = self.run_case(); c = r['calculation']
        self.assertEqual(r['state'], 'modeled-constraints-met')
        self.assertEqual(c['quotedChangeUsdcAtomic'], '200000')
        self.assertEqual(c['nativeReserveLamports'], '30000')
        self.assertEqual(c['nativeCostUsdcAtomicRoundedUp'], '6000')
        self.assertEqual(c['stressedExitUsdcAtomic'], '10098000')
        self.assertEqual(c['modeledSurplusUsdcAtomic'], '92000')
        self.assertFalse(r['executionApproved']); self.assertFalse(r['measuredNetProfit'])

    def test_rent_is_reserved_and_not_assumed_refunded(self):
        self.p['costs']['rentDebitLamports'] = '2000000'
        r = self.run_case()
        self.assertEqual(r['calculation']['modeledSurplusUsdcAtomic'], '-308000')
        self.assertEqual(r['state'], 'modeled-constraints-not-met')

    def test_priority_is_not_added_twice(self):
        before = self.run_case()['calculation']
        self.p['costs']['entryPriorityIncludedLamports'] = '10000'
        self.assertEqual(self.run_case()['calculation'], before)

    def test_priority_cannot_exceed_network_total(self):
        self.p['costs']['entryPriorityIncludedLamports'] = '10001'
        self.assertEqual(self.run_case()['reasons'], ['priority-exceeds-total-network-fee'])

    def test_separate_tip_and_failures_are_included(self):
        self.p['costs']['entryTipCapLamports'] = '20000'
        self.p['costs']['exitTipCapLamports'] = '30000'
        self.assertEqual(self.run_case()['calculation']['nativeReserveLamports'], '80000')

    def test_additional_usdc_debit(self):
        self.p['costs']['otherUsdcDebitAtomic'] = '100000'
        self.assertEqual(self.run_case()['calculation']['modeledSurplusUsdcAtomic'], '-8000')

    def test_unknown_cost_is_not_zero(self):
        for key in self.p['costs']:
            if key == 'coverage': continue
            with self.subTest(key=key):
                p = copy.deepcopy(self.p); p['costs'][key] = None
                r = evaluate(p, now_ms=100000)
                self.assertEqual(r['state'], 'unavailable'); self.assertIsNone(r['calculation'])

    def test_incomplete_coverage_cannot_pass_even_with_numbers(self):
        self.p['costs']['coverage'] = 'unknown'
        self.assertEqual(self.run_case()['reasons'], ['cost-coverage-unknown'])

    def test_failed_sell_is_not_zero_return_or_success(self):
        self.p['sell'].update(status='unavailable', outAmount=None)
        r = self.run_case()
        self.assertEqual(r['state'], 'unavailable'); self.assertIsNone(r['calculation'])

    def test_failed_buy_cannot_produce_margin(self):
        self.p['buy'].update(status='unavailable', outAmount=None)
        self.assertEqual(self.run_case()['state'], 'unavailable')

    def test_failed_quote_cannot_carry_an_amount(self):
        self.p['sell']['status'] = 'unavailable'
        self.assertEqual(self.run_case()['state'], 'invalid')

    def test_exact_reverse_quantity_required(self):
        self.p['sell']['inAmount'] = '49999'
        self.assertEqual(self.run_case()['reasons'], ['reverse-quantity-mismatch'])

    def test_mints_and_units_cannot_be_mixed(self):
        self.p['sell']['outputMint'] = self.p['sell']['inputMint']
        self.assertEqual(self.run_case()['reasons'], ['round-trip-mints'])

    def test_base58_requires_exact_32_bytes(self):
        self.p['buy']['outputMint'] = '2'*32
        self.assertEqual(self.run_case()['reasons'], ['mint-invalid'])

    def test_future_or_reversed_quote_clocks(self):
        for key, value in [('receivedAtMs', 100001), ('requestedAtMs', 99600)]:
            with self.subTest(key=key):
                p=copy.deepcopy(self.p); p['sell'][key]=value
                self.assertEqual(evaluate(p, now_ms=100000)['state'], 'invalid')

    def test_slow_response_cannot_relabel_old_request_fresh(self):
        self.p['buy']['requestedAtMs'] = 94000
        self.assertEqual(self.run_case()['reasons'], ['buy-quote-stale'])

    def test_sell_cannot_precede_known_buy_quantity(self):
        self.p['sell']['requestedAtMs'] = 99100
        self.assertEqual(self.run_case()['reasons'], ['reverse-before-buy-response'])

    def test_missing_rate_and_balance_preserve_unknown(self):
        self.p['nativeValuation']=None; self.p['nativeSpendableLamports']=None
        self.assertEqual(self.run_case()['reasons'], ['native-spendable-unknown', 'native-valuation-unknown'])

    def test_stale_and_future_rates(self):
        self.p['nativeValuation']['availableAtMs'] = 69999
        self.assertEqual(self.run_case()['reasons'], ['native-valuation-stale'])
        self.p['nativeValuation']['availableAtMs'] = 100001
        self.assertEqual(self.run_case()['reasons'], ['valuation-from-future'])

    def test_native_balance_independent_of_usdc_margin(self):
        self.p['nativeSpendableLamports'] = '29999'
        r = self.run_case()
        self.assertEqual(r['reasons'], ['native-reserve-insufficient'])
        self.assertEqual(r['calculation']['nativeReserveShortfallLamports'], '1')

    def test_exact_reserve_boundary(self):
        self.p['nativeSpendableLamports'] = '30000'
        self.assertEqual(self.run_case()['state'], 'modeled-constraints-met')

    def test_requested_minimum_is_enforced_without_selecting_a_threshold(self):
        self.p['policy']['minimumSurplusUsdcAtomic'] = '92001'
        self.assertEqual(self.run_case()['reasons'], ['modeled-margin-below-minimum'])

    def test_hundred_percent_haircut_has_no_finite_break_even(self):
        self.p['policy']['additionalExitHaircutBps'] = 10000
        c = self.run_case()['calculation']
        self.assertIsNone(c['requiredQuotedExitUsdcAtomic'])
        self.assertFalse(c['requiredExitWithinU64'])

    def test_native_conversion_rounds_up_not_down(self):
        self.p['nativeValuation']['usdcAtomicPerSolUpperBound'] = '1'
        self.assertEqual(self.run_case()['calculation']['nativeCostUsdcAtomicRoundedUp'], '1')

    def test_break_even_is_the_minimum_integer_output(self):
        rng=random.Random(7)
        for _ in range(100):
            self.p['policy']['additionalExitHaircutBps'] = rng.randrange(10000)
            self.p['policy']['minimumSurplusUsdcAtomic'] = str(rng.randrange(1000000))
            c=self.run_case()['calculation']; required=int(c['requiredQuotedExitUsdcAtomic'])
            factor=10000-self.p['policy']['additionalExitHaircutBps']
            target=int(c['principalUsdcAtomic'])+int(c['totalAdditionalCostUsdcAtomic'])+int(c['minimumSurplusUsdcAtomic'])
            self.assertGreaterEqual(required*factor//10000, target)
            self.assertLess((required-1)*factor//10000, target)

    def test_large_atomic_values_keep_precision(self):
        self.p['sell']['outAmount']=str(U64)
        self.p['policy']['additionalExitHaircutBps']=0
        c=self.run_case()['calculation']
        self.assertEqual(int(c['modeledSurplusUsdcAtomic']), U64-10000000-6000)

    def test_native_reserve_overflow_refused(self):
        self.p['costs']['entryTipCapLamports']=str(U64)
        self.assertEqual(self.run_case()['reasons'], ['native-reserve-overflow'])

    def test_numbers_bools_negative_scientific_and_noncanonical_rejected(self):
        for value in (1, True, -1, '01', '1e3', '-1', '1.0', str(U64+1), '9'*1000):
            with self.subTest(value=str(value)[:30]):
                self.p['buy']['inAmount']=value
                self.assertEqual(self.run_case()['state'], 'invalid')

    def test_unknown_fields_fail_instead_of_ignoring_costs(self):
        self.p['costs']['routeFeeToSubtractAgain']='100'
        self.assertEqual(self.run_case()['reasons'], ['cost-schema'])

    def test_deterministic_nonmutating_and_policy_bound(self):
        before=copy.deepcopy(self.p); a=self.run_case(); b=self.run_case()
        self.assertEqual(a,b); self.assertEqual(before,self.p)
        self.p['policy']['additionalExitHaircutBps']=200
        self.assertNotEqual(a['policySha256'],self.run_case()['policySha256'])
        self.assertNotEqual(a['inputSha256'],self.run_case()['inputSha256'])
        json.dumps(a,allow_nan=False)

    def test_invalid_packets_have_sanitized_errors(self):
        for packet in (None, [], {'secret':'should-not-appear'}):
            r=evaluate(packet,now_ms=100000)
            self.assertEqual(r['reasons'],['packet-schema'])
            self.assertNotIn('should-not-appear',json.dumps(r))


if __name__ == '__main__':
    unittest.main()
