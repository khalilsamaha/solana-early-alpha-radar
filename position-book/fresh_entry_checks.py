"""Portable fresh-entry lifecycle checks using public signatures, never keys."""
from contextlib import contextmanager
from types import SimpleNamespace
import json
from unittest.mock import patch

import fresh_entry as m
import fresh_signing_checks as fixtures
from admission_submission_checks import FakeOpener
from admission_receipt_checks import receipt
from core import write_new
from wire import verify_wire


@contextmanager
def case(**kwargs):
    with fixtures.case(**kwargs) as c:
        original=c.adapter
        def adapter(root,request):
            wire=original(root,request)
            b=m.signing.handoff.Admission(c.path,clock=lambda:c.now)
            try:
                s,_,_,_=b.read();head=b.db.execute('SELECT hash FROM admission_events WHERE seq=3').fetchone()[0]
                write_new(c.path.parent/'signer-attempt.json',dict(format='admission-signer-attempt-1',
                    requestSha256=s['signingRequestSha256'],admissionHeadSha256=head,atMs=c.now))
                write_new(c.path.parent/'signer-ack.json',dict(format='admission-signer-ack-1',
                    requestSha256=s['signingRequestSha256'],signedTransactionBase64=wire,
                    wireSha256=verify_wire(wire)['wireSha256']))
            finally:b.close()
            return wire
        c.adapter=adapter;c.rpc=None
        # Build the response fixture lazily, after the actual signing handoff.
        class Lazy:
            def __init__(self,**kw):self.kw=kw;self.rpc=None
            def open(self,request,timeout=None):
                if self.rpc is None:
                    b=m.submission._open(c.home,c.wallet,c.pool,lambda:c.now)
                    try:package=receipt(c.e,b.private_accounting_handoff())
                    finally:b.close()
                    fixture=SimpleNamespace(e=c.e,package=package,path=c.path,
                        signed={'signedTransactionBase64':c.signed})
                    self.rpc=c.rpc=FakeOpener(fixture,**self.kw)
                return self.rpc.open(request,timeout)
        c.opener=Lazy
        def run(*,adapter=None,rpc=None):
            return m._run(c.home,c.wallet,c.pool,signer_adapter=adapter or c.adapter,
                maximum_exit_attempts=2,maximum_exit_fee_lamports='10000',maximum_total_fee_lamports='30000',
                submission_opener=rpc or Lazy(),clock=lambda:c.now,monotonic=lambda:c.mono)
        c.run=run
        c.recover=lambda **kw:m.recover(c.home,c.wallet,c.pool,opener=kw.get('rpc',Lazy()),clock=lambda:c.now)
        def state():
            b=m.submission._open(c.home,c.wallet,c.pool,lambda:c.now)
            try:return m.submission.Submission(b).status()
            finally:b.close()
        c.transport=state
        yield c


