"""Offline rehearsal using temporary keys and synthetic responses."""
from pathlib import Path
from tempfile import TemporaryDirectory
from core import initialize, prepare, Session, SYSTEM, FLAGS
from rehearsal_fixtures import FakeRpc

def run():
    cases=[]
    with TemporaryDirectory(prefix='radar-devnet-check-') as tmp:
        for mode,expected in (
            ('ok','simulation-passed-not-submitted'),('unfunded','needs-devnet-funding'),
            ('wrong-cluster','blocked'),('high-fee','blocked'),
            ('sim-error','preparation-incomplete'),('timeout','preparation-incomplete'),
            ('missing-balances','preparation-incomplete'),('changed-between-reads','simulation-passed-not-submitted')):
            home=Path(tmp)/mode; initialize(home); rpc=FakeRpc(mode,home)
            result=prepare(home,rpc)
            if result['state']!=expected: raise ValueError('Offline case failed')
            cases.append({'case':mode,'passed':True,'state':result['state'],
                          'signed':result['signed'],'simulationPassed':result['simulationPassed'],
                          'syntheticRpcCalls':len(rpc.calls)})
        home=Path(tmp)/'restart'; initialize(home)
        with Session(home) as session: session.record({'blockhash':SYSTEM},100)
        with Session(home) as session:
            if session.status()['plans'][0]['state']!='intent-recorded': raise ValueError('Recovery failed')
        rpc=FakeRpc()
        try: prepare(home,rpc)
        except ValueError as e:
            if str(e)!='plan-already-recorded-use-status': raise
        else: raise ValueError('Recovery silently retried')
        if rpc.calls: raise ValueError('Recovery made requests')
        cases.append({'case':'restart-preserves-intent','passed':True,'syntheticRpcCalls':0})
    return {'format':'devnet-rehearsal-self-check-1','mode':'synthetic-offline',
            'cases':cases,'casesPassed':len(cases),'networkRequests':0,
            'temporaryKeysAndJournalsRemoved':True,**FLAGS}
