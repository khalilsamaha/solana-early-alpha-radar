"""Synthetic bounded transport over public pre-signed exit fixtures; no sockets."""
import base64
from contextlib import contextmanager
from copy import deepcopy
import io
import json
import sqlite3
from unittest.mock import patch

import exit_submission as m
from exit_signing_handoff_checks import ready,dispatch
from admission_submission_checks import refuses
from core import write_new


@contextmanager
def signed_case():
    with ready() as c:
        dispatch(c);b=c.book()
        try:
            state=m.ExitSubmission(b).signing()
            row=b.db.execute('SELECT hash,at_ms FROM admission_exit_signing WHERE seq=1').fetchone()
            write_new(c.path.parent/m.backend.ATTEMPT,dict(format='exit-signer-attempt-1',requestSha256=state['requestSha256'],signingHeadSha256=row['hash'],preparationSha256=state['request']['preparationSha256'],atMs=row['at_ms']))
            write_new(c.path.parent/m.backend.ACK,dict(format='exit-signer-ack-1',requestSha256=state['requestSha256'],signedTransactionBase64=c.exit_wire,wireSha256=state['signed']['wireSha256']))
            c.exit_state=state
        finally:b.close()
        yield c


class FakeRpc:
    def __init__(self,c,*,genesis=None,valid=True,fee=5000,lost=False,reply=None,missing=False,failed=False,wrong_wire=False,callback=None,confirmed=False):
        self.c=c;self.genesis=genesis or m.transport.GENESIS['devnet'];self.valid=valid;self.fee=fee
        self.lost=lost;self.reply=reply;self.missing=missing;self.failed=failed;self.wrong_wire=wrong_wire;self.callback=callback;self.confirmed=confirmed;self.requests=[]
    def open(self,request,timeout=None):
        q=json.loads(request.data);self.requests.append(q);method=q['method'];params=q['params'];c=self.c
        assert request.full_url==m.transport.ENDPOINT and request.method=='POST'
        if self.callback:self.callback(method)
        floor=c.exit_state['minimumContextSlot'];sig=c.exit_state['signed']['signature'];error={'InstructionError':[2,'Custom']} if self.failed else None
        if method=='getGenesisHash':value=self.genesis
        elif method=='isBlockhashValid':
            assert params==[c.exit_state['request']['packet']['policy']['blockhash'],{'commitment':'confirmed','minContextSlot':floor}]
            value=dict(context=dict(slot=floor),value=self.valid)
        elif method=='getFeeForMessage':
            assert params==[base64.b64encode(m.decode_wire(c.exit_wire)[1]).decode(),dict(commitment='confirmed',minContextSlot=floor)]
            value=dict(context=dict(slot=floor),value=self.fee)
        elif method=='sendTransaction':
            assert params==[c.exit_wire,dict(encoding='base64',skipPreflight=False,preflightCommitment='confirmed',maxRetries=0,minContextSlot=floor)]
            db=sqlite3.connect(c.path.as_uri()+'?mode=ro',uri=True)
            try:assert db.execute('SELECT COUNT(*) FROM admission_exit_submission').fetchone()[0]==1
            finally:db.close()
            if self.lost:raise TimeoutError('synthetic lost reply')
            value=sig if self.reply is None else self.reply
        elif method=='getSignatureStatuses':
            assert params==[[sig],{'searchTransactionHistory':True}]
            value=dict(context=dict(slot=floor+1),value=[dict(slot=floor+1,err=error,confirmations=1 if self.confirmed else None,confirmationStatus='confirmed' if self.confirmed else 'finalized')])
        elif method=='getTransaction':
            assert params==[sig,dict(encoding='base64',commitment='finalized',maxSupportedTransactionVersion=0)]
            value=None if self.missing else dict(slot=floor+1,transaction=[c.signed['signedTransactionBase64'] if self.wrong_wire else c.exit_wire,'base64'],meta=dict(err=error),version='legacy')
        else:raise AssertionError(method)
        return io.BytesIO(json.dumps(dict(jsonrpc='2.0',id=q['id'],result=value)).encode())


def submit(c,rpc=None):return m.submit(c.home,c.wallet,c.pool,allow_devnet_submit=True,opener=rpc or FakeRpc(c),clock=lambda:c.now)
def recover(c,rpc=None):return m.recover(c.home,c.wallet,c.pool,opener=rpc or FakeRpc(c),clock=lambda:c.now)
def status(c):return m.status(c.home,c.wallet,c.pool,clock=lambda:c.now)