def run():
    cases={}
    with case() as c:
        source={p.name:p.read_bytes() for p in c.home.iterdir()}
        r=c.run();assert r['state']=='rpc-acknowledged',r
        assert r['networkRequests']==25 and r['collectionRequests']==20 and r['senderRequests']==5
        assert r['sendRequestsThisRun']==1 and c.calls==c.collections==1 and r['originalDeadlineCheckedBeforeSend']
        assert r['applicationSendBoundaryRecorded'] and r['completedWithinOriginalDeadline']
        cases['fresh-collection-signing-and-exact-wire-one-send']='passed'
        assert r['transactionsSent'] is None and not r['receiptObserved'] and r['recoveryRequired']
        cases['acknowledgment-is-not-finality-or-delivery-proof']='passed'
        before=c.files();again=c.run();assert again['networkRequests']==again['sendRequestsThisRun']==0 and c.calls==c.collections==1 and before==c.files()
        cases['repeat-refused-before-collection-signing-and-send']='passed'
        c.now=c.deadline+1000;(c.home/'STOP').touch(mode=0o600)
        (c.path.parent/'signer-ack.json').unlink()
        recovered=c.recover();assert recovered['state']=='entry-effects-observed' and recovered['networkRequestsThisRun']==4
        assert recovered['sendRequestsThisRun']==0 and not recovered['resumesEntry'] and not recovered['reservationReleased']
        cases['expired-stopped-keyless-recovery-without-signer-ack']='passed'
        before=c.files();assert c.recover()['networkRequestsThisRun']==0 and c.files()==before
        cases['terminal-recovery-idempotent-without-rpc']='passed'
        source['STOP']=b'';assert source=={p.name:p.read_bytes() for p in c.home.iterdir()}
        cases['historical-source-files-unchanged']='passed'
        text=json.dumps([r,recovered]);assert c.signed not in text and 'simulation_item' not in text
        cases['public-report-excludes-wire-and-raw-evidence']='passed'
    with patch.object(m,'_run',side_effect=AssertionError('collection')):
        for signing,submit in ((False,True),(True,False),(1,True),(True,1)):
            try:m.prepare_sign_submit('/missing','wallet','pool',allow_private_key_signing=signing,allow_devnet_submit=submit)
            except ValueError:pass
            else:raise AssertionError('explicit opt-ins required')
    cases['both-opt-ins-required-before-source-access']='passed'
    for kind in ('expiry','monotonic','stop','clock-regression'):
        with case() as c:
            def change(method):
                if method!='getFeeForMessage':return
                if kind=='expiry':c.now=c.deadline
                elif kind=='monotonic':c.mono=30
                elif kind=='clock-regression':c.now-=1
                else:(c.home/'STOP').touch(mode=0o600)
            r=c.run(rpc=c.opener(callback=change))
            assert r['state']=='fresh-entry-inspection-required' and r['sendRequestsThisRun']==0,r
            assert len(c.rpc.requests)==3
            if kind!='clock-regression':assert not c.transport()['applicationSendBoundaryRecorded']
        cases[kind+'-during-preflight-prevents-next-request-and-boundary']='passed'
    with case() as c:
        original=m.submission.Submission.mark
        def expire(book,proof):
            result=original(book,proof);c.mono=30;return result
        with patch.object(m.submission.Submission,'mark',expire):r=c.run()
        assert r['state']=='fresh-entry-inspection-required' and r['sendRequestsThisRun']==0
        assert c.transport()['state']=='submission-unknown'
        again=c.run();assert again['networkRequests']==0
    cases['expiry-after-durable-send-boundary-keeps-unknown-no-send']='passed'
    with case() as c:
        r=c.run(rpc=c.opener(lost=True));assert r['state']=='submission-unknown' and r['sendRequestsThisRun']==1
        assert r['transactionsSent'] is None
        c.now=c.deadline+1000;assert c.recover()['state']=='entry-effects-observed'
        assert c.calls==c.collections==1
    cases['lost-send-response-recovered-without-recollect-resign-resend']='passed'
    with case() as c:
        def lost(root,request):c.adapter(root,request);raise TimeoutError('PRIVATE-ERROR')
        r=c.run(adapter=lost);assert r['sendRequestsThisRun']==0 and r['signaturesCreated'] is None and c.rpc is None
        m.signing.recover(c.home,c.wallet,c.pool,clock=lambda:c.now)
        assert c.run()['networkRequests']==0 and c.transport()['state']=='not-attempted'
    cases['lost-signer-response-never-automatically-resumes-submission']='passed'
    with case() as c:
        def late(root,request):
            wire=c.adapter(root,request);c.now=c.deadline+1;return wire
        r=c.run(adapter=late);assert r['sendRequestsThisRun']==0 and r['recoveryRequired'] and c.rpc is None
        assert c.transport()['state']=='not-attempted'
    cases['late-signature-retained-without-sender']='passed'
    with case() as c:
        def late(method):
            if method=='sendTransaction':c.now=c.deadline+1
        r=c.run(rpc=c.opener(callback=late));assert r['state']=='rpc-acknowledged' and not r['completedWithinOriginalDeadline']
        assert r['sendRequestsThisRun']==1 and r['recoveryRequired']
    cases['late-send-ack-retained-without-freshness-claim']='passed'
    for kind,kw in [('cluster',dict(genesis=m.submission.GENESIS['mainnet-beta'])),('blockhash',dict(valid=False)),('fee',dict(fee=99999))]:
        with case() as c:
            r=c.run(rpc=c.opener(**kw));assert r['state']=='fresh-entry-inspection-required' and r['sendRequestsThisRun']==0
            assert not c.transport()['applicationSendBoundaryRecorded']
        cases[kind+'-preflight-refuses-send']='passed'
    with case() as c:
        r=c.run(rpc=c.opener(send='wrong-signature'));assert r['state']=='quarantined' and r['sendRequestsThisRun']==1
        assert c.recover()['state']=='quarantined'
    cases['wrong-send-ack-quarantined']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',casesPassed=len(cases),cases=cases,
        mode='synthetic-offline',realNetworkRequests=0,transactionsSent=0,signaturesCreated=0,
        privateKeyAccessed=False,sourceStateChanged=False,runtimeIntegrated=False,executionApproved=False,
        signedResponseBasis='Existing public signed fixture; no key access in portable checks')
