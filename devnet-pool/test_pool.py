import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from pool_contract import *
import pool_contract
import pool_workflow as work
from pool_fixtures import Transport,BASE,RENTS,balances,token_list,post_accounts,pre_accounts,fake_key
from core import initialize,Session,write_new
from pair_fixtures import Transport as PairTransport
from pair_workflow import execute as execute_pair


class PoolCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=tempfile.TemporaryDirectory();cls.template=Path(cls.source.name)/'wallet'
        cls.wallet=initialize(cls.template)['wallet']
        r=execute_pair(cls.template,cls.wallet,opener=PairTransport(cls.template),sleeper=lambda _:None)
        assert r['state']=='finalized-success'
    @classmethod
    def tearDownClass(cls):cls.source.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)/'wallet';shutil.copytree(self.template,self.home)
        self.patches=[patch('pool_contract.BASELINE',BASE),patch('pool_workflow.BASELINE',BASE)]
        for p in self.patches:p.start()
        self.pair=json.loads((self.home/'test-token-pair-v1/accounts.json').read_text())['accounts']
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def run_pool(self,change=None):
        t=Transport(self.home,change=change);r=work.execute(self.home,self.wallet,opener=t,sleeper=lambda _:None);return r,t
    def prepare_only(self):
        t=Transport(self.home);rpc=work.PoolRpc(t)
        with Session(self.home) as s:
            c=work.capture(rpc,self.pair);child=self.home/CHILD;child.mkdir(mode=0o700)
            result=work.prepare(s,child,c,rpc)
        return result,t
    def no_send(self,change):
        r,t=self.run_pool(change);self.assertEqual(r['sendRequestsThisRun'],0);self.assertNotEqual(r['state'],'finalized-success');return r,t
    def test_complete_one_send_exact_pool_and_token_effects(self):
        r,t=self.run_pool();self.assertEqual(r['state'],'finalized-success',r);self.assertTrue(r['controlledPoolVerified'])
        p=r['latestObservation']['poolState'];self.assertEqual(p['reservesAtomic'],['500000000']*2)
        self.assertEqual(p['remainingHolderAtomic'],['500000000']*2);self.assertEqual(p['lpSupplyAtomic'],'499999900')
        receipt=r['latestObservation']['receipt'];self.assertEqual(receipt['creationFeeLamports'],'150000000')
        self.assertEqual(receipt['rentLockedLamports'],'30769560');self.assertEqual(receipt['walletAfterLamports'],'24069960')
        q=next(q for q in t.calls if q['method']=='sendTransaction');self.assertEqual(q['params'][1]['maxRetries'],0)
        self.assertFalse(q['params'][1]['skipPreflight']);self.assertNotIn(q['params'][0],json.dumps(r))
    def test_realistic_legacy_program_payload_survives_entire_journal(self):
        # Recorded devnet ATA program data is 140044 base64 characters. Earlier
        # empty executable fixtures hid the 128 KiB plan and 32 KiB observation caps.
        payload=base64.b64encode(b'\x7fELF'+bytes(105029)).decode()
        self.assertEqual(len(payload),140044)
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':
                v['value'][ROLES.index('associatedTokenProgram')]['data']=[payload,'base64']
            return v
        r,t=self.run_pool(change)
        self.assertEqual(r['state'],'finalized-success',r)
        child=self.home/CHILD
        self.assertGreater((child/'plan.json').stat().st_size,131072)
        self.assertGreater((child/'observation-000.json').stat().st_size,32768)
        self.assertEqual(work.status(self.home,self.wallet)['state'],'finalized-success')
        r=work.recover(self.home,self.wallet,opener=t,sleeper=lambda _:None)
        self.assertEqual(r['networkRequests'],0)
        self.assertEqual(sum(q['method']=='sendTransaction' for q in t.calls),1)

    def test_legacy_oversized_unsigned_plan_status_and_recovery_never_retry(self):
        payload=base64.b64encode(bytes(105033)).decode()
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':v['value'][ROLES.index('associatedTokenProgram')]['data']=[payload,'base64']
            return v
        with patch('pool_workflow.signer',side_effect=ValueError('restricted-pool-signer-refused')):
            r,t=self.run_pool(change)
        self.assertEqual(r['state'],'preparation-incomplete')
        child=self.home/CHILD;before={p.name:p.read_bytes() for p in child.iterdir()}
        for f in (work.execute,work.recover):
            r=f(self.home,self.wallet,opener=t,sleeper=lambda _:None)
            self.assertEqual(r['networkRequests'],0);self.assertEqual(r['sendRequestsThisRun'],0)
            self.assertFalse(r['journalFiles']['signed.json']['present'])
            self.assertFalse(r['journalFiles']['signing-attempt.json']['present'])
            self.assertFalse(r['journalFiles']['send-boundary.json']['present'])
            self.assertGreater(r['journalFiles']['plan.json']['bytes'],131072)
        self.assertEqual(work.status(self.home,self.wallet)['state'],'preparation-incomplete')
        self.assertEqual(before,{p.name:p.read_bytes() for p in child.iterdir()})

    def test_executable_data_caps_are_role_specific(self):
        rows=pre_accounts(self.pair)
        rows[ROLES.index('associatedTokenProgram')]['data']=['A'*(work.LEGACY_PROGRAM_BASE64+1),'base64']
        with self.assertRaisesRegex(ValueError,'pool-response-account-cap'):work.PoolRpc.accounts(rows)
        rows=pre_accounts(self.pair);rows[ROLES.index('holder0')]['data']=['A'*6001,'base64']
        with self.assertRaisesRegex(ValueError,'pool-response-account-cap'):work.PoolRpc.accounts(rows)
        rows=pre_accounts(self.pair);row=rows[ROLES.index('associatedTokenProgram')]
        row.update(executable=False,data=['A'*6001,'base64'])
        with self.assertRaisesRegex(ValueError,'pool-response-account-cap'):work.PoolRpc.accounts(rows)

    def test_journal_cap_still_bounds_python_and_signer(self):
        self.prepare_only();child=self.home/CHILD
        (child/'plan.json').write_bytes(b' '*(work.JOURNAL_BYTES+1))
        with self.assertRaisesRegex(ValueError,'unsafe-private-file'):work.read(child,'plan.json')
        with self.assertRaisesRegex(ValueError,'restricted-pool-signer-refused'):work.signer(self.home)

    def test_observation_cap_and_sequence_remain_enforced(self):
        child=self.home/CHILD;child.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError,'pool-journal-cap'):
            work.save_observation(child,'submission-unknown',evidence='A'*work.JOURNAL_BYTES)
        self.assertEqual(list(child.iterdir()),[])
        write_new(child/'observation-001.json',dict(state='submission-unknown'))
        with self.assertRaisesRegex(ValueError,'observation-sequence'):work.observations(child)

    def legacy_size_failure(self):
        payload=base64.b64encode(bytes(105033)).decode()
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':v['value'][ROLES.index('associatedTokenProgram')]['data']=[payload,'base64']
            return v
        with patch('pool_workflow.signer',side_effect=ValueError('restricted-pool-signer-refused')):
            r,t=self.run_pool(change)
        self.assertEqual(r['state'],'preparation-incomplete')
        child=self.home/CHILD;i=work.read(child,'plan.json')
        i.update(recordedAtMs=i['recordedAtMs']-100000,expiresAtMs=i['expiresAtMs']-100000,lastValidBlockHeight=800)
        (child/'plan.json').write_text(json.dumps(i,sort_keys=True,separators=(',',':')))
        return child,change

    def replacement(self,change=None):
        t=Transport(self.home,change=change)
        r=work.execute(self.home,self.wallet,allow_replace_unsigned=True,opener=t,sleeper=lambda _:None)
        return r,t

    def test_unsigned_size_replacement_archives_exact_bytes_and_sends_once(self):
        child,change=self.legacy_size_failure();old={p.name:p.read_bytes() for p in child.iterdir()}
        r,t=self.replacement(change);self.assertEqual(r['state'],'finalized-success',r)
        archive=self.home/work.UNSIGNED_ARCHIVE
        self.assertEqual(old,{p.name:p.read_bytes() for p in archive.iterdir()})
        self.assertEqual(r['unsignedReplacement']['filesSha256'],{n:hashlib.sha256(v).hexdigest() for n,v in old.items()})
        self.assertTrue(r['unsignedArchivePresent']);self.assertEqual(r['submissionAttempts'],1)
        self.assertEqual(sum(q['method']=='sendTransaction' for q in t.calls),1)
        for allow in (False,True):
            again=work.execute(self.home,self.wallet,allow_replace_unsigned=allow,opener=t,sleeper=lambda _:None)
            self.assertEqual(again['networkRequests'],0);self.assertEqual(again['state'],'finalized-success')
        self.assertEqual(work.status(self.home,self.wallet)['state'],'finalized-success')
        self.assertEqual(work.recover(self.home,self.wallet,opener=t)['networkRequests'],0)

    def test_unsigned_size_replacement_requires_explicit_flag(self):
        child,_=self.legacy_size_failure();before={p.name:p.read_bytes() for p in child.iterdir()}
        r,t=self.run_pool();self.assertEqual(t.calls,[])
        self.assertEqual(before,{p.name:p.read_bytes() for p in child.iterdir()})
        self.assertFalse((self.home/work.UNSIGNED_REPLACEMENT).exists())

    def test_unsigned_size_replacement_refuses_any_signing_simulation_or_send_file(self):
        child,_=self.legacy_size_failure()
        for name in work.JOURNAL_NAMES[1:]:
            with self.subTest(name=name):
                write_new(child/name,{})
                t=Transport(self.home)
                try:
                    try:work.execute(self.home,self.wallet,allow_replace_unsigned=True,opener=t,sleeper=lambda _:None)
                    except (ValueError,KeyError):pass  # Malformed evidence also refuses reporting.
                    self.assertEqual(t.calls,[])
                    self.assertFalse((self.home/work.UNSIGNED_REPLACEMENT).exists())
                finally:(child/name).unlink()

    def test_unsigned_size_replacement_refuses_valid_signed_attempt(self):
        self.prepare_only();child=self.home/CHILD;before={p.name:p.read_bytes() for p in child.iterdir()}
        r,t=self.replacement();self.assertEqual(t.calls,[])
        self.assertEqual(r['state'],'simulation-passed-not-submitted')
        self.assertFalse((self.home/work.UNSIGNED_REPLACEMENT).exists())
        self.assertEqual(before,{p.name:p.read_bytes() for p in child.iterdir()})

    def test_unsigned_size_replacement_refuses_unknown_journal_file(self):
        child,_=self.legacy_size_failure();write_new(child/'extra.json',{})
        r,t=self.replacement();self.assertEqual(t.calls,[])
        self.assertFalse((self.home/work.UNSIGNED_REPLACEMENT).exists())

    def test_unsigned_size_replacement_refuses_live_intent(self):
        child,_=self.legacy_size_failure();i=work.read(child,'plan.json')
        i.update(recordedAtMs=work.clock(),expiresAtMs=work.clock()+30000)
        i['expiresAtMs']=i['recordedAtMs']+30000
        (child/'plan.json').write_text(json.dumps(i))
        r,t=self.replacement();self.assertEqual(t.calls,[])
        self.assertFalse((self.home/work.UNSIGNED_REPLACEMENT).exists())

    def test_unsigned_size_replacement_refuses_live_blockhash(self):
        child,change=self.legacy_size_failure();i=work.read(child,'plan.json');i['lastValidBlockHeight']=900
        (child/'plan.json').write_text(json.dumps(i))
        r,t=self.replacement(change);self.assertEqual(r['sendRequestsThisRun'],0)
        self.assertFalse((self.home/work.UNSIGNED_REPLACEMENT).exists());self.assertTrue(child.exists())

    def test_unsigned_size_replacement_requires_valid_original_message(self):
        child,_=self.legacy_size_failure();i=work.read(child,'plan.json');i['messageSha256']='0'*64
        (child/'plan.json').write_text(json.dumps(i))
        r,t=self.replacement();self.assertEqual(t.calls,[])
        self.assertFalse((self.home/work.UNSIGNED_REPLACEMENT).exists())

    def test_unsigned_size_replacement_insufficient_funding_preserves_original(self):
        child,_=self.legacy_size_failure();before={p.name:p.read_bytes() for p in child.iterdir()}
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':v['value'][0]['lamports']=1
            return v
        r,t=self.replacement(change);self.assertEqual(r['state'],'funding-required')
        self.assertEqual(before,{p.name:p.read_bytes() for p in child.iterdir()})
        self.assertFalse((self.home/work.UNSIGNED_REPLACEMENT).exists())

    def test_unsigned_size_replacement_stop_preserves_original(self):
        child,_=self.legacy_size_failure();(self.home/'STOP').write_text('stop')
        r,t=self.replacement();self.assertEqual(t.calls,[])
        self.assertFalse((self.home/work.UNSIGNED_REPLACEMENT).exists())

    def test_unsigned_size_replacement_rechecks_program_and_absent_pool(self):
        child,_=self.legacy_size_failure()
        for mode in ('pool','program'):
            def change(q,v,t):
                if q['method']=='getMultipleAccounts':
                    if mode=='pool':v['value'][1]=v['value'][0]
                    else:v['value'][-1]['owner']=SYSTEM
                return v
            r,t=self.replacement(change);self.assertEqual(r['sendRequestsThisRun'],0)
            self.assertFalse((self.home/work.UNSIGNED_REPLACEMENT).exists());self.assertTrue(child.exists())

    def test_unsigned_size_replacement_crash_after_boundary_never_retries(self):
        child,change=self.legacy_size_failure();save=work.write_new
        def crash(p,v):
            save(p,v)
            if p.name==work.UNSIGNED_REPLACEMENT:raise KeyboardInterrupt()
        with patch('pool_workflow.write_new',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):self.replacement(change)
        self.assertTrue(child.exists())
        for allow in (False,True):
            t=Transport(self.home);r=work.execute(self.home,self.wallet,allow_replace_unsigned=allow,opener=t)
            self.assertEqual(t.calls,[]);self.assertEqual(r['sendRequestsThisRun'],0)

    def test_unsigned_size_replacement_crash_after_archive_blocks_empty_slot(self):
        child,change=self.legacy_size_failure();rename=work.os.rename
        def crash(src,dst):rename(src,dst);raise KeyboardInterrupt()
        with patch('pool_workflow.os.rename',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):self.replacement(change)
        self.assertFalse(child.exists());self.assertTrue((self.home/work.UNSIGNED_ARCHIVE).exists())
        for allow in (False,True):
            t=Transport(self.home);r=work.execute(self.home,self.wallet,allow_replace_unsigned=allow,opener=t)
            self.assertEqual(t.calls,[]);self.assertEqual(r['state'],'unsigned-replacement-incomplete')
        self.assertEqual(work.recover(self.home,self.wallet)['networkRequests'],0)

    def test_inspect_no_sign_no_journal(self):
        t=Transport(self.home);r=work.inspect(self.home,self.wallet,opener=t)
        self.assertEqual(r['state'],'funding-ready');self.assertEqual(r['networkRequests'],7)
        self.assertFalse((self.home/CHILD).exists());self.assertEqual(r['estimatedRequiredLamports'],180779560)
    def test_insufficient_funding_does_not_consume_attempt(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':v['value'][0]['lamports']=4844520
            return v
        r,t=self.no_send(change);self.assertEqual(r['state'],'funding-required');self.assertFalse((self.home/CHILD).exists())
        r,t=self.run_pool();self.assertEqual(r['state'],'finalized-success')
    def test_repeat_execute_and_recover_no_network(self):
        self.run_pool();t=Transport(self.home)
        for f in (work.execute,work.recover):
            r=f(self.home,self.wallet,opener=t,sleeper=lambda _:None);self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['networkRequests'],0)
        self.assertEqual(work.status(self.home,self.wallet)['state'],'finalized-success')
    def test_wrong_wallet(self):
        with self.assertRaises(ValueError):work.execute(self.home,fake_key('other'),opener=Transport(self.home))
        self.assertFalse((self.home/CHILD).exists())
    def test_stop_no_network(self):
        (self.home/'STOP').write_text('stop');r,t=self.run_pool();self.assertEqual(t.calls,[])
    def test_stop_after_simulation(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':(self.home/'STOP').write_text('stop')
            return v
        self.no_send(change)
    def test_stop_after_boundary(self):
        save=work.write_new
        def write(p,v):
            save(p,v)
            if p.name=='send-boundary.json':(self.home/'STOP').write_text('stop')
        with patch('pool_workflow.write_new',side_effect=write):r,t=self.run_pool()
        self.assertEqual(r['submissionAttempts'],1);self.assertEqual(r['sendRequestsThisRun'],0)
    def test_wrong_cluster(self):
        r,t=self.no_send(lambda q,v,t:GENESIS['mainnet-beta'] if q['method']=='getGenesisHash' else v)
        self.assertEqual(len(t.calls),1)
    def test_changed_deployment(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':
                raw=bytearray(base64.b64decode(v['value'][-1]['data'][0]));raw[-1]=1;v['value'][-1]['data'][0]=base64.b64encode(raw).decode()
            return v
        self.no_send(change)
    def test_program_recheck_after_simulation(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts' and len(t.calls)>7:v['value'][-1]['owner']=SYSTEM
            return v
        self.no_send(change)
    def test_existing_pool(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':v['value'][1]=v['value'][0]
            return v
        self.no_send(change)
    def test_creation_fee_cap(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':
                r=v['value'][ROLES.index('config')];raw=bytearray(base64.b64decode(r['data'][0]));raw[36:44]=(150000001).to_bytes(8,'little');r['data'][0]=base64.b64encode(raw).decode()
            return v
        self.no_send(change)
    def test_creation_disabled(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':
                r=v['value'][ROLES.index('config')];raw=bytearray(base64.b64decode(r['data'][0]));raw[9]=1;r['data'][0]=base64.b64encode(raw).decode()
            return v
        self.no_send(change)
    def test_rent_cap(self):self.no_send(lambda q,v,t:30000000 if q['method']=='getMinimumBalanceForRentExemption' else v)
    def test_fee_cap(self):
        self.no_send(lambda q,v,t:dict(context={'slot':102},value=10001) if q['method']=='getFeeForMessage' else v)
    def test_simulation_failed(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':v['value']['err']={'InstructionError':[2,1]}
            return v
        self.no_send(change)
    def test_simulation_replaced_blockhash(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':v['value']['replacementBlockhash']={}
            return v
        self.no_send(change)
    def test_simulation_native_mismatch(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':v['value']['postBalances'][0]+=1
            return v
        self.no_send(change)
    def test_simulation_token_mismatch(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':v['value']['postTokenBalances'][0]['uiTokenAmount']['amount']='499999999'
            return v
        self.no_send(change)
    def test_simulation_lp_authority_mismatch(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':
                r=v['value']['accounts'][ROLES.index('lpMint')];raw=bytearray(base64.b64decode(r['data'][0]));raw[:4]=bytes(4);r['data'][0]=base64.b64encode(raw).decode()
            return v
        self.no_send(change)
    def test_simulation_oracle_mismatch(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':
                r=v['value']['accounts'][ROLES.index('observation')];raw=bytearray(base64.b64decode(r['data'][0]));raw[11:43]=bytes(32);r['data'][0]=base64.b64encode(raw).decode()
            return v
        self.no_send(change)
    def test_state_changed_before_send(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts' and len(t.calls)>7:v['value'][0]['lamports']-=1
            return v
        self.no_send(change)
    def test_near_expiry(self):self.no_send(lambda q,v,t:999 if q['method']=='getBlockHeight' else v)
    def test_send_timeout_recovers_without_resend(self):
        def change(q,v,t):
            if q['method']=='sendTransaction':raise urllib.error.URLError('timeout')
            return v
        r,t=self.run_pool(change);self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['sendRequestsThisRun'],1)
    def test_unknown_then_recover_readonly(self):
        def change(q,v,t):
            if q['method']=='getSignatureStatuses' and t.sent:raise urllib.error.URLError('offline')
            return v
        r,t=self.run_pool(change);self.assertEqual(r['state'],'submission-unknown')
        t.change=None;r=work.recover(self.home,self.wallet,opener=t,sleeper=lambda _:None)
        self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['sendRequestsThisRun'],0)
        self.assertNotIn('sendTransaction',work.RecoveryRpc.METHODS);self.assertNotIn('simulateTransaction',work.RecoveryRpc.METHODS)
    def test_expired_unknown_not_retried(self):
        def change(q,v,t):
            if q['method']=='getSignatureStatuses' and t.sent:v['value']=[None]
            if q['method']=='getBlockHeight' and t.sent:v=1001
            return v
        r,t=self.run_pool(change);self.assertEqual(r['state'],'expired-outcome-unknown')
        self.assertEqual(work.execute(self.home,self.wallet,opener=t)['networkRequests'],0)
    def test_send_signature_mismatch(self):
        r,t=self.run_pool(lambda q,v,t:'other' if q['method']=='sendTransaction' else v);self.assertEqual(r['state'],'quarantined')
    def test_receipt_wrong_wire(self):
        def change(q,v,t):
            if q['method']=='getTransaction':v['transaction'][0]='wrong'
            return v
        r,t=self.run_pool(change);self.assertEqual(r['state'],'quarantined')
    def test_receipt_missing_tokens_remains_unknown(self):
        def change(q,v,t):
            if q['method']=='getTransaction':del v['meta']['postTokenBalances']
            return v
        r,t=self.run_pool(change);self.assertEqual(r['state'],'submission-unknown')
    def test_receipt_extra_token_quarantined(self):
        def change(q,v,t):
            if q['method']=='getTransaction':v['meta']['postTokenBalances'].append(copy.deepcopy(v['meta']['postTokenBalances'][0]))
            return v
        r,t=self.run_pool(change);self.assertEqual(r['state'],'quarantined')
    def test_finalized_failure_fee_only(self):
        def change(q,v,t):
            if q['method']=='getSignatureStatuses' and t.sent:v['value'][0]['err']={'InstructionError':[2,1]}
            if q['method']=='getTransaction':
                i=t.plan();pre,post=balances(i,False);v['meta'].update(err={'InstructionError':[2,1]},preBalances=pre,postBalances=post,
                    postTokenBalances=token_list(i,True,False))
            return v
        r,t=self.run_pool(change);self.assertEqual(r['state'],'finalized-failure',r)
        self.assertEqual(r['latestObservation']['receipt']['creationFeeLamports'],'0')
    def test_missing_post_accounts_recoverable(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts' and t.sent:v['value'][1]=None
            return v
        r,t=self.run_pool(change);self.assertEqual(r['state'],'finalized-success-accounts-unverified')
        t.change=None;r=work.recover(self.home,self.wallet,opener=t,sleeper=lambda _:None);self.assertEqual(r['state'],'finalized-success')
    def test_pool_changed_after_finality_not_called_success(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts' and t.sent:
                r=v['value'][ROLES.index('vault0')];raw=bytearray(base64.b64decode(r['data'][0]));raw[64:72]=(DEPOSIT+1).to_bytes(8,'little');r['data'][0]=base64.b64encode(raw).decode()
            return v
        r,t=self.run_pool(change);self.assertEqual(r['state'],'quarantined')
    def test_signer_cannot_repeat(self):
        self.prepare_only()
        with self.assertRaises(ValueError):work.signer(self.home)
    def test_signed_unsubmitted_execute_not_reused(self):
        self.prepare_only();r,t=self.run_pool();self.assertEqual(r['networkRequests'],0);self.assertEqual(r['sendRequestsThisRun'],0)
    def test_signing_marker_prevents_sign_after_crash(self):
        # Crash immediately after the exclusive marker; no signed bytes or execution retry.
        (result,t)=self.prepare_only();child=self.home/CHILD
        for name in ('signed.json','simulation-request.json','simulation-response.json','simulation-review.json'):(child/name).unlink()
        with self.assertRaises(ValueError):work.signer(self.home)
        r,t=self.run_pool();self.assertEqual(r['state'],'signing-outcome-unknown');self.assertEqual(r['networkRequests'],0)
    def test_crash_at_send_boundary_recovers_without_send(self):
        save=work.write_new
        def write(p,v):
            save(p,v)
            if p.name=='send-boundary.json':raise KeyboardInterrupt()
        with patch('pool_workflow.write_new',side_effect=write):
            with self.assertRaises(KeyboardInterrupt):self.run_pool()
        t=Transport(self.home);r=work.recover(self.home,self.wallet,opener=t,sleeper=lambda _:None)
        self.assertEqual(r['sendRequestsThisRun'],0);self.assertEqual(r['state'],'submission-unknown')
    def test_preexisting_pair_must_be_finalized(self):
        child=self.home/'test-token-pair-v1'
        for p in child.glob('observation-*.json'):p.unlink()
        r,t=self.run_pool();self.assertEqual(r['sendRequestsThisRun'],0);self.assertEqual(t.calls,[])
    def test_simulation_missing_token_evidence_no_send(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':del v['value']['postTokenBalances']
            return v
        self.no_send(change)
    def test_freeze_or_mint_authority_before_setup_no_journal(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':
                r=v['value'][ROLES.index('mint0')];raw=bytearray(base64.b64decode(r['data'][0]));raw[46:50]=(1).to_bytes(4,'little');raw[50:82]=raw58(self.wallet);r['data'][0]=base64.b64encode(raw).decode()
            return v
        r,t=self.no_send(change);self.assertFalse((self.home/CHILD).exists())
    def test_holder_delegate_no_journal(self):
        def change(q,v,t):
            if q['method']=='getMultipleAccounts':
                r=v['value'][ROLES.index('holder0')];raw=bytearray(base64.b64decode(r['data'][0]));raw[72:76]=(1).to_bytes(4,'little');raw[76:108]=raw58(self.wallet);r['data'][0]=base64.b64encode(raw).decode()
            return v
        r,t=self.no_send(change);self.assertFalse((self.home/CHILD).exists())
    def test_receipt_extra_native_debit_quarantines(self):
        def change(q,v,t):
            if q['method']=='getTransaction':v['meta']['postBalances'][0]-=1
            return v
        r,t=self.run_pool(change);self.assertEqual(r['state'],'quarantined')
    def test_expiry_after_simulation_prevents_send(self):
        def change(q,v,t):
            if q['method']=='simulateTransaction':
                self.future=work.clock()+31000
            return v
        original=work.clock
        with patch('pool_workflow.clock',side_effect=lambda:getattr(self,'future',original())):
            self.no_send(change)
    def test_inspect_does_not_expose_signed_bytes(self):
        r=work.inspect(self.home,self.wallet,opener=Transport(self.home))
        self.assertEqual(r['state'],'funding-ready');self.assertFalse(r['signedBytesExported'])
        wire=json.loads((self.home/'test-token-pair-v1/signed.json').read_text())['wire']
        self.assertNotIn(wire,json.dumps(r))
    def test_signer_rejects_changed_deposit(self):
        # Build a new unsigned intent, then mutate it before the restricted signer sees it.
        t=Transport(self.home);rpc=work.PoolRpc(t)
        def refuse(home):raise RuntimeError('pause-before-sign')
        with Session(self.home) as s:
            c=work.capture(rpc,self.pair);child=self.home/CHILD;child.mkdir(mode=0o700)
            with patch('pool_workflow.signer',side_effect=refuse):
                with self.assertRaises(RuntimeError):work.prepare(s,child,c,rpc)
        i=json.loads((child/'plan.json').read_text());i['depositAtomicPerMint']='500000001';(child/'plan.json').write_text(json.dumps(i))
        with self.assertRaises(ValueError):work.signer(self.home)
        self.assertFalse((child/'signing-attempt.json').exists())


class ContractCase(unittest.TestCase):
    def test_official_sdk_pda_vectors(self):
        prog='BPFLoader1111111111111111111111111111111111'
        vectors=[([b'',b'\x01'],'3gF2KMe9KiC6FNVBmfg9i267aMPvK37FewCip4eGBFcT'),
          (['☉'.encode()],'7ytmC1nT1xY4RfxCV2ZgyA7UakC93do5ZdyhdF3EtPj7'),
          ([b'Talking',b'Squirrels'],'HwRVBufQ4haG5XSgpspwKtNd3PC9GM9m1196uJW36vds'),
          ([raw58('SeedPubey1111111111111111111111111111111111')],'GUs5qLUfsEHkcMB9T38vjr18ypEhRuNWiePW2LoK4E3K')]
        for seeds,expected in vectors:self.assertEqual(create_pda(seeds,prog),expected)
        self.assertEqual(pda([b'vault_and_lp_mint_auth_seed']),(AUTHORITY,255))
    def test_recorded_devnet_pool_address_vectors(self):
        # Public accounts from the reviewed 2026-10-20 devnet snapshot; independent of this compiler.
        pool='3CxsELVbhg3L37ptLm7aihdWoSohUFnJxE3JxdCURFce'
        m0='2XS9anBPc1igefTPpowVM2hUnz7rCR8LLwVcJuNjFFSd';m1='AdHRwAhZguLSUZZRpxGZYsXRuTsiWtm3gHTanJJiaB2d'
        cases=[([b'pool',raw58(CONFIG),raw58(m0),raw58(m1)],pool,255),
          ([b'pool_lp_mint',raw58(pool)],'9qDmu73CbvXVacmrwf6THBZ5jVrusNGHumyA5bbZb8Dx',253),
          ([b'pool_vault',raw58(pool),raw58(m0)],'2xPBEyrop2uzpfBYiXteaABpZzPu7U7nutBTrwXqkXQP',255),
          ([b'pool_vault',raw58(pool),raw58(m1)],'6YxDMQME8MFHFZUKT4skEiub5GjK3EwyZCZWVBpEuqtk',253),
          ([b'observation',raw58(pool)],'EqJ6aq2Qvyb2kqQRoMLFQ8rSK16PUpR3zcxovYULKTiJ',252)]
        for seeds,key,bump in cases:self.assertEqual(pda(seeds),(key,bump))
        module=Path(__file__).with_name('pool_policy.mjs').as_uri()
        vectors=[dict(seeds=[base64.b64encode(s).decode() for s in seeds],expected=[key,bump]) for seeds,key,bump in cases]
        js=f"import {{pda}} from {json.dumps(module)};const v={json.dumps(vectors)};console.log(JSON.stringify(v.map(x=>pda(x.seeds.map(s=>Buffer.from(s,'base64')),{json.dumps(PROGRAM)}))));"
        self.assertEqual(json.loads(subprocess.check_output(['node','--input-type=module','-e',js],text=True)),[v['expected'] for v in vectors])
    def test_curve_predicate_and_aliases(self):
        self.assertTrue(on_curve(bytes.fromhex('58'+'66'*31)))
        self.assertFalse(on_curve(raw58('12rqwuEgBYiGhBrDJStCiqEtzQpTTiZbh7teNVLuYcFA')))
        pair={n:fake_key(n) for n in ('wallet','mintA','holderA','mintB','holderB')};pair['mintB']=pair['mintA']
        with self.assertRaises(ValueError):addresses(pair)
    def test_pda_seed_limits(self):
        for seeds in ([b'x'*33],[b'']*16):
            with self.assertRaises(ValueError):pda(seeds)
    def test_independent_node_and_python_addresses_and_message(self):
        pair={n:fake_key(n) for n in ('wallet','mintA','holderA','mintB','holderB')};block=fake_key('block')
        module=Path(__file__).with_name('pool_policy.mjs').as_uri()
        js=f"import {{addresses,message}} from {json.dumps(module)}; const p={json.dumps(pair)};console.log(JSON.stringify({{addresses:addresses(p),message:message(p,{json.dumps(block)}).toString('base64')}}));"
        result=json.loads(subprocess.check_output(['node','--input-type=module','-e',js],text=True))
        self.assertEqual(result['addresses'],addresses(pair));self.assertEqual(result['message'],base64.b64encode(message(pair,block)).decode())
        a=addresses(pair);self.assertLess(raw58(a['mint0']),raw58(a['mint1']))
        self.assertLessEqual(len(message(pair,block))+65,1232)
    def test_fixed_message_is_one_signer_with_exact_initialize(self):
        pair={n:fake_key(n) for n in ('wallet','mintA','holderA','mintB','holderB')};msg=message(pair,fake_key('block'))
        self.assertEqual(msg[:4],bytes([1,0,10,20]));self.assertTrue(msg.endswith(DISCRIMINATOR+DEPOSIT.to_bytes(8,'little')*2+bytes(8)))
        self.assertEqual(DISCRIMINATOR.hex(),'afaf6d1f0d989bed')

if __name__=='__main__':unittest.main()
