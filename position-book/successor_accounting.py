"""Durable exact-successor receipt accounting; all residual commitments stay held.

Internal opt-in only. No RPC, signing, transaction, balance observation or closure.
Original generation records remain immutable historical inputs.
"""
from copy import deepcopy
import json

import successor_receipt_review as receipts
from contract import digest, fields, uint
from core import check
from journal import read_only_journals
from pre_sign_admission import encoded

VERSION = 'successor-accounting-1'
TABLE = 'admission_successor_accounting'
MAX_RECORD = 16384
submission = receipts.submission


def present(book):
    return book.db.execute('SELECT type FROM sqlite_master WHERE name=?', (TABLE,)).fetchone()


def saved(book, now):
    exists = present(book)
    if not exists: return None
    check(exists[0] == 'table', 'successor-accounting-table')
    rows = book.db.execute('SELECT id,CASE WHEN length(value)<=? THEN value ELSE NULL END value,hash '
        'FROM admission_successor_accounting LIMIT 2', (MAX_RECORD,)).fetchall()
    check(len(rows) == 1 and rows[0]['id'] == 1 and type(rows[0]['value']) is str, 'successor-accounting-row')
    value = json.loads(rows[0]['value'])
    fields(value, {'format', 'recordedAtMs', 'captureSha256', 'effects'}, 'successor-accounting-schema')
    check(value['format'] == VERSION + '-record' and encoded(value) == rows[0]['value'] and
          digest(value) == rows[0]['hash'], 'successor-accounting-integrity')
    uint(value['recordedAtMs'], now, 'successor-accounting-clock', minimum=1)
    return value


def public(source, record, *, applied=False):
    usable = record is not None and source['receiptEffectsValidated'] and source['state'] != 'quarantined'
    if record is not None and source['state'] != 'quarantined':
        check(usable and record['effects'] == source['effects'] and
              record['captureSha256'] == source['captureSha256'], 'successor-accounting-source-conflict')
        check(record['recordedAtMs'] >= source['evidenceAtMs'], 'successor-accounting-before-evidence')
    state = 'quarantined' if source['state'] == 'quarantined' else 'successor-accounting-pending-held'
    if usable:
        state = ('successor-accounted-flat-held' if record['effects']['ownedAcquiredResidualAtomic'] == '0'
                 else 'successor-accounted-failed-held')
    return dict(format=VERSION, state=state, accountingRecorded=record is not None,
        accountingUsable=bool(usable), appliedThisRun=applied,
        recordSha256=None if record is None else digest(record),
        effects=deepcopy(record['effects']) if usable else None,
        successorReceiptEffectsReconciled=bool(usable), retiredAttemptEffectsReconciled=False,
        scopedClosureRecorded=False, currentWalletBalanceEstablished=False,
        reservationsReleased=False, fundsAvailableForNewEntry=False, nextCycleAuthorized=False,
        executionApproved=False, networkRequests=0, privateKeyAccessed=False,
        signaturesCreated=0, transactionsSent=0,
        basis='Known successor effects booked once; retired fee exposure and residual commitments remain held.')


def replay(root, book, wallet, pool, expected, clock):
    source = receipts.review(root, book, wallet, pool, expected, clock)
    return public(source, saved(book, clock()))


@submission.handoff.view.cycles.binding.operation
@submission.handoff.successor.history.fresh_signing.timing.signature_replay
def status(home, wallet, pool, expected, *, clock=submission.handoff.view.now):
    with submission.handoff.view.cycles.c.source_lock(home, wallet) as root, read_only_journals():
        book = submission.transport._open(root, wallet, pool, clock)
        try:
            with submission.original.ExitSubmission(book).snapshot():
                return replay(root, book, wallet, pool, expected, clock)
        finally: book.close()


@submission.handoff.view.cycles.binding.operation
@submission.handoff.successor.history.fresh_signing.timing.signature_replay
def _apply(home, wallet, pool, expected, *, allow_accounting=False, clock=submission.handoff.view.now):
    check(allow_accounting is True, 'explicit-successor-accounting-required')
    with submission.handoff.view.cycles.c.source_lock(home, wallet) as root:
        book = submission.transport._open(root, wallet, pool, clock)
        try:
            with book.j.transaction():
                with read_only_journals(), submission.original.ExitSubmission(book).snapshot():
                    source = receipts.review(root, book, wallet, pool, expected, clock)
                    record = saved(book, clock())
                    public(source, record)
                applied = False
                if record is None and source['receiptEffectsValidated']:
                    stamp = clock(); uint(stamp, 2**53-1, 'successor-accounting-clock', minimum=source['evidenceAtMs'])
                    record = dict(format=VERSION + '-record', recordedAtMs=stamp,
                        captureSha256=source['captureSha256'], effects=deepcopy(source['effects']))
                    raw = encoded(record)
                    check(len(raw.encode()) <= MAX_RECORD, 'successor-accounting-record-cap')
                    book.db.execute('CREATE TABLE admission_successor_accounting '
                        '(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL,hash TEXT NOT NULL)')
                    book.db.execute('INSERT INTO admission_successor_accounting VALUES(1,?,?)', (raw, digest(record)))
                    check(book.db.execute('PRAGMA page_count').fetchone()[0] * book.db.execute('PRAGMA page_size').fetchone()[0]
                          <= 64 * 1024 * 1024, 'successor-accounting-ledger-cap')
                    applied = True
                result = public(source, record, applied=applied)
            return result
        finally: book.close()
