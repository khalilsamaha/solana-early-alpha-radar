"""Private, local, observation-only intent journal. No submission capability.

Record the submission boundary BEFORE a future external sender would be invoked.
This module cannot prove that another process obeyed that ordering.
"""
import contextlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

from wire import check, verify_wire
from reconcile import binding, digest, reconcile, validate_intent

APPLICATION_ID = 0x52494A31
MAX_EVENTS = 10000
FLAGS = {'executionApproved': False, 'resubmitAllowed': False, 'networkRequests': 0,
         'productionLedgerUpdated': False}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class Journal:
    def __init__(self, path, clock=None, create=True):
        self.path = Path(path).absolute()
        self.clock = clock or (lambda: time.time_ns() // 1000000)
        parent = self.path.parent
        check(parent.is_dir() and not parent.is_symlink() and parent.stat().st_uid == os.getuid()
              and stat.S_IMODE(parent.stat().st_mode) == 0o700, 'journal-directory-must-be-private-owned-0700')
        created = False
        try:
            if not create and not self.path.exists():
                raise ValueError('journal-not-found')
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            created = True
        except FileExistsError:
            s = self.path.lstat()
            check(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o600
                  and s.st_nlink == 1 and s.st_size <= 64 * 1024 * 1024, 'unsafe-journal-file')
        self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            if not created:
                check(self.db.execute('PRAGMA application_id').fetchone()[0] == APPLICATION_ID and
                      self.db.execute('PRAGMA user_version').fetchone()[0] == 1, 'unrecognized-journal')
            self.db.execute('PRAGMA trusted_schema=OFF')
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA synchronous=FULL')
            check(self.db.execute('PRAGMA journal_mode=DELETE').fetchone()[0] == 'delete', 'journal-mode')
            if created:
                with self.transaction():
                    self.db.execute(f'PRAGMA application_id={APPLICATION_ID}')
                    self.db.execute('PRAGMA user_version=1')
                    self.db.execute('CREATE TABLE intents (id TEXT PRIMARY KEY, signature TEXT UNIQUE NOT NULL, '
                        'identity TEXT UNIQUE NOT NULL, intent TEXT NOT NULL, wire TEXT NOT NULL, '
                        'registered_ms INTEGER NOT NULL, state TEXT NOT NULL, evidence_hash TEXT, final_hash TEXT)')
                    self.db.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY, intent_id TEXT NOT NULL '
                        'REFERENCES intents(id), at_ms INTEGER NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL)')
                fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(fd)
                finally: os.close(fd)
            check(self.db.execute('PRAGMA application_id').fetchone()[0] == APPLICATION_ID and
                  self.db.execute('PRAGMA user_version').fetchone()[0] == 1, 'unrecognized-journal')
            check(self.db.execute('PRAGMA quick_check').fetchall()[0][0] == 'ok', 'journal-integrity')
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    @contextlib.contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def now(self):
        now = self.clock()
        check(type(now) is int and 0 < now < 2**63, 'invalid-local-clock')
        latest = self.db.execute('SELECT MAX(at_ms) FROM events').fetchone()[0]
        check(latest is None or now >= latest, 'local-clock-regressed')
        return now

    def event(self, intent_id, now, kind, detail):
        count = self.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        check(count < MAX_EVENTS, 'journal-event-cap')
        self.db.execute('INSERT INTO events(intent_id,at_ms,kind,detail) VALUES (?,?,?,?)',
                        (intent_id, now, kind, encoded(detail)))

    def row(self, intent_id):
        row = self.db.execute('SELECT * FROM intents WHERE id=?', (intent_id,)).fetchone()
        check(row is not None, 'intent-not-registered')
        return row

    def result(self, intent_id):
        row = self.row(intent_id)
        return {'format': 'intent-journal-status-1', 'logicalIntentId': row['id'], 'state': row['state'],
                'registeredAtMs': row['registered_ms'], 'signatureVerified': True,
                'eventCount': self.db.execute('SELECT COUNT(*) FROM events WHERE intent_id=?', (intent_id,)).fetchone()[0],
                **FLAGS}

    def register(self, package):
        check(isinstance(package, dict) and set(package) == {'format', 'logicalIntentId', 'intent', 'signedTransactionBase64'}
              and package['format'] == 'signed-intent-registration-1', 'invalid-registration-schema')
        intent_id, intent = package['logicalIntentId'], package['intent']
        check(isinstance(intent_id, str) and re.fullmatch('[a-zA-Z0-9_-]{1,80}', intent_id), 'invalid-logical-id')
        validate_intent(intent)
        wire = verify_wire(package['signedTransactionBase64'])
        check(wire['signatures'][0] == intent['signature'] and wire['wallet'] == intent['wallet']
              and wire['canonicalMessageSha256'] == intent['messageSha256'], 'signed-intent-binding-mismatch')
        identity = digest({'intent': intent, 'wire': wire})
        with self.transaction():
            now = self.now()
            check(intent['preparedAtMs'] <= now, 'intent-in-future')
            existing = self.db.execute('SELECT * FROM intents WHERE id=?', (intent_id,)).fetchone()
            if existing:
                check(existing['identity'] == identity, 'logical-intent-conflict')
                return self.result(intent_id)  # Retry never resets a state or adds an event.
            check(self.db.execute('SELECT 1 FROM intents WHERE signature=? OR identity=?',
                                  (intent['signature'], identity)).fetchone() is None, 'duplicate-signed-transaction')
            self.db.execute('INSERT INTO intents VALUES (?,?,?,?,?,?,?,NULL,NULL)',
                (intent_id, intent['signature'], identity, encoded(intent), encoded(wire), now, 'prepared'))
            self.event(intent_id, now, 'registered', {'identity': identity})
        return self.result(intent_id)

    def mark_submission_boundary(self, intent_id):
        with self.transaction():
            row, now = self.row(intent_id), self.now()
            check(row['state'] == 'prepared', 'submission-boundary-already-crossed')
            self.db.execute('UPDATE intents SET state=? WHERE id=?', ('submission-unknown', intent_id))
            self.event(intent_id, now, 'submission-boundary', {'meaning': 'may-or-may-not-have-been-sent'})
        return self.result(intent_id)

    def observe(self, intent_id, bundle):
        # Imported evidence is never trusted as a permission or used to construct a transaction.
        check(len(encoded(bundle)) <= 4 * 1024 * 1024, 'evidence-byte-cap')
        evidence_hash = digest(bundle)
        with self.transaction():
            row, now = self.row(intent_id), self.now()
            check(row['state'] != 'prepared', 'submission-boundary-not-recorded')
            check(isinstance(bundle, dict) and bundle.get('intent') == json.loads(row['intent']), 'receipt-intent-conflict')
            if row['evidence_hash'] == evidence_hash:
                return self.result(intent_id)
            outcome = reconcile(bundle)
            # The prior comparator binds parsed messages but checks only the first
            # signature. Require the complete previously verified signature vector.
            if outcome['state'] in ('balance-consistent-with-bound-message', 'finalized-failure-fee-only'):
                tx = bundle['rpcEvidence']['transaction']['result']
                wire = json.loads(row['wire'])
                if tx['transaction']['signatures'] != wire['signatures'] or binding(tx)[0] != wire['canonicalMessageSha256']:
                    outcome = {'state': 'mismatch', 'reason': 'verified-wire-receipt-mismatch'}
            state, final_hash = row['state'], row['final_hash']
            if state != 'quarantined':
                if outcome['state'] in ('mismatch', 'invalid-input', 'unsupported'):
                    state = 'quarantined'
                elif outcome['state'] in ('balance-consistent-with-bound-message', 'finalized-failure-fee-only'):
                    wanted = 'reconciled' if outcome['state'] == 'balance-consistent-with-bound-message' else 'failed-fee-only'
                    # RPC context/capture time may advance. Compare the reconciled economic
                    # outcome, exact verified wire identity, slot and failure instead.
                    tx = bundle['rpcEvidence']['transaction']['result']
                    final_identity = digest({'slot': tx['slot'], 'error': tx['meta']['err'],
                        'wire': json.loads(row['wire'])['wireSha256'], 'state': outcome['state'],
                        'tokenAccounts': outcome['tokenAccounts'], 'native': outcome['native']})
                    state = 'quarantined' if final_hash is not None and final_hash != final_identity else wanted
                    final_hash = final_hash or final_identity
            self.event(intent_id, now, 'evidence', {'evidenceSha256': evidence_hash,
                'outcome': outcome['state'], 'reason': outcome.get('reason'), 'nextState': state})
            self.db.execute('UPDATE intents SET state=?,evidence_hash=?,final_hash=? WHERE id=?',
                            (state, evidence_hash, final_hash, intent_id))
        return self.result(intent_id)
