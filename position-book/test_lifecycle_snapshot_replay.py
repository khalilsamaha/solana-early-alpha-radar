"""Same-snapshot lifecycle evidence reuse preserves all held-exit decisions."""
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import admission_lifecycle as m
from exit_submission_checks import signed_case, submit
from test_signed_exit_timing import files

transport = m.exit_accounting.submission


def legacy_evidence(sender, clock=None):
    """Previous lifecycle order: preparation, signing, then transport replay."""
    clock = sender.b.j.now if clock is None else clock
    prepared = m.preparation.saved(sender.b, clock())
    signed = m.signing.read(sender.b, clock())
    status = None
    if signed is not None and signed['signed'] is not None and signed['state'] != 'exit-signing-quarantined':
        status = sender._status(None)
    return prepared, signed, status


class LifecycleReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager = signed_case()
        cls.c = cls.manager.__enter__()
        cls.saved = files(cls.c)
        cls.stamp = cls.c.now

    @classmethod
    def tearDownClass(cls):
        cls.manager.__exit__(None, None, None)

    def setUp(self):
        self.c.now = self.stamp
        for name, data in self.saved.items(): Path(name).write_bytes(data)

    def projection(self, book):
        return m._projection(book, self.c.home, self.c.wallet, self.c.pool, lambda: self.c.now)

    def test_exact_projection_three_replays_become_one(self):
        book = self.c.book()
        try:
            with patch.object(m.preparation, 'saved', wraps=m.preparation.saved) as replay:
                with patch.object(transport.ExitSubmission, '_lifecycle_evidence', legacy_evidence):
                    expected = self.projection(book)
                self.assertEqual(replay.call_count, 3)
                replay.reset_mock()
                actual = self.projection(book)
                self.assertEqual(replay.call_count, 1)
            self.assertEqual(actual, expected)
            self.assertEqual(m.digest(actual), m.digest(expected))
            with transport.ExitSubmission(book).snapshot():
                _, _, status = transport.ExitSubmission(book)._lifecycle_evidence()
                self.assertEqual(m.exit_accounting.pending(status), m.exit_accounting.review(book))
            self.assertEqual(files(self.c), self.saved)
            self.assertFalse(book.db.in_transaction)
        finally: book.close()

    def test_unsigned_unknown_and_quarantined_states_equal_legacy(self):
        for mode in ('unprepared', 'unsigned', 'unknown', 'quarantined'):
            with self.subTest(mode=mode):
                self.setUp()
                book = self.c.book()
                try:
                    if mode in ('unprepared', 'unsigned'):
                        book.db.execute('DROP TABLE admission_exit_signing')
                        if mode == 'unprepared': book.db.execute('DROP TABLE admission_exit_preparation')
                    elif mode == 'unknown':
                        book.db.execute('DELETE FROM admission_exit_signing WHERE seq=2')
                    else:
                        state = m.signing.read(book, self.c.now)
                        m.signing.append(book, dict(state='exit-signing-quarantined', reason='signed-response-rejected'), state, self.c.now)
                    book.db.commit()
                    with patch.object(transport.ExitSubmission, '_lifecycle_evidence', legacy_evidence):
                        expected = self.projection(book)
                    self.assertEqual(self.projection(book), expected)
                finally: book.close()

    def test_orphan_ack_and_capture_are_not_mistaken_for_unsent(self):
        for table in (transport.ACK, transport.CAPTURES):
            with self.subTest(table=table):
                self.setUp()
                book = self.c.book()
                try:
                    if table == transport.ACK:
                        book.db.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY,value TEXT)')
                        value = dict(state='rpc-acknowledged', boundarySha256='0'*64, atMs=self.c.now)
                        book.db.execute(f'INSERT INTO {table} VALUES(1,?)', (m.signing.encoded(value),))
                    else:
                        book.db.execute(f'CREATE TABLE {table} (seq INTEGER PRIMARY KEY,value TEXT,hash TEXT)')
                    book.db.commit()
                    with self.assertRaises(ValueError): self.projection(book)
                    self.assertFalse(book.db.in_transaction)
                finally: book.close()

    def test_later_calls_replay_changed_preparation_and_signing(self):
        for table in ('admission_exit_preparation', 'admission_exit_signing'):
            with self.subTest(table=table):
                self.setUp()
                book = self.c.book()
                try:
                    self.projection(book)
                    book.db.execute(f'UPDATE {table} SET hash=?', ('0'*64,))
                    book.db.commit()
                    with self.assertRaises(ValueError): self.projection(book)
                finally: book.close()

    def test_snapshot_clock_and_exception_ownership(self):
        book = self.c.book()
        sender = transport.ExitSubmission(book)
        try:
            with self.assertRaisesRegex(ValueError, 'exit-read-snapshot-required'):
                sender._lifecycle_evidence()
            with self.assertRaises(ValueError):
                with sender.snapshot(): sender._lifecycle_evidence(lambda: 0)
            self.assertFalse(book.db.in_transaction)
            self.assertEqual(book.db.execute('PRAGMA query_only').fetchone()[0], 0)
            book.db.execute('BEGIN IMMEDIATE')
            with sender.snapshot(): sender._lifecycle_evidence()
            self.assertTrue(book.db.in_transaction)
            with patch.object(sender, '_status_for_signing', side_effect=OSError('fixture')):
                with self.assertRaises(OSError):
                    with sender.snapshot(): sender._lifecycle_evidence()
            self.assertTrue(book.db.in_transaction)
            self.assertEqual(book.db.execute('PRAGMA query_only').fetchone()[0], 0)
            book.db.rollback()
            self.assertEqual(files(self.c), self.saved)
        finally: book.close()

    def test_submitted_generation_keeps_full_accounting_review(self):
        submit(self.c)
        book = self.c.book()
        try:
            with patch.object(transport.ExitSubmission, '_lifecycle_evidence', legacy_evidence):
                expected = self.projection(book)
            with patch.object(m.exit_accounting, 'review', wraps=m.exit_accounting.review) as review:
                self.assertEqual(self.projection(book), expected)
                self.assertEqual(review.call_count, 1)
            self.assertEqual(expected[3]['exitTransport'], 'rpc-acknowledged')
        finally: book.close()

    def test_snapshot_blocks_competing_commit(self):
        book = self.c.book()
        original = transport.ExitSubmission._status_for_signing
        calls = []
        def observed(sender, *args, **kwargs):
            other = sqlite3.connect(self.c.path, timeout=0, isolation_level=None)
            try:
                other.execute('BEGIN IMMEDIATE')
                other.execute('CREATE TABLE competing (n INTEGER)')
                with self.assertRaises(sqlite3.OperationalError): other.execute('COMMIT')
                other.execute('ROLLBACK')
                calls.append(True)
            finally: other.close()
            return original(sender, *args, **kwargs)
        try:
            with patch.object(transport.ExitSubmission, '_status_for_signing', observed): self.projection(book)
            self.assertEqual(calls, [True])
            self.assertEqual(files(self.c), self.saved)
        finally: book.close()

    def test_unsent_does_not_hide_orphan_accounting_or_closure(self):
        for table in ('admission_exit_accounting', 'admission_exit_closure'):
            with self.subTest(table=table):
                self.setUp()
                book = self.c.book()
                try:
                    book.db.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY,value TEXT,hash TEXT)')
                    book.db.execute(f'INSERT INTO {table} VALUES(1,?,?)', ('{}', '0'*64))
                    book.db.commit()
                    with self.assertRaises(ValueError): self.projection(book)
                finally: book.close()


if __name__ == '__main__': unittest.main()
