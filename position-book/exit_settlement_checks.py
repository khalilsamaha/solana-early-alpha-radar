"""Connected fresh exit and settlement over synthetic RPC, no wallet keys."""
from contextlib import contextmanager
from copy import deepcopy
import json
from unittest.mock import patch
import exit_settlement as m
from fresh_exit_checks import case as fresh_case
from exit_accounting_checks import package,ReceiptRpc
from exit_balance_checks import FakeRpc as BalanceRpc,fixture_rows
from exit_submission_checks import FakeRpc as IncompleteRpc
from admission_receipt_checks import failed


@contextmanager
def case():
    with fresh_case() as c:
        c.open_exit=c.run
        c.receipt=lambda **kw:ReceiptRpc(c,kw.get('package',package(c)[0]))
        c.balances=lambda **kw:BalanceRpc(c,**kw)
        c.advance=lambda **kw:m.advance(c.home,c.wallet,c.pool,clock=c.clock,monotonic=lambda:c.mono,**kw)
        c.inspect=lambda:m.status(c.home,c.wallet,c.pool,clock=c.clock,monotonic=lambda:c.mono)
        c.finish=lambda **kw:c.advance(close_exit=True,receipt_opener=kw.pop('receipt',c.receipt()),
            balance_opener=kw.pop('balance',c.balances()),**kw)
        yield c


def histories(c):
    book=c.book()
    try:return {name:[tuple(row) for row in book.db.execute('SELECT * FROM '+name)] for name in
        ('admission_events','admission_entry_accounting','admission_exit_signing','admission_exit_submission')}
    finally:book.close()


