"""Same-snapshot successor load preserves complete historical validation."""
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import successor_signing_handoff as m
import test_successor_submission as fixture
from test_signed_exit_timing import files


def legacy_load(c, book):
    record=m.successor.row(book)
    phase,_,amounts,_,_,_=m.successor.history.lifecycle._projection(book,c.home,c.wallet,c.pool,lambda:c.now)
    assert phase=='exit-signed-not-submitted' and amounts is not None
    ctx=m.successor.retirement.position_context(book,c.home,c.wallet,c.pool,lambda:c.now,amounts)
    retired=m.successor.retirement.row(book)
    m.successor.retirement.validate(retired,ctx,c.now)
    m.successor.validate(book,ctx,retired,record,c.now)
    return record,ctx,retired,m.read(book,record,c.now)


class LoadSnapshotTests(unittest.TestCase):
    F=fixture.SuccessorSubmissionTests
    setUpClass=classmethod(F.setUpClass.__func__)
    tearDownClass=classmethod(F.tearDownClass.__func__)
    setUp=F.setUp
    tearDown=F.tearDown
    dispatch=F.dispatch
    lost=F.lost
    boundary=F.boundary
    markers=F.markers
    rows=F.rows

    def load(self,book):
        return m.load(self.c.home,book,self.c.wallet,self.c.pool,self.candidate,lambda:self.c.now)

    def test_identical_context_and_hashes_with_two_preparation_replays_instead_of_three(self):
        book=self.c.book();before=files(self.c)
        try:
            with patch.object(m.preparation,'saved',wraps=m.preparation.saved) as counted:
                expected=legacy_load(self.c,book);self.assertEqual(counted.call_count,3)
                counted.reset_mock();actual=self.load(book);self.assertEqual(counted.call_count,2)
            self.assertEqual(actual,expected);self.assertEqual(m.digest(actual),m.digest(expected))
            self.assertFalse(book.db.in_transaction);self.assertEqual(files(self.c),before)
        finally:book.close()

    def test_pinned_query_only_snapshot_excludes_competing_commit(self):
        book=self.c.book();before=files(self.c);original=m.successor.retirement._context_from_evidence;seen=[]
        def collide(*args,**kwargs):
            self.assertTrue(book.db.in_transaction)
            self.assertEqual(book.db.execute('PRAGMA query_only').fetchone()[0],1)
            with self.assertRaises(sqlite3.OperationalError):book.db.execute('CREATE TABLE forbidden_write(n)')
            other=sqlite3.connect(self.c.path,timeout=0,isolation_level=None)
            try:
                other.execute('BEGIN IMMEDIATE');other.execute('CREATE TABLE competing_write(n)')
                with self.assertRaises(sqlite3.OperationalError):other.execute('COMMIT')
                other.execute('ROLLBACK')
            finally:other.close()
            seen.append(True);return original(*args,**kwargs)
        try:
            with patch.object(m.successor.retirement,'_context_from_evidence',side_effect=collide):self.load(book)
            self.assertEqual(seen,[True]);self.assertEqual(files(self.c),before)
        finally:book.close()

    def test_each_later_load_rejects_changed_preparation_or_signing(self):
        before=files(self.c)
        for table in ('admission_exit_preparation','admission_exit_signing'):
            with self.subTest(table=table):
                book=self.c.book()
                try:
                    self.load(book);book.db.execute('UPDATE '+table+' SET hash=?',('0'*64,))
                    with self.assertRaises(ValueError):self.load(book)
                    self.assertFalse(book.db.in_transaction)
                finally:book.close()
                for name,raw in before.items():Path(name).write_bytes(raw)

    def test_backend_files_and_clock_rechecked_and_stop_history_remains_readable(self):
        book=self.c.book();stamp=self.c.now
        try:
            expected=self.load(book)
            with patch.object(m.successor.history.backend,'_read_ack',return_value='wrong-wire'):
                with self.assertRaisesRegex(ValueError,'retirement-backend-conflict'):self.load(book)
            self.c.now=1
            with self.assertRaises(ValueError):self.load(book)
            self.c.now=stamp;(self.c.home/'STOP').touch(mode=0o600)
            self.assertEqual(self.load(book),expected)
        finally:self.c.now=stamp;book.close()

    def test_snapshot_and_query_mode_ownership_survive_success_and_exception(self):
        book=self.c.book()
        try:
            for caller_transaction in (False,True):
                if caller_transaction:book.db.execute('BEGIN')
                self.load(book);self.assertEqual(book.db.in_transaction,caller_transaction)
                self.assertEqual(book.db.execute('PRAGMA query_only').fetchone()[0],0)
                with patch.object(m.successor.retirement,'_context_from_evidence',side_effect=OSError('fixture')):
                    with self.assertRaises(OSError):self.load(book)
                self.assertEqual(book.db.in_transaction,caller_transaction)
                self.assertEqual(book.db.execute('PRAGMA query_only').fetchone()[0],0)
                if caller_transaction:book.db.rollback()
            book.db.execute('PRAGMA query_only=ON');self.load(book)
            self.assertEqual(book.db.execute('PRAGMA query_only').fetchone()[0],1)
        finally:book.close()

    def test_evidence_sink_and_context_require_pinned_query_only_snapshot(self):
        book=self.c.book();lifecycle=m.successor.history.lifecycle;seen=[]
        args=(book,self.c.home,self.c.wallet,self.c.pool,lambda:self.c.now)
        try:
            for transaction in (False,True):
                if transaction:book.db.execute('BEGIN')
                with self.assertRaisesRegex(ValueError,'lifecycle-exit-snapshot-required'):
                    lifecycle._projection(*args,_unsent_exit_sink=seen.append)
                with self.assertRaisesRegex(ValueError,'retirement-read-snapshot-required'):
                    m.successor.retirement._context_from_evidence(book,self.c.home,self.c.wallet,lambda:self.c.now,None,None,None,None)
                if transaction:book.db.rollback()
            self.assertEqual(seen,[])
            with m.successor.history.transport.ExitSubmission(book).snapshot():
                lifecycle._projection(*args,_unsent_exit_sink=seen.append)
            self.assertEqual(len(seen),1)
            self.assertEqual(seen[0][2]['state'],'not-attempted')
        finally:book.close()

    def test_orphan_transport_never_publishes_reusable_evidence(self):
        book=self.c.book();before=files(self.c);seen=[]
        try:
            book.db.execute('CREATE TABLE admission_exit_submission_ack(id INTEGER PRIMARY KEY,value TEXT)')
            book.db.execute('INSERT INTO admission_exit_submission_ack VALUES(1,?)',('{}',))
            with m.successor.history.transport.ExitSubmission(book).snapshot():
                with self.assertRaises(ValueError):
                    m.successor.history.lifecycle._projection(book,self.c.home,self.c.wallet,self.c.pool,
                        lambda:self.c.now,_unsent_exit_sink=seen.append)
            self.assertEqual(seen,[])
            with self.assertRaises(ValueError):self.load(book)
        finally:
            book.close()
            for name,raw in before.items():Path(name).write_bytes(raw)


if __name__=='__main__':unittest.main()
