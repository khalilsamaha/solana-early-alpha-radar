"""Read local controlled-cycle commitments under the cooperating sender's lock.

Observation only: no reservation creation, repair, signing, RPC or execution.
This is not a wallet-wide portfolio ledger or permission for a third cycle.
"""
from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
import time

import cycles
from core import check
from journal import read_only_journals

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'swap-state'))
import quote_binding

VERSION = 'controlled-reservation-view-1'
MAX_READ_MS = 10000
FINAL = ('finalized-success', 'finalized-failure')
ERRORS = (ValueError, KeyError, TypeError, IndexError, OSError, sqlite3.Error)


def now():
    return time.time_ns() // 1000000


def base():
    return dict(format=VERSION, state='unavailable', reasons=[], reservations=None,
        networkRequests=0, transactionsSent=0, signaturesCreated=0, privateKeyAccessed=False,
        sourceStateChanged=False, databaseConnectionsReadOnly=True, executionApproved=False,
        nextCycleAuthorized=False, walletWideReservationsKnown=False, currentWalletBalancesKnown=False,
        scope='fixed-controlled-two-cycle-devnet',
        limitations=[
            'Only commitments in the existing controlled devnet cycles are covered.',
            'The wallet lock coordinates cooperating local processes, not external wallet activity.',
            'The view expires after release of the lock; it is not a spending authorization.',
            'Missing or contradictory evidence stays unavailable; no repair or reservation release.',
            'No mainnet, new cycle, frozen-study evaluation or strategy profitability claim.'])


def project(state, summary, *, wallet, pool):
    """Project internally read, hash-checked state; never a public report input API."""
    check(state and state['wallet'] == wallet and state['pool'] == pool, 'reservation-scope-mismatch')
    check(not state['quarantined'] and summary['accountingUsable'], 'reservation-quarantined')
    entry = state['legs'].get('entry')
    check(entry is not None, 'entry-reservation-missing')
    a = entry['contract']['accounts']
    check(a['wallet'] == wallet and a['pool'] == pool, 'reservation-account-scope')
    phase = summary['state']
    check(phase in ('entry-unresolved', 'entry-failed', 'open', 'exit-unresolved',
                    'exit-failed-position-open', 'closed'), 'reservation-phase')
    # An unresolved entry may have acquired an unknown quantity. Do not label
    # that account free merely because no finalized entry receipt is present.
    acquired = None if phase == 'entry-unresolved' else summary['lastReconciledAcquiredAtomic']
    return dict(phase=phase, wallet=wallet, pool=pool,
        nativeHeldLamports=summary['reservedFeeLamports'],
        tokenAccounts=[
            dict(account=a['source'], mint=a['inputMint'], heldAtomic=summary['heldEntryPrincipalAtomic']),
            dict(account=a['destination'], mint=a['outputMint'], heldAtomic=acquired)],
        confirmedFeeLamports=summary['cumulativeConfirmedFeeLamports'],
        unresolved=phase in ('entry-unresolved', 'exit-unresolved'),
        exposureOpen=phase not in ('closed', 'entry-failed'))


def read_locked(home, wallet, pool, clock):
    start = clock()
    check(type(start) is int and 0 <= start <= 2**53-1, 'reservation-clock')
    check(not cycles.c.submit.swap.stop(home), 'stop-marker-present')
    child = home / cycles.binding.CYCLE
    # Guard.load validates cycle-two preparation and replays the closed first
    # cycle. Thus its historical fees are not counted as a second live reserve.
    with cycles.c.submit.spend_guard.Guard(child) as guard:
        state, count, head, event_at = guard.read()
        summary = guard.summary()
        check(state is not None and count > 0 and event_at <= start, 'reservation-ledger-empty-or-future')
        check(guard.cycle['wallet'] == wallet and guard.cycle['pool'] == pool, 'reservation-cycle-scope')
        values = project(state, summary, wallet=wallet, pool=pool)
        for side, reverse in (('entry', False), ('exit', True)):
            report = cycles.c.submit.report(child, wallet, reverse=reverse)
            leg = state['legs'].get(side)
            stored = leg['receipt'] if leg else None
            if report['state'] in FINAL:
                check(stored is not None and stored == report['observation']['receipt'],
                      'reservation-receipt-not-reconciled')
            else:
                check(stored is None and report['state'] != 'quarantined', 'reservation-receipt-unavailable')
            if report.get('scope'):
                check(report['scope']['accounts']['wallet'] == wallet and
                      report['scope']['accounts']['pool'] == pool, 'reservation-receipt-scope')
        check(guard.read() == (state, count, head, event_at), 'reservation-ledger-changed')
    finish = clock()
    check(type(finish) is int and start <= finish <= 2**53-1 and finish-start <= MAX_READ_MS,
          'reservation-read-deadline')
    check(not cycles.c.submit.swap.stop(home), 'stop-marker-present')
    return dict(values, observedAtMs=finish, readStartedAtMs=start, eventCount=count,
                ledgerHeadSha256=head, lastLedgerEventAtMs=event_at,
                cycleBindingSha256=cycles.c.digest(guard.cycle))


@cycles.binding.operation
def inspect(home, wallet, pool, *, clock=now):
    result = base()
    try:
        with cycles.c.source_lock(home, wallet) as root, read_only_journals():
            result['reservations'] = read_locked(root, wallet, pool, clock)
        result['state'] = 'local-reservations-observed'
    except ERRORS:
        result['reasons'] = ['local-reservation-evidence-unavailable']
    return result


@cycles.binding.operation
def bind(home, wallet, pool, bundle, *, clock=now):
    """Derive amounts directly from local storage, then review while still locked.

Public bundles must leave reservations null. No previously exported reservation
report is accepted as an authoritative input, and no unknown becomes zero.
"""
    result = dict(base(), binding=None, localLedgerRead=False)
    try:
        check(type(bundle) is dict and bundle.get('reservations', 'missing') is None,
              'caller-reservations-not-accepted')
        with cycles.c.source_lock(home, wallet) as root, read_only_journals():
            view = read_locked(root, wallet, pool, clock)
            q = bundle['quote']
            check(q['wallet'] == wallet and q['pool'] == pool, 'binding-wallet-or-pool')
            selected = [a for a in view['tokenAccounts'] if a['account'] == q['source'] and a['mint'] == q['inputMint']]
            check(len(selected) == 1 and selected[0]['heldAtomic'] is not None, 'token-reservations-unavailable')
            # No new allocation fits the fixed two-cycle experiment. A consistent
            # arithmetic result below does not change that historical scope.
            p = deepcopy(bundle)
            p['reservations'] = dict(wallet=wallet, source=q['source'], inputMint=q['inputMint'],
                otherTokenAtomic=selected[0]['heldAtomic'], otherNativeLamports=view['nativeHeldLamports'],
                asOfMs=view['observedAtMs'])
            stamp = clock()
            checked = quote_binding._review(p, now_ms=stamp, current_local_reservations=True)
            check(not cycles.c.submit.swap.stop(root), 'stop-marker-present')
            result.update(localLedgerRead=True, reservations=view, binding=checked)
            if checked['state'] == 'declared-quote-state-consistent':
                result['state'] = 'local-reservation-binding-consistent'
            else:
                result['reasons'] = ['quote-state-binding-unavailable']
    except ERRORS:
        result.update(state='unavailable', reservations=None, binding=None, localLedgerRead=False,
                      reasons=['local-reservation-binding-unavailable'])
    return result
