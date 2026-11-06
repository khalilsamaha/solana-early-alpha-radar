"""Bound raw entry receipts to the private handoff in its existing ledger.

No sender, signing, release, new allocation or production CLI. RPC claims are
revalidated, not independently authenticated. Original reservations remain held.
"""
from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path
import sys

import signer_handoff as handoff
from pre_sign_admission import Admission, encoded
from contract import digest, uint
from core import check
sys.path.append(str(Path(__file__).resolve().parents[1]/'token-reconciliation'))
from audit import audit
from reconcile import binding, instructions, transfer, TOKEN

VERSION = 'admission-receipt-gate-1'
MAX_EVENTS = 16
MAX_RECEIPT_BYTES = 4 * 1024 * 1024
TERMINAL = {'signed-token-accounting-consistent': 'entry-effects-observed',
            'finalized-failure-fee-only': 'entry-failure-observed'}


def evaluate(package, private, signed_at, now, scope):
    """Only raw, exact-wire/intent evidence may produce entry effects."""
    bound = (isinstance(package, dict) and
             package.get('signedTransactionBase64') == private['signedTransactionBase64'] and
             isinstance(package.get('bundle'), dict) and
             package['bundle'].get('intent') == private['intent'])
    if not bound:
        return 'quarantined', None
    captured = package['bundle'].get('capturedAtMs')
    uint(captured, now, 'receipt-capture-clock', minimum=signed_at)
    result = audit(package)
    if result['state'] == 'unknown':
        return 'receipt-unknown', None
    if result['state'] not in TERMINAL or result.get('wireSha256') != private['wireSha256']:
        return 'quarantined', None
    if result['state'] == 'signed-token-accounting-consistent':
        # The generic reconciler permits compatible counterparties. This gate is
        # narrower: the two transfers must use the exact admitted pool vaults.
        tx = package['bundle']['rpcEvidence']['transaction']['result']
        _, keys, outer = binding(tx)
        moves = [op for op in instructions(tx['meta'], outer, keys)
                 if op['program'] == TOKEN and transfer(op)]
        roles = scope['accounts']
        expected = [(roles['source'], roles['inputVault'], roles['wallet']),
                    (roles['outputVault'], roles['destination'], roles['authority'])]
        actual = [(op['accounts'][0], op['accounts'][2 if op['data'][0] == 12 else 1],
                   op['accounts'][-1]) for op in moves]
        if actual != expected:
            return 'quarantined', None
    check(result['native']['rentSpentLamports'] == result['native']['rentRefundedLamports'] == '0',
          'receipt-unexpected-rent')
    summary = {k: deepcopy(result[k]) for k in ('state', 'slot', 'wireSha256', 'tokenAccounts', 'native')}
    return TERMINAL[result['state']], summary


