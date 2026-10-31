"""Same-ledger entry settlement from collected receipts; no new allocation.

Original admission commitments remain immutable history. This ledger owns the
acquired delta and separates paid fees from retained commitments. Nothing is
released for reuse, no exit is enabled, and wallet-wide ownership is not implied.
"""
from copy import deepcopy
import json

import admission_submission as submission
from pre_sign_admission import Admission, encoded
from contract import digest, fields, atomic, uint
from core import check
from journal import read_only_journals

VERSION='admission-entry-accounting-1'
TABLE='admission_entry_accounting'
MAX_RECORD=8192


def derive(private, reservation, summary, boundary, policy):
    """Accounting arithmetic only; caller must replay the collected raw receipt."""
    intent=private['intent'];tokens=summary['tokenAccounts'];native=summary['native']
    principal=atomic(reservation['reservedPrincipalAtomic'],'entry-principal',positive=True)
    fee_budget=atomic(reservation['reservedFeeLamports'],'entry-fee-budget',positive=True)
    fee_cap=atomic(reservation['entryFeeCapLamports'],'entry-fee-cap',positive=True)
    exit_fee=atomic(reservation['exitFeeCapLamports'],'exit-fee-cap',positive=True)
    attempts=reservation['maximumExitAttempts'];uint(attempts,3,'exit-attempt-cap',minimum=1)
    check(attempts==policy['maximumExitAttempts'] and
          fee_budget==fee_cap+exit_fee*attempts and
          fee_budget<=int(policy['maximumTotalFeeLamports']), 'entry-budget-conservation')
    fee=atomic(native['feeLamports'],'observed-entry-fee',positive=True)
    check(fee<=fee_cap and native['rentSpentLamports']==native['rentRefundedLamports']=='0' and
          int(native['walletDeltaLamports'])==-fee,'entry-native-conservation')
    source=tokens['source'];destination=tokens['destination']
    for side in ('source','destination'):
        t=tokens[side]
        check(t['lifecycle']=='existing' and t['preAtomic']==intent[side]['preAmountAtomic'], 'entry-token-prebalance')
        check(atomic(t['postAtomic'],'entry-token-post')-atomic(t['preAtomic'],'entry-token-pre')==int(t['deltaAtomic']), 'entry-token-conservation')
    success=summary['state']=='signed-token-accounting-consistent'
    check(success or summary['state']=='finalized-failure-fee-only','entry-settlement-outcome')
    spent=-int(source['deltaAtomic']);acquired=int(destination['deltaAtomic'])
    check(principal==int(intent['inputAtomic']) and spent==(principal if success else 0), 'entry-principal-conservation')
    check((success and acquired>=int(intent['minimumOutputAtomic'])>0) or (not success and acquired==0), 'entry-acquired-quantity')
    return dict(format=VERSION, allocationId=private['id'], owner='same-admission-ledger',
        handoffSha256=reservation['accountingHandoffSha256'], policySha256=digest(policy),
        submissionBoundarySha256=digest(boundary), receiptIdentity=digest(summary),
        wireSha256=private['wireSha256'], receiptSlot=summary['slot'],
        wallet=intent['wallet'], sourceAccount=intent['source']['account'], sourceMint=intent['source']['mint'],
        acquiredAccount=intent['destination']['account'], acquiredMint=intent['destination']['mint'],
        sourceDecimals=intent['source']['decimals'], acquiredDecimals=intent['destination']['decimals'],
        state='entry-position-open' if success else 'entry-failed-held',
        originalPrincipalAtomic=str(principal), sourcePrincipalSpentAtomic=str(spent),
        sourcePrincipalHeldAtomic=str(principal-spent), ownedAcquiredAtomic=str(acquired),
        preexistingDestinationAtomic=destination['preAtomic'],
        originalFeeCommitmentLamports=str(fee_budget), entryFeePaidLamports=str(fee),
        feeCommitmentRemainingLamports=str(fee_budget-fee),
        exitAttemptFeeHeldLamports=str(exit_fee*attempts), unusedEntryFeeHeldLamports=str(fee_cap-fee),
        maximumExitAttempts=attempts, exitAttemptsConsumed=0)


def review(book):
    """Read-only evidence replay; no network, imported report or inference of zero."""
    transport=submission.Submission(book);status=transport.status()
    reservation,_,_,last=book.read()
    result=dict(transportState=status['state'], reservation=reservation,
                originalPrincipalAtomic=reservation['reservedPrincipalAtomic'],
                originalFeeCommitmentLamports=reservation['reservedFeeLamports'],
                evidenceAtMs=last, accounting=None)
    if status['state']=='quarantined':return result
    if not status['genesisBoundReceiptCollected']:return result
    private=transport.private;gate=submission.receipts.ReceiptGate(book)
    current,_,_,at=gate.read(private,transport.identity,book.j.now())
    check(current is not None and current['state'] in submission.receipts.TERMINAL.values() and
          current['terminalIdentity']==status['receiptEffects']['terminalIdentity'], 'entry-collected-receipt-required')
    result['evidenceAtMs']=at
    result['accounting']=derive(private,reservation,current['terminalSummary'],transport.boundary(),book.policy)
    return result


