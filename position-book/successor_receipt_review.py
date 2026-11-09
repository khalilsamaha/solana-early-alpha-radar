"""Read-only successor receipt effects; no durable accounting or closure.

Replay the exact generation and raw receipt in one snapshot. Keep the retired
attempt's unresolved fee exposure separate from this generation's known fee.
No RPC, signing, imported reports, journal writes or reservation release.
"""
from copy import deepcopy
import json

import successor_submission as submission
import exit_accounting as original
from contract import atomic, digest
from core import check
from journal import read_only_journals

VERSION = 'successor-receipt-review-1'


def effects(opened, record, retired, summary, private, policy):
    a = opened['accounting']; b = record['candidate']['binding']
    intent = private['intent']; source = summary['tokenAccounts']['source']
    destination = summary['tokenAccounts']['destination']; native = summary['native']
    quantity = atomic(a['ownedAcquiredAtomic'], 'successor-receipt-owned', positive=True)
    check(quantity == int(b['quantityAtomic']) == int(intent['inputAtomic']), 'successor-receipt-owned')
    success = summary['state'] == 'signed-token-accounting-consistent'
    check(success or summary['state'] == 'finalized-failure-fee-only', 'successor-receipt-outcome')
    for name, side in (('source', source), ('destination', destination)):
        check(side['lifecycle'] == 'existing' and side['preAtomic'] == intent[name]['preAmountAtomic'],
              'successor-receipt-prebalance')
        check(int(side['postAtomic']) - int(side['preAtomic']) == int(side['deltaAtomic']),
              'successor-receipt-conservation')
    spent = -int(source['deltaAtomic']); returned = int(destination['deltaAtomic'])
    check(spent == (quantity if success else 0), 'successor-receipt-exact-spend')
    check((success and returned >= int(intent['minimumOutputAtomic']) > 0) or
          (not success and returned == 0), 'successor-receipt-output')
    protected = int(b['protectedInventoryAtomic']); residual = quantity - spent
    check(int(source['preAtomic']) == protected + quantity and
          int(source['postAtomic']) == protected + residual, 'successor-receipt-protected')
    fee = atomic(native['feeLamports'], 'successor-receipt-fee', positive=True)
    cap = int(b['feeCapLamports'])
    check(fee <= cap <= int(policy['maximumExitFeeLamports']) and
          native['rentSpentLamports'] == native['rentRefundedLamports'] == '0' and
          int(native['walletDeltaLamports']) == -fee, 'successor-receipt-native')
    held = int(a['feeCommitmentRemainingLamports']); entry_fee = int(a['entryFeePaidLamports'])
    exposure = int(b['retiredFeeExposureHeldLamports']); other = int(b['otherHeldFeeLamports'])
    check(b['additionalFeeReservationLamports'] == '0' and exposure > 0 and
          exposure + other == held == int(b['feeCommitmentRemainingLamports']) and other >= cap,
          'successor-receipt-held-partition')
    check(int(a['originalFeeCommitmentLamports']) == entry_fee + held,
          'successor-receipt-fee-conservation')
    check(b['attemptNumber'] == b['attemptsConsumed'] + 1 <= a['maximumExitAttempts'],
          'successor-receipt-attempt-budget')
    check(b['retirementSha256'] == record['retirementSha256'] == digest(retired),
          'successor-receipt-retirement')
    return dict(successorSha256=digest(record), retirementSha256=digest(retired),
        entryAccountingSha256=digest(opened), receiptIdentity=digest(summary),
        wireSha256=private['wireSha256'], receiptSlot=summary['slot'],
        state='successor-effects-observed-held' if success else 'successor-failure-effects-observed-held',
        ownedAcquiredBeforeAtomic=str(quantity), acquiredSpentAtomic=str(spent),
        ownedAcquiredResidualAtomic=str(residual), protectedAcquiredInventoryAtomic=str(protected),
        sourceProceedsObservedAtomic=str(returned), successorFeePaidLamports=str(fee),
        knownFeesPaidLamports=str(entry_fee + fee), retiredFeeExposureHeldLamports=str(exposure),
        journalFeeHeldLamports=str(held), projectedFeeHoldAfterKnownFeesLamports=str(held - fee),
        projectedOtherFeeHeldLamports=str(other - fee), attemptNumber=b['attemptNumber'])