class ReceiptGate:
    """A bounded receipt inbox in the admission database, never a second book."""
    def __init__(self, admission):
        check(type(admission) is Admission, 'receipt-admission-required')
        self.a = admission
        self.db = admission.db

    def bound(self):
        private = self.a.private_accounting_handoff()
        return private, digest({k: v for k, v in private.items() if k != 'signedTransactionBase64'})

    def source(self, identity):
        state, _, _, at = self.a.read()
        check(state is not None and state['state'] in ('signed-recorded', 'stopped') and
              state.get('accountingHandoffSha256') == identity, 'receipt-handoff-changed')
        return state, at

    def read(self, private, identity, now):
        state, admission_at = self.source(identity)
        exists = self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='admission_receipt_events'").fetchone()
        if not exists:
            check(now >= admission_at, 'receipt-clock-regressed')
            return None, 0, '', admission_at
        rows = self.db.execute('SELECT seq, at_ms, CASE WHEN length(value)<=4096 THEN value ELSE NULL END AS value, previous_hash, hash FROM admission_receipt_events ORDER BY seq LIMIT ?', (MAX_EVENTS + 1,)).fetchall()
        check(len(rows) <= MAX_EVENTS, 'receipt-event-cap')
        previous = ''; last = 0; current = None; terminal_package_hash = None
        for seq, row in enumerate(rows, 1):
            check(row['seq'] == seq and type(row['at_ms']) is int and row['at_ms'] >= last and
                  isinstance(row['value'], str) and len(row['value']) <= 4096, 'receipt-event-shape')
            value = json.loads(row['value'])
            check(encoded(value) == row['value'] and set(value) ==
                  {'state', 'handoffSha256', 'packageSha256', 'terminalIdentity', 'terminalSummary'} and
                  value['state'] in ('receipt-unknown', 'entry-effects-observed', 'entry-failure-observed', 'quarantined') and
                  value['handoffSha256'] == identity, 'receipt-event-shape')
            if current:
                check(current['state'] != 'quarantined', 'receipt-after-quarantine')
                if current['terminalIdentity']:
                    check(value['terminalIdentity'] == current['terminalIdentity'] and
                          value['terminalSummary'] == current['terminalSummary'] and
                          value['state'] == 'quarantined', 'receipt-terminal-replaced')
            expected = digest(dict(seq=seq, atMs=row['at_ms'], value=value, previousHash=previous))
            check(row['previous_hash'] == previous and row['hash'] == expected, 'receipt-event-integrity')
            if value['terminalIdentity'] and terminal_package_hash is None:
                terminal_package_hash = value['packageSha256']
            previous = expected; last = row['at_ms']; current = value
        check(now >= max(last, admission_at), 'receipt-clock-regressed')
        saved = self.db.execute('SELECT length(value), CASE WHEN length(value)<=? THEN value ELSE NULL END FROM admission_receipt_raw WHERE id=1', (MAX_RECEIPT_BYTES,)).fetchone()
        if current and current['terminalIdentity']:
            check(saved is not None and saved[0] <= MAX_RECEIPT_BYTES, 'receipt-raw-required')
            package = json.loads(saved[1])
            check(encoded(package) == saved[1] and digest(package) == terminal_package_hash,
                  'receipt-raw-identity')
            result_state, summary = evaluate(package, private, state['signedRecordedAtMs'], now, self.a.policy['scope'])
            check(result_state in TERMINAL.values() and summary == current['terminalSummary'] and
                  digest(summary) == current['terminalIdentity'] and
                  current['state'] in (result_state, 'quarantined'), 'receipt-raw-replay-conflict')
        else:
            check(saved is None, 'receipt-orphan-raw')
            check(current is None or (current['terminalSummary'] is None and
                  current['state'] in ('receipt-unknown', 'quarantined')), 'receipt-terminal-missing')
        return current, len(rows), previous, last

    def observe(self, package):
        check(len(encoded(package).encode()) <= MAX_RECEIPT_BYTES, 'receipt-size-cap')
        package = deepcopy(package)
        private, identity = self.bound()
        with self.a.j.transaction():
            now = self.a.j.now()
            current, count, previous, last = self.read(private, identity, now)
            if current and current['state'] == 'quarantined':
                return self.public(current, count)
            source, _ = self.source(identity)
            state, summary = evaluate(package, private, source['signedRecordedAtMs'], now, self.a.policy['scope'])
            terminal = digest(summary) if summary is not None else None
            if current and current['terminalIdentity']:
                if state == 'receipt-unknown' or terminal == current['terminalIdentity']:
                    return self.public(current, count)
                state = 'quarantined'
                summary = current['terminalSummary']; terminal = current['terminalIdentity']
            value = dict(state=state, handoffSha256=identity, packageSha256=digest(package),
                         terminalIdentity=terminal, terminalSummary=summary)
            if value == current:
                return self.public(current, count)
            check(count < MAX_EVENTS, 'receipt-event-cap')
            end = self.a.j.now(); check(end >= now >= last, 'receipt-clock-regressed')
            check(len(encoded(value)) <= 4096, 'receipt-summary-cap')
            # Both raw terminal evidence and its event commit or roll back together.
            self.db.execute('CREATE TABLE IF NOT EXISTS admission_receipt_events (seq INTEGER PRIMARY KEY, at_ms INTEGER NOT NULL, value TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS admission_receipt_raw (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
            if terminal and not (current and current['terminalIdentity']):
                self.db.execute('INSERT INTO admission_receipt_raw VALUES (1,?)', (encoded(package),))
            event_hash = digest(dict(seq=count+1, atMs=end, value=value, previousHash=previous))
            self.db.execute('INSERT INTO admission_receipt_events VALUES (?,?,?,?,?)',
                            (count+1, end, encoded(value), previous, event_hash))
            return self.public(value, count+1)

    def status(self):
        private, identity = self.bound()
        # Pure read: preserve an enclosing evidence snapshot or writer transaction.
        with nullcontext() if self.db.in_transaction else self.a.j.transaction():
            current, count, _, _ = self.read(private, identity, self.a.j.now())
            return self.public(current, count)

    def public(self, current, count):
        source, _, _, _ = self.a.read()
        summary = None if current is None else current['terminalSummary']
        usable = current is not None and current['state'] in TERMINAL.values()
        return dict(format=VERSION, state='awaiting-receipt' if current is None else current['state'],
            receiptEventCount=count, handoffSha256=source['accountingHandoffSha256'],
            terminalIdentity=None if current is None else current['terminalIdentity'],
            observedEffectsUsable=usable,
            observedSlot=summary['slot'] if usable else None,
            observedEntryFeeLamports=summary['native']['feeLamports'] if usable else None,
            observedAcquiredAtomic=summary['tokenAccounts']['destination']['deltaAtomic'] if usable else None,
            reservedPrincipalAtomic=source['reservedPrincipalAtomic'],
            reservedFeeLamports=source['reservedFeeLamports'],
            allocationTransferred=False, reservationReleased=False, submissionProvenanceVerified=False,
            rpcProvenanceVerified=False, currentWalletBalanceEstablished=False,
            productionLedgerUpdated=False, liveSenderIntegrated=False, executionApproved=False,
            networkRequests=0, signaturesCreated=0, transactionsSent=0)


def observe(home, wallet, pool, package=None, *, clock=handoff.bridge.view.now):
    """Trusted internal seam. Existing fixed ledger only; no report-import CLI."""
    with handoff.bridge.view.cycles.c.source_lock(home, wallet) as root:
        book = Admission(handoff.storage(root), clock=clock)
        try:
            roles = book.policy['scope']['accounts']
            check(roles['wallet'] == wallet and roles['pool'] == pool, 'receipt-source-scope')
            # STOP blocks new actions; it must not hide effects of an existing signature.
            gate = ReceiptGate(book)
            return gate.status() if package is None else gate.observe(package)
        finally:
            book.close()