def run():
    cases={}
    with signed_case() as c:
        before=c.path.read_bytes();rpc=FakeRpc(c);r=recover(c,rpc)
        assert r['state']=='not-attempted' and not rpc.requests and c.path.read_bytes()==before
        cases['no-send-boundary-no-recovery-rpc']='passed'
        b=c.book()
        try:accounting=b.db.execute('SELECT value FROM admission_entry_accounting').fetchone()[0]
        finally:b.close()
        rpc=FakeRpc(c);r=submit(c,rpc)
        assert r['state']=='rpc-acknowledged' and r['sendRequestsThisRun']==1 and len(rpc.requests)==5
        cases['committed-boundary-before-one-exact-exit-send']='passed'
        before=c.path.read_bytes();rpc=FakeRpc(c);r=submit(c,rpc)
        assert not rpc.requests and c.path.read_bytes()==before
        cases['repeat-submit-never-resends']='passed'
        c.now+=30000;(c.home/'STOP').touch(mode=0o600)
        rpc=FakeRpc(c);r=recover(c,rpc)
        assert r['state']=='exit-finalized-evidence' and len(rpc.requests)==4 and not r['receiptEffectsReconciled']
        cases['stop-expiry-recovery-observes-original-signature']='passed'
        before=c.path.read_bytes();rpc=FakeRpc(c);r=recover(c,rpc)
        assert not rpc.requests and c.path.read_bytes()==before
        cases['terminal-evidence-replays-without-network']='passed'
        b=c.book()
        try:assert b.db.execute('SELECT value FROM admission_entry_accounting').fetchone()[0]==accounting
        finally:b.close()
        assert all(r[k] is False for k in ('reservationReleased','allocationTransferred','residualInventoryVerified','receiptEffectsReconciled','executionApproved','nextCycleAuthorized'))
        cases['accounting-and-fee-commitments-held-pending-reconciliation']='passed'
        assert c.exit_wire not in json.dumps(r) and 'rpcEvidence' not in json.dumps(r)
        cases['public-report-excludes-signed-wire-and-raw-evidence']='passed'
    for name,opts in [('lost-response',dict(lost=True)),('failed-exit',dict(failed=True)),('missing-receipt',dict(missing=True)),('confirmed-only',dict(confirmed=True))]:
        with signed_case() as c:
            r=submit(c,FakeRpc(c,lost=opts.get('lost',False)))
            if name=='lost-response':assert r['state']=='exit-submission-unknown'
            r=recover(c,FakeRpc(c,**opts))
            if name=='failed-exit':assert r['state']=='exit-failed-evidence' and not r['reservationReleased']
            elif name in ('missing-receipt','confirmed-only'):assert not r['finalizedEvidenceObserved']
            else:assert r['state']=='exit-finalized-evidence'
            assert submit(c,FakeRpc(c))['sendRequestsThisRun']==0
            cases[name+'-no-resend-or-release']='passed'
    for name,opts in [('wrong-genesis',dict(genesis='mainnet')),('invalid-blockhash',dict(valid=False)),('fee-cap',dict(fee=10001))]:
        with signed_case() as c:
            rpc=FakeRpc(c,**opts);refuses(lambda:submit(c,rpc))
            assert not status(c)['applicationSendBoundaryRecorded'] and not any(q['method']=='sendTransaction' for q in rpc.requests)
            cases[name+'-refuses-before-boundary']='passed'
    for name in ('stop','expiry','missing-backend-ack'):
        with signed_case() as c:
            if name=='stop':(c.home/'STOP').touch(mode=0o600)
            if name=='expiry':c.now+=30000
            if name=='missing-backend-ack':(c.path.parent/m.backend.ACK).unlink()
            rpc=FakeRpc(c);refuses(lambda:submit(c,rpc));assert not rpc.requests
            cases[name+'-refuses-before-rpc']='passed'
    for name in ('stop','expiry'):
        with signed_case() as c:
            def callback(method):
                if method=='getFeeForMessage':
                    if name=='stop':(c.home/'STOP').touch(mode=0o600)
                    else:c.now+=30000
            rpc=FakeRpc(c,callback=callback);refuses(lambda:submit(c,rpc))
            assert not status(c)['applicationSendBoundaryRecorded']
            cases[name+'-during-preflight-refuses-before-boundary']='passed'
    for name in ('wrong-send-signature','wrong-recovery-genesis','wrong-receipt-wire'):
        with signed_case() as c:
            r=submit(c,FakeRpc(c,reply=c.wallet if name=='wrong-send-signature' else None))
            if name!='wrong-send-signature':r=recover(c,FakeRpc(c,genesis='mainnet' if name=='wrong-recovery-genesis' else None,wrong_wire=name=='wrong-receipt-wire'))
            assert r['state']=='quarantined'
            rpc=FakeRpc(c);assert recover(c,rpc)['state']=='quarantined' and not rpc.requests
            cases[name+'-quarantines-without-retry']='passed'
    with signed_case() as c:
        original=m.ExitSubmission.mark
        def after(*args):
            value=original(*args);(c.home/'STOP').touch(mode=0o600);return value
        with patch.object(m.ExitSubmission,'mark',after):refuses(lambda:submit(c))
        assert status(c)['state']=='exit-submission-unknown'
        assert submit(c)['sendRequestsThisRun']==0
        cases['stop-after-commit-retains-uncertain-attempt']='passed'
    with signed_case() as c:
        rpc=FakeRpc(c)
        with patch.object(m.ExitSubmission,'acknowledge',side_effect=OSError('synthetic ack write')):refuses(lambda:submit(c,rpc))
        assert sum(q['method']=='sendTransaction' for q in rpc.requests)==1 and status(c)['state']=='exit-submission-unknown'
        assert recover(c)['state']=='exit-finalized-evidence'
        cases['ack-write-failure-recovers-without-resend']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',casesPassed=len(cases),cases=cases,
        networkRequests=0,transactionsSent=0,signaturesCreated=0,privateKeyAccessed=False,temporaryLedgersRemoved=True,
        productionLedgerUpdated=False,receiptEffectsReconciled=False,residualInventoryVerified=False,
        reservationReleased=False,allocationTransferred=False,executionApproved=False,runtimeIntegrated=False)
