"""Synthetic complete fresh-entry, receipt settlement and delayed exit evidence."""
from contextlib import contextmanager
from copy import deepcopy
import json
from unittest.mock import patch

import settled_exit as m
from fresh_entry_checks import case as fresh_case
import admission_exit_capture_checks as exit_fixture
from admission_submission_checks import FakeOpener
from admission_receipt_checks import failed


@contextmanager
def case():
    with fresh_case() as c:
        c.run_entry=c.run
        c.now+=1000
        def advance(**kwargs):
            return m.advance(c.home,c.wallet,c.pool,clock=lambda:c.now,
                receipt_opener=kwargs.pop('receipt_opener',c.opener()),**kwargs)
        c.advance=advance
        c.inspect=lambda:m.status(c.home,c.wallet,c.pool,clock=lambda:c.now)
        yield c


@contextmanager
def delayed(c,*,hook=None,mutate=None):
    first,e,baseline=exit_fixture.setup(c)
    simulation=exit_fixture.simulation_response(e['capture'],e['price']['quote']['outAmount'])
    if mutate:mutate(first,e)
    clock=exit_fixture.Clock();clock.at=max(clock.at,c.now)
    def now():
        c.now=clock();return c.now
    rpc=exit_fixture.Opener(first,e,hook=hook,sim=simulation)
    snapshot=deepcopy(c.e['costInputs']['reservations'])
    with patch.object(m.exits.exit,'BASELINE',baseline),patch.object(m.view,'read_locked',return_value=snapshot):
        c.delay_clock=clock
        c.prepare=lambda **kw:m.advance(c.home,c.wallet,c.pool,prepare_exit=True,
            receipt_opener=c.opener(),exit_opener=rpc,clock=now,monotonic=lambda:0,**kw)
        yield rpc


