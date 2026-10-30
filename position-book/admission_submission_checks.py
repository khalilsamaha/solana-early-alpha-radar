"""Synthetic RPC transport checks with an existing public signature fixture.

No sockets, private keys, signatures, actual sends or production files.
"""
import base64
from contextlib import contextmanager
from copy import deepcopy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

import admission_submission as m
import pre_sign_admission as admission
from admission_receipt_checks import receipt, failed
from locked_admission_checks import fixture, home_fixture, NOW
from core import write_new


class FakeOpener:
    def __init__(self, case, *, send=None, lost=False, genesis=None, valid=True, fee=5001, package=None, callback=None):
        self.case=case; self.send=send; self.lost=lost; self.genesis=genesis or m.GENESIS['devnet']
        self.valid=valid; self.fee=fee; self.package=deepcopy(package or case.package)
        self.callback=callback; self.requests=[]
    def open(self, request, timeout=None):
        q=json.loads(request.data); self.requests.append(q)
        assert request.full_url==m.ENDPOINT and request.method=='POST'
        method=q['method']; params=q['params']
        if self.callback: self.callback(method)
        signature=self.case.package['bundle']['intent']['signature']
        tx=self.package['bundle']['rpcEvidence']['transaction']['result']
        # Existing fixture uses slot 100. Contexts must remain at or after it.
        if method=='getGenesisHash': value=self.genesis
        elif method=='isBlockhashValid':
            assert params==[self.case.e['costInputs']['packet']['policy']['blockhash'],{'commitment':'confirmed'}]
            value=dict(context=dict(slot=100),value=self.valid)
        elif method=='getFeeForMessage':
            assert params[0]==base64.b64encode(m.decode_wire(self.case.signed['signedTransactionBase64'])[1]).decode()
            assert params[1]=={'commitment':'confirmed','minContextSlot':100}
            value=dict(context=dict(slot=100),value=self.fee)
        elif method=='sendTransaction':
            assert params==[self.case.signed['signedTransactionBase64'],dict(encoding='base64',skipPreflight=False,preflightCommitment='confirmed',maxRetries=0,minContextSlot=100)]
            # A separate reader must see the committed boundary before transport.
            db=sqlite3.connect(self.case.path.as_uri()+'?mode=ro',uri=True)
            try: assert db.execute('SELECT COUNT(*) FROM admission_submission').fetchone()[0]==1
            finally: db.close()
            if self.lost: raise TimeoutError('synthetic lost send response')
            value=signature if self.send is None else self.send
        elif method=='getSignatureStatuses':
            assert params==[[signature],{'searchTransactionHistory':True}]
            value=self.package['bundle']['rpcEvidence']['signatureStatus']['result']
        elif method=='getTransaction':
            assert params==[signature,dict(encoding='base64',commitment='finalized',maxSupportedTransactionVersion=0)]
            value=None if tx is None else dict(deepcopy(tx),transaction=[self.package['signedTransactionBase64'],'base64'])
        else: raise AssertionError('unexpected method '+method)
        return io.BytesIO(json.dumps(dict(jsonrpc='2.0',id=q['id'],result=value)).encode())


class Case:
    def __init__(self, root):
        self.e,self.p,self.signed=fixture(); self.now=NOW+200
        self.wallet=self.p['scope']['accounts']['wallet']; self.pool=self.p['scope']['accounts']['pool']
        self.home=home_fixture(root/'source',self.wallet)
        snapshot=deepcopy(self.e['costInputs']['reservations']);snapshot.update(readStartedAtMs=self.now,observedAtMs=self.now)
        with patch.object(admission,'BASELINE',self.e['costInputs']['baseline']),patch.object(m.handoff.bridge.view,'read_locked',return_value=snapshot):
            m.handoff.dispatch(self.home,self.wallet,self.pool,self.e,self.p,
                signer_adapter=lambda _:self.signed['signedTransactionBase64'],clock=lambda:self.now)
        self.path=m.handoff.storage(self.home)
        b=self.book()
        try:
            state,_,_,_=b.read();head=b.db.execute('SELECT hash FROM admission_events WHERE seq=3').fetchone()[0]
            write_new(self.path.parent/'signer-attempt.json',dict(format='admission-signer-attempt-1',requestSha256=state['signingRequestSha256'],admissionHeadSha256=head,atMs=self.now))
            write_new(self.path.parent/'signer-ack.json',dict(format='admission-signer-ack-1',requestSha256=state['signingRequestSha256'],signedTransactionBase64=self.signed['signedTransactionBase64'],wireSha256=state['signedWireSha256']))
            self.package=receipt(self.e,b.private_accounting_handoff())
        finally:b.close()
        self.now=NOW+1100
    def book(self):return admission.Admission(self.path,clock=lambda:self.now)
    def submit(self,rpc):return m.submit(self.home,self.wallet,self.pool,allow_devnet_submit=True,opener=rpc,clock=lambda:self.now)
    def recover(self,rpc):return m.recover(self.home,self.wallet,self.pool,opener=rpc,clock=lambda:self.now)
    def status(self):
        b=self.book()
        try:return m.Submission(b).status()
        finally:b.close()


@contextmanager
def case():
    with tempfile.TemporaryDirectory() as d,patch('socket.socket',side_effect=AssertionError('network')),patch('core.signer',side_effect=AssertionError('private key')):
        yield Case(Path(d))


def refuses(fn):
    try:fn()
    except (ValueError,OSError):return
    raise AssertionError('expected refusal')


