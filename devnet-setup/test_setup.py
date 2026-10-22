import base64
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fresh_packet import build, message, prepare_fresh, scope_check, PacketRpc, ROOT
from swap_rehearsal import scope_for, policy_check, CHILD
from swap_fixtures import fixture, fake_key, NOW, encode
from contract import decode_wire, validate, decode
from recorded_capture import GENESIS
from setup_costs import review, _collect_costs, CostRpc, SIZES
from preflight_checks import fixture as pool_fixture, edit
from preflight import _review
from core import initialize


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class Transport:
    def __init__(self, change=None): self.calls=[]; self.change=change
    def open(self, request, timeout=None):
        q=json.loads(request.data); self.calls.append(q); m=q['method']
        assert request.full_url == 'https://api.devnet.solana.com'
        if m=='getGenesisHash': v=GENESIS['devnet']
        elif m=='getLatestBlockhash': v=dict(context={'slot':101},value=dict(blockhash=fake_key('fresh'),lastValidBlockHeight=1000))
        elif m=='getFeeForMessage': v=dict(context={'slot':102},value=5000)
        elif m=='getMultipleAccounts':
            v=dict(context={'slot':102},value=[dict(data=['','base64'],owner='11111111111111111111111111111111',executable=False,lamports=9980000)])
        elif m=='getMinimumBalanceForRentExemption': v=q['params'][0]*10+100
        else: raise AssertionError(m)
        if self.change: v=self.change(q,v)
        return Response(json.dumps(dict(jsonrpc='2.0',id=q['id'],result=v)).encode())


