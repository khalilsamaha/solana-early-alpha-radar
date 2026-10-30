"""Bounded exit-budget exercise over existing synthetic signed receipt fixtures."""
from pathlib import Path
import tempfile
from book import Book
from position_fixtures import package, registration, policy as legacy_policy, clock


def policy(attempts=2):
    p=legacy_policy();p.update(format='position-book-policy-2',maximumExitAttempts=attempts)
    return p


def opened(path,p=None):return Book(path,policy() if p is None else p,clock)


def entry(b):
    b.reserve('p','entry',registration(package(),'buy'));b.boundary('buy')
    return b.observe('buy',package())


def exit_leg(b,name='exit',failed=False):
    b.reserve('p','exit',registration(package(name),name));b.boundary(name)
    return b.observe(name,package(name,failed=failed))


def rejected(action,reason):
    try:action()
    except ValueError as exc:
        if str(exc)!=reason:raise
    else:raise AssertionError('expected rejection: '+reason)


def run():
    cases={}
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'lifecycle.positions.sqlite';b=opened(path)
        try:
            s=b.reserve('p','entry',registration(package(),'buy'))
            assert s['reservedFeeLamports']=='30000';cases['reserve-entry-and-two-exits']='passed'
            b.boundary('buy');s=b.observe('buy',package(unknown=True))
            assert s['reservedFeeLamports']=='30000' and s['reservedQuoteAtomic']=='100'
            b.close();b=Book(path,clock=clock)
            assert b.status()['reservedFeeLamports']=='30000';cases['unknown-entry-survives-reopen']='passed'
            b.observe('buy',package());assert b.status()['reservedFeeLamports']=='20000'
            cases['settled-entry-keeps-two-exit-caps']='passed'
            b.stop_entries();b.reserve('p','exit',registration(package('exit'),'exit'));b.boundary('exit')
            s=b.observe('exit',package('exit',unknown=True));assert s['reservedFeeLamports']=='20000'
            pending=package('retry');pending['bundle']['intent']['walletPreLamports']=b.status()['lastReconciledNativeLamports']
            rejected(lambda:b.reserve('p','exit',registration(pending,'retry')),'position-not-open')
            assert b.exit_attempts('p')==1;cases['unknown-exit-blocks-replacement']='passed'
            s=b.observe('exit',package('exit',failed=True))
            assert s['reservedFeeLamports']=='10000' and s['feesSpentLamports']=='10000'
            assert s['positions'][0]['quantity']=='200' and s['positions'][0]['state']=='open'
            cases['failed-exit-retains-acquisition-and-last-exit-cap']='passed'
            b.close();b=Book(path,clock=clock)
            assert b.status()['reservedFeeLamports']=='10000' and b.exit_attempts('p')==1
            cases['failed-exit-budget-persists']='passed'
            s=exit_leg(b,'retry');assert s['reservedFeeLamports']=='0' and s['feesSpentLamports']=='15000'
            assert s['positions'][0]['state']=='closed' and s['lastReconciledQuoteAtomic']=='980'
            assert s==b.observe('retry',package('retry'));cases['separate-final-exit-idempotent-fees']='passed'
            assert s['entriesStopped'] and not s['automaticRetryAllowed'];cases['entry-stop-still-permits-validated-exit']='passed'
        finally:b.close()
        for name in ('entry-fee-only-failure','cap-before-admission','attempt-cap-keeps-exposure','unknown-quarantine-keeps-holds','expired-preparation-keeps-cap','legacy-policy-unchanged'):
            p=policy(1 if name=='attempt-cap-keeps-exposure' else 2)
            if name=='cap-before-admission':p['maximumTotalFeeLamports']='29999'
            if name=='legacy-policy-unchanged':p=legacy_policy()
            b=opened(Path(temp)/(name+'.positions.sqlite'),p)
            try:
                if name=='cap-before-admission':
                    rejected(lambda:b.reserve('p','entry',registration(package(),'buy')),'cumulative-fee-limit')
                    assert b.db.execute('SELECT COUNT(*) FROM intents').fetchone()[0]==0
                    assert b.db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]==0
                elif name=='attempt-cap-keeps-exposure':
                    entry(b);s=exit_leg(b,failed=True)
                    rejected(lambda:b.reserve('p','exit',registration(package('retry'),'retry')),'exit-attempt-cap')
                    assert s['principalExposureAtomic']=='100' and s['positions'][0]['quantity']=='200'
                    assert s['positionExitBudgets'][0]['exitAttemptsExhausted']
                    assert s['reservedFeeLamports']=='0' and b.exit_attempts('p')==1
                else:
                    b.reserve('p','entry',registration(package(),'buy'))
                    if name=='legacy-policy-unchanged':
                        assert b.status()['format']=='position-book-status-1' and b.status()['reservedFeeLamports']=='20000'
                    elif name=='expired-preparation-keeps-cap':
                        b.j.clock=lambda:clock()+6000
                        rejected(lambda:b.boundary('buy'),'stale-intent')
                        assert b.status()['reservedFeeLamports']=='30000'
                    else:
                        b.boundary('buy')
                        if name=='entry-fee-only-failure':
                            s=b.observe('buy',package(failed=True))
                            assert s['reservedFeeLamports']=='0' and s['principalExposureAtomic']=='0' and s['feesSpentLamports']=='5000'
                        else:
                            s=b.observe('buy',{'state':'finalized-success'})
                            assert s['quarantined'] and not s['accountingUsable']
                            assert s['reservedFeeLamports']=='30000' and s['reservedQuoteAtomic']=='100'
                cases[name]='passed'
            finally:b.close()
    return dict(format='bounded-exit-budget-self-check-1',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,temporaryLedgersRemoved=True,
        networkRequests=0,signaturesCreated=0,transactionsSent=0,productionLedgerUpdated=False,
        executionApproved=False,automaticRetryAllowed=False,liveSenderIntegrated=False,roundTripFundingEstablished=False,
        note='Explicit attempt budget in temporary offline ledgers; no production migration or actual-wallet funding approval.')
