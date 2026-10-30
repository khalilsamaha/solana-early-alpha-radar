"""Atomic entry settlement, source integrity and existing-inventory ownership."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import entry_accounting as m
from entry_accounting_checks import apply, status, collect, run
from admission_submission_checks import case, FakeOpener
from admission_receipt_checks import failed
from contract import digest
from pre_sign_admission import encoded

HERE=Path(__file__).resolve().parent


class AccountingTests(unittest.TestCase):
    def test_portable_checks(self):
        r=run();self.assertEqual(r['casesPassed'],15)
        self.assertEqual((r['networkRequests'],r['signaturesCreated'],r['transactionsSent']),(0,0,0))

    def test_no_receipt_status_does_not_create_table(self):
        with case() as c:
            before=c.path.read_bytes();self.assertFalse(status(c)['accountingRecorded'])
            self.assertEqual(before,c.path.read_bytes())

    def test_late_unknown_does_not_erase_owned_quantity(self):
        with case() as c:
            collect(c);r=apply(c);c.now+=1000;p=deepcopy(c.package)
            p['bundle']['rpcEvidence']['transaction']['result']=None
            m.submission.receipts.observe(c.home,c.wallet,c.pool,p,clock=lambda:c.now)
            self.assertEqual(status(c)['accounting'],r['accounting'])
            self.assertFalse(apply(c)['appliedThisRun'])

    def test_conflicting_terminal_quarantines_without_deleting_accounting(self):
        with case() as c:
            collect(c);r=apply(c);c.now+=1000
            m.submission.receipts.observe(c.home,c.wallet,c.pool,failed(c.package),clock=lambda:c.now)
            for value in (status(c),apply(c)):
                self.assertEqual(value['state'],'quarantined');self.assertTrue(value['accountingRecorded'])
                self.assertFalse(value['accountingUsable']);self.assertIsNone(value['accounting'])
                self.assertEqual(value['recordSha256'],r['recordSha256'])

    def test_later_durable_stop_does_not_invalidate_historical_settlement(self):
        with case() as c:
            collect(c);r=apply(c);c.now+=1000
            (c.home/'STOP').touch(mode=0o600)
            b=c.book()
            try:b.stop()
            finally:b.close()
            again=apply(c)
            self.assertTrue(again['stopRequested']);self.assertTrue(again['accountingUsable'])
            self.assertEqual(again['recordSha256'],r['recordSha256'])
            self.assertFalse(again['appliedThisRun'])

    def test_rehashed_amount_tampering_fails_source_replay(self):
        with case() as c:
            collect(c);apply(c);b=c.book()
            try:
                v=json.loads(b.db.execute('SELECT value FROM admission_entry_accounting').fetchone()[0])
                v['accounting']['ownedAcquiredAtomic']='999'
                b.db.execute('UPDATE admission_entry_accounting SET value=?,hash=?',(encoded(v),digest(v)))
            finally:b.close()
            for fn in (status,apply):
                with self.assertRaisesRegex(ValueError,'entry-accounting-source-conflict'):fn(c)

    def test_receipt_raw_tampering_cannot_be_hidden_by_accounting(self):
        with case() as c:
            collect(c);apply(c);b=c.book()
            try:b.db.execute("UPDATE admission_receipt_raw SET value='{}'")
            finally:b.close()
            with self.assertRaisesRegex(ValueError,'receipt-raw-identity'):status(c)

    def test_collector_tampering_cannot_be_hidden_by_accounting(self):
        with case() as c:
            collect(c);apply(c);b=c.book()
            try:b.db.execute("UPDATE admission_rpc_captures SET hash='changed'")
            finally:b.close()
            with self.assertRaisesRegex(ValueError,'collection-binding'):apply(c)

    def test_oversized_record_rejected_before_json_decode(self):
        with case() as c:
            collect(c);apply(c);b=c.book()
            try:b.db.execute('UPDATE admission_entry_accounting SET value=?',('x'*(m.MAX_RECORD+1),))
            finally:b.close()
            with self.assertRaisesRegex(ValueError,'entry-accounting-record'):status(c)

    def test_future_and_pre_evidence_record_times_refused(self):
        for offset in (1,-1):
            with self.subTest(offset=offset),case() as c:
                collect(c);apply(c);b=c.book()
                try:
                    v=json.loads(b.db.execute('SELECT value FROM admission_entry_accounting').fetchone()[0])
                    v['recordedAtMs']=c.now+offset
                    b.db.execute('UPDATE admission_entry_accounting SET value=?,hash=?',(encoded(v),digest(v)))
                finally:b.close()
                with self.assertRaises(ValueError):status(c)

    def test_scope_mismatch_refuses(self):
        with case() as c:
            with self.assertRaisesRegex(ValueError,'submission-source-scope'):
                m.apply(c.home,c.wallet,c.wallet,clock=lambda:c.now)

    def test_atomic_rollback_if_validation_after_insert_fails(self):
        with case() as c:
            collect(c);before=c.path.read_bytes()
            with patch.object(m,'public',side_effect=RuntimeError('crash before commit')):
                with self.assertRaises(RuntimeError):apply(c)
            self.assertEqual(c.path.read_bytes(),before)
            self.assertFalse(status(c)['accountingRecorded'])
            self.assertTrue(apply(c)['appliedThisRun'])

    def test_writer_exclusion_during_independent_read_only_replay(self):
        with case() as c:
            collect(c);review=m.review;observed=[]
            def guarded(reader):
                # Independent SQLite writer, not just the cooperating file lock.
                db=sqlite3.connect(c.path,timeout=0,isolation_level=None)
                try:
                    with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                        db.execute('BEGIN IMMEDIATE')
                    observed.append(True)
                finally:db.close()
                return review(reader)
            with patch.object(m,'review',guarded):self.assertTrue(apply(c)['accountingUsable'])
            self.assertEqual(observed,[True])

    def test_cooperating_concurrent_application_refused(self):
        with case() as c:
            collect(c);review=m.review
            def compete(reader):
                with self.assertRaises(BlockingIOError):apply(c)
                return review(reader)
            with patch.object(m,'review',compete):self.assertTrue(apply(c)['accountingUsable'])

    def test_process_death_after_commit_does_not_double_count(self):
        with case() as c:
            collect(c)
            code='''import os,sys
import entry_accounting as m
m.apply(sys.argv[1],sys.argv[2],sys.argv[3],clock=lambda:int(sys.argv[4]))
os._exit(73)
'''
            r=subprocess.run([sys.executable,'-E','-s','-c',code,str(c.home),c.wallet,c.pool,str(c.now)],cwd=HERE,capture_output=True)
            self.assertEqual(r.returncode,73,r.stderr)
            before=c.path.read_bytes();r=apply(c)
            self.assertFalse(r['appliedThisRun']);self.assertEqual(r['accounting']['entryFeePaidLamports'],'5001')
            self.assertEqual(c.path.read_bytes(),before)

    def test_cli_only_synthetic_and_exclusive_private_output(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(HERE/'entry_accounting_cli.py'),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(raw))['casesPassed'],15)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
            for flag in ('--execute','--directory','--wallet','--allow-devnet-submit','--receipt'):
                self.assertNotEqual(subprocess.run(cmd+[flag],capture_output=True).returncode,0)


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_restricted_signer as fixtures
        fixtures.RealSourceBackendTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):
        import test_restricted_signer as fixtures
        fixtures.RealSourceBackendTests.tearDownClass.__func__(cls)
    def setUp(self):
        import test_restricted_signer as fixtures
        fixtures.RealSourceBackendTests.setUp(self)
    def tearDown(self):
        import test_restricted_signer as fixtures
        fixtures.RealSourceBackendTests.tearDown(self)
    def files(self):
        import test_restricted_signer as fixtures
        return fixtures.RealSourceBackendTests.files(self)
    def evidence(self):
        import test_restricted_signer as fixtures
        return fixtures.RealSourceBackendTests.evidence(self)

    def test_source_signer_collector_settlement_preserves_preexisting_inventory(self):
        from types import SimpleNamespace
        import test_restricted_signer as fixtures
        import pre_sign_admission as admission
        from admission_receipt_checks import receipt
        e,p,baseline=fixtures.RealSourceBackendTests.prepare(self);before=self.files()
        with patch.object(admission,'BASELINE',baseline),patch('socket.socket',side_effect=AssertionError('network')):
            m.submission.restricted_signer.dispatch(self.home,self.wallet,self.pool,e,p,allow_private_key_signing=True)
            b=admission.Admission(m.submission.handoff.storage(self.home))
            try:private=b.private_accounting_handoff();package=receipt(e,private)
            finally:b.close()
            c=SimpleNamespace(e=e,package=package,signed={'signedTransactionBase64':private['signedTransactionBase64']},path=m.submission.handoff.storage(self.home))
            m.submission.submit(self.home,self.wallet,self.pool,allow_devnet_submit=True,opener=FakeOpener(c))
            m.submission.recover(self.home,self.wallet,self.pool,opener=FakeOpener(c))
            with patch('core.signer',side_effect=AssertionError('key')):
                r=m.apply(self.home,self.wallet,self.pool)
            a=r['accounting'];self.assertGreater(int(a['preexistingDestinationAtomic']),0)
            self.assertEqual(a['ownedAcquiredAtomic'],'996')
            self.assertGreater(int(a['ownedAcquiredAtomic']),int(private['intent']['minimumOutputAtomic']))
            self.assertEqual(a['preexistingDestinationAtomic'],private['intent']['destination']['preAmountAtomic'])
            self.assertNotEqual(int(a['ownedAcquiredAtomic']),int(a['ownedAcquiredAtomic'])+int(a['preexistingDestinationAtomic']))
            self.assertEqual(r['state'],'entry-position-open');self.assertFalse(r['allocationTransferred'])
            self.assertEqual(before,self.files())


if __name__=='__main__':unittest.main()
