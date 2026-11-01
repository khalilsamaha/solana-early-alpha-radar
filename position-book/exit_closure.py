"""Durable scoped exit closure; no allocator, signer, sender or runtime activation.

Only the internal fresh collector can supply a candidate capture. Commit replay
uses an independent reader under a writer transaction. Historical summaries are
never inputs to release and never establish funds available for a new trade.
"""
from copy import deepcopy
import time

import exit_balance as balance
from contract import digest, fields, uint
from core import check
from journal import encoded, read_only_journals

VERSION = 'admission-exit-closure-1'
TABLE = 'admission_exit_closure'
MAX_RECORD = 98304
view = balance.view


def saved(book, now):
    exists = book.db.execute('SELECT type FROM sqlite_master WHERE name=?', (TABLE,)).fetchone()
    if exists is None:
        return None
    check(exists[0] == 'table', 'closure-table')
    rows = book.db.execute('SELECT id, CASE WHEN length(value)<=? THEN value ELSE NULL END value, hash '
                          'FROM admission_exit_closure LIMIT 2', (MAX_RECORD,)).fetchall()
    check(len(rows) == 1 and rows[0]['id'] == 1 and type(rows[0]['value']) is str, 'closure-record')
    record = balance.loads(rows[0]['value'])
    fields(record, {'format', 'recordedAtMs', 'capture', 'settlement'}, 'closure-schema')
    check(record['format'] == VERSION + '-record' and encoded(record) == rows[0]['value'] and
          digest(record) == rows[0]['hash'], 'closure-integrity')
    uint(record['recordedAtMs'], now, 'closure-clock', minimum=1)
    return record


def derive(accounting, checked):
    a = accounting['accounting']
    check(a['state'] == 'exit-position-flat-held' and a['ownedAcquiredResidualAtomic'] == '0', 'closure-flat-required')
    fee = int(a['feeCommitmentRemainingLamports'])
    paid = int(a['totalFeePaidLamports'])
    check(int(a['originalFeeCommitmentLamports']) == paid + fee, 'closure-fee-conservation')
    check(checked['feeHeldLamports'] == str(fee) and
          checked['sourceProceedsHeldAtomic'] == a['sourceProceedsHeldAtomic'] and
          checked['protectedInventoryAtomic'] == a['protectedAcquiredInventoryAtomic'] and
          checked['ownedAcquiredResidualAtomic'] == '0', 'closure-balance-binding')
    return dict(format=VERSION, allocationId=a['allocationId'], owner='same-admission-ledger',
        state='closed-scoped-commitments-released', exitAccountingSha256=digest(accounting),
        originalSourcePrincipalAtomic=a['originalSourcePrincipalAtomic'],
        sourceProceedsReleasedAtomic=a['sourceProceedsHeldAtomic'],
        originalFeeCommitmentLamports=a['originalFeeCommitmentLamports'], totalFeePaidLamports=str(paid),
        unusedFeeReleasedLamports=str(fee), remainingFeeHeldLamports='0', remainingProceedsHeldAtomic='0',
        ownedAcquiredResidualAtomic='0', protectedAcquiredInventoryAtomic=a['protectedAcquiredInventoryAtomic'],
        protectedInventoryReleasedAtomic='0', principalRestoredAtomic='0',
        balanceSnapshotSlot=checked['snapshotSlot'], balanceObservedAtMs=checked['observedAtMs'])


def replay(book, root, wallet, pool, clock):
    """Replay a historical close as of commit time; STOP and age do not erase it."""
    record = saved(book, clock())
    if record is None:
        return None
    ctx = balance.context(book, root, wallet, pool, clock, _allow_stopped=True)
    checked = balance.review(ctx, record['capture'], record['recordedAtMs'])
    accounting = balance.accounting.saved(book.db, clock())
    check(record['settlement'] == derive(accounting, checked), 'closure-source-conflict')
    return record


