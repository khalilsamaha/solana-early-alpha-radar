"""Actual collectors and journals with public signed fixtures; no private keys."""
from contextlib import contextmanager
from pathlib import Path
import json
from unittest.mock import patch
import fresh_exit as m
import admission_submission_checks as entry
import admission_exit_capture_checks as capture
from locked_admission_checks import fixture
from entry_accounting_checks import collect,apply
from exit_submission_checks import FakeRpc
from core import write_new


@contextmanager
def case():
    public=json.loads(Path(__file__).with_name('exit-handoff-signed-fixture.json').read_text())
    with patch.object(entry,'fixture',side_effect=lambda:fixture(public['entry'])),entry.case() as c:
        collect(c);apply(c);first,e,baseline=capture.setup(c)
        c.timer=capture.Clock();c.mono=0;c.signs=0;c.rpc=None;c.exit_wire=public['exitSignedTransactionBase64']
        def clock():c.now=c.timer();return c.now
        c.clock=clock;c.collector=capture.Opener(first,e)
        def adapter(root,request):
            c.signs+=1;b=c.book()
            try:
                state=m.handoff.read(b,c.now)
                row=b.db.execute('SELECT hash,at_ms FROM admission_exit_signing WHERE seq=1').fetchone()
                write_new(c.path.parent/m.backend.ATTEMPT,dict(format='exit-signer-attempt-1',requestSha256=state['requestSha256'],signingHeadSha256=row['hash'],preparationSha256=request['preparationSha256'],atMs=c.now))
                wire=m.handoff.signed_check(c.exit_wire,request)
                write_new(c.path.parent/m.backend.ACK,dict(format='exit-signer-ack-1',requestSha256=state['requestSha256'],signedTransactionBase64=c.exit_wire,wireSha256=wire['wireSha256']))
            finally:b.close()
            return c.exit_wire
        c.adapter=adapter
        class Lazy:
            def __init__(self,**kw):self.kw=kw;self.rpc=None
            def open(self,request,timeout=None):
                if self.rpc is None:
                    b=c.book()
                    try:c.exit_state=m.submission.ExitSubmission(b).signing()
                    finally:b.close()
                    self.rpc=c.rpc=FakeRpc(c,**self.kw)
                return self.rpc.open(request,timeout)
        c.opener=Lazy
        c.run=lambda **kw:m._run(c.home,c.wallet,c.pool,signer_adapter=kw.get('adapter',adapter),
            collection_opener=c.collector,submission_opener=kw.get('rpc',Lazy()),clock=clock,monotonic=lambda:c.mono)
        c.recover=lambda:m.recover(c.home,c.wallet,c.pool,opener=Lazy(),clock=clock)
        c.status=lambda:m.submission.status(c.home,c.wallet,c.pool,clock=clock)
        with patch.object(m.collection.exit,'BASELINE',baseline),patch.object(m.view,'read_locked',return_value=c.e['costInputs']['reservations']),patch('socket.socket',side_effect=AssertionError('network')):
            yield c


