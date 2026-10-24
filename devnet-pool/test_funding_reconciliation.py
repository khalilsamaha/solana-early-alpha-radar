"""Real Ed25519 funding wires, synthetic finalized RPC, no funded keys or network."""
import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import shutil
import unittest
from unittest.mock import patch
import cycle_preparation as c
import funding_reconciliation as f
from core import raw58
import test_cycle_preparation as cycle_tests
from test_cycle_preparation import Transport
from pool_fixtures import Response, fake_key


def signed_credit(wallet, before, amount, slot=135, *, compute=False, recipient=None, opcode=2):
    # A fresh disposable donor signs a fixed synthetic message. No project key is read.
    script = r'''
const crypto=require('node:crypto'); const fs=require('node:fs');
const a=JSON.parse(fs.readFileSync(0,'utf8')); const {privateKey,publicKey}=crypto.generateKeyPairSync('ed25519');
const donor=publicKey.export({format:'der',type:'spki'}).subarray(-32);
const msg=Buffer.concat([Buffer.from(a.prefix,'base64'),donor,Buffer.from(a.tail,'base64')]);
const sig=crypto.sign(null,msg,privateKey);
process.stdout.write(JSON.stringify({wire:Buffer.concat([Buffer.from([1]),sig,msg]).toString('base64')}));
'''
    keys = [raw58(recipient or wallet), bytes(32)] + ([raw58(f.COMPUTE)] if compute else [])
    ix = bytes([2, 2, 0, 1, 12]) + opcode.to_bytes(4, 'little') + amount.to_bytes(8, 'little')
    if compute: ix = bytes([3, 0, 5, 2])+(200000).to_bytes(4,'little')+ix
    tail = b''.join(keys)+raw58(fake_key('funding-block-'+str(slot)))+bytes([2 if compute else 1])+ix
    payload=dict(prefix=base64.b64encode(bytes([1,0,len(keys)-1,len(keys)+1])).decode(),tail=base64.b64encode(tail).decode())
    result=subprocess.run([str(Path(shutil.which('node')).resolve()),'-e',script],input=json.dumps(payload),text=True,capture_output=True,
                          check=True,timeout=5,env={'PATH':os.defpath})
    wire=json.loads(result.stdout)['wire']; sig=f.decode_wire(wire)[4]['transaction']['signatures'][0]
    pre=[amount+100000,before,1]+([1] if compute else [])
    post=pre.copy();post[0]-=amount+5000;post[1]+=amount
    tx=dict(slot=slot,version='legacy',transaction=[wire,'base64'],meta=dict(err=None,fee=5000,
        preBalances=pre,postBalances=post,preTokenBalances=[],postTokenBalances=[],innerInstructions=[],
        loadedAddresses=dict(writable=[],readonly=[])))
    return dict(signature=sig,slot=slot,err=None,confirmationStatus='finalized'),tx


class FundingTransport(Transport):
    def __init__(self,home,wallet,amounts=(20000000000,),change=None,compute=False):
        super().__init__(home,wallet,change)
        self.fund=[]; before=self.rows[wallet]['lamports']
        for n,amount in enumerate(amounts):
            row,tx=signed_credit(wallet,before,amount,135+n,compute=compute)
            self.fund.append((row,tx));before+=amount
        self.rows[wallet]['lamports']=before
        last=c.local(home,wallet,c.submit.read(home/c.submit.CHILD,'plan.json')['scope']['accounts']['pool'])[0]['exitReceipt']
        self.history=[x[0] for x in reversed(self.fund)]+[dict(signature=last['signature'],slot=last['slot'],err=None,confirmationStatus='finalized')]
        self.latest=max(140,135+len(amounts));self.scans=0
    def open(self,req,timeout=None):
        q=json.loads(req.data);method=q['method']
        if method not in ('getSignaturesForAddress','getMultipleAccounts') and not (
            method=='getTransaction' and q['params'][0] not in self.receipts):
            return super().open(req,timeout)
        self.calls.append(q)
        assert req.full_url=='https://api.devnet.solana.com'
        if method=='getSignaturesForAddress':
            assert q['params'][1]['limit']==17 and q['params'][1]['commitment']=='finalized'
            self.scans+=1;v=copy.deepcopy(self.history)
        elif method=='getTransaction':
            assert q['params'][1]==dict(encoding='base64',commitment='finalized',maxSupportedTransactionVersion=0)
            v=copy.deepcopy(next(tx for row,tx in self.fund if row['signature']==q['params'][0]))
        else:
            assert q['params'][1]['commitment']=='finalized'
            v=dict(context={'slot':self.latest},value=[copy.deepcopy(self.rows[k]) for k in q['params'][0]])
        if self.change:v=self.change(q,v)
        return Response(json.dumps(dict(jsonrpc='2.0',id=q['id'],result=v)).encode())


