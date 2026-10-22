"""Historical controlled-devnet receipt ledger. No signer, RPC, sender or budget approval.

The public CLI only accepts the dedicated private journal directory. Public report
summaries are never accepted as accounting evidence. Existing generic Book policy
is deliberately not backdated: these swaps occurred before ledger registration.
"""
import contextlib
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'devnet-pool'))
import swap_submission as submit
from core import check, directory, private_file, loads
from journal import Journal, encoded

VERSION = 'controlled-position-ledger-1'
NAME = 'controlled.positions.sqlite'
MAX_EVENTS = 64
MAX_SNAPSHOT = 16384
FLAGS = dict(network='devnet', historicalImport=True, pretradeBudgetEnforced=False,
             liveUseAllowed=False, executionApproved=False, productionLedgerUpdated=False,
             networkRequests=0, signaturesCreated=0, transactionsSent=0, privateKeyAccessed=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


@contextlib.contextmanager
def source_lock(home, wallet):
    """Share the execution lock, but do not instantiate the key-reading Session."""
    home = directory(home)
    private_file(home / 'session.lock', 0)
    fd = os.open(home / 'session.lock', os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        meta = loads(private_file(home / 'wallet.json', 4096))
        check(meta.get('format') == 'devnet-wallet-1' and meta.get('network') == 'devnet'
              and meta.get('purpose') == 'fixed-self-transfer-rehearsal'
              and meta.get('wallet') == wallet, 'dedicated-wallet-mismatch')
        yield home
    finally:
        os.close(fd)


def read_evidence(home, wallet, pool):
    scope, proof = submit.bridge.source_scope(SimpleNamespace(home=home, wallet=wallet), pool)
    entry = submit.forward_evidence(home, wallet)
    check(entry['scope'] == scope, 'accounting-entry-scope')
    exit_report = submit.report(home, wallet, reverse=True)
    return snapshot(entry, exit_report, proof)


def snapshot(entry, exit_report, proof):
    """Pure projection of internally replayed receipts; not an external input API."""
    check(entry['state'] == 'finalized-success' and entry['submissionBoundaryRecorded'], 'entry-not-final')
    e = entry['observation']['receipt']
    acquired = int(e['outputAtomic'])
    check(acquired > 0, 'empty-acquisition')
    x = exit_report.get('observation', {}).get('receipt')
    terminal = exit_report['state'] in ('finalized-success', 'finalized-failure')
    trip = submit.round_trip(e, x) if terminal else None
    state = ('closed' if exit_report['state'] == 'finalized-success' else 'open') if terminal else (
        'quarantined' if exit_report['state'] == 'quarantined' else
        'open' if exit_report['state'] == 'not-started' else 'exit-unresolved')
    effects = e['tokenEffects']
    return dict(format=VERSION, wallet=entry['wallet'], pool=entry['scope']['accounts']['pool'],
                entrySignature=entry['signature'], entryReceiptSha256=digest(e),
                entryScopeSha256=digest(entry['scope']), setupEvidenceSha256=digest(proof),
                exitSignature=exit_report.get('signature'),
                exitReceiptSha256=digest(x) if terminal else None,
                sourceExitState=exit_report['state'], state=state,
                acquiredAtomic=str(acquired), originalSpentAtomic=str(e['inputAtomic']),
                originalMint=effects['source']['mint'], acquiredMint=effects['destination']['mint'],
                backgroundAcquiredAtomic=effects['destination']['beforeAtomic'],
                lastReconciledResidualAtomic=trip['residualAcquiredTokenAtomic'] if trip else str(acquired),
                returnedOriginalAtomic=trip['returnedOriginalAtomic'] if trip else '0',
                netOriginalTokenAtomic=trip['netOriginalTokenAtomic'] if trip else str(-int(e['inputAtomic'])),
                confirmedFeeLamports=trip['totalFeeLamports'] if trip else str(e['feeLamports']),
                lastReceiptSlot=x['slot'] if terminal else e['slot'],
                lastReconciledWalletLamports=x['walletAfterLamports'] if terminal else e['walletAfterLamports'],
                exitOutcomeResolved=terminal or exit_report['state'] == 'not-started',
                accountingUsable=state != 'quarantined', currentWalletBalancesKnown=False,
                quarantineReason='source-quarantined' if state == 'quarantined' else None)


def conflict(old, new):
    fixed = ('wallet', 'pool', 'entrySignature', 'entryReceiptSha256', 'entryScopeSha256', 'setupEvidenceSha256')
    if any(old[k] != new[k] for k in fixed):
        return True
    if old['exitSignature'] and old['exitSignature'] != new['exitSignature']:
        return True
    if old['sourceExitState'] != 'not-started' and new['sourceExitState'] == 'not-started':
        return True
    if old['exitReceiptSha256'] and old != new:
        return True
    return new['lastReceiptSlot'] < old['lastReceiptSlot']


def quarantine(old, reason):
    value = copy.deepcopy(old)
    value.update(state='quarantined', accountingUsable=False, exitOutcomeResolved=False, quarantineReason=reason)
    return value


class Ledger:
    """One position, bounded append-only snapshots, one atomic commit per update."""
    def __init__(self, home, *, create, clock=None):
        path = directory(home) / NAME
        existed = os.path.lexists(path)
        if existed:
            private_file(path, 2 * 1024 * 1024)
        self.j = Journal(path, clock=clock, create=create)
        try:
            if not existed:
                with self.j.transaction():
                    self.j.db.execute('CREATE TABLE controlled_events (seq INTEGER PRIMARY KEY, at_ms INTEGER NOT NULL, '
                                      'snapshot TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL)')
            check(self.j.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='controlled_events'")
                  .fetchone()[0] == 1, 'unrecognized-controlled-ledger')
            check(self.j.db.execute('SELECT COUNT(*) FROM intents').fetchone()[0] == 0 and
                  self.j.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0, 'mixed-ledger-refused')
            self.read()
        except BaseException:
            self.j.close()
            raise

    def close(self):
        self.j.close()

    def read(self):
        rows = self.j.db.execute('SELECT * FROM controlled_events ORDER BY seq LIMIT ?', (MAX_EVENTS + 1,)).fetchall()
        check(len(rows) <= MAX_EVENTS, 'controlled-event-cap')
        previous = ''; last = None; stamp = 0
        for seq, r in enumerate(rows, 1):
            check(r['seq'] == seq and type(r['at_ms']) is int and r['at_ms'] >= stamp
                  and len(r['snapshot'].encode()) <= MAX_SNAPSHOT, 'controlled-event-order-or-size')
            value = loads(r['snapshot'])
            check(value.get('format') == VERSION and encoded(value) == r['snapshot'], 'controlled-snapshot-format')
            expected = digest(dict(seq=seq, atMs=r['at_ms'], snapshot=value, previousHash=previous))
            check(r['previous_hash'] == previous and r['event_hash'] == expected, 'controlled-event-integrity')
            previous = expected; last = value; stamp = r['at_ms']
        return last, len(rows), previous, stamp

    def apply(self, value=None, *, source_error=False):
        with self.j.transaction():
            old, count, previous, stamp = self.read()
            if old and old['state'] == 'quarantined':
                return self.result(old, count, False)
            if source_error:
                check(old is not None, 'no-valid-source-or-prior-ledger')
                value = quarantine(old, 'source-validation-failed')
            elif old and conflict(old, value):
                value = quarantine(old, 'source-regressed-or-conflicted')
            check(value is not None, 'missing-accounting-evidence')
            if old == value:
                return self.result(old, count, False)
            check(count < MAX_EVENTS and len(encoded(value).encode()) <= MAX_SNAPSHOT, 'controlled-ledger-cap')
            at = self.j.now()
            check(at >= stamp, 'controlled-clock-regressed')
            event_hash = digest(dict(seq=count + 1, atMs=at, snapshot=value, previousHash=previous))
            self.j.db.execute('INSERT INTO controlled_events VALUES (?,?,?,?,?)',
                              (count + 1, at, encoded(value), previous, event_hash))
            return self.result(value, count + 1, True)

    @staticmethod
    def result(value, count, changed):
        return dict(format=VERSION, state=value['state'], position=value, eventCount=count,
                    ledgerChanged=changed, **FLAGS, limitations=[
                        'Historical import of one controlled acquisition and its reverse, not a pretrade reservation.',
                        'Replays locally retained finalized RPC evidence; does not query current chain or wallet balances.',
                        'Background token holdings are excluded from the acquired position; fees remain in native units.',
                        'Unresolved exits retain last reconciled exposure, not an assertion that the tokens remain spendable.',
                        'Local hashes detect accidental changes, not tampering by the same user who controls all files.',
                        'No generic router, mainnet, execution approval, budget enforcement or strategy profitability claim.'])


def sync(home, wallet, pool):
    with source_lock(home, wallet) as home:
        try:
            value = read_evidence(home, wallet, pool)
        except (ValueError, KeyError, TypeError, OSError):
            # Never create an empty ledger on invalid input or erase prior accounting.
            if not os.path.lexists(home / NAME):
                raise ValueError('source-validation-failed') from None
            ledger = Ledger(home, create=False)
            try:
                old = ledger.read()[0]
                check(old and old['wallet'] == wallet and old['pool'] == pool, 'explicit-ledger-identity-mismatch')
                return ledger.apply(source_error=True)
            finally:
                ledger.close()
        ledger = Ledger(home, create=True)
        try:
            return ledger.apply(value)
        finally:
            ledger.close()
