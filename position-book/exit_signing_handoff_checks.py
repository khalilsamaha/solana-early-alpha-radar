"""Offline signing handoff: public pre-signed fixtures, no keys or live transport."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

import exit_signing_handoff as m
import admission_submission_checks as submission
from locked_admission_checks import fixture
from entry_accounting_checks import collect,apply
import admission_exit_collection_checks as collection


@contextmanager
def ready(*,legacy=False):
    public=json.loads(Path(__file__).with_name('exit-handoff-signed-fixture.json').read_text())
    with patch.object(submission,'fixture',side_effect=lambda:fixture(public['entry'])):
        with submission.case() as c:
            collect(c);apply(c);e,p,b=collection.collected(c)
            if legacy:collection.fixture.prepare(c,e,b)
            else:collection.prepare(c,e,p,b)
            c.exit_wire=public['exitSignedTransactionBase64'];c.baseline=b
            c.exit_record=collection.status(c,b)
            with patch.object(m.preparation,'BASELINE',b),patch.object(m.view,'read_locked',return_value=c.e['costInputs']['reservations']):
                yield c


def dispatch(c,adapter=None):
    return m.dispatch(c.home,c.wallet,c.pool,signer_adapter=adapter or (lambda _:c.exit_wire),clock=lambda:c.now)


def status(c):return m.status(c.home,c.wallet,c.pool,clock=lambda:c.now)
def recover(c,wire=None):return m.recover(c.home,c.wallet,c.pool,signed_response=wire,clock=lambda:c.now)


def run():
    cases={}
    with ready() as c:
        source={p.name:p.read_bytes() for p in c.home.iterdir()};before=apply(c);calls=[]
        def adapter(request):
            # A separate connection sees the committed request before adapter use.
            db=sqlite3.connect(c.path.as_uri()+'?mode=ro',uri=True)
            try:
                row=json.loads(db.execute('SELECT value FROM admission_exit_signing WHERE seq=1').fetchone()[0])
                assert row['request']==request and row['requestSha256']==m.digest(request)
            finally:db.close()
            calls.append(request);return c.exit_wire
        r=dispatch(c,adapter);assert r['state']=='exit-signed-recorded' and r['signerAdapterCallsThisRun']==1
        cases['committed-exact-request-before-single-adapter-call']='passed'
        assert calls[0]['quantityAtomic']=='98' and calls[0]['feeCapLamports']=='10000'
        assert apply(c)==before and source=={p.name:p.read_bytes() for p in c.home.iterdir()}
        cases['entry-accounting-source-inventory-and-fee-holds-unchanged']='passed'
        old=c.path.read_bytes();r2=dispatch(c,lambda _:(_ for _ in ()).throw(AssertionError('second signing')))
        assert r2['signerAdapterCallsThisRun']==0 and r2['acknowledgmentRecorded'] and c.path.read_bytes()==old
        assert recover(c,c.exit_wire)['state']=='exit-signed-recorded' and c.path.read_bytes()==old
        assert status(c)['headSha256']==r['headSha256'] and c.path.read_bytes()==old
        cases['reopen-dispatch-and-duplicate-recovery-never-resign']='passed'
        assert c.exit_wire not in json.dumps(r) and 'packet' not in json.dumps(r)
        assert all(r[k] is False for k in ('executionApproved','validForSubmission','liveKeyBackendConnected','liveSenderIntegrated','reservationReleased','allocationTransferred'))
        cases['public-summary-withholds-wire-and-execution-capability']='passed'
        c.now+=30000;assert status(c)['evidenceExpired'] and dispatch(c)['signerAdapterCallsThisRun']==0
        assert c.path.read_bytes()==old
        cases['expired-signed-record-remains-inspectable-without-refresh']='passed'
        (c.home/'STOP').touch(mode=0o600)
        assert recover(c,c.exit_wire)['state']=='exit-signing-stopped' and c.path.read_bytes()==old
        cases['stop-preserves-existing-acknowledgment-and-holds']='passed'
    with ready() as c:
        calls=[]
        def lost(request):calls.append(request);raise TimeoutError('synthetic lost response')
        try:dispatch(c,lost)
        except TimeoutError:pass
        else:raise AssertionError('lost response accepted')
        assert len(calls)==1 and status(c)['state']=='exit-signing-unknown'
        assert dispatch(c,lost)['signerAdapterCallsThisRun']==0 and len(calls)==1
        cases['lost-reply-preserves-unknown-boundary-with-no-retry']='passed'
        c.now+=30000;(c.home/'STOP').touch(mode=0o600)
        r=recover(c,c.exit_wire);assert r['acknowledgmentRecorded'] and r['evidenceExpired'] and r['stopRequested']
        assert r['signerAdapterCallsThisRun']==0 and not r['reservationReleased']
        cases['late-response-recovered-after-stop-and-expiry-without-signing']='passed'
    with ready() as c:
        old=c.path.read_bytes();submission.refuses(lambda:recover(c,c.exit_wire));assert c.path.read_bytes()==old
        cases['acknowledgment-without-boundary-refused']='passed'
    for name,mutate in {
        'expiry':lambda c:setattr(c,'now',c.now+30000),
        'stop-marker':lambda c:(c.home/'STOP').touch(mode=0o600),
        'durable-stop':lambda c:stop_book(c),
    }.items():
        with ready() as c:
            mutate(c);old=c.path.read_bytes();called=[]
            submission.refuses(lambda:dispatch(c,lambda _:called.append(True)))
            assert not called and c.path.read_bytes()==old
            cases[name+'-blocks-boundary-and-adapter']='passed'
    with ready(legacy=True) as c:
        old=c.path.read_bytes();submission.refuses(lambda:dispatch(c));assert c.path.read_bytes()==old
        cases['legacy-raw-preparation-cannot-sign']='passed'
    for name,response in (('entry-wire',lambda c:c.signed['signedTransactionBase64']),('malformed-wire',lambda c:'invalid'),('oversized-wire',lambda c:'a'*1645)):
        with ready() as c:
            r=dispatch(c,lambda _:response(c));assert r['state']=='exit-signing-quarantined'
            old=c.path.read_bytes();assert recover(c,c.exit_wire)['state']=='exit-signing-quarantined'
            assert dispatch(c)['signerAdapterCallsThisRun']==0 and c.path.read_bytes()==old
            cases[name+'-quarantined-without-retry-or-release']='passed'
    with ready() as c:
        dispatch(c);r=recover(c,c.signed['signedTransactionBase64']);assert r['state']=='exit-signing-quarantined'
        assert r['acknowledgmentRecorded'] and not r['reservationReleased']
        cases['conflicting-later-response-preserves-first-wire-and-quarantines']='passed'
    for mode in ('storage-failure','stop-before-commit','expiry-before-commit'):
        with ready() as c:
            old=c.path.read_bytes();writer=m.append;called=[]
            def fault(*args):
                writer(*args)
                if mode=='storage-failure':raise OSError('synthetic write')
                if mode=='stop-before-commit':(c.home/'STOP').touch(mode=0o600)
                if mode=='expiry-before-commit':c.now+=30000
            with patch.object(m,'append',side_effect=fault):submission.refuses(lambda:dispatch(c,lambda _:called.append(True)))
            assert not called and c.path.read_bytes()==old
            cases[mode+'-rolls-back-boundary-without-adapter']='passed'
    with ready() as c:
        calls=[]
        with patch.object(m,'acknowledge',side_effect=OSError('synthetic acknowledgment write')):
            submission.refuses(lambda:dispatch(c,lambda r:calls.append(r) or c.exit_wire))
        assert len(calls)==1 and status(c)['state']=='exit-signing-unknown'
        assert dispatch(c)['signerAdapterCallsThisRun']==0
        assert recover(c,c.exit_wire)['state']=='exit-signed-recorded'
        cases['acknowledgment-write-failure-recovers-without-second-adapter']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        privateKeyAccessed=False,temporaryLedgersRemoved=True,productionLedgerUpdated=False,
        durableSigningBoundary=True,automaticResigningAllowed=False,liveKeyBackendConnected=False,
        reservationReleased=False,allocationTransferred=False,executionApproved=False,runtimeIntegrated=False)


def stop_book(c):
    book=c.book()
    try:book.stop()
    finally:book.close()
