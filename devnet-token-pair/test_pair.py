import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from pair_contract import *
from pair_workflow import execute, recover, status, signer, prepare, initialize_pair, PairRpc, RecoveryRpc, signed_plan, digest, simulation_review
from core import initialize, Session, write_new
from pair_fixtures import Transport, states, balances, token_rows, fake_key


class PairCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name)/'wallet'
        self.wallet=initialize(self.home)['wallet']
    def tearDown(self):self.temp.cleanup()
    def run_pair(self,change=None):
        t=Transport(self.home,change=change)
        r=execute(self.home,self.wallet,opener=t,sleeper=lambda _:None)
        return r,t
    def prepare_only(self):
        t=Transport(self.home)
        with Session(self.home) as s:
            child,keys=initialize_pair(s);i,w,v,sim=prepare(s,child,keys,t_rpc:=PairRpc(t))
        return i,w,v,t
    def test_success_exact_supply_authorities_rent_and_one_send(self):
        r,t=self.run_pair();self.assertEqual(r['state'],'finalized-success',r)
        self.assertTrue(r['setupPairVerified']);self.assertFalse(r['controlledPoolCreated'])
        self.assertEqual(r['submissionAttempts'],1);self.assertEqual(r['sendRequestsThisRun'],1)
        self.assertEqual(r['latestObservation']['receipt']['rentLockedLamports'],'5110480')
        self.assertEqual(r['latestObservation']['receipt']['walletAfterLamports'],'4844520')
        for a in r['latestObservation']['accounts']:
            self.assertIsNone(a['mintAuthority']);self.assertIsNone(a['freezeAuthority'])
            self.assertEqual(a['supply'],'1000000000');self.assertEqual(a['holderAmountAtomic'],'1000000000')
        q=next(q for q in t.calls if q['method']=='sendTransaction')
        self.assertEqual(q['params'][1]['maxRetries'],0);self.assertFalse(q['params'][1]['skipPreflight'])
        self.assertEqual(len(base64.b64decode(q['params'][0])),1012)
        # Public report contains no signed wire or private key material.
        self.assertNotIn(q['params'][0],json.dumps(r));self.assertFalse(r['signedBytesExported'])
    def test_repeat_execute_and_terminal_recovery_make_no_rpc(self):
        self.run_pair();t=Transport(self.home)
        for fn in (execute,recover):
            r=fn(self.home,self.wallet,opener=t,sleeper=lambda _:None)
            self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['networkRequests'],0)
        self.assertEqual(t.calls,[]);self.assertEqual(status(self.home,self.wallet)['state'],'finalized-success')
    def test_stop_before_initialization(self):
        (self.home/'STOP').write_text('stop');r,t=self.run_pair()
        self.assertEqual(r['state'],'not-started');self.assertFalse(t.calls);self.assertFalse((self.home/CHILD).exists())
    def test_stop_after_simulation_no_send(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':(self.home/'STOP').write_text('stop')
            return v
        r,t=self.run_pair(change);self.assertEqual(r['submissionAttempts'],0)
        self.assertFalse(any(q['method']=='sendTransaction' for q in t.calls))
    def test_stop_after_boundary_no_send(self):
        import pair_workflow
        original=pair_workflow.write_new
        def save(path,value):
            original(path,value)
            if path.name=='send-boundary.json':(self.home/'STOP').write_text('stop')
        with patch('pair_workflow.write_new',side_effect=save):r,t=self.run_pair()
        self.assertEqual(r['submissionAttempts'],1);self.assertEqual(r['sendRequestsThisRun'],0)
        self.assertEqual(r['state'],'submission-unknown')
    def test_wrong_wallet_no_mutation(self):
        with self.assertRaises(ValueError):execute(self.home,fake_key('other'),opener=Transport(self.home))
        self.assertFalse((self.home/CHILD).exists())
    def test_wrong_genesis_stops_before_signing(self):
        r,t=self.run_pair(lambda q,v,t:GENESIS['mainnet-beta'] if q['method']=='getGenesisHash' else v)
        self.assertEqual(r['state'],'preparation-incomplete');self.assertEqual(len(t.calls),1)
        self.assertFalse((self.home/CHILD/'signed.json').exists())
    def test_existing_new_account_prevents_signing(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts' and len(q['params'][0])==5:v['value'][1]=v['value'][0]
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'preparation-incomplete')
        self.assertFalse((self.home/CHILD/'plan.json').exists())
    def test_insufficient_balance_prevents_signing(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':v['value'][0]['lamports']=5000000
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'preparation-incomplete')
        self.assertFalse((self.home/CHILD/'signed.json').exists())
    def test_total_spend_cap(self):
        r,t=self.run_pair(lambda q,v,t:2000000 if q['method']=='getMinimumBalanceForRentExemption' else v)
        self.assertEqual(r['state'],'preparation-incomplete');self.assertFalse((self.home/CHILD/'signed.json').exists())
    def test_fee_cap(self):
        def change(q,v,t):
            if q['method']=='getFeeForMessage':v['value']=50001
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'preparation-incomplete')
        self.assertFalse((self.home/CHILD/'signed.json').exists())
    def test_simulation_error_no_send(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':v['value']['err']={'InstructionError':[1,'failure']}
            return v
        r,t=self.run_pair(change);self.assertEqual(r['submissionAttempts'],0);self.assertEqual(r['sendRequestsThisRun'],0)
    def test_simulation_native_mismatch_no_send(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':v['value']['postBalances'][0]-=1
            return v
        r,t=self.run_pair(change);self.assertEqual(r['sendRequestsThisRun'],0)
    def test_simulation_supply_mismatch_no_send(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':v['value']['postTokenBalances'][0]['uiTokenAmount']['amount']='1'
            return v
        r,t=self.run_pair(change);self.assertEqual(r['sendRequestsThisRun'],0)
    def test_replacement_blockhash_no_send(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':v['value']['replacementBlockhash']={'blockhash':fake_key('other')}
            return v
        r,t=self.run_pair(change);self.assertEqual(r['sendRequestsThisRun'],0)
    def test_near_expiry_no_send(self):
        r,t=self.run_pair(lambda q,v,t:996 if q['method']=='getBlockHeight' else v)
        self.assertEqual(r['sendRequestsThisRun'],0);self.assertEqual(r['submissionAttempts'],0)
    def test_send_timeout_recovers_without_resend(self):
        def change(q,v,t):
            if q['method']=='sendTransaction':raise TimeoutError()
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'finalized-success')
        self.assertEqual(sum(q['method']=='sendTransaction' for q in t.calls),1)
    def test_timeout_unknown_then_readonly_recovery(self):
        def change(q,v,t):
            if q['method']=='sendTransaction':raise TimeoutError()
            if q['method']=='getSignatureStatuses':v['value']=[None]
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'submission-unknown')
        recovery=Transport(self.home);recovery.sent=True
        r=recover(self.home,self.wallet,opener=recovery,sleeper=lambda _:None)
        self.assertEqual(r['state'],'finalized-success')
        self.assertFalse(any(q['method']=='sendTransaction' for q in recovery.calls))
    def test_expired_unknown_never_retried(self):
        def change(q,v,t):
            if t.sent and q['method']=='getBlockHeight':return 1001
            if q['method']=='getSignatureStatuses':v['value']=[None]
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'expired-outcome-unknown')
        r2=execute(self.home,self.wallet,opener=Transport(self.home));self.assertEqual(r2['networkRequests'],0)
    def test_send_signature_mismatch_quarantines(self):
        r,t=self.run_pair(lambda q,v,t:fake_key('bad-signature') if q['method']=='sendTransaction' else v)
        self.assertEqual(r['state'],'quarantined')
    def test_receipt_wrong_wire_quarantines(self):
        def change(q,v,t):
            if q['method']=='getTransaction':v['transaction']=['wrong','base64']
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'quarantined')
    def test_finalized_failure_is_fee_only(self):
        def change(q,v,t):
            if q['method']=='getSignatureStatuses' and t.sent:v['value'][0]['err']={'InstructionError':[0,'failure']}
            if q['method']=='getTransaction':
                v['meta']['err']={'InstructionError':[0,'failure']};pre,post=balances(t.plan(),False)
                v['meta'].update(preBalances=pre,postBalances=post,postTokenBalances=[])
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'finalized-failure')
        self.assertEqual(r['latestObservation']['receipt']['rentLockedLamports'],'0');self.assertFalse(r['setupPairVerified'])
    def test_finalized_account_missing_remains_recoverable(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts' and len(q['params'][0])==4:v['value'][0]=None
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'finalized-success-accounts-unverified')
        retry=Transport(self.home);retry.sent=True
        r=recover(self.home,self.wallet,opener=retry,sleeper=lambda _:None)
        self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['sendRequestsThisRun'],0)
    def test_mint_authority_still_present_quarantines(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts' and len(q['params'][0])==4:
                a=v['value'][0];b=bytearray(base64.b64decode(a['data'][0]));b[:4]=(1).to_bytes(4,'little');b[4:36]=raw58(self.wallet);a['data'][0]=base64.b64encode(b).decode()
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'quarantined')
    def test_recovery_has_no_sign_or_send_methods(self):
        for method in ('sendTransaction','simulateTransaction'):
            with self.assertRaises(ValueError):RecoveryRpc(Transport(self.home)).request(method,[])
    def test_crash_after_boundary_recovers_no_send(self):
        import pair_workflow
        original=pair_workflow.write_new
        def save(path,value):
            original(path,value)
            if path.name=='send-boundary.json':raise SystemExit('simulated process loss')
        with patch('pair_workflow.write_new',side_effect=save):
            with self.assertRaises(SystemExit):self.run_pair()
        t=Transport(self.home);r=recover(self.home,self.wallet,opener=t,sleeper=lambda _:None)
        self.assertEqual(r['submissionAttempts'],1);self.assertEqual(r['sendRequestsThisRun'],0)
        self.assertFalse(any(q['method']=='sendTransaction' for q in t.calls))
    def test_repeat_signer_refuses_existing_attempt(self):
        self.prepare_only()
        with self.assertRaises(ValueError):signer(self.home,'sign')
    def test_signer_rejects_wrong_supply_independently(self):
        with Session(self.home) as s:
            child,keys=initialize_pair(s)
            with patch('pair_workflow.signer',side_effect=ValueError('stop before signer')):
                with self.assertRaises(ValueError):prepare(s,child,keys,PairRpc(Transport(self.home)))
        path=self.home/CHILD/'plan.json';i=json.loads(path.read_text());i['supplyAtomicPerMint']='1000000001';path.write_text(json.dumps(i))
        with self.assertRaises(ValueError):signer(self.home,'sign')
        self.assertFalse((self.home/CHILD/'signing-attempt.json').exists())
    def test_signer_rejects_expired_plan_independently(self):
        with Session(self.home) as s:
            child,keys=initialize_pair(s)
            with patch('pair_workflow.signer',side_effect=ValueError('stop before signer')):
                with self.assertRaises(ValueError):prepare(s,child,keys,PairRpc(Transport(self.home)))
        path=self.home/CHILD/'plan.json';i=json.loads(path.read_text());i['recordedAtMs']-=60000;i['expiresAtMs']-=60000;path.write_text(json.dumps(i))
        with self.assertRaises(ValueError):signer(self.home,'sign')
    def test_crash_after_signing_never_resigns_or_sends(self):
        import pair_workflow
        original=pair_workflow.signer
        def interrupted(home,action):
            result=original(home,action)
            if action=='sign':raise SystemExit('simulated crash after signing')
            return result
        with patch('pair_workflow.signer',side_effect=interrupted):
            with self.assertRaises(SystemExit):self.run_pair()
        self.assertEqual(status(self.home,self.wallet)['state'],'signed-not-submitted')
        for fn in (execute,recover):
            r=fn(self.home,self.wallet,opener=Transport(self.home))
            self.assertEqual(r['networkRequests'],0);self.assertEqual(r['submissionAttempts'],0)
    def test_crash_with_only_signing_marker_is_unknown(self):
        import pair_workflow
        original=pair_workflow.signer
        def interrupted(home,action):
            if action=='sign':
                write_new(Path(home)/CHILD/'signing-attempt.json',{'atMs':1})
                raise SystemExit('simulated crash at signing boundary')
            return original(home,action)
        with patch('pair_workflow.signer',side_effect=interrupted):
            with self.assertRaises(SystemExit):self.run_pair()
        self.assertEqual(status(self.home,self.wallet)['state'],'signing-outcome-unknown')
        r=execute(self.home,self.wallet,opener=Transport(self.home));self.assertEqual(r['networkRequests'],0)
    def test_signer_rejects_arbitrary_message_hash(self):
        with Session(self.home) as s:
            child,keys=initialize_pair(s)
            with patch('pair_workflow.signer',side_effect=ValueError('pause before signing')):
                with self.assertRaises(ValueError):prepare(s,child,keys,PairRpc(Transport(self.home)))
        path=self.home/CHILD/'plan.json';i=json.loads(path.read_text());i['messageSha256']='f'*64;path.write_text(json.dumps(i))
        with self.assertRaises(ValueError):signer(self.home,'sign')
        self.assertFalse((self.home/CHILD/'signing-attempt.json').exists())
    def test_incomplete_receipt_can_be_recovered(self):
        def change(q,v,t):
            if q['method']=='getTransaction':v['meta'].pop('postBalances')
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'submission-unknown')
        retry=Transport(self.home);retry.sent=True
        r=recover(self.home,self.wallet,opener=retry,sleeper=lambda _:None)
        self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['sendRequestsThisRun'],0)
    def test_missing_token_receipt_is_not_success(self):
        def change(q,v,t):
            if q['method']=='getTransaction':v['meta'].pop('postTokenBalances')
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'submission-unknown');self.assertFalse(r['setupPairVerified'])
    def test_receipt_changed_token_amount_quarantines(self):
        def change(q,v,t):
            if q['method']=='getTransaction':v['meta']['postTokenBalances'][0]['uiTokenAmount']['amount']='100'
            return v
        r,t=self.run_pair(change);self.assertEqual(r['state'],'quarantined')
    def test_simulation_retained_freeze_authority_no_send(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':
                a=v['value']['accounts'][1];b=bytearray(base64.b64decode(a['data'][0]));b[46:50]=(1).to_bytes(4,'little');b[50:82]=raw58(self.wallet);a['data'][0]=base64.b64encode(b).decode()
            return v
        r,t=self.run_pair(change);self.assertEqual(r['sendRequestsThisRun'],0)
    def test_simulation_delegate_no_send(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':
                a=v['value']['accounts'][2];b=bytearray(base64.b64decode(a['data'][0]));b[72:76]=(1).to_bytes(4,'little');b[76:108]=raw58(self.wallet);a['data'][0]=base64.b64encode(b).decode()
            return v
        r,t=self.run_pair(change);self.assertEqual(r['sendRequestsThisRun'],0)

    def test_partial_initialization_never_regenerated(self):
        (self.home/CHILD).mkdir(mode=0o700)
        r,t=self.run_pair();self.assertEqual(r['state'],'initialization-incomplete');self.assertFalse(t.calls)


class ContractTests(unittest.TestCase):
    def test_exact_instruction_layout(self):
        k={n:fake_key(n) for n in NAMES};msg=message(k,fake_key('blockhash'),1066800,1488440)
        wire=base64.b64encode(bytes([5])+bytes(320)+msg).decode();tx=decode_wire(wire)[4]['transaction']['message']
        self.assertEqual(tx['header'],dict(numRequiredSignatures=5,numReadonlySignedAccounts=0,numReadonlyUnsignedAccounts=2))
        instructions=tx['instructions'];self.assertEqual(len(instructions),12)
        from contract import decode
        for ixindex,m,h in ((0,1,2),(6,3,4)):
            ops=instructions[ixindex:ixindex+6]
            self.assertEqual([o['programIdIndex'] for o in ops],[5,6,5,6,6,6])
            self.assertEqual([o['accounts'] for o in ops],[[0,m],[m],[0,h],[h,m],[m,h,0],[m,0]])
            self.assertEqual(decode(ops[1]['data']),bytes([20,6])+raw58(k['wallet'])+bytes([0]))
            self.assertEqual(decode(ops[4]['data']),bytes([14])+int(1e9).to_bytes(8,'little')+bytes([6]))
            self.assertEqual(decode(ops[5]['data']),bytes([6,0,0]))
    def test_rent_and_alias_caps(self):
        k={n:fake_key(n) for n in NAMES}
        for mr,hr in ((True,1),(0,1),(2000001,1),(1,2500001),(2000000,2000000)):
            with self.subTest(mr=mr,hr=hr):
                with self.assertRaises(ValueError):message(k,fake_key('bh'),mr,hr)
        k['mintA']=k['wallet']
        with self.assertRaises(ValueError):message(k,fake_key('bh'),1,1)


if __name__=='__main__':unittest.main()