def run():
    cases={}
    with case() as c:
        source={p.name:p.read_bytes() for p in c.home.iterdir()}
        assert c.run_entry()['state']=='rpc-acknowledged'
        c.now+=1000
        r=c.advance();a=r['accounting']['accounting']
        assert r['state']=='entry-settled-exit-not-prepared' and r['receiptRequestsThisRun']==4 and r['exitRequestsThisRun']==0
        assert r['accountingAppliedThisRun'] and a['ownedAcquiredAtomic']=='98' and a['entryFeePaidLamports']=='5001'
        cases['fresh-entry-to-collected-receipt-and-owned-delta']='passed'
        assert a['sourcePrincipalSpentAtomic']=='100' and a['feeCommitmentRemainingLamports']=='20999'
        cases['actual-fee-and-held-commitments-conserved']='passed'
        before=c.files();again=c.advance();assert not again['accountingAppliedThisRun'] and again['networkRequests']==0 and c.files()==before
        cases['repeat-settlement-idempotent-no-rpc']='passed'
        with delayed(c) as rpc:
            prepared=c.prepare();assert prepared['state']=='exit-prepared-research-only',prepared
            b=prepared['exitPreparation']['binding']
            assert prepared['networkRequests']==20 and prepared['receiptRequestsThisRun']==0 and len(rpc.calls)==20
            assert b['entryAccountingSha256']==r['accounting']['recordSha256'] and b['quantityAtomic']=='98' and b['protectedInventoryAtomic']=='902'
            cases['separate-delayed-collector-owns-exact-acquired-quantity']='passed'
            assert b['feeCommitmentRemainingLamports']=='20999' and b['otherFeeCommitmentsHeldLamports']=='10999'
            cases['delayed-exit-protects-other-inventory-and-fees']='passed'
            assert c.now>c.deadline and prepared['exitPreparation']['collectionRecorded'] and prepared['exitCreatedThisRun']
            cases['new-exit-evidence-after-original-entry-expired']='passed'
            before=c.files();c.delay_clock.at+=30000
            later=c.prepare();assert later['state']=='exit-preparation-expired' and later['networkRequests']==0 and c.files()==before
            cases['existing-expired-exit-never-refreshed-or-recollected']='passed'
            inspected=c.inspect();assert inspected['state']=='exit-preparation-expired' and c.files()==before
            cases['read-only-combined-status-preserves-records']='passed'
        assert source=={p.name:p.read_bytes() for p in c.home.iterdir()}
        assert not prepared['reservationReleased'] and not prepared['preparedExitUsableForSigning'] and prepared['transactionsSent']==0
        assert c.signed not in json.dumps(prepared) and 'unsignedTransactionBase64' not in json.dumps(prepared)
        cases['source-unchanged-no-wire-or-signing-permit-exported']='passed'
    with case() as c:
        before=c.files();r=c.advance(prepare_exit=True)
        # No admission exists before entry; explicit inspection, never implicit creation.
        assert r['state']=='inspection-required' and r['networkRequests']==0 and c.files()==before
    cases['absent-entry-never-initialized-by-recovery']='passed'
    with case() as c:
        c.run_entry();c.now+=1000
        # A missing chain transaction remains unresolved, not a zero position.
        opener=c.opener();original=opener.open
        def missing(request,timeout=None):
            import io
            result=json.loads(original(request,timeout).read())
            if json.loads(request.data)['method']=='getTransaction':result['result']=None
            return io.BytesIO(json.dumps(result).encode())
        opener.open=missing
        r=c.advance(prepare_exit=True,receipt_opener=opener)
        assert r['state']=='entry-accounting-pending' and r['networkRequests']==4 and not r['accounting']['accountingRecorded'] and r['exitRequestsThisRun']==0
    cases['unknown-entry-blocks-exit-without-inventing-loss-or-quantity']='passed'
    with case() as c:
        c.run_entry();c.now+=1000
        bad=failed(c.rpc.case.package)
        r=c.advance(prepare_exit=True,receipt_opener=FakeOpener(c.rpc.case,package=bad))
        assert r['state']=='entry-failed-held' and r['accounting']['accounting']['ownedAcquiredAtomic']=='0' and r['exitRequestsThisRun']==0
        assert r['accounting']['accounting']['sourcePrincipalHeldAtomic']=='100'
    cases['failed-entry-records-fee-keeps-principal-and-blocks-exit']='passed'
    with case() as c:
        c.run_entry(rpc=c.opener(send='wrong'));c.now+=1000
        r=c.advance(prepare_exit=True);assert r['state']=='quarantined' and r['networkRequests']==0 and not r['accounting']['accountingUsable']
    cases['quarantined-entry-blocks-accounting-and-exit']='passed'
    with case() as c:
        c.run_entry();c.now=c.deadline+1000;(c.home/'STOP').touch(mode=0o600)
        r=c.advance(prepare_exit=True)
        assert r['state']=='entry-settled-exit-stopped' and r['accountingAppliedThisRun'] and r['networkRequests']==4 and r['exitRequestsThisRun']==0
    cases['stopped-expired-entry-still-settles-but-never-collects-exit']='passed'
    for mode in ('rpc-failure','stop-during','expiry-during','inventory-shortfall'):
        with case() as c:
            c.run_entry();c.now+=1000;c.advance()
            before=c.path.read_bytes()
            def hook(n,q,o):
                if n!=4:return
                if mode=='rpc-failure':o.rows[0]=TimeoutError('PRIVATE')
                elif mode=='stop-during':(c.home/'STOP').touch(mode=0o600)
                elif mode=='expiry-during':c.delay_clock.at+=10001
            def mutate(f,e):
                if mode=='inventory-shortfall':exit_fixture.edit(e['capture'],9,64,(97).to_bytes(8,'little'))
            with delayed(c,hook=hook,mutate=mutate) as rpc:
                r=c.prepare();assert r['state']=='entry-settled-exit-unavailable',r
                assert r['accounting']['accountingUsable'] and not r['exitPreparation']['recorded'] and len(rpc.calls)<=20
                assert c.path.read_bytes()==before and 'PRIVATE' not in json.dumps(r)
        cases[mode+'-preserves-settlement-and-withholds-exit']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',casesPassed=len(cases),cases=cases,
        mode='synthetic-offline',realNetworkRequests=0,signaturesCreated=0,transactionsSent=0,
        privateKeyAccessed=False,sourceStateChanged=False,runtimeIntegrated=False,executionApproved=False,
        allocationTransferred=False,reservationReleased=False)
