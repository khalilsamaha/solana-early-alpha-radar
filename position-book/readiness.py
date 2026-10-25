"""Read-only operational evidence check for the fixed two-cycle devnet rehearsal.

No service health, live wallet state, research qualification or trading approval
is inferred from historical receipt consistency.
"""
import os
import sqlite3
import cycles
from core import check
from journal import read_only_journals

VERSION = 'controlled-devnet-readiness-1'
ERRORS = (ValueError, KeyError, TypeError, OSError, sqlite3.Error)
FINAL = ('finalized-success', 'finalized-failure')


def leg_view(report):
    state = report['state']
    # Only terminal receipt replay provides a resolved execution outcome.
    unresolved = state not in FINAL and state != 'not-started'
    return dict(state=state, receiptFinalized=state in FINAL,
                submissionBoundaryRecorded=report['submissionBoundaryRecorded'],
                signatureOutcomeUnknown=report['signatureOutcomeUnknown'],
                unresolved=unresolved, requiresReadOnlyRecovery=unresolved and (
                    report['submissionBoundaryRecorded'] or report['signatureOutcomeUnknown']
                    or state == 'signed-simulated-not-submitted'))


def inspect_locked(home, wallet, pool):
    components = {}; blockers = []; actions = []
    def block(code, action, **scope):
        blockers.append(code)
        item=dict(action=action, **scope)
        if item not in actions: actions.append(item)
    stop = cycles.c.submit.swap.stop(home)
    if stop: block('stop-marker-present', 'review-stop-without-removing-it')
    for cycle_id, root in (('controlled-cycle-0001', home), (cycles.binding.CYCLE, home / cycles.binding.CYCLE)):
        for leg, reverse in (('entry', False), ('exit', True)):
            key = cycle_id + '/' + leg
            try:
                report = cycles.c.submit.report(root, wallet, reverse=reverse)
                # Explicit pool binding applies also to the original cycle.
                scope = report.get('scope')
                check(scope is None or scope['accounts']['pool'] == pool, 'explicit-pool-mismatch')
                view = leg_view(report); components[key] = view
                if report['state'] != 'finalized-success':
                    action = 'read-only-recovery' if view['requiresReadOnlyRecovery'] else 'review-preserved-journal'
                    block(key + '/not-finalized-success', action, cycle=cycle_id, leg=leg)
            except ERRORS:
                components[key] = dict(state='unavailable-or-invalid', unresolved=True,
                                       receiptFinalized=False, requiresReadOnlyRecovery=False)
                block(key + '/evidence-unavailable-or-invalid', 'review-preserved-journal', cycle=cycle_id, leg=leg)
    # The bound cycle-two guard is mandatory; it already carries cycle-one fees.
    try:
        with cycles.c.submit.spend_guard.Guard(home / cycles.binding.CYCLE) as guard:
            summary = guard.summary()
            components['spending'] = dict(state=summary['state'],
                accountingUsable=summary.get('accountingUsable', False),
                reservationsClear=summary.get('reservedFeeLamports') == '0' and summary.get('heldEntryPrincipalAtomic') == '0')
            if summary['state'] != 'closed' or not components['spending']['accountingUsable'] or not components['spending']['reservationsClear']:
                block('spending-not-closed-and-clear', 'review-spending-and-receipts')
    except ERRORS:
        components['spending'] = dict(state='unavailable-or-invalid', accountingUsable=False, reservationsClear=False)
        block('spending-unavailable-or-invalid', 'review-spending-and-receipts')
    expected = None
    try:
        expected = cycles.read_evidence(home, wallet, pool)
        components['receiptContinuity'] = dict(state='verified', closedCycles=2)
    except ERRORS:
        components['receiptContinuity'] = dict(state='unavailable-or-inconsistent')
        block('receipt-continuity-unverified', 'review-preserved-journal')
    path = home / cycles.NAME
    if not os.path.lexists(path):
        components['historicalAccounting'] = dict(state='missing', matchesReceipts=False)
        block('accounting-missing', 'run-historical-accounting-sync' if expected is not None else 'review-preserved-journal')
    else:
        ledger = None
        try:
            ledger = cycles.Ledger(home, create=False)
            old, count, _, _ = ledger.read()
            check(old is None or (old['wallet'] == wallet and old['pool'] == pool), 'accounting-identity-mismatch')
            matches = old is not None and expected is not None and old == expected
            state = 'empty' if old is None else 'quarantined' if old['state'] == 'quarantined' else 'consistent' if matches else 'mismatch-or-unverified'
            components['historicalAccounting'] = dict(state=state, eventCount=count, matchesReceipts=matches)
            if not matches:
                block('accounting-' + state, 'run-historical-accounting-sync' if state == 'empty' and expected is not None else 'review-accounting-without-reset')
        except ERRORS:
            components['historicalAccounting'] = dict(state='unavailable-or-invalid', matchesReceipts=False)
            block('accounting-unavailable-or-invalid', 'review-accounting-without-reset')
        finally:
            if ledger is not None: ledger.close()
    return dict(format=VERSION, state='review-required' if blockers else 'closed-evidence-consistent',
        scope='fixed-two-cycle-local-devnet-evidence', components=components, stopRequested=stop,
        blockingReasons=blockers, nextActions=actions,
        unresolvedLegs=sum(int(components[k].get('unresolved', False)) for k in components if '/' in k),
        network='devnet', networkRequests=0, signaturesCreated=0, transactionsSent=0,
        privateKeyAccessed=False, sourceStateChanged=False, databaseConnectionsReadOnly=True,
        executionApproved=False, nextCycleAuthorized=False, mainnetEnabled=False, tradingReady=False,
        strategyReadiness='not-assessed', serviceHealth='not-assessed', currentWalletBalancesKnown=False,
        limitations=[
            'Consistency of retained local evidence only; no fresh RPC or current balance observation.',
            'A missing or invalid receipt is unresolved evidence, not proof of transaction failure.',
            'Recovery recommendations are read-only; this checker never resends, exits, repairs or clears STOP.',
            'Database recovery files are refused without repair; preserve them for investigation.',
            'Closed devnet evidence does not authorize a new cycle, mainnet trading or claim profitability.',
            'Scanner health and frozen research results require their separate checks.'])


@cycles.binding.operation
def inspect(home, wallet, pool):
    # The shared wallet lock protects cooperating processes. No private key is read.
    with cycles.c.source_lock(home, wallet) as home, read_only_journals():
        return inspect_locked(home, wallet, pool)
