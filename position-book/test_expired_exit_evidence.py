"""Synthetic expiry observations must never become execution or release authority."""
from copy import deepcopy
import base64
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import expired_exit_evidence as m
from exit_submission_checks import signed_case
from test_signed_exit_timing import files


@m.view.cycles.binding.operation
@m.chain.history.fresh_signing.timing.signature_replay
def fixture(c):
    with m.read_only_journals():
        b=c.book()
        try:
            with m.chain.history.lifecycle.admission_read_lock(b.j.path):
                return m.context(c.home,b,c.wallet,c.pool,c.exit_state['request']['preparationSha256'],lambda:c.now)
        finally:b.close()


def evidence(c,ctx):
    slot=ctx['identity']['minimumContextSlot']+10
    values=dict(genesisBefore=m.chain.GENESIS['devnet'],genesisAfter=m.chain.GENESIS['devnet'],
        validity=dict(context=dict(slot=slot),value=False),height=ctx['lastValidBlockHeight']+1,
        status=dict(context=dict(slot=slot+1),value=[None]),transaction=None,
        accounts=dict(context=dict(slot=slot+2),value=deepcopy(ctx['expectedAccounts'])),blockTime=c.now//1000)
    return {k:dict(state='received',result=v) for k,v in values.items()}


class Replies:
    def __init__(self,c,ctx,hook=None):
        self.ev=evidence(c,ctx);self.calls=[];self.hook=hook
        i=ctx['identity'];slot=i['minimumContextSlot']+10
        self.params=[[],[i['blockhash'],dict(commitment='finalized',minContextSlot=i['minimumContextSlot'])],
            [dict(commitment='finalized',minContextSlot=slot)],[[i['signature']],dict(searchTransactionHistory=True)],
            [i['signature'],dict(encoding='base64',commitment='finalized',maxSupportedTransactionVersion=0)],
            [ctx['accountKeys'],dict(encoding='base64',commitment='finalized',minContextSlot=slot+1)],[slot+2],[]]
    def open(self,request,timeout):
        q=json.loads(request.data);n=len(self.calls);self.calls.append(q)
        assert request.full_url==m.chain.ENDPOINTS['devnet'] and request.method=='POST'
        assert q['method']==m.ORDER[n] and q['params']==self.params[n] and q['id']==n+1
        key=('genesisBefore','validity','height','status','transaction','accounts','blockTime','genesisAfter')[n]
        v=self.ev[key]['result']
        if self.hook:v=self.hook(q,v)
        return io.BytesIO(json.dumps(dict(jsonrpc='2.0',id=q['id'],result=v)).encode())


class EvidenceTests(unittest.TestCase):
    def observe(self,c,rpc,expected=None,mono=lambda:0):
        return m.inspect(c.home,c.wallet,c.pool,expected or c.exit_state['request']['preparationSha256'],
            opener=rpc,clock=lambda:c.now,monotonic=mono)

    def test_eight_exact_reads_preserve_stop_journals_and_every_hold(self):
        with signed_case() as c:
            c.now+=30000;ctx=fixture(c);(c.home/'STOP').touch(mode=0o600);before=files(c)
            with patch.object(m.chain.history.backend,'_invoke',side_effect=AssertionError('signer')):
                result=self.observe(c,Replies(c,ctx))
            self.assertEqual(result['state'],'expired-exit-evidence-observed',result)
            self.assertEqual(result['assessment']['state'],'expiry-evidence-consistent-held')
            self.assertEqual(result['requestMethods'],list(m.ORDER));self.assertEqual(result['networkRequests'],8)
            self.assertEqual(files(c),before)
            for k in ('privateKeyAccessed','sourceStateChanged','signaturesCreated','transactionsSent',
                      'reservationsReleasedThisRun','replacementAuthorized','retryAllowed','executionApproved'):
                self.assertFalse(result[k])
            for k in ('nonExecutionProven','recoveryAuthorized'):self.assertFalse(result['assessment'][k])
            public=json.dumps(result)
            for secret in (c.exit_wire,c.wallet,ctx['identity']['signature']):self.assertNotIn(secret,public)

    def test_expiry_receipt_and_account_changes_remain_explicit_blockers(self):
        with signed_case() as c:
            c.now+=30000;ctx=fixture(c);original=evidence(c,ctx);before=files(c)
            cases=[]
            ev=deepcopy(original);ev['height']['result']=ctx['lastValidBlockHeight'];cases.append((ev,'block-expiry-not-established'))
            ev=deepcopy(original);ev['validity']['result']['value']=True;cases.append((ev,'block-expiry-not-established'))
            ev=deepcopy(original);ev['status']['result']['value']=[dict(slot=ctx['identity']['minimumContextSlot'],err=None,confirmations=None,confirmationStatus='finalized')];cases.append((ev,'signature-status-present'))
            for wire in (ctx['signedWire'],'different'):
                ev=deepcopy(original);ev['transaction']['result']=dict(slot=ctx['identity']['minimumContextSlot'],transaction=[wire,'base64'])
                cases.append((ev,'transaction-present-receipt-required' if wire==ctx['signedWire'] else 'returned-transaction-wire-conflict'))
            for delta in (-1,100):
                ev=deepcopy(original);ev['accounts']['result']['value'][0]['lamports']+=delta;cases.append((ev,'wallet-account-changed'))
            ev=deepcopy(original);ev['accounts']['result']['value'][0]['lamports']=1;cases.append((ev,'held-fee-shortfall'))
            for index,reason in ((1,'token-account-changed'),(2,'protected-or-owned-inventory-shortfall'),(3,'mint-account-changed')):
                ev=deepcopy(original);row=ev['accounts']['result']['value'][index];raw=bytearray(base64.b64decode(row['data'][0]))
                if index<3:raw[64:72]=(0).to_bytes(8,'little')
                else:raw[36:44]=(1).to_bytes(8,'little')
                row['data'][0]=base64.b64encode(raw).decode();cases.append((ev,reason))
            ev=deepcopy(original);row=ev['accounts']['result']['value'][2];raw=bytearray(base64.b64decode(row['data'][0]));raw[129:133]=(1).to_bytes(4,'little');raw[133:165]=b'\x01'*32;row['data'][0]=base64.b64encode(raw).decode();cases.append((ev,'token-controls-changed'))
            for ev,reason in cases:
                with self.subTest(reason=reason):
                    result=m.assess(ctx,ev,c.now,c.now)
                    self.assertIn(reason,result['blockers']);self.assertFalse(result['recoveryAuthorized'])
                    self.assertEqual(result['state'],'expiry-evidence-needs-review-held')
            self.assertEqual(files(c),before)

    def test_bad_slots_times_heights_or_accounts_are_not_success(self):
        with signed_case() as c:
            c.now+=30000;ctx=fixture(c);original=evidence(c,ctx)
            for key,value in (('height',True),('height',-1),('blockTime',None),('blockTime',c.now//1000-31),('blockTime',c.now//1000+3),('genesisAfter','wrong')):
                ev=deepcopy(original);ev[key]['result']=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):m.assess(ctx,ev,c.now,c.now)
            ev=deepcopy(original);ev['accounts']['result']['context']['slot']=ctx['identity']['minimumContextSlot']
            with self.assertRaises(ValueError):m.assess(ctx,ev,c.now,c.now)
            ev=deepcopy(original);ev['accounts']['result']['value'][2]=None
            with self.assertRaises((ValueError,TypeError)):m.assess(ctx,ev,c.now,c.now)

    def test_unavailable_rpc_identity_and_changed_local_state_publish_no_assessment(self):
        with signed_case() as c:
            c.now+=30000;ctx=fixture(c);before=files(c);rpc=Replies(c,ctx)
            result=self.observe(c,rpc,expected='0'*64);self.assertEqual(rpc.calls,[]);self.assertIsNone(result['assessment'])
            class Broken:
                def open(self,*a,**k):raise TimeoutError('private provider detail')
            result=self.observe(c,Broken());self.assertEqual(result['networkRequests'],1);self.assertNotIn('private provider detail',json.dumps(result))
            def stale(q,v):return c.now//1000-31 if q['method']=='getBlockTime' else v
            result=self.observe(c,Replies(c,ctx,stale));self.assertIsNone(result['assessment']);self.assertEqual(files(c),before)
            def mutation(q,v):
                if q['id']==8:(c.path.parent/m.chain.history.backend.ACK).write_text('{}')
                return v
            result=self.observe(c,Replies(c,ctx,mutation));self.assertEqual(result['networkRequests'],8);self.assertIsNone(result['assessment'])

    def test_budget_stops_reads_and_sender_method_is_disallowed(self):
        with signed_case() as c:
            c.now+=30000;ctx=fixture(c);counter=[0];before=files(c)
            def slow(q,v):counter[0]=31;return v
            result=self.observe(c,Replies(c,ctx,slow),mono=lambda:counter[0])
            self.assertEqual(result['networkRequests'],1);self.assertIsNone(result['assessment']);self.assertEqual(files(c),before)
        rpc=m.Rpc('devnet')
        with self.assertRaises(ValueError):rpc.request('sendTransaction',[])

    def test_failed_private_handoff_never_publishes_success(self):
        with signed_case() as c:
            c.now+=30000;ctx=fixture(c);before=files(c)
            def broken(_):raise ValueError('private handoff failed')
            result=m.inspect(c.home,c.wallet,c.pool,c.exit_state['request']['preparationSha256'],
                opener=Replies(c,ctx),clock=lambda:c.now,monotonic=lambda:0,_evidence_sink=broken)
            self.assertEqual(result['state'],'expiry-evidence-unavailable')
            self.assertIsNone(result['assessment']);self.assertEqual(files(c),before)

    def test_cli_has_no_execution_mode_and_preserves_existing_output(self):
        cli=Path(__file__).with_name('expired_exit_evidence_cli.py')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out.gz';root=Path(d)/'source';root.mkdir()
            base=[sys.executable,'-E','-s',str(cli),'--directory',str(root),'--wallet','invalid','--pool','invalid','--preparation-sha256','0'*64,'--output',str(out)]
            for flag in ('--allow-devnet-submit','--action'):
                p=subprocess.run(base+[flag],capture_output=True,timeout=10);self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())
            out.write_bytes(b'keep');p=subprocess.run(base,capture_output=True,timeout=10)
            self.assertNotEqual(p.returncode,0);self.assertEqual(out.read_bytes(),b'keep')
            p=subprocess.run(base[:-1]+[str(root/'out.gz')],capture_output=True,timeout=10)
            self.assertNotEqual(p.returncode,0);self.assertFalse((root/'out.gz').exists())


if __name__=='__main__':unittest.main()