def run():
    cases={}
    with case() as c:
        source={p.name:p.read_bytes() for p in c.home.iterdir()}
        r=c.run();assert r['state']=='rpc-acknowledged',r
        assert r['networkRequests']==25 and r['collectionRequests']==20 and r['senderRequests']==5
        assert r['sendRequestsThisRun']==c.signs==1 and r['originalDeadlineCheckedBeforeSend']
        assert r['completedWithinOriginalDeadline'] and r['signerAcknowledgmentValidated']
        cases['actual-fresh-collector-to-committed-signing-and-one-send']='passed'
        assert r['preparation']['binding']['quantityAtomic']=='98' and r['preparation']['binding']['protectedInventoryAtomic']=='902'
        cases['acquired-delta-and-protected-inventory-preserved']='passed'
        assert r['transactionsSent'] is None and not r['receiptEffectsReconciled'] and not r['reservationReleased']
        cases['acknowledgment-does-not-release-funds-or-prove-effects']='passed'
        before=c.path.read_bytes();again=c.run();assert again['networkRequests']==0 and c.signs==1 and before==c.path.read_bytes()
        cases['occupied-slot-refused-before-collection-and-signing']='passed'
        c.timer.at+=30000;(c.home/'STOP').touch(mode=0o600);(c.path.parent/m.backend.ACK).unlink()
        recovered=c.recover();assert recovered['state']=='exit-finalized-evidence' and recovered['networkRequestsThisRun']==4
        assert recovered['sendRequestsThisRun']==0 and not recovered['resumesExit']
        cases['expired-stopped-recovery-without-backend-ack-or-key']='passed'
        before=c.path.read_bytes();assert c.recover()['networkRequestsThisRun']==0 and before==c.path.read_bytes()
        cases['terminal-recovery-idempotent']='passed'
        source['STOP']=b'';assert source=={p.name:p.read_bytes() for p in c.home.iterdir()}
        cases['historical-source-unchanged']='passed'
        assert c.exit_wire not in json.dumps(r) and 'unsignedTransactionBase64' not in json.dumps(r)
        cases['public-summary-excludes-wire']='passed'
    with patch.object(m,'_run',side_effect=AssertionError('access')):
        for a,b in ((False,True),(True,False),(1,True),(True,1)):
            entry.refuses(lambda:m.prepare_sign_submit('/missing','wallet','pool',allow_private_key_signing=a,allow_devnet_submit=b))
    cases['both-exact-opt-ins-before-access']='passed'
    for kind in ('expiry','monotonic','stop','clock-regression'):
        with case() as c:
            def change(method):
                if method!='getFeeForMessage':return
                if kind=='expiry':c.timer.at+=10000
                elif kind=='monotonic':c.mono=30
                elif kind=='clock-regression':c.timer.at-=1000
                else:(c.home/'STOP').touch(mode=0o600)
            r=c.run(rpc=c.opener(callback=change));assert r['state']=='fresh-exit-inspection-required',r
            assert r['senderRequests']==3 and r['sendRequestsThisRun']==0
        cases[kind+'-preflight-blocks-next-request']='passed'
    with case() as c:
        mark=m.submission.ExitSubmission.mark
        def expired(*args):result=mark(*args);c.mono=30;return result
        with patch.object(m.submission.ExitSubmission,'mark',expired):r=c.run()
        assert r['sendRequestsThisRun']==0 and c.status()['state']=='exit-submission-unknown'
        assert c.run()['networkRequests']==0
    cases['post-boundary-expiry-preserves-unknown-without-send']='passed'
    with case() as c:
        r=c.run(rpc=c.opener(lost=True));assert r['state']=='exit-submission-unknown' and r['sendRequestsThisRun']==1
        c.timer.at+=30000;assert c.recover()['state']=='exit-finalized-evidence' and c.signs==1
    cases['lost-send-recovered-without-resigning-or-resend']='passed'
    with case() as c:
        def lost(root,request):c.adapter(root,request);raise TimeoutError('PRIVATE')
        r=c.run(adapter=lost);assert r['signaturesCreated'] is None and r['senderRequests']==0
        assert 'PRIVATE' not in json.dumps(r)
        m.backend.recover(c.home,c.wallet,c.pool,clock=c.clock)
        assert c.run()['networkRequests']==0 and c.status()['state']=='not-attempted'
    cases['lost-signer-response-never-resumes-send']='passed'
    with case() as c:
        def late(root,request):wire=c.adapter(root,request);c.timer.at+=10000;return wire
        r=c.run(adapter=late);assert r['senderRequests']==0 and not r['completedWithinOriginalDeadline']
        assert c.status()['state']=='not-attempted'
    cases['late-signature-retained-without-send']='passed'
    with case() as c:
        def late(method):
            if method=='sendTransaction':c.timer.at+=10000
        r=c.run(rpc=c.opener(callback=late));assert r['state']=='rpc-acknowledged' and not r['completedWithinOriginalDeadline']
    cases['late-transport-acknowledgment-retained-as-historical']='passed'
    for kind,kw in [('cluster',dict(genesis='wrong')),('blockhash',dict(valid=False)),('fee',dict(fee=99999))]:
        with case() as c:
            r=c.run(rpc=c.opener(**kw));assert r['sendRequestsThisRun']==0 and not c.status()['applicationSendBoundaryRecorded']
        cases[kind+'-preflight-refusal']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',casesPassed=len(cases),cases=cases,
        mode='synthetic-offline',realNetworkRequests=0,transactionsSent=0,signaturesCreated=0,
        privateKeyAccessed=False,runtimeIntegrated=False,executionApproved=False,
        signedResponseBasis='Public signed fixtures; actual bounded collectors over synthetic HTTP')
