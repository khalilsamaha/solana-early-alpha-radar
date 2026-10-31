"""Reconcile collected exit effects in the admission ledger; keep all funds held.

No RPC, signer, sender, imported report, current-balance claim or allocation release.
"""
from copy import deepcopy
import json
import exit_submission as submission
import entry_accounting as entry
import admission_receipt as receipt
from contract import digest, fields, atomic, uint, TOKEN
from core import check
from journal import read_only_journals
from pre_sign_admission import encoded
from state import token,mint
from wire import parse
from reconcile import validate_intent

VERSION='admission-exit-accounting-1'
TABLE='admission_exit_accounting'
MAX_RECORD=16384
view=submission.view


def private_intent(book,signing,prepared):
    packet=signing['request']['packet'];scope=submission.handoff.preparation.scope_for(packet['policy'])
    c=prepared['evidence']['capture'];roles=scope['accounts']
    rows=dict(zip(c['accountKeys'],c['evidence']['accounts']['result']['value']))
    def side(account_role,mint_role):
        t=token(rows[roles[account_role]],roles[mint_role],roles['wallet']);m=mint(rows[roles[mint_role]])
        return dict(account=roles[account_role],mint=roles[mint_role],programId=TOKEN,decimals=m['decimals'],preAmountAtomic=t['amount'],lifecycle='existing')
    intent=dict(format='transaction-intent-1',network='devnet',wallet=roles['wallet'],
        signature=signing['signed']['signature'],messageSha256=parse(packet['unsignedTransactionBase64'])[5],
        preparedAtMs=packet['policy']['issuedAtMs'],walletPreLamports=str(rows[roles['wallet']]['lamports']),
        source=side('source','inputMint'),destination=side('destination','outputMint'),
        inputAtomic=scope['amountIn'],minimumOutputAtomic=scope['minimumAmountOut'],
        maximumFeeLamports=signing['request']['feeCapLamports'],maximumRentLamports='0')
    validate_intent(intent)
    return dict(intent=intent,signedTransactionBase64=signing['signed']['signedWireBase64'],wireSha256=signing['signed']['wireSha256']),scope