def saved(db,now):
    exists=db.execute("SELECT type FROM sqlite_master WHERE name=?",(TABLE,)).fetchone()
    if not exists:return None
    check(exists[0]=='table','entry-accounting-table')
    rows=db.execute('SELECT id,CASE WHEN length(value)<=? THEN value ELSE NULL END AS value,hash FROM admission_entry_accounting LIMIT 2',(MAX_RECORD,)).fetchall()
    check(len(rows)==1 and rows[0]['id']==1 and type(rows[0]['value']) is str,'entry-accounting-record')
    value=json.loads(rows[0]['value'])
    fields(value,{'format','recordedAtMs','accounting'},'entry-accounting-schema')
    check(value['format']==VERSION+'-record' and encoded(value)==rows[0]['value'] and
          digest(value)==rows[0]['hash'],'entry-accounting-integrity')
    uint(value['recordedAtMs'],now,'entry-accounting-clock',minimum=1)
    return value


def public(source,record,*,applied=False,stopped=False):
    usable=record is not None and source['accounting'] is not None and source['transportState']!='quarantined'
    if record is not None and source['transportState']!='quarantined':
        check(source['accounting'] is not None and record['accounting']==source['accounting'], 'entry-accounting-source-conflict')
        check(record['recordedAtMs']>=source['evidenceAtMs'], 'entry-accounting-before-evidence')
    state='entry-accounting-pending'
    if source['transportState']=='quarantined':state='quarantined'
    elif usable:state=record['accounting']['state']
    return dict(format=VERSION,state=state,accountingRecorded=record is not None,
        accountingUsable=usable,appliedThisRun=applied,stopRequested=stopped,
        accounting=deepcopy(record['accounting']) if usable else None,
        recordSha256=None if record is None else digest(record),
        originalPrincipalAtomic=source['originalPrincipalAtomic'],
        originalFeeCommitmentLamports=source['originalFeeCommitmentLamports'],
        allocationOwner='same-admission-ledger',allocationTransferred=False,
        reservationReleased=False,fundsAvailableForNewEntry=False,exitPreparationIntegrated=False,
        currentWalletBalanceEstablished=False,walletWideReservationsKnown=False,
        networkRequests=0,signaturesCreated=0,transactionsSent=0,privateKeyAccessed=False,
        productionLedgerUpdated=False,runtimeIntegrated=False,executionApproved=False,
        basis='Collected receipt effects within the existing scoped allocation; not current wallet solvency or net profit')


def status(home,wallet,pool,*,clock=submission.handoff.bridge.view.now):
    with submission.handoff.bridge.view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
        book=submission._open(root,wallet,pool,clock)
        try:
            source=review(book);record=saved(book.db,book.j.now())
            return public(source,record,stopped=submission.handoff.bridge.view.cycles.c.submit.swap.stop(root))
        finally:book.close()


def apply(home,wallet,pool,*,clock=submission.handoff.bridge.view.now):
    """Atomic one-time entry settlement. No new book, sender, exit or release."""
    with submission.handoff.bridge.view.cycles.c.source_lock(home,wallet) as root:
        book=submission._open(root,wallet,pool,clock)
        try:
            # BEGIN IMMEDIATE excludes other writers before the independent reader
            # checks evidence. No writes/rollback sidecar occur until that reader
            # has closed. All source replay uses read-only SQLite connections.
            with book.j.transaction():
                with read_only_journals():
                    reader=submission._open(root,wallet,pool,clock)
                    try:source=review(reader)
                    finally:reader.close()
                now=book.j.now();check(now>=source['evidenceAtMs'],'entry-accounting-clock')
                record=saved(book.db,now);applied=False
                if record is None and source['accounting'] is not None:
                    record=dict(format=VERSION+'-record',recordedAtMs=now,accounting=source['accounting'])
                    check(len(encoded(record))<=MAX_RECORD,'entry-accounting-size')
                    book.db.execute('CREATE TABLE admission_entry_accounting (id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL,hash TEXT NOT NULL)')
                    book.db.execute('INSERT INTO admission_entry_accounting VALUES(1,?,?)',(encoded(record),digest(record)))
                    applied=True
                result=public(source,record,applied=applied,
                    stopped=submission.handoff.bridge.view.cycles.c.submit.swap.stop(root))
            return result
        finally:book.close()