class PacketTests(unittest.TestCase):
    def setUp(self): self.scope=scope_for(fixture()['policy'])
    def test_fresh_packet_preserves_scope_and_exact_fee_message(self):
        t=Transport(); original=copy.deepcopy(self.scope); r=build(self.scope,opener=t,now=lambda:NOW)
        self.assertEqual(self.scope,original)
        p=r['packet']; self.assertEqual(scope_for(p['policy']),original)
        self.assertEqual(validate(p,now_ms=NOW)['state'],'instruction-policy-match')
        self.assertEqual(p['policy']['blockhash'],fake_key('fresh'))
        msg=decode_wire(p['unsignedTransactionBase64'])[1]
        self.assertEqual(base64.b64decode(t.calls[2]['params'][0]),msg)
        self.assertEqual(len(t.calls),4); self.assertEqual(r['signaturesCreated'],0)
        self.assertEqual(t.calls[2]['params'][1]['minContextSlot'],101)
        self.assertEqual(decode_wire(p['unsignedTransactionBase64'])[3],[bytes(64)])
    def test_serializer_matches_independent_test_encoder(self):
        p=fixture(); tx=decode_wire(p['unsignedTransactionBase64'])[4]['transaction']['message']
        tx['instructions'][0]['data']=__import__('wire').b58(b'\x02'+(300000).to_bytes(4,'little'))
        tx['instructions'][1]['data']=__import__('wire').b58(b'\x03'+bytes(8))
        expected=decode_wire(encode(tx)[0])[1]
        self.assertEqual(message(self.scope,p['policy']['blockhash']),expected)
    def test_null_fee_fails(self):
        t=Transport(lambda q,v: dict(context={'slot':102},value=None) if q['method']=='getFeeForMessage' else v)
        with self.assertRaises(ValueError): build(self.scope,opener=t,now=lambda:NOW)
        self.assertEqual(len(t.calls),3)
    def test_fee_above_independent_cap_fails(self):
        t=Transport(lambda q,v: dict(context={'slot':102},value=6001) if q['method']=='getFeeForMessage' else v)
        with self.assertRaises(ValueError): build(self.scope,opener=t,now=lambda:NOW)
    def test_fee_slot_regression(self):
        t=Transport(lambda q,v: dict(context={'slot':100},value=5000) if q['method']=='getFeeForMessage' else v)
        with self.assertRaises(ValueError): build(self.scope,opener=t,now=lambda:NOW)
    def test_genesis_before_stops_immediately(self):
        t=Transport(lambda q,v: GENESIS['mainnet-beta'] if q['method']=='getGenesisHash' else v)
        with self.assertRaises(ValueError): build(self.scope,opener=t,now=lambda:NOW)
        self.assertEqual(len(t.calls),1)
    def test_genesis_after_fails(self):
        t=Transport(lambda q,v: GENESIS['mainnet-beta'] if q['id']==4 else v)
        with self.assertRaises(ValueError): build(self.scope,opener=t,now=lambda:NOW)
    def test_elapsed_build_does_not_renew_policy(self):
        clock=iter([NOW,NOW,NOW,NOW,NOW,NOW,NOW,NOW,NOW+15000,NOW+15000])
        with self.assertRaises(ValueError): build(self.scope,opener=Transport(),now=lambda:next(clock))
    def test_stale_fee_fails_even_inside_policy_window(self):
        clock=iter([NOW,NOW,NOW,NOW,NOW,NOW,NOW,NOW,NOW+10001,NOW+10001])
        with self.assertRaises(ValueError): build(self.scope,opener=Transport(),now=lambda:next(clock))
    def test_invalid_scope_before_any_requests(self):
        for field,value in [('amountIn','1001'),('maxComputeUnits',300001),('minimumAmountOut','0'),('network','mainnet-beta')]:
            with self.subTest(field=field):
                s=copy.deepcopy(self.scope);s[field]=value;t=Transport()
                with self.assertRaises(ValueError): build(s,opener=t,now=lambda:NOW)
                self.assertFalse(t.calls)
    def test_alias_and_extra_roles_fail(self):
        for mode in ('alias','extra'):
            s=copy.deepcopy(self.scope)
            s['accounts']['source' if mode=='alias' else 'extra']=s['accounts']['wallet']
            with self.assertRaises(ValueError): build(s,opener=Transport(),now=lambda:NOW)
    def test_no_send_method(self):
        for cls in (PacketRpc,CostRpc):
            with self.assertRaises(ValueError): cls(Transport()).request('sendTransaction',[])
    def test_stop_prevents_build(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'wallet'; info=initialize(home)
            with __import__('core').Session(home) as s: wallet=s.wallet
            scope=copy.deepcopy(self.scope);scope['accounts']['wallet']=wallet
            (home/'STOP').write_text('stop')
            with patch('fresh_packet.build') as builder:
                with self.assertRaises(ValueError): prepare_fresh(home,wallet,scope)
                builder.assert_not_called()
    def test_existing_one_shot_not_refreshed(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'wallet';initialize(home)
            with __import__('core').Session(home) as s: wallet=s.wallet
            scope=copy.deepcopy(self.scope);scope['accounts']['wallet']=wallet
            (home/CHILD).mkdir(mode=0o700)
            with patch('fresh_packet.build') as builder, patch('fresh_packet.report',return_value={'state':'existing'}) as reporter:
                self.assertEqual(prepare_fresh(home,wallet,scope),{'state':'existing'})
                builder.assert_not_called();reporter.assert_called_once()
    def test_built_wire_passes_restricted_signer_and_simulation(self):
        from swap_rehearsal_fixtures import scenario, Transport as SimulationTransport
        from swap_rehearsal import _prepare
        import time
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'wallet'; initialize(home)
            with __import__('core').Session(home) as session: wallet=session.wallet
            c,b,scope=scenario(wallet)
            built=build(scope,opener=Transport())
            c['packet']=built['packet'];c['messageSha256']=built['packet']['feeAssertion']['messageSha256']
            c['startedAtMs']=built['packet']['policy']['issuedAtMs']
            c['finishedAtMs']=time.time_ns()//1000000
            for item in c['evidence'].values(): item['receivedAtMs']=c['finishedAtMs']
            c['evidence']['fee']['result']['value']=5000
            result=_prepare(home,wallet,scope,built['packet'],opener=SimulationTransport(c),
                            collector=lambda **kwargs:copy.deepcopy(c),reviewer=lambda capture,now_ms:_review(capture,b,now_ms))
            self.assertEqual(result['state'],'signed-simulation-consistent',result)
            self.assertEqual(result['signaturesCreatedThisRun'],1)
            self.assertEqual(result['transactionsSent'],0)

    def test_handoff_uses_original_scope_and_fresh_packet(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'wallet';initialize(home)
            with __import__('core').Session(home) as s: wallet=s.wallet
            scope=copy.deepcopy(self.scope);scope['accounts']['wallet']=wallet
            built=build(scope,opener=Transport(),now=lambda:NOW)
            with patch('fresh_packet.build',return_value=built),patch('fresh_packet.prepare',return_value={'state':'prepared'}) as prepared:
                r=prepare_fresh(home,wallet,scope)
                self.assertEqual(prepared.call_args.args[2:],(scope,built['packet']))
                self.assertNotIn('packet',r['packetBuild'])


class CostTests(unittest.TestCase):
    def setUp(self):
        self.c,self.b=pool_fixture(False);self.wallet=fake_key('wallet')
        self.reviewer=lambda c,now_ms:_review(c,self.b,now_ms)
    def capture(self,t=None):
        return _collect_costs(self.c['pool'],self.wallet,opener=t or Transport(),
                              collector=lambda **kwargs:copy.deepcopy(self.c),pool_reviewer=self.reviewer)
    def test_exact_cost_arithmetic_and_replay(self):
        edit(self.c,1,36,(150000000).to_bytes(8,'little'))
        r=self.capture();v=r['review'];rent={n:n*10+100 for n in SIZES}
        self.assertEqual(v['state'],'costs-observed')
        total=3*rent[82]+5*rent[165]+rent[637]+rent[4075]+150000000+100000
        self.assertEqual(int(v['estimatedTotalLamports']),total)
        self.assertEqual(int(v['estimatedShortfallLamports']),total-9980000)
        self.assertFalse(v['setupReady']);self.assertFalse(v['executionApproved'])
        self.assertEqual(review(r['sourcePoolCapture'],self.wallet,r['evidence'],pool_reviewer=self.reviewer),v)
    def test_zero_creation_fee_is_not_assumed(self):
        edit(self.c,1,36,bytes(8));v=self.capture()['review']
        self.assertEqual(v['configCreationFeeLamports'],'0');self.assertTrue(v['balanceCoversEstimate'])
        self.assertFalse(v['setupReady'])
    def test_disabled_creation_reported(self):
        edit(self.c,1,9,b'\x01');v=self.capture()['review']
        self.assertEqual(v['state'],'costs-observed');self.assertFalse(v['poolCreationEnabled'])
        self.assertIn('config-disables-new-pools',v['blockers'])
    def test_missing_wallet_means_zero_balance(self):
        t=Transport(lambda q,v: dict(context={'slot':102},value=[None]) if q['method']=='getMultipleAccounts' else v)
        v=self.capture(t)['review'];self.assertEqual(v['walletLamports'],'0')
        self.assertEqual(v['estimatedShortfallLamports'],v['estimatedTotalLamports'])
    def test_bad_wallet_owner_rejected(self):
        def change(q,v):
            if q['method']=='getMultipleAccounts':v['value'][0]['owner']=fake_key('bad')
            return v
        self.assertEqual(self.capture(Transport(change))['review']['state'],'unavailable')
    def test_missing_rent_no_partial_totals(self):
        t=Transport(lambda q,v: None if q['method']=='getMinimumBalanceForRentExemption' else v)
        v=self.capture(t)['review'];self.assertEqual(v['state'],'unavailable');self.assertNotIn('estimatedTotalLamports',v)
    def test_bool_rent_not_integer(self):
        t=Transport(lambda q,v: True if q['method']=='getMinimumBalanceForRentExemption' else v)
        self.assertEqual(self.capture(t)['review']['state'],'unavailable')
    def test_genesis_change_rejected(self):
        t=Transport(lambda q,v:GENESIS['mainnet-beta'] if q['id']==7 else v)
        self.assertEqual(self.capture(t)['review']['state'],'unavailable')
    def test_current_pin_failure_stops_cost_requests(self):
        with self.assertRaises(ValueError):
            _collect_costs(self.c['pool'],self.wallet,opener=Transport(),collector=lambda **k:self.c,
                           pool_reviewer=lambda *a,**k:dict(state='unavailable'))
    def test_request_sizes_and_no_key_access(self):
        t=Transport();r=self.capture(t)
        self.assertEqual([q['params'][0] for q in t.calls if q['method']=='getMinimumBalanceForRentExemption'],list(SIZES))
        self.assertEqual(len(t.calls),7);self.assertFalse(r['review']['walletKeyRead'])


if __name__=='__main__':unittest.main()
