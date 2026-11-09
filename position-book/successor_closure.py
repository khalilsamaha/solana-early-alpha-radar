"""Read-only successor closure contract: unresolved exposure blocks all release.

There is deliberately no successful closure state, writer or provider adapter.
Historical receipt accounting cannot establish current balances or non-execution
of the retired attempt. Unknown amounts remain None, never inferred zero.
"""
import successor_accounting as accounting
from contract import digest
from core import check
from journal import read_only_journals

VERSION = 'successor-closure-contract-1'
submission = accounting.submission
view = submission.handoff.view


def review(root, book, wallet, pool, expected, clock):
    """Caller owns source lock and a pinned query-only database snapshot."""
    check(book.db.in_transaction and book.db.execute('PRAGMA query_only').fetchone()[0] == 1,
          'successor-closure-read-snapshot-required')
    # A deferred BEGIN pins its SQLite view on the first database read. Establish
    # that view before replaying the linked histories, not merely PRAGMA state.
    candidate = submission.handoff.successor.row(book)
    check(candidate is not None and digest(candidate) == expected, 'successor-closure-identity')
    source = accounting.replay(root, book, wallet, pool, expected, clock)
    check(book.db.execute("SELECT 1 FROM sqlite_master WHERE name='admission_exit_closure'").fetchone() is None,
          'successor-closure-legacy-record-conflict')
    result = dict(format=VERSION, state='successor-closure-blocked-held',
        accountingState=source['state'], accountingUsable=source['accountingUsable'],
        identity=dict(successorSha256=expected, retiredPreparationSha256=candidate['retiredPreparationSha256'],
            retirementSha256=candidate['retirementSha256'], successorAccountingSha256=source['recordSha256'],
            entryAccountingSha256=None, receiptIdentity=None, receiptCaptureSha256=None),
        blockers=[], held=None, closureEligible=False, closureRecorded=False,
        scopedClosureRecorded=False, retiredAttemptEffectsReconciled=False,
        retiredAttemptNonExecutionProven=False, freshBalancesEvaluated=False,
        currentWalletBalanceEstablished=False, sourceStateChanged=False,
        reservationsReleased=False, retiredExposureReleased=False, fundsAvailableForNewEntry=False,
        nextCycleAuthorized=False, executionApproved=False, networkRequests=0,
        privateKeyAccessed=False, signaturesCreated=0, transactionsSent=0,
        basis='Historical exact-successor closure assessment; no release contract or operational authority.')
    if not source['accountingUsable']:
        result['blockers'] = [('successor-evidence-quarantined' if source['state'] == 'quarantined'
                               else 'successor-accounting-required'), 'retired-exposure-unresolved']
        return result
    effects = source['effects']; saved = accounting.saved(book, clock())
    opened = accounting.receipts.original.entry.saved(book.db, clock())
    check(opened is not None and effects['entryAccountingSha256'] == digest(opened) and
          effects['successorSha256'] == expected and effects['retirementSha256'] == candidate['retirementSha256'],
          'successor-closure-source-binding')
    paid = int(effects['knownFeesPaidLamports']); held = int(effects['projectedFeeHoldAfterKnownFeesLamports'])
    retired = int(effects['retiredFeeExposureHeldLamports']); other = int(effects['projectedOtherFeeHeldLamports'])
    original = int(opened['accounting']['originalFeeCommitmentLamports'])
    check(retired > 0 and other >= 0 and held == retired + other and original == paid + held,
          'successor-closure-fee-conservation')
    result['identity'].update(entryAccountingSha256=digest(opened), receiptIdentity=effects['receiptIdentity'],
        receiptCaptureSha256=saved['captureSha256'])
    result['held'] = dict(originalFeeCommitmentLamports=str(original), knownFeesPaidLamports=str(paid),
        remainingFeeHeldLamports=str(held), retiredFeeExposureHeldLamports=str(retired),
        otherFeeHeldLamports=str(other), sourceProceedsHeldAtomic=effects['sourceProceedsObservedAtomic'],
        ownedAcquiredResidualAtomic=effects['ownedAcquiredResidualAtomic'],
        protectedAcquiredInventoryAtomic=effects['protectedAcquiredInventoryAtomic'])
    if effects['ownedAcquiredResidualAtomic'] != '0': result['blockers'].append('owned-inventory-remains')
    result['blockers'].append('retired-exposure-unresolved')
    return result


@view.cycles.binding.operation
@submission.handoff.successor.history.fresh_signing.timing.signature_replay
def status(home, wallet, pool, expected, *, clock=view.now):
    with view.cycles.c.source_lock(home, wallet) as root, read_only_journals():
        book = submission.transport._open(root, wallet, pool, clock)
        try:
            with submission.original.ExitSubmission(book).snapshot():
                return review(root, book, wallet, pool, expected, clock)
        finally: book.close()
