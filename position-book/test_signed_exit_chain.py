"""Exact saved identity, bounded synthetic RPC, and no mutation/authority on observation."""
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import signed_exit_chain as m
from exit_submission_checks import signed_case, submit, FakeRpc
from test_signed_exit_timing import files


class Replies:
    def __init__(self,c,valid=False,status=None,hook=None):
        self.c=c;self.valid=valid;self.status=status;self.hook=hook;self.calls=[]
    def open(self,request,timeout):
        q=json.loads(request.data);self.calls.append(q)
        self.assert_request(q,request)
        slot=self.c.exit_state['minimumContextSlot']+10
        if q['method']=='getGenesisHash':value=m.GENESIS['devnet']
        elif q['method']=='isBlockhashValid':value=dict(context=dict(slot=slot),value=self.valid)
        else:value=dict(context=dict(slot=slot+1),value=[self.status])
        if self.hook:value=self.hook(q,value)
        return io.BytesIO(json.dumps(dict(jsonrpc='2.0',id=q['id'],result=value)).encode())
    def assert_request(self,q,request):
        assert request.full_url==m.ENDPOINTS['devnet'] and request.get_method()=='POST'
        state=self.c.exit_state
        expected=[('getGenesisHash',[]),('isBlockhashValid',[state['request']['packet']['policy']['blockhash'],
            dict(commitment='finalized',minContextSlot=state['minimumContextSlot'])]),
            ('getSignatureStatuses',[[state['signed']['signature']],dict(searchTransactionHistory=True)]),('getGenesisHash',[])]
        assert (q['method'],q['params'])==expected[len(self.calls)-1]