def run():
    cases={}
    with case() as c:
        r=c.recover(FakeOpener(c));assert r['state']=='not-attempted' and r['networkRequestsThisRun']==0
        cases['no-boundary-no-rpc-or-allocation']='passed'
        rpc=FakeOpener(c);r=c.submit(rpc)
        assert r['state']=='rpc-acknowledged' and r['sendRequestsThisRun']==1
        assert [q['method'] for q in rpc.requests]==['getGenesisHash','isBlockhashValid','getFeeForMessage','getGenesisHash','sendTransaction']
        cases['committed-boundary-before-one-exact-send']='passed'
        repeat=FakeOpener(c);r=c.submit(repeat);assert not repeat.requests and r['sendRequestsThisRun']==0
        cases['reentry-never-resubmits']='passed'
        c.now+=30000;(c.home/'STOP').touch(mode=0o600)
        rpc=FakeOpener(c);r=c.recover(rpc)
        assert r['state']=='entry-effects-observed' and r['genesisBoundReceiptCollected']
        assert len(rpc.requests)==4 and all(q['method']!='sendTransaction' for q in rpc.requests)
        cases['expired-stop-recovery-collects-exact-wire']='passed'
        r=c.recover(FakeOpener(c));assert r['networkRequestsThisRun']==0 and r['receiptCaptureCount']==1
        cases['terminal-recovery-replays-without-network']='passed'
        b=c.book()
        try:assert b.status()['reservation']['reservedFeeLamports']=='26000' and b.status()['reservation']['reservedPrincipalAtomic']=='100'
        finally:b.close()
        assert not r['reservationReleased'] and not r['allocationTransferred']
        cases['original-fees-and-principal-remain-held']='passed'
        text=json.dumps(r)
        assert c.signed['signedTransactionBase64'] not in text and 'rpcEvidence' not in text
        cases['public-output-excludes-wire-and-raw-rpc']='passed'
    with case() as c:
        r=c.submit(FakeOpener(c,lost=True));assert r['state']=='submission-unknown'
        assert c.submit(FakeOpener(c))['networkRequestsThisRun']==0
        assert c.recover(FakeOpener(c))['state']=='entry-effects-observed'
        cases['lost-send-response-recovers-without-resend']='passed'
    with case() as c:
        c.submit(FakeOpener(c))
        r=c.recover(FakeOpener(c,package=failed(c.package)))
        assert r['state']=='entry-failure-observed' and r['receiptEffects']['observedAcquiredAtomic']=='0'
        cases['failed-chain-transaction-retains-fee-only-evidence']='passed'
    with case() as c:
        c.submit(FakeOpener(c));p=deepcopy(c.package);p['bundle']['rpcEvidence']['transaction']['result']=None
        r=c.recover(FakeOpener(c,package=p));assert r['state']=='rpc-acknowledged' and not r['genesisBoundReceiptCollected']
        assert c.recover(FakeOpener(c))['state']=='entry-effects-observed'
        cases['missing-receipt-is-unknown-not-failure']='passed'
    for name,changes in [('wrong-genesis',dict(genesis=m.GENESIS['mainnet-beta'])),('expired-blockhash',dict(valid=False)),('fee-over-cap',dict(fee=6001))]:
        with case() as c:
            rpc=FakeOpener(c,**changes);refuses(lambda:c.submit(rpc))
            assert all(q['method']!='sendTransaction' for q in rpc.requests) and not c.status()['applicationSendBoundaryRecorded']
            cases[name+'-refuses-before-send']='passed'
    with case() as c:
        rpc=FakeOpener(c,send=c.wallet);r=c.submit(rpc)
        assert r['state']=='quarantined' and c.recover(FakeOpener(c))['networkRequestsThisRun']==0
        cases['wrong-response-signature-quarantines']='passed'
    with case() as c:
        def stop_after(method):
            if method=='getFeeForMessage':(c.home/'STOP').touch(mode=0o600)
        rpc=FakeOpener(c,callback=stop_after);refuses(lambda:c.submit(rpc))
        assert not c.status()['applicationSendBoundaryRecorded']
        cases['stop-during-preflight-blocks-send']='passed'
    with case() as c:
        c.submit(FakeOpener(c));r=c.recover(FakeOpener(c,genesis=m.GENESIS['mainnet-beta']))
        assert r['state']=='quarantined' and r['networkRequestsThisRun']==1
        assert c.recover(FakeOpener(c))['networkRequestsThisRun']==0
        cases['wrong-recovery-genesis-stays-quarantined']='passed'
    with case() as c:
        c.submit(FakeOpener(c));p=deepcopy(c.package);p['signedTransactionBase64']=c.signed['otherSignedTransactionBase64']
        assert c.recover(FakeOpener(c,package=p))['state']=='quarantined'
        cases['different-receipt-wire-quarantines']='passed'
    with case() as c:
        c.submit(FakeOpener(c))
        with patch.object(m.receipts.ReceiptGate,'observe',side_effect=RuntimeError('synthetic crash after capture commit')):
            try:c.recover(FakeOpener(c))
            except RuntimeError:pass
            else:raise AssertionError('missing injected crash')
        rpc=FakeOpener(c);r=c.recover(rpc)
        assert r['state']=='entry-effects-observed' and not rpc.requests
        cases['saved-capture-replays-after-application-interruption']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,temporaryLedgersRemoved=True,
        networkRequests=0,transactionsSent=0,signaturesCreated=0,privateKeyAccessed=False,
        productionLedgerUpdated=False,executionApproved=False,nextCycleAuthorized=False,
        runtimeIntegrated=False,reservationReleased=False,allocationTransferred=False)