def run():
    cases={}
    with case() as c:
        r=c.inspect();assert r['state']=='entry-open' and r['networkRequests']==0 and r['accounting'] is None
        assert c.advance(close_exit=True)['networkRequests']==0
        cases['no-signed-exit-does-not-create-or-send-one']='passed'
        c.open_exit();history=histories(c);source={p.name:p.read_bytes() for p in c.home.iterdir()}
        receipt=c.receipt();balance=c.balances()
        r=c.advance(receipt_opener=receipt,balance_opener=balance)
        assert r['state']=='exit-position-flat-held' and r['receiptRequestsThisRun']==4 and r['balanceRequestsThisRun']==0,r
        assert r['accountingAppliedThisRun'] and not r['closureRecorded'] and not balance.requests
        cases['default-reconciles-receipt-without-closure-or-balance-requests']='passed'
        a=r['accounting']['accounting'];assert a['ownedAcquiredResidualAtomic']=='0' and a['protectedAcquiredInventoryAtomic']=='902'
        assert int(a['originalFeeCommitmentLamports'])==int(a['totalFeePaidLamports'])+int(a['feeCommitmentRemainingLamports'])
        cases['paid-fees-owned-delta-and-protected-inventory-conserve']='passed'
        r=c.finish();assert r['state']=='closed-scoped-commitments-released' and r['networkRequests']==4,r
        assert r['closureAppliedThisRun'] and r['closureRecorded'] and r['coherent']
        cases['explicit-choice-collects-fresh-balances-and-closes']='passed'
        s=r['closure']['settlement'];assert s['sourceProceedsReleasedAtomic']=='96' and s['principalRestoredAtomic']=='0'
        assert s['protectedInventoryReleasedAtomic']=='0' and r['scopedAccounting']['feeHeldLamports']=='0'
        assert r['recordIdentity']['exitAccountingSha256']==r['accounting']['recordSha256']==s['exitAccountingSha256']
        cases['combined-projection-binds-closure-to-accounting-and-actual-proceeds']='passed'
        assert all(r[k] is False for k in ('privateKeyAccessed','fundsAvailableForNewEntry','walletWideReservationsKnown','nextCycleAuthorized','allocationTransferred','executionApproved','runtimeIntegrated'))
        assert r['transactionsSent']==r['signaturesCreated']==0
        cases['scoped-release-does-not-credit-an-allocator-or-authorize-an-entry']='passed'
        assert histories(c)==history and source=={p.name:p.read_bytes() for p in c.home.iterdir()}
        cases['original-admission-entry-signing-and-source-history-unchanged']='passed'
        before=c.path.read_bytes();again=c.finish();assert again['networkRequests']==0 and not again['closureAppliedThisRun'] and before==c.path.read_bytes()
        cases['completed-recovery-neither-recollects-nor-releases-twice']='passed'
        c.timer.at+=30000;(c.home/'STOP').touch(mode=0o600)
        assert c.finish()['networkRequests']==0 and c.inspect()['closureRecorded'] and c.path.read_bytes()==before
        cases['stop-and-expiry-preserve-historical-closure']='passed'
        assert c.exit_wire not in json.dumps(r) and 'rpcEvidence' not in json.dumps(r) and 'unsignedTransactionBase64' not in json.dumps(r)
        cases['public-summary-excludes-wire-and-raw-evidence']='passed'
    with case() as c:
        c.open_exit();r=c.finish();assert r['networkRequests']==8 and r['receiptRequestsThisRun']==r['balanceRequestsThisRun']==4
        assert r['accountingAppliedThisRun'] and r['closureAppliedThisRun']
    cases['complete-connected-settlement-is-bounded-to-eight-read-only-requests']='passed'
    with patch.object(m,'_snapshot',side_effect=AssertionError('source')):
        for choice in (1,'true',None,[]):
            try:m.advance('/missing','wallet','pool',close_exit=choice)
            except ValueError:pass
            else:raise AssertionError('choice accepted')
    cases['exact-boolean-choice-before-source-access']='passed'
    for name in ('missing','headers-only','failed','wrong-prebalance'):
        with case() as c:
            c.open_exit();p,_=package(c)
            if name=='failed':p=failed(p)
            if name=='wrong-prebalance':p['bundle']['rpcEvidence']['transaction']['result']['meta']['preTokenBalances'][0]['uiTokenAmount']['amount']='99999'
            rpc=IncompleteRpc(c,missing=name=='missing') if name in ('missing','headers-only') else ReceiptRpc(c,p)
            balance=c.balances();r=c.finish(receipt=rpc,balance=balance)
            assert not r['closureRecorded'] and not balance.requests and r['balanceRequestsThisRun']==0,r
            if name=='failed':assert r['accounting']['accounting']['ownedAcquiredResidualAtomic']=='98' and r['accountingAppliedThisRun']
            if name=='wrong-prebalance':assert not r['coherent'] and r['state']=='quarantined'
        cases[name+'-cannot-release-commitments']='passed'
    for name in ('wallet-credit','protected-inventory-debit','provider-error'):
        with case() as c:
            c.open_exit();_,rows,_=fixture_rows(c)
            if name=='wallet-credit':rows[0]['lamports']+=1
            if name=='protected-inventory-debit':
                from exit_balance_checks import token_change
                token_change(rows[2],64,0)
            r=c.finish(balance=c.balances(rows=rows,error=name=='provider-error'))
            assert r['state']=='exit-settled-closure-unavailable' and r['accounting']['accountingUsable'] and not r['closureRecorded'],r
            assert not r['scopedCommitmentsReleased']
        cases[name+'-keeps-settled-commitments-held']='passed'
    for kind in ('file','durable'):
        with case() as c:
            c.open_exit()
            if kind=='file':(c.home/'STOP').touch(mode=0o600)
            else:
                b=c.book()
                try:b.stop()
                finally:b.close()
            r=c.finish();assert r['state']=='exit-settled-closure-stopped' and r['accountingAppliedThisRun'] and r['balanceRequestsThisRun']==0,r
            assert not r['scopedCommitmentsReleased']
        cases[kind+'-stop-allows-accounting-but-blocks-new-closure']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',casesPassed=len(cases),cases=cases,
        mode='synthetic-offline',realNetworkRequests=0,privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,
        syntheticScopedClosureExercised=True,productionReservationsReleased=False,
        fundsAvailableForNewEntry=False,nextCycleAuthorized=False,executionApproved=False,runtimeIntegrated=False)