def public(record, *, applied=False, requests=0):
    return dict(format=VERSION, state='exit-closure-pending' if record is None else record['settlement']['state'],
        closureRecorded=record is not None, appliedThisRun=applied,
        recordSha256=None if record is None else digest(record),
        settlement=None if record is None else deepcopy(record['settlement']),
        recordedAtMs=None if record is None else record['recordedAtMs'],
        scopedCommitmentsReleased=record is not None, fundsAvailableForNewEntry=False,
        originalAdmissionHistoryUnchanged=True, protectedInventoryReleased=False,
        walletWideReservationsKnown=False, currentWalletBalanceEstablished=False,
        nextCycleAuthorized=False, executionApproved=False, runtimeIntegrated=False,
        networkRequests=requests, signaturesCreated=0, transactionsSent=0, privateKeyAccessed=False,
        basis='Historical same-allocation closure; no current solvency, portfolio credit or new-entry permission')


def status(home, wallet, pool, *, clock=view.now):
    with view.cycles.c.source_lock(home, wallet) as root, read_only_journals():
        book = balance.accounting.submission.transport._open(root, wallet, pool, clock)
        try:
            return public(replay(book, root, wallet, pool, clock))
        finally:
            book.close()


def _insert(book, record):
    value = encoded(record)
    check(len(value.encode()) <= MAX_RECORD, 'closure-size-cap')
    book.db.execute('CREATE TABLE admission_exit_closure '
                    '(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL, hash TEXT NOT NULL)')
    book.db.execute('INSERT INTO admission_exit_closure VALUES(1,?,?)', (value, digest(record)))
    check(book.db.execute('PRAGMA page_count').fetchone()[0] *
          book.db.execute('PRAGMA page_size').fetchone()[0] <= 64 * 1024 * 1024, 'closure-ledger-cap')


def _commit(home, wallet, pool, capture, deadline, *, clock, monotonic):
    """Trusted in-process handoff only; never accepts a public report or file."""
    with view.cycles.c.source_lock(home, wallet) as root:
        book = balance.accounting.submission.transport._open(root, wallet, pool, clock)
        try:
            with book.j.transaction():
                with read_only_journals():
                    reader = balance.accounting.submission.transport._open(root, wallet, pool, clock)
                    try:
                        previous = replay(reader, root, wallet, pool, clock)
                        if previous is not None:
                            return public(previous)
                        ctx = balance.context(reader, root, wallet, pool, clock)
                        accounting = balance.accounting.saved(reader.db, clock())
                    finally:
                        reader.close()
                now = book.j.now()
                first_tick = monotonic()
                check(deadline[0] <= first_tick < deadline[1], 'closure-monotonic-expired')
                checked = balance.review(ctx, capture, now)
                record = dict(format=VERSION+'-record', recordedAtMs=now,
                              capture=deepcopy(capture), settlement=derive(accounting, checked))
                _insert(book, record)
                # A rollback covers table, raw capture and release arithmetic together.
                check(not balance.accounting.submission.handoff.stopped(root, book), 'closure-stopped')
                end = book.j.now()
                check(end >= now and end < capture['startedAtMs'] + balance.FRESH_MS, 'closure-expired-before-commit')
                check(first_tick <= monotonic() < deadline[1], 'closure-monotonic-expired')
            return public(record, applied=True)
        finally:
            book.close()


@view.cycles.binding.operation
def collect_and_close(home, wallet, pool, *, opener=None, clock=view.now, monotonic=time.monotonic):
    """Four bounded reads, then fresh atomic scoped closure. No execution mode."""
    previous = status(home, wallet, pool, clock=clock)
    if previous['closureRecorded']:
        return previous  # Durable recovery after an ambiguous caller result; no RPC.
    captures = []
    start = monotonic()
    result = balance.collect(home, wallet, pool, opener=opener, clock=clock,
                             monotonic=monotonic, _evidence_sink=captures.append)
    if not result['balanceReconciliationPassed']:
        out = public(None, requests=result['networkRequests'])
        out.update(state='exit-closure-blocked', diagnosticCode=result['diagnosticCode'])
        return out
    check(len(captures) == 1, 'closure-capture-required')
    # Count collection and writer replay against one monotonic budget, including
    # pre-collection context work. A frozen wall clock cannot extend that budget.
    closed = _commit(home, wallet, pool, captures[0], (start, start + balance.FRESH_MS / 1000),
                     clock=clock, monotonic=monotonic)
    closed['networkRequests'] = result['networkRequests']
    return closed
