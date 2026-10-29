from copy import deepcopy
from fractions import Fraction
import unittest
from cpmm_quote import calculate, derive
from cpmm_quote_checks import run
from state_fixtures import fixture, NOW, change_row


def scope_for(c):
    p = fixture(with_packet=True)['packet']['policy']
    return dict(network='devnet', accounts=deepcopy(p['accounts']), amountIn='1000')


class CurveTests(unittest.TestCase):
    def test_host_vectors(self):
        self.assertEqual(run()['casesPassed'],11)

    def test_integer_curve_invariant_and_fee_rounding(self):
        for amount in (10,20,101,999,1000,2**53+1):
            for reserves in ((10000,20000),(2**63,2**63)):
                for creator_side in (False,True):
                    r=calculate(amount,*reserves,2500,1500,creator_side)
                    fee=int(r['inputFeeAtomic']); net=amount-fee
                    expected=Fraction(net*reserves[1],reserves[0]+net)
                    raw=int(r['curveOutputBeforeOutputFeeAtomic'])
                    self.assertLessEqual(raw,expected);self.assertLess(expected,raw+1)
                    self.assertGreaterEqual((reserves[0]+net)*(reserves[1]-raw),reserves[0]*reserves[1])
                    self.assertLessEqual(int(r['outputAtomic']),raw)

    def test_reserve_fee_subtraction_and_precise_minimum(self):
        c=fixture();s=scope_for(c)
        change_row(c,0,341,(100).to_bytes(8,'little'))
        r=derive(c,s,slippage_bps=100,now_ms=NOW)
        self.assertEqual(r['economicInputs']['reserves'],['9900','10000'])
        self.assertEqual(r['quote']['outAmount'],'914')
        self.assertEqual(r['quote']['minimumOutAmount'],'905')

    def test_each_creator_side_and_reverse_direction(self):
        for reverse in (False,True):
            for mode in (0,1,2):
                c=fixture(reverse=reverse);s=scope_for(c)
                change_row(c,0,389,bytes([mode,1]));change_row(c,1,108,(1500).to_bytes(8,'little'))
                r=derive(c,s,slippage_bps=100,now_ms=NOW)
                on_input=mode==0 or mode==(2 if reverse else 1)
                self.assertEqual(r['arithmetic'],calculate(1000,10000,10000,2500,1500,on_input))

    def test_disabled_creator_is_not_charged(self):
        c=fixture();s=scope_for(c);change_row(c,1,108,(1500).to_bytes(8,'little'))
        self.assertEqual(derive(c,s,slippage_bps=100,now_ms=NOW)['quote']['outAmount'],'906')

    def test_raw_account_changes_are_not_summary_overrides(self):
        c=fixture();s=scope_for(c);c['review']={'effectiveReservesAtomic':['999999','999999']}
        self.assertEqual(derive(c,s,slippage_bps=100,now_ms=NOW)['quote']['outAmount'],'906')
        change_row(c,4,64,(0).to_bytes(8,'little'))
        with self.assertRaises(ValueError):derive(c,s,slippage_bps=100,now_ms=NOW)

    def test_wrong_scope_and_unsupported_native_and_freshness(self):
        for mode in ('pool','inputMint','vault','network','amount','slippage','stale','future','native'):
            c=fixture(native=mode=='native');s=scope_for(c);at=NOW;bps=100
            if mode in ('pool','inputMint'):s['accounts'][mode]=s['accounts']['wallet']
            if mode=='vault':s['accounts']['inputVault']=s['accounts']['outputVault']
            if mode=='network':s['network']='mainnet-beta'
            if mode=='amount':s['amountIn']='1001'
            if mode=='slippage':bps=101
            if mode=='stale':at=NOW+10001
            if mode=='future':at=NOW-1
            with self.subTest(mode=mode),self.assertRaises(ValueError):derive(c,s,slippage_bps=bps,now_ms=at)

    def test_authority_and_input_vault_overflow_fail_closed(self):
        c=fixture();s=scope_for(c)
        change_row(c,2,0,(1).to_bytes(4,'little')+bytes([1])*32)
        with self.assertRaises(ValueError):derive(c,s,slippage_bps=100,now_ms=NOW)
        c=fixture();change_row(c,4,64,(2**64-1).to_bytes(8,'little'))
        with self.assertRaises(ValueError):derive(c,s,slippage_bps=100,now_ms=NOW)


if __name__=='__main__':unittest.main()