class FundingCase(unittest.TestCase):
    setUpClass=classmethod(cycle_tests.CyclePreparationCase.setUpClass.__func__)
    tearDownClass=classmethod(cycle_tests.CyclePreparationCase.tearDownClass.__func__)
    setUp=cycle_tests.CyclePreparationCase.setUp
    tearDown=cycle_tests.CyclePreparationCase.tearDown
    old_files=cycle_tests.CyclePreparationCase.old_files

    def prepare(self,t=None,**kw):
        return c.run(self.home,self.wallet,self.pool,prepare=True,reconcile_funding=True,
                     opener=t or FundingTransport(self.home,self.wallet),**kw)
    def refuses(self,t,reason=None):
        with self.assertRaisesRegex(ValueError,reason or '.'):
            self.prepare(t)
        self.assertFalse((self.home/c.CYCLE).exists())

    def test_twenty_sol_credit_preserves_old_files_and_budget_and_replays_without_rpc(self):
        before=self.old_files();r=self.prepare()
        self.assertEqual(r['networkRequests'],12)
        self.assertEqual(r['fundingReconciliation']['externalCreditLamports'],'20000000000')
        self.assertEqual(r['budget']['cumulativeSwapFeesWithAllocationLamports'],'30000')
        self.assertEqual(r['budget']['cumulativeEntryWithAllocationAtomic'],'2000')
        self.assertFalse(r['executionApproved']);self.assertFalse(r['privateKeyAccessed'])
        self.assertFalse(r['fundingReconciliation']['spendingAllowanceIncreased'])
        self.assertEqual(before,self.old_files())
        t=FundingTransport(self.home,self.wallet);r2=self.prepare(t)
        self.assertEqual(r['preparationSha256'],r2['preparationSha256']);self.assertEqual(t.calls,[])
        self.assertEqual(r2,c.run(self.home,self.wallet,self.pool))

    def test_multiple_credits_and_compute_limit_are_verified_chronologically(self):
        r=self.prepare(FundingTransport(self.home,self.wallet,(10000000000,10000000000),compute=True))
        proof=r['fundingReconciliation'];self.assertEqual(proof['credits'],2)
        self.assertEqual(proof['externalCreditLamports'],'20000000000')
        self.assertEqual([r['slot'] for r in proof['receipts']],[135,136])

    def test_private_key_missing_still_prepares(self):
        t=FundingTransport(self.home,self.wallet);(self.home/'signer.pk8').unlink()
        with patch('core.signer',side_effect=AssertionError('key accessed')):r=self.prepare(t)
        self.assertFalse(r['privateKeyAccessed'])

    def test_unchanged_balance_uses_original_seven_requests(self):
        r=self.prepare(Transport(self.home,self.wallet));self.assertEqual(r['networkRequests'],7)
        self.assertNotIn('fundingReconciliation',r)

    def test_debit_and_token_changes_fail_without_history_reads(self):
        for kind in ('debit','token'):
            t=FundingTransport(self.home,self.wallet)
            if kind=='debit':t.rows[self.wallet]['lamports']=1
            else:
                a=c.local(self.home,self.wallet,self.pool)[0]['scope']['accounts']['source']
                raw=bytearray(base64.b64decode(t.rows[a]['data'][0]));raw[64:72]=(123).to_bytes(8,'little')
                t.rows[a]['data'][0]=base64.b64encode(raw).decode()
            self.refuses(t);self.assertEqual(t.scans,0)

    def test_missing_anchor_duplicate_and_same_slot_refuse(self):
        for kind in ('missing','duplicate','same-slot'):
            t=FundingTransport(self.home,self.wallet,(1,2))
            if kind=='missing':t.history=t.history[:-1]
            elif kind=='duplicate':t.history[0]=copy.deepcopy(t.history[1])
            else:t.history[0]['slot']=t.history[1]['slot']
            self.refuses(t)

    def test_nonfinal_or_failed_history_or_null_transaction_refuse(self):
        for field,value in (('confirmationStatus','confirmed'),('err',{'error':1})):
            t=FundingTransport(self.home,self.wallet);t.history[0][field]=value;self.refuses(t)
        t=FundingTransport(self.home,self.wallet,change=lambda q,v:None if q['method']=='getTransaction' and q['params'][0] not in t.receipts else v)
        self.refuses(t,'funding-transaction-unavailable')

    def test_receipt_balance_fee_and_signature_tampering_refuse(self):
        for kind in ('balance','fee','signature','slot'):
            t=FundingTransport(self.home,self.wallet);tx=t.fund[0][1]
            if kind=='balance':tx['meta']['postBalances'][1]+=1
            elif kind=='fee':tx['meta']['fee']+=1
            elif kind=='slot':tx['slot']+=1
            else:
                raw=bytearray(base64.b64decode(tx['transaction'][0]));raw[1]^=1
                tx['transaction'][0]=base64.b64encode(raw).decode()
            self.refuses(t)

    def test_inner_instructions_token_effects_and_loaded_addresses_refuse(self):
        for key,value in (('innerInstructions',[{}]),('preTokenBalances',[{}]),('postTokenBalances',[{}]),
                          ('loadedAddresses',dict(writable=[self.wallet],readonly=[]))):
            t=FundingTransport(self.home,self.wallet);t.fund[0][1]['meta'][key]=value;self.refuses(t)

    def test_wrong_recipient_and_system_opcode_refuse(self):
        for kw in (dict(recipient=fake_key('other')),dict(opcode=3)):
            t=FundingTransport(self.home,self.wallet);before=t.fund[0][1]['meta']['preBalances'][1]
            t.fund[0]=signed_credit(self.wallet,before,20000000000,**kw);t.history[0]=t.fund[0][0]
            self.refuses(t,'funding-unsupported-transaction')

    def test_unexplained_intermediate_or_final_balance_refuse(self):
        for kind in ('intermediate','final'):
            t=FundingTransport(self.home,self.wallet,(1,2))
            if kind=='intermediate':
                tx=t.fund[1][1];tx['meta']['preBalances'][1]+=1;tx['meta']['postBalances'][1]+=1
            else:t.rows[self.wallet]['lamports']+=1
            self.refuses(t)

    def test_history_changed_during_snapshot_refuses(self):
        t=FundingTransport(self.home,self.wallet)
        def change(q,v):
            if q['method']=='getSignaturesForAddress' and t.scans==2:return v[1:]
            return v
        t.change=change;self.refuses(t,'funding-history-changed')

    def test_fresh_snapshot_regression_and_stale_completion_refuse(self):
        t=FundingTransport(self.home,self.wallet)
        def change(q,v):
            if q['method']=='getMultipleAccounts' and t.scans:v['context']['slot']=139
            return v
        t.change=change;self.refuses(t,'funding-snapshot-mismatch')
        with self.assertRaisesRegex(ValueError,'balance-observation-expired'):
            self.prepare(now=iter((100000,100000,110000,120001)).__next__)
        self.assertFalse((self.home/c.CYCLE).exists())

    def test_saved_funding_is_reverified_even_if_seal_is_replaced(self):
        self.prepare();child=self.home/c.CYCLE;p=child/'preparation.json';r=json.loads(p.read_text())
        r['fundingProof']['transactions'][0]['meta']['fee']+=1;p.write_text(json.dumps(r))
        (child/'complete.json').write_text(json.dumps(dict(format=c.VERSION,preparationSha256=c.controlled.digest(r))))
        with self.assertRaisesRegex(ValueError,'funding-receipt-mismatch'):c.run(self.home,self.wallet,self.pool)

    def test_stop_during_funding_never_writes_preparation(self):
        t=FundingTransport(self.home,self.wallet)
        def change(q,v):
            if q['method']=='getSignaturesForAddress':
                (self.home/'STOP').touch(mode=0o600)
            return v
        t.change=change;self.refuses(t,'stop-requested')

    def test_rpc_caps_no_send_and_legacy_discovery_cap_unchanged(self):
        t=FundingTransport(self.home,self.wallet);rpc=f.FundingRpc('devnet',t)
        for name in ('sendTransaction','requestAirdrop','simulateTransaction'):
            with self.assertRaisesRegex(ValueError,'method not allowed'):rpc.request(name,[])
        for _ in range(27):rpc.request('getGenesisHash',[])
        with self.assertRaisesRegex(ValueError,'request cap'):rpc.request('getGenesisHash',[])
        legacy=f.Client('devnet',t)
        self.assertEqual(legacy.request('getSignaturesForAddress',[self.wallet,dict(limit=17,commitment='finalized')])['state'],'invalid-response')

    def test_cap_rejects_seventeen_credits_before_transaction_reads(self):
        t=FundingTransport(self.home,self.wallet)
        t.history=t.history*9
        self.refuses(t);self.assertFalse((self.home/c.CYCLE).exists())

    def test_supported_maximum_sixteen_credits_fits_record_and_request_cap(self):
        r=self.prepare(FundingTransport(self.home,self.wallet,tuple(range(1,17))))
        self.assertEqual(r['networkRequests'],27);self.assertEqual(r['fundingReconciliation']['credits'],16)
        self.assertLess((self.home/c.CYCLE/'preparation.json').stat().st_size,c.LIMIT)

    def test_boolean_negative_and_overflow_receipt_numbers_refuse(self):
        for key,value in (('fee',True),('fee',-1),('fee',2**64)):
            t=FundingTransport(self.home,self.wallet);t.fund[0][1]['meta'][key]=value;self.refuses(t)
        t=FundingTransport(self.home,self.wallet);t.fund[0][1]['version']=False;self.refuses(t)

    def test_token_changes_in_final_snapshot_refuse(self):
        t=FundingTransport(self.home,self.wallet)
        def change(q,v):
            if q['method']=='getMultipleAccounts' and t.scans:
                row=v['value'][1];raw=bytearray(base64.b64decode(row['data'][0]))
                raw[64:72]=(1).to_bytes(8,'little');row['data'][0]=base64.b64encode(raw).decode()
            return v
        t.change=change;self.refuses(t,'token-balance-changed-since-close')

    def test_prepare_funded_cli_exports_only_public_evidence(self):
        import cycle_cli
        import gzip
        import io
        import sys
        from contextlib import redirect_stdout
        output=Path(self.tmp.name)/'funding.json.gz';t=FundingTransport(self.home,self.wallet)
        rpc=f.FundingRpc('devnet',t)
        args=['cycle_cli.py','--action','prepare-funded','--directory',str(self.home),'--wallet',self.wallet,
              '--pool',self.pool,'--output',str(output)]
        with patch.object(sys,'argv',args),patch.object(f,'FundingRpc',return_value=rpc),redirect_stdout(io.StringIO()):
            cycle_cli.main()
        with gzip.open(output,'rt') as stream:r=json.load(stream)
        self.assertEqual(r['state'],'prepared-not-executable')
        self.assertEqual(r['fundingReconciliation']['externalCreditLamports'],'20000000000')
        self.assertNotIn(t.fund[0][1]['transaction'][0],json.dumps(r))
        self.assertEqual(r['signaturesCreated'],0);self.assertEqual(r['transactionsSent'],0)
