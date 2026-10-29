"""Deterministic single-leg cost cases; never read a wallet or contact RPC."""
from copy import deepcopy
import fresh_quote  # Initialize existing module paths before isolated cost review.
import cost_readiness as m
from unsigned_simulation_checks import fixture as effects_fixture
from preflight_checks import fixture as preflight_fixture, NOW, edit


def fixture():
    c,p,item=effects_fixture();_,baseline=preflight_fixture(True)
    # Synthetic initial quote precedes the synthetic policy and account capture.
    p['quote'].update(requestedAtMs=NOW-1600,receivedAtMs=NOW-1100)
    a=c['packet']['policy']['accounts']
    r=dict(phase='closed',wallet=a['wallet'],pool=a['pool'],nativeHeldLamports='0',
        tokenAccounts=[dict(account=a['source'],mint=a['inputMint'],heldAtomic='0')],
        readStartedAtMs=NOW+130,observedAtMs=NOW+150,
        ledgerHeadSha256='a'*64,cycleBindingSha256='b'*64,confirmedFeeLamports='20000')
    return dict(packet=c['packet'],capture=c,price=p,simulation_item=item,reservations=r,
        baseline=baseline,simulation_started=NOW+10,simulation_received=NOW+100,
        simulation_finished=NOW+120,now_ms=NOW+200)


def run():
    cases={}
    good=m.assess(**fixture())
    if good['state']!='single-leg-cost-evidence-consistent':raise ValueError('cost-self-check')
    cases['consistent-single-leg']=good
    mutations={
        'missing-own-simulation-fee': lambda x:x['simulation_item']['result']['value'].pop('fee'),
        'changed-simulated-output': lambda x:x['price']['quote'].update(outAmount='99'),
        'unknown-native-reservation': lambda x:x['reservations'].update(nativeHeldLamports=None),
        'unknown-token-reservation': lambda x:x['reservations']['tokenAccounts'][0].update(heldAtomic=None),
        'native-reservation-shortfall': lambda x:x['reservations'].update(nativeHeldLamports='99999'),
        'token-reservation-shortfall': lambda x:x['reservations']['tokenAccounts'][0].update(heldAtomic='901'),
        'expired-evidence': lambda x:x.update(now_ms=NOW+10001),
        'future-simulation': lambda x:x.update(simulation_received=NOW+1000),
        'open-cycle': lambda x:x['reservations'].update(phase='open'),
        'changed-deployment': lambda x:edit(x['capture'],-1,120,b'\x01'),
        'wrong-message-fee': lambda x:x['packet']['feeAssertion'].update(lamports='1'),
        'summary-is-not-raw-evidence': lambda x:x.update(simulation_item={'state':'unsigned-effects-match-quote'}),
    }
    for name,change in mutations.items():
        x=fixture();change(x);r=m.assess(**x)
        if r['state']!='unavailable' or r['calculation'] is not None:raise ValueError('cost-rejection-self-check')
        cases[name]=r
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        executionApproved=False,productionStateChanged=False)
