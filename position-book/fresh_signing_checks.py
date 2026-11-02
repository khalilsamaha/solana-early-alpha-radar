"""Synthetic collection/admission/backend boundary checks; no actual key access."""
from contextlib import contextmanager
from copy import deepcopy
import json
from unittest.mock import patch

import fresh_signing as m
import durable_admission_checks as fixtures
from locked_admission_checks import fixture


@contextmanager
def case(**kwargs):
    e,p,signed=fixture()
    with patch.object(fixtures,'fixture',lambda:(deepcopy(e),deepcopy(p))),fixtures.case(**kwargs) as c:
        c.calls=0
        def adapter(root,request):
            c.calls+=1
            b=m.handoff.Admission(m.handoff.storage(root),clock=lambda:c.now)
            try:
                assert b.status()['state']=='signing-unknown' and b.status()['eventCount']==3
                assert b.read()[0]['signingRequest']==request
            finally:b.close()
            # The dispatcher still owns the source lock at the backend boundary.
            try:
                with m.view.cycles.c.source_lock(c.home,c.wallet):pass
            except BlockingIOError:pass
            else:raise AssertionError('source lock absent')
            return signed['signedTransactionBase64']
        c.adapter=adapter
        c.run=lambda **kw:m._run(c.home,c.wallet,c.pool,signer_adapter=kw.get('adapter',c.adapter),
            maximum_exit_attempts=2,maximum_exit_fee_lamports='10000',maximum_total_fee_lamports='30000',
            clock=lambda:c.now,monotonic=lambda:c.mono)
        c.path=c.home.parent/(c.home.name+'-entry-handoff-v1')/m.handoff.NAME
        c.signed=signed['signedTransactionBase64']
        yield c


def state(c):
    b=m.handoff.Admission(c.path,clock=lambda:c.now)
    try:return b.status()
    finally:b.close()


def run():
    cases={}
    with case() as c:
        source={p.name:p.read_bytes() for p in c.home.iterdir()};r=c.run()
        assert r['state']=='signed-recorded' and r['signerAcknowledgmentValidated'],r
        assert c.calls==c.collections==1 and c.reads==2
        assert r['originalDeadlineCheckedAtInvocation'] and r['completedWithinOriginalDeadline']
        cases['fresh-raw-collection-to-one-durable-signer-boundary']='passed'
        assert r['handoff']['accountingHandoffReady'] and r['handoff']['admission']['eventCount']==5
        cases['signed-acknowledgment-and-accounting-outbox-retained']='passed'
        assert source=={p.name:p.read_bytes() for p in c.home.iterdir()}
        cases['source-journals-unchanged']='passed'
        text=json.dumps(r);assert 'unsignedTransactionBase64' not in text and 'signedWireBase64' not in text and 'simulation_item' not in text
        cases['public-report-omits-private-evidence']='passed'
        before=c.files();again=c.run();assert again['diagnosticCode']=='timing-existing-admission' and c.calls==c.collections==1 and before==c.files()
        cases['repeat-stops-before-collection-and-backend']='passed'
    with patch.object(m,'_run',side_effect=AssertionError('source')):
        try:m.prepare_and_sign('/missing','wallet','pool')
        except ValueError as exc:assert str(exc)=='explicit-private-key-opt-in-required'
        else:raise AssertionError('missing opt-in')
    cases['real-backend-requires-explicit-internal-opt-in']='passed'
    with case(collect_hook=lambda c,r:r['preflight'].update(validUntilExclusiveMs=c.deadline-1)) as c:
        r=c.run();assert r['diagnosticCode']=='fresh-signing-deadline-mismatch' and not c.path.exists() and c.calls==0
    cases['narrower-original-deadline-never-widened']='passed'
    with case(collect_hook=lambda c,r:setattr(c,'now',c.deadline)) as c:
        r=c.run();assert r['diagnosticCode']=='fresh-signing-expired' and not c.path.exists() and c.calls==0
    cases['collection-expiry-before-durable-slot']='passed'
    for mode in ('source','stop','monotonic'):
        def hook(c,n,r):
            if n!=2:return
            if mode=='source':r['ledgerHeadSha256']='d'*64
            if mode=='stop':(c.home/'STOP').touch(mode=0o600)
            if mode=='monotonic':c.mono=31
        with case(read_hook=hook) as c:
            r=c.run();assert r['state']=='fresh-signing-inspection-required' and c.calls==0,r
        cases[mode+'-change-before-backend-blocks-signing']='passed'
    with case() as c:
        original=m.handoff.Admission.mark_signing_boundary
        def expire(b,e):
            r=original(b,e);c.now=c.deadline;return r
        with patch.object(m.handoff.Admission,'mark_signing_boundary',expire):r=c.run()
        assert r['state']=='fresh-signing-inspection-required' and c.calls==0 and state(c)['state']=='signing-unknown'
    cases['expired-committed-boundary-never-invokes-backend']='passed'
    with case() as c:
        def late(root,request):
            wire=c.adapter(root,request);c.now=c.deadline+1;return wire
        r=c.run(adapter=late);assert r['state']=='signed-recorded' and not r['completedWithinOriginalDeadline'] and state(c)['state']=='signed-recorded',r
    cases['late-valid-signature-retained-without-freshness-claim']='passed'
    with case() as c:
        def lost(root,request):c.calls+=1;raise TimeoutError('private transport detail')
        r=c.run(adapter=lost);assert r['state']=='fresh-signing-inspection-required' and r['signaturesCreated'] is None and r['privateKeyAccessed'] is None
        assert state(c)['state']=='signing-unknown' and 'private transport detail' not in json.dumps(r)
        before=c.files();c.run();assert before==c.files() and c.calls==c.collections==1
    cases['unknown-signer-outcome-held-without-retry']='passed'
    with case() as c:
        r=c.run(adapter=lambda root,req:'invalid')
        assert state(c)['state']=='quarantined' and not r['signerAcknowledgmentValidated'] and r['recoveryRequired']
    cases['wrong-acknowledgment-quarantined']='passed'
    with case() as c:
        def stop(root,request):
            wire=c.adapter(root,request);(c.home/'STOP').touch(mode=0o600);return wire
        r=c.run(adapter=stop);assert r['state']=='stopped' and r['handoff']['accountingHandoffReady'] and c.calls==1
    cases['stop-during-signing-keeps-signed-history']='passed'
    with case(collect_hook=lambda c,r:(c.home.parent/(c.home.name+'-entry-handoff-v1')).mkdir(mode=0o700)) as c:
        r=c.run();assert r['diagnosticCode']=='timing-existing-admission' and c.calls==0 and list(c.path.parent.iterdir())==[]
    cases['competitor-slot-after-collection-preserved']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',casesPassed=len(cases),cases=cases,
        mode='synthetic-offline',signaturesCreated=0,privateKeyAccessed=False,realNetworkRequests=0,
        transactionsSent=0,sourceStateChanged=False,runtimeIntegrated=False,executionApproved=False,
        signedResponseBasis='Existing public signed fixture; no key access in portable checks')