def review(root, book, wallet, pool, expected, clock):
    """Caller owns the source lock and one read-only snapshot."""
    record, _, retired, signed, saved = submission.load(root, book, wallet, pool, expected, clock)
    result = dict(format=VERSION, state='successor-receipt-pending-held', successorSha256=digest(record),
        transportState='not-attempted' if saved is None else saved['state'], effects=None,
        receiptEffectsValidated=False, accountingApplied=False, receiptEffectsReconciled=False,
        scopedClosureRecorded=False, currentWalletBalanceEstablished=False,
        retiredAttemptNonExecutionProven=False, sourceStateChanged=False,
        reservationsReleased=False, fundsAvailableForNewEntry=False, nextCycleAuthorized=False,
        executionApproved=False, networkRequests=0, privateKeyAccessed=False,
        signaturesCreated=0, transactionsSent=0,
        basis='Exact-generation historical RPC effects only; projected fee changes are not applied to the ledger.')
    if saved is None: return result
    if saved['state'] == 'quarantined':
        result['state'] = 'quarantined'; return result
    opened = original.entry.saved(book.db, clock())
    check(opened is not None, 'successor-receipt-entry-required')
    private, scope = original.private_intent(book, signed, record['candidate'])
    minimum = submission.original.proof_check(saved['boundary']['preflight'], signed)
    # Finish times live in the authenticated event envelope, not the capture value.
    rows = book.db.execute('SELECT at_ms,value FROM admission_successor_transport ORDER BY seq').fetchall()
    captured = [(r['at_ms'], json.loads(r['value'])) for r in rows]
    check([v for _, v in captured if v.get('kind') == 'capture'] == saved['captures'],
          'successor-receipt-snapshot')
    boundary_at = captured[0][0]
    for finished, capture in captured:
        if capture.get('kind') != 'capture': continue
        try:
            kind, _ = submission.original.classify(capture, signed, minimum)
            if kind == 'quarantined': raise ValueError('successor-receipt-conflict')
            if kind not in submission.original.TERMINAL: continue
            normalized, package = submission.transport.normalized_package(
                dict(capture, finishedAtMs=finished), private, minimum)
            if normalized == 'quarantined': raise ValueError('successor-receipt-conflict')
            if package is None: continue
            kind, summary = original.receipt.evaluate(package, private, boundary_at, clock(), scope)
            if kind == 'quarantined': raise ValueError('successor-receipt-conflict')
            if kind not in original.receipt.TERMINAL.values(): continue
            observed = effects(opened, record, retired, summary, private, book.policy)
            if result['effects'] is not None and result['effects'] != observed:
                raise ValueError('successor-receipt-conflicting-effects')
            result.update(state=observed['state'], effects=deepcopy(observed), receiptEffectsValidated=True)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            if str(exc) == 'node-runtime-unavailable': raise
            result.update(state='quarantined', effects=None, receiptEffectsValidated=False)
            return result
    return result


@submission.handoff.view.cycles.binding.operation
@submission.handoff.successor.history.fresh_signing.timing.signature_replay
def status(home, wallet, pool, expected, *, clock=submission.handoff.view.now):
    with submission.handoff.view.cycles.c.source_lock(home, wallet) as root, read_only_journals():
        book = submission.transport._open(root, wallet, pool, clock)
        try:
            with submission.original.ExitSubmission(book).snapshot():
                return review(root, book, wallet, pool, expected, clock)
        finally:
            book.close()
