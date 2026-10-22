"""Deterministic summary of offline lifecycle cases with temporary synthetic wallets."""
import tempfile
from pathlib import Path
from core import initialize
from token_lifecycle import execute,recover
from token_lifecycle_fixtures import FakeTokenRpc


def run():
    expected={'ok':'finalized-success','failed':'finalized-failure','wrong-cluster':'not-prepared',
              'rent-cap':'not-prepared','sim-failed':'preparation-incomplete',
              'timeout':'finalized-success','wrong-signature':'quarantined',
              'bad-balance':'quarantined','missing-receipt':'submission-unknown'}
    cases={}
    for mode,state in expected.items():
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'wallet';wallet=initialize(home)['wallet'];fake=FakeTokenRpc(home,mode)
            r=execute(home,wallet,opener=fake,sleeper=lambda _:None)
            if r['state']!=state:raise ValueError('Token self-check mismatch')
            again=execute(home,wallet,opener=fake,sleeper=lambda _:None)
            if state!='not-prepared' and again['networkRequests']!=0:raise ValueError('Duplicate execution')
            cases[mode]={'state':r['state'],'submissionBoundaries':r['submissionAttempts'],
                         'syntheticSendCalls':r['sendRequestsThisRun']}
    with tempfile.TemporaryDirectory() as d:
        home=Path(d)/'wallet';wallet=initialize(home)['wallet'];fake=FakeTokenRpc(home,'crash')
        try:execute(home,wallet,opener=fake,sleeper=lambda _:None)
        except SystemExit:pass
        r=recover(home,wallet,opener=FakeTokenRpc(home,sent=True),sleeper=lambda _:None)
        if r['state']!='finalized-success' or r['sendRequestsThisRun']!=0:raise ValueError('Recovery failed')
        cases['restart-after-boundary']={'state':r['state'],'submissionBoundaries':r['submissionAttempts'],'syntheticSendCalls':0}
    return {'format':'devnet-token-lifecycle-self-check-1','mode':'synthetic-offline','casesPassed':len(cases),
            'cases':cases,'networkRequests':0,'transactionsSent':0,'executionApproved':False,'productionLedgerUpdated':False,
            'temporaryKeysAndJournalsRemoved':True}
