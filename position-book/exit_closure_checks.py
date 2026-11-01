"""Portable scoped closure checks. Public signatures, temporary ledgers, fake RPC."""
from copy import deepcopy
import json
from unittest.mock import patch

import exit_closure as m
from exit_balance_checks import signed_case, collect_receipt, apply, FakeRpc, fixture_rows
from exit_accounting_checks import package
from admission_receipt_checks import failed
from admission_submission_checks import refuses


def close(c, rpc=None):
    return m.collect_and_close(c.home,c.wallet,c.pool,opener=rpc or FakeRpc(c),clock=lambda:c.now,monotonic=lambda:0)


def status(c):
    return m.status(c.home,c.wallet,c.pool,clock=lambda:c.now)


def commit(c, capture):
    return m._commit(c.home,c.wallet,c.pool,capture,(0,10),clock=lambda:c.now,monotonic=lambda:0)


def histories(c):
    b=c.book()
    try:
        return {name:[tuple(r) for r in b.db.execute('SELECT * FROM '+name)] for name in
                ('admission_events','admission_entry_accounting','admission_exit_accounting')}
    finally:b.close()


def run():
    cases={}
    with signed_case() as c:
        rpc=FakeRpc(c);before=c.path.read_bytes();r=close(c,rpc)
        assert r['state']=='exit-closure-blocked' and not rpc.requests and c.path.read_bytes()==before
        cases['unsettled-exit-keeps-commitments-without-rpc']='passed'
        collect_receipt(c);apply(c);original=c.path.read_bytes();history=histories(c)
        source={p.name:p.read_bytes() for p in c.home.iterdir() if p.is_file()}
        r=close(c);a=r['settlement'];closed=c.path.read_bytes()
        assert r['closureRecorded'] and r['appliedThisRun'] and r['scopedCommitmentsReleased'] and r['networkRequests']==4
        cases['fresh-collector-atomically-records-scoped-closure']='passed'
        assert int(a['originalFeeCommitmentLamports'])==int(a['totalFeePaidLamports'])+int(a['unusedFeeReleasedLamports'])
        assert a['remainingFeeHeldLamports']==a['remainingProceedsHeldAtomic']=='0'
        cases['paid-fees-plus-released-unused-fees-conserve']='passed'
        assert a['originalSourcePrincipalAtomic']=='100' and a['sourceProceedsReleasedAtomic']=='96' and a['principalRestoredAtomic']=='0'
        cases['only-actual-proceeds-released-no-principal-refund-invented']='passed'
        assert a['protectedAcquiredInventoryAtomic']=='902' and a['protectedInventoryReleasedAtomic']==a['ownedAcquiredResidualAtomic']=='0'
        cases['protected-inventory-never-released']='passed'
        assert histories(c)==history and source=={p.name:p.read_bytes() for p in c.home.iterdir() if p.is_file()}
        cases['original-admission-receipts-and-source-remain-unchanged']='passed'
        b=c.book()
        try:record=m.saved(b,c.now)
        finally:b.close()
        cap=deepcopy(record['capture']);assert len(m.encoded(record).encode())<=m.MAX_RECORD
        cases['private-raw-balance-capture-is-durable-with-closure']='passed'
        assert all(r[k] is False for k in ('fundsAvailableForNewEntry','nextCycleAuthorized','executionApproved','runtimeIntegrated','walletWideReservationsKnown','privateKeyAccessed'))
        assert 'capture' not in r and c.exit_wire not in json.dumps(r)
        cases['public-summary-is-not-new-allocation-authority']='passed'
        rpc=FakeRpc(c);again=close(c,rpc)
        assert not rpc.requests and not again['appliedThisRun'] and again['recordSha256']==r['recordSha256'] and c.path.read_bytes()==closed
        cases['idempotent-recovery-never-recollects-or-releases-twice']='passed'
        c.now+=30000;(c.home/'STOP').touch(mode=0o600)
        assert status(c)['recordSha256']==r['recordSha256'] and close(c)['networkRequests']==0 and c.path.read_bytes()==closed
        c.now-=30000;(c.home/'STOP').unlink()
        cases['stop-and-expiry-preserve-historical-closure']='passed'
        # Restore only disposable fixture bytes to examine failures before a close.
        c.path.write_bytes(original)
        _,rows,_=fixture_rows(c);rows[0]['lamports']+=1;rpc=FakeRpc(c,rows=rows)
        assert not close(c,rpc)['closureRecorded'] and c.path.read_bytes()==original
        cases['unexpected-wallet-credit-keeps-scoped-commitments']='passed'
        (c.home/'STOP').touch(mode=0o600);rpc=FakeRpc(c)
        assert not close(c,rpc)['closureRecorded'] and not rpc.requests
        (c.home/'STOP').unlink();cases['stop-prevents-new-closure']='passed'
        c.now+=m.balance.FRESH_MS;refuses(lambda:commit(c,cap));c.now-=m.balance.FRESH_MS
        assert c.path.read_bytes()==original
        cases['stale-capture-cannot-close']='passed'
        altered=deepcopy(cap);altered['identity']['accountingSha256']='0'*64
        refuses(lambda:commit(c,altered));assert c.path.read_bytes()==original
        cases['changed-source-identity-cannot-close']='passed'
        refuses(lambda:commit(c,r));assert c.path.read_bytes()==original
        cases['public-report-cannot-be-imported-as-release-evidence']='passed'
        insert=m._insert
        def fault(book,record):insert(book,record);raise OSError('simulated storage fault')
        with patch.object(m,'_insert',fault):
            try:commit(c,cap)
            except OSError:pass
            else:raise AssertionError('fault not raised')
        assert c.path.read_bytes()==original and not status(c)['closureRecorded']
        cases['storage-failure-rolls-back-record-capture-and-release']='passed'
        def stop(book,record):insert(book,record);(c.home/'STOP').touch(mode=0o600)
        with patch.object(m,'_insert',stop):refuses(lambda:commit(c,cap))
        (c.home/'STOP').unlink();assert c.path.read_bytes()==original
        cases['stop-before-commit-rolls-back-release']='passed'
        def late(book,record):insert(book,record);c.now+=m.balance.FRESH_MS
        with patch.object(m,'_insert',late):refuses(lambda:commit(c,cap))
        c.now-=m.balance.FRESH_MS;assert c.path.read_bytes()==original
        cases['expiry-before-commit-rolls-back-release']='passed'
        c.path.write_bytes(closed);b=c.book()
        try:
            v=m.saved(b,c.now);v['settlement']['sourceProceedsReleasedAtomic']='9999'
            b.db.execute('UPDATE admission_exit_closure SET value=?,hash=?',(m.encoded(v),m.digest(v)))
        finally:b.close()
        refuses(lambda:status(c));cases['rehashing-false-release-arithmetic-cannot-pass-replay']='passed'
        c.path.write_bytes(closed);b=c.book()
        try:
            v=m.saved(b,c.now);v['capture']['evidence']['accounts']['result']['value'][0]['lamports']+=1
            b.db.execute('UPDATE admission_exit_closure SET value=?,hash=?',(m.encoded(v),m.digest(v)))
        finally:b.close()
        refuses(lambda:status(c));cases['rehashing-false-raw-balances-cannot-pass-replay']='passed'
    with signed_case() as c:
        p,_=package(c);collect_receipt(c,failed(p));apply(c);rpc=FakeRpc(c)
        before=c.path.read_bytes();r=close(c,rpc)
        assert not r['closureRecorded'] and not rpc.requests and c.path.read_bytes()==before
        cases['failed-exit-with-owned-inventory-cannot-close']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,realNetworkRequests=0,privateKeyAccessed=False,
        signaturesCreated=0,transactionsSent=0,temporaryLedgersRemoved=True,
        syntheticScopedClosureExercised=True,productionLedgerUpdated=False,productionReservationsReleased=False,
        fundsAvailableForNewEntry=False,walletWideReservationsKnown=False,nextCycleAuthorized=False,
        executionApproved=False,runtimeIntegrated=False)
