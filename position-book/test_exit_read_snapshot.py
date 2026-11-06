"""Read reuse must not survive a snapshot, hide corruption or release a writer."""
import json
import sqlite3
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import exit_submission as m
from exit_submission_checks import signed_case,submit,recover,FakeRpc


class SnapshotTests(unittest.TestCase):
    def test_ack_snapshot_requires_read_transaction_and_standalone_replays(self):
        with signed_case() as c:
            b=c.book();s=m.ExitSubmission(b)
            try:
                state=s.signing()
                with self.assertRaisesRegex(ValueError,'exit-ack-read-snapshot-required'):
                    m.backend._acknowledgment_in_snapshot(c.home,b,state)
                b.db.execute('BEGIN')
                with self.assertRaisesRegex(ValueError,'exit-ack-read-snapshot-required'):
                    m.backend._acknowledgment_in_snapshot(c.home,b,state)
                b.db.execute('ROLLBACK')
                with s.snapshot():
                    state=s.signing()
                    with patch.object(m.handoff,'read',side_effect=AssertionError('duplicate replay')):
                        self.assertEqual(m.backend._acknowledgment_in_snapshot(c.home,b,state),c.exit_wire)
                with patch.object(m.handoff,'read',wraps=m.handoff.read) as replay:
                    self.assertEqual(m.backend.acknowledgment(c.home,b),c.exit_wire)
                    self.assertEqual(replay.call_count,1)
            finally:b.close()

    def test_ack_file_changes_are_checked_even_inside_same_snapshot(self):
        with signed_case() as c:
            b=c.book();s=m.ExitSubmission(b);path=c.path.parent/m.backend.ACK
            try:
                with s.snapshot():
                    state=s.signing()
                    self.assertEqual(m.backend._acknowledgment_in_snapshot(c.home,b,state),c.exit_wire)
                    value=json.loads(path.read_text());value['wireSha256']='0'*64
                    path.write_text(json.dumps(value))
                    with self.assertRaisesRegex(ValueError,'exit-signer-ack-hash'):
                        m.backend._acknowledgment_in_snapshot(c.home,b,state)
            finally:b.close()

    def test_rpc_has_no_read_transaction_and_changed_ack_blocks_boundary(self):
        with signed_case() as c:
            path=c.path.parent/m.backend.ACK;rpc_calls=[]
            def change(method):
                # An exclusive transaction can start only if transport released
                # its read snapshot before invoking the provider.
                db=sqlite3.connect(c.path,timeout=0,isolation_level=None)
                try:db.execute('BEGIN EXCLUSIVE');db.execute('ROLLBACK')
                finally:db.close()
                rpc_calls.append(method)
                if method=='getFeeForMessage':
                    value=json.loads(path.read_text());value['requestSha256']='0'*64
                    path.write_text(json.dumps(value))
            rpc=FakeRpc(c,callback=change)
            with self.assertRaisesRegex(ValueError,'exit-signer-ack-binding'):submit(c,rpc)
            self.assertTrue(rpc_calls);self.assertNotIn('sendTransaction',rpc_calls)
            b=c.book()
            try:self.assertIsNone(b.db.execute('SELECT name FROM sqlite_master WHERE name=?',(m.BOUNDARY,)).fetchone())
            finally:b.close()

    def test_changed_signing_after_rpc_is_replayed_before_send(self):
        with signed_case() as c:
            def corrupt(method):
                if method=='getFeeForMessage':
                    db=sqlite3.connect(c.path)
                    try:
                        db.execute("UPDATE admission_exit_signing SET value='{}' WHERE seq=2");db.commit()
                    finally:db.close()
            rpc=FakeRpc(c,callback=corrupt)
            with self.assertRaises(ValueError):submit(c,rpc)
            self.assertFalse(any(r['method']=='sendTransaction' for r in rpc.requests))
            b=c.book()
            try:self.assertIsNone(b.db.execute('SELECT name FROM sqlite_master WHERE name=?',(m.BOUNDARY,)).fetchone())
            finally:b.close()

    def test_snapshot_forbids_writes_and_restores_query_only(self):
        db=sqlite3.connect(':memory:',isolation_level=None)
        db.execute('CREATE TABLE probe (n INTEGER)')
        s=m.ExitSubmission(SimpleNamespace(db=db))
        try:
            with s.snapshot():
                with self.assertRaises(sqlite3.OperationalError):db.execute('INSERT INTO probe VALUES(1)')
                with s.snapshot():self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],1)
                self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],1)
            self.assertFalse(db.in_transaction)
            self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],0)
            db.execute('INSERT INTO probe VALUES(2)')
            db.execute('PRAGMA query_only=ON')
            with self.assertRaisesRegex(ValueError,'synthetic'):
                with s.snapshot():raise ValueError('synthetic')
            self.assertFalse(db.in_transaction)
            self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],1)
        finally:db.close()

    def test_single_replay_per_status_and_no_retained_verdict(self):
        with signed_case() as c:
            submit(c)
            b=c.book();s=m.ExitSubmission(b)
            try:
                before=c.path.read_bytes()
                with patch.object(s,'signing',wraps=s.signing) as replay:
                    first=s.status();second=s.status()
                self.assertEqual(first,second)
                self.assertEqual(replay.call_count,2)
                self.assertEqual(first['state'],'rpc-acknowledged')
                self.assertEqual(c.path.read_bytes(),before)
                self.assertFalse(b.db.in_transaction)
                raw=b.db.execute('SELECT value FROM admission_exit_signing WHERE seq=2').fetchone()[0]
                b.db.execute("UPDATE admission_exit_signing SET value='{}' WHERE seq=2")
                with self.assertRaises(ValueError):s.status()
                self.assertFalse(b.db.in_transaction)
                b.db.execute('UPDATE admission_exit_signing SET value=? WHERE seq=2',(raw,))
                self.assertEqual(s.status(),first)
            finally:b.close()

    def test_status_preserves_caller_transaction_and_rollback(self):
        with signed_case() as c:
            submit(c);b=c.book()
            try:
                b.db.execute('BEGIN IMMEDIATE')
                b.db.execute('CREATE TABLE caller_probe (value TEXT)')
                self.assertEqual(m.ExitSubmission(b).status()['state'],'rpc-acknowledged')
                self.assertTrue(b.db.in_transaction)
                b.db.execute('ROLLBACK')
                self.assertIsNone(b.db.execute("SELECT name FROM sqlite_master WHERE name='caller_probe'").fetchone())
            finally:b.close()

    def test_snapshot_blocks_competing_commit_and_releases_on_error(self):
        with signed_case() as c:
            submit(c);b=c.book();s=m.ExitSubmission(b);row=s.row;attempts=[]
            def competing(table,cap):
                if table==m.BOUNDARY:
                    other=sqlite3.connect(c.path,timeout=0,isolation_level=None)
                    try:
                        other.execute('BEGIN IMMEDIATE')
                        other.execute('UPDATE admission_exit_submission SET value=value')
                        with self.assertRaises(sqlite3.OperationalError):other.execute('COMMIT')
                        attempts.append(True)
                    finally:other.close()
                    raise ValueError('synthetic read error')
                return row(table,cap)
            try:
                before=c.path.read_bytes()
                with patch.object(s,'row',competing):
                    with self.assertRaisesRegex(ValueError,'synthetic read error'):s.status()
                self.assertEqual(attempts,[True]);self.assertFalse(b.db.in_transaction)
                self.assertEqual(c.path.read_bytes(),before)
                self.assertEqual(s.status()['state'],'rpc-acknowledged')
                other=sqlite3.connect(c.path,timeout=0,isolation_level=None)
                try:
                    other.execute('BEGIN EXCLUSIVE');other.execute('ROLLBACK')
                finally:other.close()
            finally:b.close()

    def test_explicit_reads_revalidate_between_calls_and_keep_nested_snapshot(self):
        with signed_case() as c:
            submit(c);recover(c);b=c.book();s=m.ExitSubmission(b)
            try:
                with s.snapshot():
                    with s.snapshot():
                        self.assertTrue(b.db.in_transaction)
                        self.assertEqual(len(s.captures()),1)
                    self.assertTrue(b.db.in_transaction)
                self.assertFalse(b.db.in_transaction)
                raw=b.db.execute('SELECT value FROM admission_exit_submission').fetchone()[0]
                invalid=json.loads(raw);invalid['signature']=c.wallet
                b.db.execute('UPDATE admission_exit_submission SET value=?',(m.encoded(invalid),))
                for method in (s.boundary,s.captures,s.status):
                    with self.assertRaisesRegex(ValueError,'exit-boundary-binding'):method()
                    self.assertFalse(b.db.in_transaction)
                b.db.execute('UPDATE admission_exit_submission SET value=?',(raw,))
                self.assertEqual(s.status()['state'],'exit-finalized-evidence')
            finally:b.close()

    def test_send_callback_still_detects_changed_signing_before_ack(self):
        with signed_case() as c:
            def corrupt(method):
                if method=='sendTransaction':
                    db=sqlite3.connect(c.path)
                    try:
                        db.execute("UPDATE admission_exit_signing SET value='{}' WHERE seq=2");db.commit()
                    finally:db.close()
            rpc=FakeRpc(c,callback=corrupt)
            with self.assertRaises(ValueError):submit(c,rpc)
            self.assertEqual(sum(r['method']=='sendTransaction' for r in rpc.requests),1)
            b=c.book()
            try:
                self.assertEqual(b.db.execute('SELECT COUNT(*) FROM admission_exit_submission').fetchone()[0],1)
                self.assertIsNone(b.db.execute('SELECT name FROM sqlite_master WHERE name=?',(m.ACK,)).fetchone())
            finally:b.close()


if __name__=='__main__':unittest.main()
