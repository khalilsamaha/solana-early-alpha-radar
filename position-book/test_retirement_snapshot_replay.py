"""Retirement consumes one fresh signing replay per pinned read snapshot."""
from pathlib import Path
import unittest
from unittest.mock import patch

import exit_retirement as m
from exit_submission_checks import signed_case
from test_expired_exit_evidence import fixture
from test_signed_exit_timing import files


def legacy_context(book,c,amounts):
    """Pre-optimization path, retained here as an equality oracle."""
    record=m.history.lifecycle.preparation.saved(book,c.now)
    with m.history.transport.ExitSubmission(book).snapshot():
        sender=m.history.transport.ExitSubmission(book);state=sender.signing()
        assert sender._boundary(state) is None
        status=sender._status(None)
        assert status['state']=='not-attempted' and not status['receiptCaptureCount']
        assert state['state']=='exit-signed-recorded' and c.now>=state['request']['validUntilExclusiveMs']
        m.history.backend._attempt_record_for_state(c.home,book,state)
        assert m.history.backend._read_ack(c.home,book,state)==state['signed']['signedWireBase64']
    identity=dict(preparationSha256=m.digest(record),signingStateSha256=m.digest(state),
        signature=state['signed']['signature'],blockhash=state['request']['packet']['policy']['blockhash'],
        minimumContextSlot=state['minimumContextSlot'],scopedAccounting=amounts)
    return m.expiry.scope_context(book,c.wallet,identity,record)


class SnapshotReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager=signed_case();cls.c=cls.manager.__enter__();cls.c.now+=30000
        cls.ctx=fixture(cls.c);cls.saved=files(cls.c);cls.stamp=cls.c.now
    @classmethod
    def tearDownClass(cls):cls.manager.__exit__(None,None,None)
    def setUp(self):
        self.c.now=self.stamp
        for name,data in self.saved.items():Path(name).write_bytes(data)
    def tearDown(self):
        for name,data in self.saved.items():Path(name).write_bytes(data)
    def context(self,book):
        return m.position_context(book,self.c.home,self.c.wallet,self.c.pool,lambda:self.c.now,
                                  self.ctx['identity']['scopedAccounting'])

    def test_exact_legacy_context_with_one_replay_instead_of_four(self):
        book=self.c.book();saved=m.history.lifecycle.preparation.saved
        try:
            with patch.object(m.history.lifecycle.preparation,'saved',wraps=saved) as calls:
                expected=legacy_context(book,self.c,self.ctx['identity']['scopedAccounting'])
                self.assertEqual(calls.call_count,4)
                calls.reset_mock();actual=self.context(book)
                self.assertEqual(calls.call_count,1)
            self.assertEqual(actual,expected);self.assertEqual(m.digest(actual),m.digest(expected))
            self.assertFalse(book.db.in_transaction)
            self.assertEqual(files(self.c),self.saved)
        finally:book.close()

    def test_status_evidence_requires_snapshot_and_preserves_status_schema(self):
        book=self.c.book();sender=m.history.transport.ExitSubmission(book)
        try:
            with self.assertRaisesRegex(ValueError,'exit-read-snapshot-required'):sender._status_evidence()
            with sender.snapshot():
                status,state,prepared=sender._status_evidence()
                self.assertEqual(status,sender._status(None))
                self.assertEqual(state,sender.signing())
                self.assertEqual(m.digest(prepared),state['request']['preparationSha256'])
            self.assertFalse(book.db.in_transaction)
        finally:book.close()

    def test_orphan_ack_and_capture_tables_still_rejected(self):
        transport=m.history.transport
        for table in (transport.ACK,transport.CAPTURES):
            with self.subTest(table=table):
                book=self.c.book()
                try:
                    if table==transport.ACK:
                        book.db.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY,value TEXT)')
                        value=dict(state='rpc-acknowledged',boundarySha256='0'*64,atMs=self.c.now)
                        book.db.execute(f'INSERT INTO {table} VALUES(1,?)',(m.encoded(value),))
                    else:book.db.execute(f'CREATE TABLE {table} (seq INTEGER PRIMARY KEY,value TEXT,hash TEXT)')
                    book.db.commit()
                    with self.assertRaisesRegex(ValueError,'exit-(ack-binding|capture-boundary)'):self.context(book)
                    self.assertFalse(book.db.in_transaction)
                finally:book.close()
                for name,data in self.saved.items():Path(name).write_bytes(data)

    def test_later_call_reloads_modified_journal_instead_of_cached_decision(self):
        book=self.c.book()
        try:
            self.context(book)
            book.db.execute("UPDATE admission_exit_signing SET hash=? WHERE seq=2",('0'*64,));book.db.commit()
            with self.assertRaises(ValueError):self.context(book)
            self.assertFalse(book.db.in_transaction)
        finally:book.close()

    def test_clock_and_backend_ack_are_still_checked_each_call(self):
        book=self.c.book()
        try:
            self.context(book)
            self.c.now=self.c.exit_state['request']['validUntilExclusiveMs']-1
            with self.assertRaisesRegex(ValueError,'retirement-expired-signature-required'):self.context(book)
            self.c.now=self.stamp
            with patch.object(m.history.backend,'_read_ack',return_value='changed'):
                with self.assertRaisesRegex(ValueError,'retirement-backend-conflict'):self.context(book)
            self.assertEqual(files(self.c),self.saved)
        finally:book.close()

    def test_failure_releases_owned_snapshot_but_preserves_callers_transaction(self):
        book=self.c.book()
        try:
            previous=book.db.execute('PRAGMA query_only').fetchone()[0]
            with patch.object(m.history.backend,'_read_ack',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):self.context(book)
            self.assertFalse(book.db.in_transaction)
            self.assertEqual(book.db.execute('PRAGMA query_only').fetchone()[0],previous)
            book.db.execute('BEGIN')
            self.context(book);self.assertTrue(book.db.in_transaction)
            book.db.rollback()
            self.assertEqual(files(self.c),self.saved)
        finally:book.close()