class ChainTests(unittest.TestCase):
    def observe(self,c,rpc,expected=None,mono=lambda:0):
        return m.inspect(c.home,c.wallet,c.pool,
            expected or c.exit_state['request']['preparationSha256'],opener=rpc,
            clock=lambda:c.now,monotonic=mono)

    def test_absent_status_keeps_holds_for_valid_and_invalid_blockhash_and_stop(self):
        with signed_case() as c:
            c.now+=30000
            for valid in (True,False):
                (c.home/'STOP').touch(mode=0o600)
                before=files(c);rpc=Replies(c,valid=valid)
                with patch.object(m.history.backend,'_invoke',side_effect=AssertionError('signer')):
                    result=self.observe(c,rpc)
                self.assertEqual(result['state'],'signed-exit-chain-observed',result)
                self.assertEqual(result['observation']['blockhashValidAtFinalized'],valid)
                self.assertFalse(result['observation']['signatureFound'])
                self.assertEqual(result['networkRequests'],4);self.assertEqual(files(c),before)
                for key in ('privateKeyAccessed','sourceStateChanged','transactionsSent','signaturesCreated',
                            'reservationsReleasedThisRun','replacementAuthorized','retryAllowed','executionApproved'):
                    self.assertFalse(result[key])
                public=json.dumps(result)
                for secret in (c.exit_wire,c.wallet,c.exit_state['signed']['signature']):self.assertNotIn(secret,public)
                self.assertEqual(result['scopedAccounting']['ownedAcquiredHeldAtomic'],'98')

    def test_found_status_requires_receipt_even_if_finalized(self):
        with signed_case() as c:
            c.now+=30000;slot=c.exit_state['minimumContextSlot']+1;before=files(c)
            for confirmation,failed in (('processed',False),('confirmed',False),('finalized',False),('finalized',True)):
                row=dict(slot=slot,confirmationStatus=confirmation,confirmations=None if confirmation=='finalized' else 1,
                         err={'private-provider-detail':1} if failed else None)
                result=self.observe(c,Replies(c,status=row))
                self.assertEqual(result['state'],'signed-exit-chain-observed',result)
                obs=result['observation'];self.assertEqual(obs['classification'],'signature-status-observed-receipt-required')
                self.assertEqual(obs['signatureStatus']['executionErrorReported'],failed)
                self.assertFalse(obs['receiptEffectsReconciled'])
                self.assertNotIn('private-provider-detail',json.dumps(result))
            self.assertEqual(files(c),before)

    def test_local_mismatch_corrupt_ack_and_send_boundary_refuse_before_rpc(self):
        with signed_case() as c:
            c.now+=30000;rpc=Replies(c);before=files(c)
            result=self.observe(c,rpc,expected='0'*64)
            self.assertEqual(result['state'],'chain-observation-unavailable');self.assertEqual(rpc.calls,[])
            self.assertEqual(files(c),before)
            ack=c.path.parent/m.history.backend.ACK;ack.write_text('{}');before=files(c)
            result=self.observe(c,rpc)
            self.assertEqual(result['state'],'chain-observation-unavailable');self.assertEqual(rpc.calls,[])
            self.assertEqual(files(c),before)
        with signed_case() as c:
            submit(c,FakeRpc(c,lost=True));c.now+=30000;before=files(c);rpc=Replies(c)
            result=self.observe(c,rpc)
            self.assertEqual(result['state'],'chain-observation-unavailable');self.assertEqual(rpc.calls,[])
            self.assertEqual(files(c),before)

    def test_rpc_failures_cluster_mismatch_and_malformed_context_publish_no_partial_result(self):
        with signed_case() as c:
            c.now+=30000;before=files(c)
            mutations=[lambda q,v:'wrong-cluster' if q['id']==1 else v,
                       lambda q,v:'wrong-cluster' if q['id']==4 else v,
                       lambda q,v:dict(context=dict(slot=0),value=False) if q['id']==2 else v,
                       lambda q,v:dict(context=dict(slot=c.exit_state['minimumContextSlot']),value=[None]) if q['id']==3 else v,
                       lambda q,v:dict(context=dict(slot=999999),value=0) if q['id']==2 else v,
                       lambda q,v:dict(context=dict(slot=999999),value=[]) if q['id']==3 else v]
            for mutation in mutations:
                result=self.observe(c,Replies(c,hook=mutation))
                self.assertEqual(result['state'],'chain-observation-unavailable')
                self.assertIsNone(result['observation']);self.assertIsNone(result['identity'])
                self.assertEqual(files(c),before)
            class Broken:
                def open(self,*a,**kw):raise TimeoutError('private-rpc-error')
            result=self.observe(c,Broken())
            self.assertEqual(result['networkRequests'],1);self.assertNotIn('private-rpc-error',json.dumps(result))

    def test_changed_backend_during_read_and_network_budget_discard_observation(self):
        with signed_case() as c:
            c.now+=30000
            def mutate(q,value):
                if q['id']==4:(c.path.parent/m.history.backend.ACK).write_text('{}')
                return value
            result=self.observe(c,Replies(c,hook=mutate))
            self.assertEqual(result['networkRequests'],4);self.assertIsNone(result['observation'])
        with signed_case() as c:
            c.now+=30000;counter=[0];before=files(c)
            def slow(q,value):counter[0]=31;return value
            result=self.observe(c,Replies(c,hook=slow),mono=lambda:counter[0])
            self.assertEqual(result['networkRequests'],1);self.assertIsNone(result['observation'])
            self.assertEqual(files(c),before)

    def test_response_cap_request_binding_and_no_sender_method(self):
        import urllib.request
        class Large:
            def open(self,*a,**kw):return io.BytesIO(b'x'*(m.MAX_RESPONSE+1))
        plan=[('getGenesisHash',[])]
        transport=m.BoundedReads(plan,Large(),lambda:0);rpc=m.ChainRpc('devnet',transport)
        self.assertEqual(rpc.request('getGenesisHash',[])['state'],'invalid-response')
        with self.assertRaises(ValueError):rpc.request('sendTransaction',[])
        class Truncated:
            def open(self,*a,**kw):
                response=io.BytesIO(b'{"jsonrpc":"2.0","id":1,"result":"ok"}')
                response.length=999
                return response
        bad=m.ChainRpc('devnet',m.BoundedReads(plan,Truncated(),lambda:0))
        self.assertEqual(bad.request('getGenesisHash',[])['state'],'invalid-response')
        t=m.BoundedReads(plan,Large(),lambda:0)
        req=urllib.request.Request('https://api.mainnet-beta.solana.com',data=b'{}')
        with self.assertRaises(ValueError):t.open(req,10)
        self.assertEqual(t.calls,[])

    def test_status_types_and_finalized_fields_are_not_coerced(self):
        validity=dict(state='received',result=dict(context=dict(slot=10),value=False))
        normal=dict(slot=10,err=None,confirmations=None,confirmationStatus='finalized')
        for key,value in (('slot',True),('slot',12),('err',False),('confirmations',0),('confirmationStatus','unknown')):
            row=dict(normal);row[key]=value
            statuses=dict(state='received',result=dict(context=dict(slot=11),value=[row]))
            with self.assertRaises(ValueError):m.classify(validity,statuses,5)

    def test_cli_requires_exact_scope_and_cannot_execute_or_overwrite(self):
        cli=Path(__file__).with_name('signed_exit_chain_cli.py')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz'
            base=[sys.executable,'-E','-s',str(cli),'--output',str(out)]
            for extra in ([],['--action','execute'],['--allow-devnet-submit']):
                p=subprocess.run(base+extra,capture_output=True,timeout=10)
                self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())
            scope=['--directory',str(Path(d)/'source'),'--wallet','invalid',
                   '--pool','invalid','--preparation-sha256','0'*64]
            out.write_bytes(b'keep')
            p=subprocess.run(base+scope,capture_output=True,timeout=10)
            self.assertNotEqual(p.returncode,0);self.assertEqual(out.read_bytes(),b'keep')
            root=Path(d)/'source';root.mkdir()
            inside=root/'report.gz'
            p=subprocess.run(base[:-1]+[str(inside)]+scope,capture_output=True,timeout=10)
            self.assertNotEqual(p.returncode,0);self.assertFalse(inside.exists())


if __name__=='__main__':unittest.main()
