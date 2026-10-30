"""Portable raw-admission and durable-boundary tests in temporary synthetic ledgers."""
from copy import deepcopy
from pathlib import Path
import tempfile
from unittest.mock import patch
import pre_sign_admission as m
from paired_checks import leg, NOW, edit


def fixture():
    e=leg()
    p=dict(format=m.VERSION+'-policy',scope=deepcopy(e['scope']),maximumExitAttempts=2,
           maximumExitFeeLamports='10000',maximumTotalFeeLamports='30000')
    return e,p


def reject(fn):
    try: fn()
    except ValueError: return
    raise AssertionError('expected rejection')


def run():
    e,p=fixture();cases={}
    with patch.object(m,'BASELINE',e['costInputs']['baseline']), tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'check.admission.sqlite';clock=lambda:NOW+200
        b=m.Admission(path,p,clock)
        try:
            s=b.reserve(e)
            assert s['reservation']['reservedPrincipalAtomic']=='100' and s['reservation']['reservedFeeLamports']=='26000'
            cases['raw-price-fee-effects-to-reservation']='passed'
            assert b.reserve(e)==s;cases['duplicate-does-not-refresh']='passed'
            b.close();b=m.Admission(path,clock=clock)
            assert b.status()==s;cases['reservation-survives-reopen']='passed'
            altered=deepcopy(e);altered['costInputs']['reservations']['ledgerHeadSha256']='c'*64
            reject(lambda:b.mark_signing_boundary(altered));assert b.status()==s
            cases['changed-source-ledger-blocked']='passed'
            s=b.mark_signing_boundary(e)
            assert s['state']=='signing-unknown' and s['reservation']['reservedFeeLamports']=='26000'
            cases['durable-before-sign-boundary']='passed'
            b.close();b=m.Admission(path,clock=lambda:NOW+30000)
            assert b.status()==s;reject(lambda:b.mark_signing_boundary(e))
            cases['unknown-never-released-on-expiry']='passed'
            s=b.stop();assert s['reservation']['reservedFeeLamports']=='26000'
            reject(lambda:b.mark_signing_boundary(e));cases['stop-preserves-commitment']='passed'
        finally:b.close()
        mutations={
            'summary-not-raw':lambda e,p:e['costInputs'].update(simulation_item={'state':'success'}),
            'price-tamper':lambda e,p:e['costInputs']['price']['quote'].update(outAmount='999'),
            'deployment-tamper':lambda e,p:edit(e['costInputs']['capture'],-1,120,b'\x01'),
            'native-all-exits-shortfall':lambda e,p:e['costInputs']['reservations'].update(nativeHeldLamports='80000'),
            'total-fee-shortfall':lambda e,p:p.update(maximumTotalFeeLamports='25999'),
            'unknown-source-reservation':lambda e,p:e['costInputs']['reservations'].update(nativeHeldLamports=None),
            'signed-packet-rejected':lambda e,p:e['costInputs']['packet'].update(unsignedTransactionBase64='AA=='),
        }
        for name,change in mutations.items():
            raw,policy=fixture();change(raw,policy)
            b=m.Admission(Path(tmp)/(name+'.admission.sqlite'),policy,clock)
            try:
                reject(lambda:b.reserve(raw));assert b.status()['state']=='empty';cases[name]='passed'
            finally:b.close()
        b=m.Admission(Path(tmp)/'stale.admission.sqlite',p,lambda:NOW+20000)
        try:reject(lambda:b.reserve(e));assert b.status()['state']=='empty';cases['stale-evidence-rejected']='passed'
        finally:b.close()
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
                casesPassed=len(cases),cases=cases,temporaryLedgersRemoved=True,**m.FLAGS)
