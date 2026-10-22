"""Offline submission/recovery self-check; all RPC responses synthetic."""
from tempfile import TemporaryDirectory
from pathlib import Path
from core import initialize,prepare
from rehearsal_fixtures import FakeRpc
from submission_fixtures import SubmissionRpc
from submission import execute,recover,stop,Lifecycle

def run():
    cases=[]
    with TemporaryDirectory(prefix='radar-submit-check-') as tmp:
        for mode,expected in (('ok','finalized-success'),('timeout','finalized-success'),
            ('wrong-signature','quarantined'),('bad-balance','quarantined'),
            ('final-failed','finalized-failure'),('absent','submission-unknown')):
            home=Path(tmp)/mode; wallet=initialize(home)['wallet']; prepare(home,FakeRpc())
            rpc=SubmissionRpc(home,mode); r=execute(home,wallet,opener=rpc,sleeper=lambda _:None)
            if r['state']!=expected: raise ValueError('Synthetic submission case failed')
            if sum(c['method']=='sendTransaction' for c in rpc.calls)!=1: raise ValueError('Send count')
            repeated=SubmissionRpc(home); again=execute(home,wallet,opener=repeated,sleeper=lambda _:None)
            if repeated.calls or again['submissionAttempts']!=1: raise ValueError('Repeated submission')
            cases.append({'case':mode,'state':r['state'],'passed':True,'syntheticSendCalls':1})
        home=Path(tmp)/'expiry'; wallet=initialize(home)['wallet']; prepare(home,FakeRpc())
        rpc=SubmissionRpc(home,expired=True)
        r=execute(home,wallet,allow_replace=True,opener=rpc,sleeper=lambda _:None)
        if r['state']!='finalized-success' or len(r['plans'])!=2: raise ValueError('Replacement failed')
        cases.append({'case':'explicit-expired-replacement','state':r['state'],'passed':True,'syntheticSendCalls':1})
        home=Path(tmp)/'restart'; wallet=initialize(home)['wallet']; prepare(home,FakeRpc())
        with Lifecycle(home) as s: s.boundary(s.plan())
        rpc=SubmissionRpc(home,sent=True); r=recover(home,wallet,opener=rpc,sleeper=lambda _:None)
        if r['state']!='finalized-success' or any(c['method']=='sendTransaction' for c in rpc.calls): raise ValueError('Recovery failed')
        cases.append({'case':'restart-observes-without-sending','state':r['state'],'passed':True,'syntheticSendCalls':0})
        home=Path(tmp)/'stop'; wallet=initialize(home)['wallet']; prepare(home,FakeRpc()); stop(home)
        rpc=SubmissionRpc(home); r=execute(home,wallet,opener=rpc)
        if rpc.calls or r['reason']!='stop-requested': raise ValueError('Stop failed')
        cases.append({'case':'stop-before-submit','state':r['state'],'passed':True,'syntheticSendCalls':0})
    return {'format':'devnet-submission-self-check-1','mode':'synthetic-offline','cases':cases,
        'casesPassed':len(cases),'networkRequests':0,'transactionsSent':0,'temporaryKeysAndJournalsRemoved':True,
        'productionLedgerUpdated':False,'executionApproved':False}
