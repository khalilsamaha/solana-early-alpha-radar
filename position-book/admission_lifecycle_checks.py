"""Portable lifecycle checks; public signatures, synthetic RPC and disposable journals."""
import json
from unittest.mock import patch

import admission_lifecycle as m
from admission_submission_checks import case,FakeOpener
from entry_accounting_checks import collect as entry_collect,apply as entry_apply
from exit_balance_checks import signed_case,collect_receipt,apply,FakeRpc
from exit_accounting_checks import package,ReceiptRpc
from exit_submission_checks import submit,recover
from admission_receipt_checks import failed
from exit_closure_checks import close


def inspect(c):
    return m.inspect(c.home,c.wallet,c.pool,clock=lambda:c.now,monotonic=lambda:0)


def run():
    cases={}
    with case() as c,patch.object(m.view,'read_locked',return_value=None) as read:
        read.return_value=c.e['costInputs']['reservations']
        r=inspect(c);a=r['scopedAccounting']
        assert r['coherent'] and r['phase']=='entry-not-submitted'
        cases['signed-entry-without-send-remains-reserved']='passed'
        assert a['ownedAcquiredHeldAtomic'] is None and a['feePaidLamports'] is None and a['sourcePrincipalSpentAtomic'] is None
        cases['unsettled-quantities-remain-unknown-not-zero']='passed'
        assert r['originalAdmission']['principalAtomic']==a['sourcePrincipalHeldAtomic']=='100'
        assert a['feeHeldLamports']=='26000' and 'not-extra-holds' in r['originalAdmission']['basis']
        cases['original-caps-are-separate-from-current-scoped-holds']='passed'
        c.submit(FakeOpener(c));r=inspect(c)
        assert r['phase']=='entry-unresolved' and r['scopedAccounting']['ownedAcquiredHeldAtomic'] is None
        cases['send-acknowledgment-does-not-settle-entry']='passed'
        c.recover(FakeOpener(c));r=inspect(c)
        assert r['phase']=='entry-receipt-awaiting-accounting' and r['scopedAccounting']['feeHeldLamports']=='26000'
        cases['raw-entry-receipt-does-not-pretend-accounting-was-applied']='passed'
        entry_apply(c);r=inspect(c);a=r['scopedAccounting']
        assert r['phase']=='entry-open' and a['sourcePrincipalHeldAtomic']=='0' and a['ownedAcquiredHeldAtomic']=='98'
        assert a['feePaidLamports']=='5001' and a['feeHeldLamports']=='20999'
        cases['settled-entry-reports-owned-delta-and-remaining-fees']='passed'
        before=c.path.read_bytes();c.now+=30000;(c.home/'STOP').touch(mode=0o600);r=inspect(c)
        assert r['phase']=='entry-open' and r['stopRequested'] and r['admissionEvidenceExpired']
        assert r['scopedAccounting']==a and c.path.read_bytes()==before
        cases['stop-and-expiry-do-not-erase-entry-holds']='passed'
        b=c.book()
        try:b.db.execute('CREATE TABLE admission_future_unknown (value TEXT)')
        finally:b.close()
        r=inspect(c);assert not r['coherent'] and r['scopedAccounting'] is None
        cases['unrecognized-stage-schema-is-unavailable-not-ignored']='passed'
    with case() as c,patch.object(m.view,'read_locked',return_value=None) as read:
        read.return_value=c.e['costInputs']['reservations'];entry_collect(c,failed(c.package));entry_apply(c)
        r=inspect(c);a=r['scopedAccounting']
        assert r['phase']=='entry-failed-held' and a['sourcePrincipalHeldAtomic']=='100' and a['ownedAcquiredHeldAtomic']=='0' and a['feeHeldLamports']=='20999'
        cases['failed-entry-preserves-principal-and-unused-fees']='passed'
    with signed_case() as c:
        r=inspect(c);assert r['phase']=='exit-signed-not-submitted' and r['scopedAccounting']['ownedAcquiredHeldAtomic']=='98'
        cases['signed-exit-still-holds-owned-inventory']='passed'
        submit(c);r=inspect(c);assert r['phase']=='exit-unresolved' and r['scopedAccounting']['feeHeldLamports']=='20999'
        cases['exit-send-acknowledgment-keeps-entry-commitments']='passed'
        p,_=package(c);recover(c,ReceiptRpc(c,p));r=inspect(c)
        assert r['phase']=='exit-receipt-awaiting-accounting' and r['scopedAccounting']['ownedAcquiredHeldAtomic']=='98'
        cases['raw-exit-receipt-awaits-durable-accounting']='passed'
        apply(c);r=inspect(c);a=r['scopedAccounting']
        assert r['phase']=='exit-position-flat-held' and a['ownedAcquiredHeldAtomic']=='0' and a['sourceProceedsHeldAtomic']=='96'
        assert a['feeHeldLamports']=='15998' and a['sourceProceedsReleasedAtomic']=='0'
        cases['flat-exit-retains-fees-and-proceeds-until-closure']='passed'
        close(c);r=inspect(c);a=r['scopedAccounting'];before=c.path.read_bytes()
        assert r['phase']=='closed' and a['scopedClosureRecorded'] and a['sourceProceedsHeldAtomic']==a['feeHeldLamports']=='0'
        cases['verified-closure-supersedes-holds-with-scoped-releases']='passed'
        assert int(r['originalAdmission']['feeCommitmentLamports'])==sum(int(a[k]) for k in ('feePaidLamports','feeHeldLamports','unusedFeeReleasedLamports'))
        cases['paid-held-and-released-fees-conserve-original-budget']='passed'
        assert a['sourceProceedsReleasedAtomic']=='96' and a['sourcePrincipalSpentAtomic']=='100' and a['sourcePrincipalHeldAtomic']=='0'
        cases['proceeds-never-double-count-original-principal']='passed'
        assert a['protectedAcquiredInventoryAtomic']=='902' and a['protectedInventoryReleasedAtomic']=='0'
        cases['protected-inventory-stays-outside-released-allocation']='passed'
        assert all(r[k] is False for k in ('fundsAvailableForNewEntry','nextCycleAuthorized','executionApproved','runtimeIntegrated','walletWideReservationsKnown','reservationsReleasedThisRun','privateKeyAccessed'))
        assert c.exit_wire not in json.dumps(r) and 'rpcEvidence' not in json.dumps(r)
        cases['public-lifecycle-is-not-execution-or-new-allocation-authority']='passed'
        again=inspect(c);assert again==r and c.path.read_bytes()==before
        cases['repeated-inspection-preserves-bytes-and-stable-identities']='passed'
        c.now+=30000;(c.home/'STOP').touch(mode=0o600);r=inspect(c)
        assert r['phase']=='closed' and r['stopRequested'] and r['scopedAccounting']==a and c.path.read_bytes()==before
        cases['stopped-historical-closure-remains-visible-without-current-balance-claim']='passed'
        c.now-=30000;(c.home/'STOP').unlink();b=c.book()
        try:
            v=m.closure.saved(b,c.now);v['settlement']['unusedFeeReleasedLamports']='0'
            b.db.execute('UPDATE admission_exit_closure SET value=?,hash=?',(m.closure.encoded(v),m.closure.digest(v)))
        finally:b.close()
        tampered=c.path.read_bytes();r=inspect(c)
        assert not r['coherent'] and r['scopedAccounting'] is None and c.path.read_bytes()==tampered
        cases['rehashed-closure-conflict-suppresses-all-current-amounts']='passed'
        c.path.write_bytes(before);b=c.book()
        try:b.db.execute('DROP TABLE admission_exit_accounting')
        finally:b.close()
        r=inspect(c);assert not r['coherent'] and r['scopedAccounting'] is None
        cases['orphan-closure-cannot-report-released-money']='passed'
    with signed_case() as c:
        p,_=package(c);collect_receipt(c,failed(p));apply(c);r=inspect(c);a=r['scopedAccounting']
        assert r['phase']=='exit-failed-inventory-held' and a['ownedAcquiredHeldAtomic']=='98' and a['sourceProceedsReleasedAtomic']=='0'
        cases['failed-exit-keeps-owned-inventory-and-records-only-fees']='passed'
        c.path.unlink();r=inspect(c);assert not r['coherent'] and r['scopedAccounting'] is None and not c.path.exists()
        cases['missing-ledger-does-not-create-empty-or-zero-state']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,realNetworkRequests=0,privateKeyAccessed=False,
        signaturesCreated=0,transactionsSent=0,temporaryLedgersRemoved=True,
        lifecycleInspectionReadOnly=True,productionLedgerUpdated=False,productionReservationsReleased=False,
        fundsAvailableForNewEntry=False,walletWideReservationsKnown=False,nextCycleAuthorized=False,
        executionApproved=False,runtimeIntegrated=False)
