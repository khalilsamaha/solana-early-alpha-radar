"""Slow replay precedes RPC; exact SQLite writer pin and freshness stay enforced."""
import sqlite3
import unittest
from unittest.mock import patch

import exit_retirement as m
from exit_submission_checks import signed_case
from test_expired_exit_evidence import fixture,Replies
from test_signed_exit_timing import files


class SnapshotTests(unittest.TestCase):
    def run_retire(self,c,rpc,mono=lambda:0):
        return m.retire(c.home,c.wallet,c.pool,c.exit_state['request']['preparationSha256'],
            allow_retire=True,opener=rpc,clock=lambda:c.now,monotonic=mono)

    def test_twenty_second_replay_precedes_first_rpc_and_only_runs_once(self):
        with signed_case() as c:
            c.now+=30000;ctx=fixture(c);original=m.expiry.context;ticks=[0];replays=[]
            def slow(*args,**kw):
                value=original(*args,**kw);c.now+=20000;ticks[0]+=20;replays.append(True);return value
            def live(q,v):return c.now//1000 if q['method']=='getBlockTime' else v
            rpc=Replies(c,ctx,live)
            with patch.object(m.expiry,'context',side_effect=slow):r=self.run_retire(c,rpc,lambda:ticks[0])
            self.assertEqual(r['state'],'exit-retired-held',r);self.assertEqual(len(replays),1)
            self.assertGreaterEqual(r['timing']['local-replayMs'],20000)
            self.assertLessEqual(r['observationAgeMs'],10000);self.assertEqual(r['networkRequests'],8)
            self.assertTrue(r['snapshotPinnedAcrossRpc'])
            for k in ('transactionsSent','signaturesCreated','reservationsReleasedThisRun','replacementAuthorized'):self.assertFalse(r[k])

    def test_sqlite_writer_is_excluded_during_each_rpc_read(self):
        with signed_case() as c:
            c.now+=30000;ctx=fixture(c);checked=[]
            def collision(q,v):
                db=sqlite3.connect(c.path,timeout=0,isolation_level=None)
                try:
                    with self.assertRaises(sqlite3.OperationalError):db.execute('BEGIN IMMEDIATE')
                    checked.append(q['method'])
                finally:db.close()
                return v
            r=self.run_retire(c,Replies(c,ctx,collision))
            self.assertEqual(r['state'],'exit-retired-held',r);self.assertEqual(checked,list(m.expiry.ORDER))

    def test_ack_change_during_rpc_is_rechecked_without_second_full_replay(self):
        with signed_case() as c:
            c.now+=30000;ctx=fixture(c);before=c.path.read_bytes()
            def corrupt(q,v):
                if q['id']==8:(c.path.parent/m.history.backend.ACK).write_text('{}')
                return v
            r=self.run_retire(c,Replies(c,ctx,corrupt))
            self.assertEqual(r['state'],'retirement-refused-held',r);self.assertEqual(r['stage'],'precommit')
            self.assertFalse(r['recorded']);self.assertEqual(c.path.read_bytes(),before)

    def test_slow_precommit_still_rejects_and_reports_fixed_reason(self):
        with signed_case() as c:
            c.now+=30000;ctx=fixture(c);original=m._persist;before=files(c)
            def slow(*a,**kw):c.now+=10001;return original(*a,**kw)
            with patch.object(m,'_persist',side_effect=slow):r=self.run_retire(c,Replies(c,ctx))
            self.assertEqual(r['state'],'retirement-refused-held',r)
            self.assertEqual(r['diagnosticCode'],'retirement-evidence-stale');self.assertEqual(r['observationAgeMs'],10001)
            self.assertEqual(files(c),before)

    def test_local_timeout_sends_no_requests_and_provider_timeout_releases_writer(self):
        with signed_case() as c:
            c.now+=30000;ctx=fixture(c);before=files(c);original=m.expiry.context;ticks=[0]
            def slow(*a,**kw):v=original(*a,**kw);ticks[0]=121;return v
            rpc=Replies(c,ctx)
            with patch.object(m.expiry,'context',side_effect=slow):r=self.run_retire(c,rpc,lambda:ticks[0])
            self.assertEqual(r['diagnosticCode'],'retirement-operation-budget');self.assertEqual(rpc.calls,[])
            class Failed:
                def open(self,*a,**kw):raise TimeoutError('private provider text')
            r=self.run_retire(c,Failed());self.assertEqual(r['state'],'retirement-refused-held')
            self.assertEqual(files(c),before)
            db=sqlite3.connect(c.path,timeout=0,isolation_level=None)
            try:db.execute('BEGIN IMMEDIATE');db.execute('ROLLBACK')
            finally:db.close()

    def test_diagnostic_allowlist_never_exports_arbitrary_exception_text(self):
        self.assertEqual(m.reason(ValueError('private provider text')),'retirement-validation-unavailable')
        self.assertEqual(m.reason(ValueError('expiry-account-time')),'expiry-account-time')
        e=sqlite3.OperationalError('private pathname');e.sqlite_errorcode=sqlite3.SQLITE_BUSY
        self.assertEqual(m.reason(e),'sqlite-locked')


if __name__=='__main__':unittest.main()
