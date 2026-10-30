"""Portable same-ledger settlement checks. Fixtures only; no keys or network."""
from copy import deepcopy
import json

import entry_accounting as m
from admission_submission_checks import case, FakeOpener, refuses
from admission_receipt_checks import failed


def apply(c):return m.apply(c.home,c.wallet,c.pool,clock=lambda:c.now)
def status(c):return m.status(c.home,c.wallet,c.pool,clock=lambda:c.now)
def collect(c,package=None):
    c.submit(FakeOpener(c));c.recover(FakeOpener(c,package=package))


def run():
    cases={}
    with case() as c:
        raw=c.path.read_bytes();r=apply(c)
        assert r['state']=='entry-accounting-pending' and not r['accountingRecorded']
        assert c.path.read_bytes()==raw
        cases['no-boundary-no-accounting-or-new-allocation']='passed'
        c.submit(FakeOpener(c));raw=c.path.read_bytes()
        assert not apply(c)['accountingUsable'] and c.path.read_bytes()==raw
        cases['send-acknowledgment-is-not-a-receipt']='passed'
        c.recover(FakeOpener(c));b=c.book()
        try:original=b.status()
        finally:b.close()
        source={p.name:p.read_bytes() for p in c.home.iterdir()}
        r=apply(c);a=r['accounting']
        assert r['state']=='entry-position-open' and r['appliedThisRun']
        assert (a['sourcePrincipalSpentAtomic'],a['sourcePrincipalHeldAtomic'],a['ownedAcquiredAtomic'])==('100','0','98')
        cases['collected-success-owns-only-acquired-delta']='passed'
        assert (a['originalFeeCommitmentLamports'],a['entryFeePaidLamports'],a['feeCommitmentRemainingLamports'])==('26000','5001','20999')
        assert (a['exitAttemptFeeHeldLamports'],a['unusedEntryFeeHeldLamports'])==('20000','999')
        cases['actual-paid-fee-and-held-exit-budget-conserve-commitment']='passed'
        raw=c.path.read_bytes();again=apply(c)
        assert not again['appliedThisRun'] and again['recordSha256']==r['recordSha256'] and c.path.read_bytes()==raw
        cases['repeated-application-never-double-counts']='passed'
        assert status(c)['accounting']==a and c.path.read_bytes()==raw
        cases['read-only-status-replays-receipt-without-writing']='passed'
        b=c.book()
        try:assert b.status()==original
        finally:b.close()
        assert {p.name:p.read_bytes() for p in c.home.iterdir()}==source
        assert len(list(c.path.parent.glob('*.sqlite')))==1
        cases['original-admission-and-historical-source-remain-unchanged']='passed'
        assert all(r[k] is False for k in ('allocationTransferred','reservationReleased','fundsAvailableForNewEntry','exitPreparationIntegrated','currentWalletBalanceEstablished','walletWideReservationsKnown','executionApproved','runtimeIntegrated'))
        cases['accounting-does-not-authorize-release-exit-or-new-entry']='passed'
        assert c.signed['signedTransactionBase64'] not in json.dumps(r) and 'rpcEvidence' not in json.dumps(r)
        cases['public-output-excludes-wire-and-raw-evidence']='passed'
    with case() as c:
        collect(c,failed(c.package));r=apply(c);a=r['accounting']
        assert r['state']=='entry-failed-held'
        assert (a['sourcePrincipalSpentAtomic'],a['sourcePrincipalHeldAtomic'],a['ownedAcquiredAtomic'],a['entryFeePaidLamports'])==('0','100','0','5001')
        assert a['feeCommitmentRemainingLamports']=='20999' and not r['fundsAvailableForNewEntry']
        cases['failed-entry-keeps-principal-and-unused-fees-held']='passed'
    with case() as c:
        m.submission.receipts.observe(c.home,c.wallet,c.pool,c.package,clock=lambda:c.now)
        assert not apply(c)['accountingRecorded']
        cases['imported-receipt-without-collector-provenance-cannot-settle']='passed'
    with case() as c:
        c.submit(FakeOpener(c,lost=True));p=deepcopy(c.package)
        p['bundle']['rpcEvidence']['transaction']['result']=None
        c.recover(FakeOpener(c,package=p))
        assert not apply(c)['accountingRecorded']
        cases['missing-receipt-keeps-unknown-exposure']='passed'
        c.now+=30000;(c.home/'STOP').touch(mode=0o600)
        c.recover(FakeOpener(c));r=apply(c)
        assert r['stopRequested'] and r['state']=='entry-position-open'
        cases['stop-and-expiry-do-not-hide-existing-receipt-effects']='passed'
    with case() as c:
        c.submit(FakeOpener(c,send=c.wallet));r=apply(c)
        assert r['state']=='quarantined' and not r['accountingRecorded']
        cases['quarantined-source-cannot-create-usable-accounting']='passed'
    with case() as c:
        collect(c);apply(c);b=c.book()
        try:b.db.execute("UPDATE admission_entry_accounting SET hash='changed'")
        finally:b.close()
        refuses(lambda:apply(c));refuses(lambda:status(c))
        cases['changed-record-refused-on-read-and-apply']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,temporaryLedgersRemoved=True,networkRequests=0,
        signaturesCreated=0,transactionsSent=0,privateKeyAccessed=False,productionLedgerUpdated=False,
        allocationTransferred=False,reservationReleased=False,exitPreparationIntegrated=False,
        runtimeIntegrated=False,executionApproved=False,nextCycleAuthorized=False)