def derive(opened,prepared,boundary,summary,private,policy):
    """Conservation after raw receipt validation, not a spendable-balance projection."""
    a=opened['accounting'];intent=private['intent'];b=prepared['binding']
    source=summary['tokenAccounts']['source'];destination=summary['tokenAccounts']['destination'];native=summary['native']
    quantity=atomic(a['ownedAcquiredAtomic'],'exit-owned-quantity',positive=True)
    check(quantity==int(b['quantityAtomic'])==int(intent['inputAtomic']),'exit-owned-quantity')
    for name,t in (('source',source),('destination',destination)):
        check(t['lifecycle']=='existing' and t['preAtomic']==intent[name]['preAmountAtomic'],'exit-receipt-prebalance')
        check(int(t['postAtomic'])-int(t['preAtomic'])==int(t['deltaAtomic']),'exit-token-conservation')
    success=summary['state']=='signed-token-accounting-consistent'
    check(success or summary['state']=='finalized-failure-fee-only','exit-receipt-outcome')
    spent=-int(source['deltaAtomic']);returned=int(destination['deltaAtomic'])
    check(spent==(quantity if success else 0),'exit-exact-owned-spend')
    check((success and returned>=int(intent['minimumOutputAtomic'])>0) or (not success and returned==0),'exit-returned-quantity')
    protected=int(b['protectedInventoryAtomic']);residual=quantity-spent
    check(int(source['preAtomic'])==protected+quantity and int(source['postAtomic'])==protected+residual,'exit-protected-inventory')
    cap=int(b['feeCapLamports']);fee=atomic(native['feeLamports'],'exit-paid-fee',positive=True)
    check(fee<=cap and native['rentSpentLamports']==native['rentRefundedLamports']=='0' and int(native['walletDeltaLamports'])==-fee,'exit-native-conservation')
    original=int(a['originalFeeCommitmentLamports']);entry_fee=int(a['entryFeePaidLamports']);held=int(a['feeCommitmentRemainingLamports'])
    check(original==entry_fee+held and held>=fee and held>=int(a['exitAttemptFeeHeldLamports']),'exit-fee-conservation')
    attempts=a['maximumExitAttempts'];uint(attempts,3,'exit-attempt-budget',minimum=1)
    attempt_cap=int(policy['maximumExitFeeLamports']);check(cap<=attempt_cap and int(a['exitAttemptFeeHeldLamports'])==attempts*attempt_cap,'exit-attempt-budget')
    remaining_attempts=(attempts-1)*attempt_cap;unused_exit=attempt_cap-fee;unused_entry=int(a['unusedEntryFeeHeldLamports'])
    remaining=held-fee;check(remaining==remaining_attempts+unused_exit+unused_entry,'exit-fee-held-partition')
    return dict(format=VERSION,allocationId=a['allocationId'],owner='same-admission-ledger',
        entryAccountingSha256=digest(opened),preparationSha256=digest(prepared),submissionBoundarySha256=digest(boundary),
        receiptIdentity=digest(summary),wireSha256=private['wireSha256'],receiptSlot=summary['slot'],
        state='exit-position-flat-held' if success else 'exit-failed-inventory-held',wallet=a['wallet'],
        acquiredAccount=a['acquiredAccount'],acquiredMint=a['acquiredMint'],sourceAccount=a['sourceAccount'],sourceMint=a['sourceMint'],
        originalSourcePrincipalAtomic=a['originalPrincipalAtomic'],ownedAcquiredBeforeAtomic=str(quantity),
        acquiredSpentAtomic=str(spent),ownedAcquiredResidualAtomic=str(residual),protectedAcquiredInventoryAtomic=str(protected),
        sourceProceedsHeldAtomic=str(returned),sourceProceedsMinusEntryPrincipalAtomic=str(returned-int(a['sourcePrincipalSpentAtomic'])) if success else None,
        observedAcquiredAccountPostAtomic=source['postAtomic'],observedSourceAccountPostAtomic=destination['postAtomic'],
        originalFeeCommitmentLamports=str(original),entryFeePaidLamports=str(entry_fee),exitFeePaidLamports=str(fee),
        totalFeePaidLamports=str(entry_fee+fee),feeCommitmentRemainingLamports=str(remaining),
        remainingAttemptFeeHeldLamports=str(remaining_attempts),unusedExitFeeHeldLamports=str(unused_exit),unusedEntryFeeHeldLamports=str(unused_entry),
        exitAttemptsConsumed=1,maximumExitAttempts=attempts)


def review(book):
    t=submission.ExitSubmission(book);status=t.status();now=book.j.now()
    result=dict(state='exit-accounting-pending',accounting=None,evidenceAtMs=0,captureSha256=None,transportState=status['state'])
    if status['state']=='quarantined':result['state']='quarantined';return result
    if not status['applicationSendBoundaryRecorded']:return result
    signing=t.signing();prepared=submission.handoff.preparation.saved(book,now);opened=entry.saved(book.db,now)
    check(opened is not None,'exit-entry-accounting-required')
    private,scope=private_intent(book,signing,prepared);boundary=t.boundary();minimum=submission.proof_check(boundary['preflight'],signing)
    for c in t.captures():
        kind,_=submission.classify(c,signing,minimum)
        if kind=='quarantined':result.update(state='quarantined',accounting=None);return result
        if kind not in submission.TERMINAL:continue
        normalized,package=submission.transport.normalized_package(c,private,minimum)
        if normalized=='quarantined':result.update(state='quarantined',accounting=None);return result
        if package is None:continue
        try:kind,summary=receipt.evaluate(package,private,boundary['atMs'],now,scope)
        except ValueError as exc:
            if str(exc)=='node-runtime-unavailable':raise
            result.update(state='quarantined',accounting=None);return result
        if kind=='quarantined':result.update(state='quarantined',accounting=None);return result
        if kind not in receipt.TERMINAL.values():continue
        try:a=derive(opened,prepared,boundary,summary,private,book.policy)
        except ValueError:result.update(state='quarantined',accounting=None);return result
        if result['accounting'] is not None:
            if result['accounting']!=a:result.update(state='quarantined',accounting=None);return result
            continue
        result.update(state=a['state'],accounting=a,evidenceAtMs=c['finishedAtMs'],captureSha256=digest(c))
    return result


