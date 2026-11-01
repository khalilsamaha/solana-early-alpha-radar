"""Portable timing contracts over raw public fixtures; no real RPC or private key."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import admission_timing as m
from pre_sign_checks import fixture,NOW
from locked_admission_checks import home_fixture


@contextmanager
def case(*,change=None,read_hook=None,collector_hook=None,review_hook=None):
    e,p=fixture()
    with tempfile.TemporaryDirectory() as d:
        a=p['scope']['accounts'];home=home_fixture(Path(d)/'source',a['wallet'])
        c=SimpleNamespace(e=e,p=p,home=home,wallet=a['wallet'],pool=a['pool'],now=NOW+200,mono=0,reads=0,collections=0)
        with patch.object(m.admission,'BASELINE',e['costInputs']['baseline']):
            deadline=m.admission.review(e,p,c.now)['validUntilExclusiveMs']
        if change:change(c)
        def collect(*args,**kw):
            c.collections+=1
            assert kw['simulate'] and kw['assess_costs'] and kw['refreshed_deployment']
            kw['_evidence_sink'](deepcopy(c.e))
            result=dict(state='controlled-cost-observation-consistent',stage='complete',networkRequests=20,
                requestMethods=['getGenesisHash']*20,costReadiness=dict(validUntilExclusiveMs=deadline),
                preflight=dict(validUntilExclusiveMs=deadline),binding=dict(binding=dict(validUntilExclusiveMs=deadline)))
            if collector_hook:collector_hook(c,kw,result)
            return result
        def read(root,wallet,pool,clock):
            assert root==home and wallet==c.wallet and pool==c.pool
            c.reads+=1;r=deepcopy(c.e['costInputs']['reservations'])
            r.update(readStartedAtMs=clock(),observedAtMs=clock())
            if read_hook:read_hook(c,c.reads,r)
            return r
        original=m.admission.review
        def review(*args,**kw):
            r=original(*args,**kw)
            if review_hook:review_hook(c,r)
            return r
        with patch.object(m.fresh_quote,'observe',collect),patch.object(m.view,'read_locked',read),\
             patch.object(m.admission,'BASELINE',e['costInputs']['baseline']),patch.object(m.admission,'review',review),\
             patch('socket.socket',side_effect=AssertionError('network')),\
             patch.object(m.admission,'Admission',side_effect=AssertionError('durable admission')),\
             patch('core.signer',side_effect=AssertionError('signer')):
            c.run=lambda **kw:m.observe(c.home,c.wallet,c.pool,clock=lambda:c.now,monotonic=lambda:c.mono,
                maximum_exit_attempts=kw.get('attempts',2),maximum_exit_fee_lamports=kw.get('exit_fee','10000'),
                maximum_total_fee_lamports=kw.get('total','30000'))
            yield c


def rejected(r):
    assert r['state']=='unavailable' and not r['rawAdmissionValidationPassed'] and r['assessment'] is None,r


def run():
    cases={}
    with case() as c:
        before={p.name:p.read_bytes() for p in c.home.iterdir()};r=c.run()
        assert r['state']=='entry-admission-timing-consistent' and r['assessment']['projectedFeeCommitmentLamports']=='26000',r
        cases['raw-entry-evidence-revalidated-with-all-exit-fee-caps']='passed'
        assert c.reads==2 and len(r['timings'])==5 and r['remainingMs']>0
        cases['collection-and-two-source-reads-have-separate-timings']='passed'
        assert {p.name:p.read_bytes() for p in c.home.iterdir()}==before
        assert not (c.home.parent/(c.home.name+'-entry-handoff-v1')).exists()
        cases['source-bytes-unchanged-no-admission-created']='passed'
        assert all(r[k] is False for k in ('privateKeyAccessed','signingApproved','executionApproved','nextCycleAuthorized','productionReservationsCreated'))
        assert 'unsignedTransactionBase64' not in json.dumps(r) and 'simulation_item' not in json.dumps(r)
        cases['report-is-not-a-signing-or-allocation-permit']='passed'
    for n in (1,2):
        def changed(c,i,r):
            if i==n:r['ledgerHeadSha256']='c'*64
        with case(read_hook=changed) as c:rejected(c.run())
        cases['changed-source-'+('before' if n==1 else 'after')+'-validation-refused']='passed'
    with case(review_hook=lambda c,r:setattr(c,'now',r['validUntilExclusiveMs'])) as c:
        r=c.run();rejected(r);assert r['remainingMs']==0
    cases['validation-cannot-consume-original-deadline']='passed'
    def slow_last(c,n,r):
        if n==2:c.now+=10000
    with case(read_hook=slow_last) as c:rejected(c.run())
    cases['final-source-read-cannot-refresh-expiry']='passed'
    with case(review_hook=lambda c,r:setattr(c,'mono',31)) as c:rejected(c.run())
    cases['monotonic-budget-blocks-unchanged-wall-clock']='passed'
    with case(review_hook=lambda c,r:setattr(c,'now',c.now-1)) as c:rejected(c.run())
    cases['clock-regression-cannot-pass']='passed'
    with case() as c:rejected(c.run(total='25999'))
    cases['combined-fee-budget-shortfall-refused']='passed'
    with case(change=lambda c:c.e['costInputs']['reservations'].update(nativeHeldLamports=None)) as c:rejected(c.run())
    cases['unknown-reservations-never-become-zero']='passed'
    with case(collector_hook=lambda c,k,r:k['_evidence_sink'](deepcopy(c.e))) as c:rejected(c.run())
    cases['multiple-private-handoffs-refused']='passed'
    with case(collector_hook=lambda c,k,r:r.update(state='unavailable',diagnosticCode='observation-expired-before-completion')) as c:
        r=c.run();rejected(r);assert c.collections==1 and r['networkRequests']==20
    cases['collector-failure-after-emission-never-promoted-or-retried']='passed'
    with case() as c:
        (c.home.parent/(c.home.name+'-entry-handoff-v1')).mkdir();rejected(c.run());assert c.collections==0
    cases['existing-admission-stops-before-network']='passed'
    with case() as c:
        (c.home/'STOP').touch();rejected(c.run());assert c.collections==0
    cases['stop-before-collection-stops-before-network']='passed'
    with case(review_hook=lambda c,r:(c.home/'STOP').touch()) as c:rejected(c.run())
    cases['stop-during-validation-refused']='passed'
    with case() as c:
        rejected(c.run(attempts=4));assert c.collections==0
    cases['invalid-policy-stops-before-network']='passed'
    with case(change=lambda c:c.e['costInputs'].update(simulation_item={'state':'provider-private-detail'})) as c:
        r=c.run();rejected(r);assert 'provider-private-detail' not in json.dumps(r)
    cases['public-summary-and-private-error-text-not-accepted']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,realNetworkRequests=0,privateKeyAccessed=False,
        signaturesCreated=0,transactionsSent=0,sourceStateChanged=False,admissionLedgerCreated=False,
        productionReservationsCreated=False,executionApproved=False,nextCycleAuthorized=False,runtimeIntegrated=False)
