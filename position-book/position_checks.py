"""Deterministic host gate; all ledger files are temporary synthetic state."""
import tempfile
from pathlib import Path
from book import Book, FLAGS
from position_fixtures import package, registration, policy, clock


def run():
    cases={}
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'roundtrip.positions.sqlite'
        b=Book(path,policy(),clock)
        b.reserve('p','entry',registration(package(),'buy'));b.boundary('buy')
        u=b.observe('buy',package(unknown=True));b.close()
        assert u['reservedQuoteAtomic']=='100' and u['principalExposureAtomic']=='100'
        b=Book(path,clock=clock)
        assert b.status('p')['positions'][0]['state']=='entry-unknown'
        cases['unknown-entry-restart']=b.status('p')
        b.observe('buy',package());b.stop_entries()
        b.reserve('p','exit',registration(package('exit'),'sell'));b.boundary('sell')
        cases['unknown-exit']=b.observe('sell',package('exit',unknown=True))
        cases['failed-exit-preserves-position']=b.observe('sell',package('exit',failed=True))
        b.close();b=Book(path,clock=clock)
        b.reserve('p','exit',registration(package('retry'),'retry'));b.boundary('retry')
        closed=b.observe('retry',package('retry'))
        assert closed==b.observe('retry',package('retry'))
        assert closed['lastReconciledQuoteAtomic']=='980' and closed['feesSpentLamports']=='15000'
        assert closed['cumulativeGrossLossAtomic']=='20' and closed['positions'][0]['state']=='closed'
        cases['stopped-entry-exit-allowed-and-duplicate-idempotent']=closed
        b.close()
    for name in ('principal-limit','exit-fee-reserve','unknown-not-resubmitted','conflict-quarantines','fee-only-entry-failure','loss-limit'):
        with tempfile.TemporaryDirectory() as d:
            p=policy()
            if name=='principal-limit':p['maximumPrincipalAtomic']='99'
            if name=='exit-fee-reserve':p['maximumTotalFeeLamports']='19999'
            b=Book(Path(d)/'test.positions.sqlite',p,clock)
            if name in ('principal-limit','exit-fee-reserve'):
                try:b.reserve('p','entry',registration(package(),'buy'))
                except ValueError:pass
                else:raise AssertionError('Reservation accepted')
                assert b.db.execute('SELECT COUNT(*) FROM intents').fetchone()[0]==0
            else:
                b.reserve('p','entry',registration(package(),'buy'));b.boundary('buy')
                if name=='unknown-not-resubmitted':
                    try:b.boundary('buy')
                    except ValueError:pass
                    else:raise AssertionError('Duplicate boundary')
                elif name=='fee-only-entry-failure':
                    r=b.observe('buy',package(failed=True));assert r['feesSpentLamports']=='5000' and r['lastReconciledQuoteAtomic']=='1000'
                elif name=='conflict-quarantines':
                    b.observe('buy',package());r=b.observe('buy',package(failed=True));assert r['quarantined']
                else:
                    b.observe('buy',package());b.reserve('p','exit',registration(package('exit'),'sell'));b.boundary('sell')
                    b.observe('sell',package('exit',failed=True))
                    b.reserve('p','exit',registration(package('retry'),'retry'));b.boundary('retry');b.observe('retry',package('retry'))
                    try:b.reserve('new','entry',registration(package('entry2'),'buy2'))
                    except ValueError as e:assert str(e)=='gross-loss-limit'
                    else:raise AssertionError('Loss limit bypassed')
            cases[name]=b.status();b.close()
    return {'format':'position-book-self-check-1','mode':'synthetic-offline','casesPassed':len(cases),
        'cases':cases,'temporaryLedgersRemoved':True,**FLAGS,
        'limitations':['Synthetic signed evidence, not observed market trades.',
            'No sender, router validation, wallet access or live spending enforcement.',
            'No strategy performance or funded-test approval.']}
