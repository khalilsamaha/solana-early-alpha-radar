"""Synthetic fee evidence including missing fees, cross-message and budget failures."""
import projected_fee as m
from projected_exit_checks import fixture as parent_fixture
from recorded_capture import GENESIS


def fixture():
    a,p=parent_fixture();d=m.projected_exit.build(a,p)
    start=a['simulation_finished'];a['now_ms']=max(a['now_ms'],start+3)
    e=dict(params=m.parameters(a,p,d),fee=dict(state='received',result=dict(
        context=dict(slot=a['simulation_item']['result']['context']['slot']),value=6000)),
        genesis=dict(state='received',result=GENESIS['devnet']),
        startedAtMs=start,receivedAtMs=start+1,finishedAtMs=start+2)
    return a,p,d,e


def run():
    a,p,d,e=fixture();r=m.assess(a,p,d,e)
    if r['state']!='projected-exit-fee-consistent':raise ValueError('fee-self-check')
    cases={'exact-message-fee-and-conditional-caps':'passed'}
    changes={
        'null-fee':lambda a,p,d,e:e['fee']['result'].update(value=None),
        'boolean-fee':lambda a,p,d,e:e['fee']['result'].update(value=True),
        'over-cap':lambda a,p,d,e:e['fee']['result'].update(value=10001),
        'wrong-message':lambda a,p,d,e:e['params'].__setitem__(0,'AAAA'),
        'old-context':lambda a,p,d,e:e['fee']['result']['context'].update(slot=0),
        'wrong-cluster':lambda a,p,d,e:e['genesis'].update(result=GENESIS['mainnet-beta']),
        'clock-regression':lambda a,p,d,e:e.update(receivedAtMs=e['startedAtMs']-1),
        'expired-parent':lambda a,p,d,e:a.update(now_ms=a['now_ms']+20000),
        'unknown-reservation':lambda a,p,d,e:a['reservations'].update(nativeHeldLamports=None),
        'insufficient-both-caps':lambda a,p,d,e:a['reservations'].update(nativeHeldLamports='89000'),
    }
    for name,change in changes.items():
        a,p,d,e=fixture();change(a,p,d,e);r=m.assess(a,p,d,e)
        if r['state']!='unavailable' or r['calculation'] is not None:raise ValueError('fee-rejection-self-check-'+name)
        cases[name]='rejected'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        executionApproved=False,productionStateChanged=False)