def saved(db,now):
    found=db.execute('SELECT type FROM sqlite_master WHERE name=?',(TABLE,)).fetchone()
    if not found:return None
    check(found[0]=='table','exit-accounting-table')
    rows=db.execute('SELECT id,CASE WHEN length(value)<=? THEN value ELSE NULL END value,hash FROM admission_exit_accounting LIMIT 2',(MAX_RECORD,)).fetchall()
    check(len(rows)==1 and rows[0]['id']==1 and type(rows[0]['value']) is str,'exit-accounting-row')
    v=json.loads(rows[0]['value']);fields(v,{'format','recordedAtMs','captureSha256','accounting'},'exit-accounting-schema')
    check(v['format']==VERSION+'-record' and encoded(v)==rows[0]['value'] and digest(v)==rows[0]['hash'],'exit-accounting-integrity')
    uint(v['recordedAtMs'],now,'exit-accounting-clock',minimum=1);return v


def public(source,record,*,applied=False,stop=False):
    usable=record is not None and source['accounting'] is not None and source['state']!='quarantined'
    if record is not None and source['state']!='quarantined':
        check(source['accounting']==record['accounting'] and source['captureSha256']==record['captureSha256'],'exit-accounting-source-conflict')
        check(record['recordedAtMs']>=source['evidenceAtMs'],'exit-accounting-before-evidence')
    return dict(format=VERSION,state=source['state'] if usable or source['state']=='quarantined' else 'exit-accounting-pending',
        accountingRecorded=record is not None,accountingUsable=usable,appliedThisRun=applied,stopRequested=stop,
        recordSha256=None if record is None else digest(record),accounting=deepcopy(record['accounting']) if usable else None,
        receiptEffectsReconciled=usable,receiptResidualAccounted=usable,currentWalletBalanceEstablished=False,
        reservationReleased=False,allocationTransferred=False,fundsAvailableForNewEntry=False,walletWideReservationsKnown=False,
        nextCycleAuthorized=False,automaticRetryAllowed=False,runtimeIntegrated=False,executionApproved=False,
        networkRequests=0,signaturesCreated=0,transactionsSent=0,privateKeyAccessed=False,
        basis='Historical exact-wire RPC receipt effects; balances and fees remain scoped and held, not current spendability or economic profitability')


def status(home,wallet,pool,*,clock=view.now):
    with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
        b=submission.transport._open(root,wallet,pool,clock)
        try:return public(review(b),saved(b.db,b.j.now()),stop=submission.handoff.stopped(root,b))
        finally:b.close()


def apply(home,wallet,pool,*,clock=view.now):
    with view.cycles.c.source_lock(home,wallet) as root:
        b=submission.transport._open(root,wallet,pool,clock)
        try:
            with b.j.transaction():
                with read_only_journals():
                    reader=submission.transport._open(root,wallet,pool,clock)
                    try:source=review(reader)
                    finally:reader.close()
                now=b.j.now();check(now>=source['evidenceAtMs'],'exit-accounting-clock')
                record=saved(b.db,now);applied=False
                if record is None and source['accounting'] is not None:
                    record=dict(format=VERSION+'-record',recordedAtMs=now,captureSha256=source['captureSha256'],accounting=source['accounting'])
                    check(len(encoded(record).encode())<=MAX_RECORD,'exit-accounting-cap')
                    b.db.execute('CREATE TABLE admission_exit_accounting (id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL,hash TEXT NOT NULL)')
                    b.db.execute('INSERT INTO admission_exit_accounting VALUES(1,?,?)',(encoded(record),digest(record)))
                    check(b.db.execute('PRAGMA page_count').fetchone()[0]*b.db.execute('PRAGMA page_size').fetchone()[0]<=64*1024*1024,'exit-ledger-size-cap')
                    applied=True
                result=public(source,record,applied=applied,stop=submission.handoff.stopped(root,b))
            return result
        finally:b.close()
