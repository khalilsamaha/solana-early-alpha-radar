"""Combined private recovery using disposable signed fixtures and synthetic RPC."""
from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import admission_recovery as m
import pre_sign_admission as admission
import test_restricted_signer as fixture
from admission_receipt_checks import receipt,failed
from admission_submission_checks import FakeOpener
from contract import digest
from pre_sign_admission import encoded

HERE=Path(__file__).resolve().parent


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch('socket.socket',side_effect=AssertionError('network')):
            fixture.RealSourceBackendTests.setUpClass.__func__(cls)
            helper=fixture.RealSourceBackendTests()
            helper.home=cls.template;helper.wallet=cls.wallet;helper.pool=cls.pool;helper.test_key=cls.test_key
            e,p,baseline=helper.prepare();cls.e=e
            with patch.object(admission,'BASELINE',baseline):
                m.restricted_signer.dispatch(cls.template,cls.wallet,cls.pool,e,p,allow_private_key_signing=True)
            path=m.accounting.submission.handoff.storage(cls.template)
            cls.stamp=m.NOW()
            b=admission.Admission(path,clock=lambda:cls.stamp)
            try:
                private=b.private_accounting_handoff();cls.package=receipt(e,private)
                cls.signed={'signedTransactionBase64':private['signedTransactionBase64']}
            finally:b.close()
            cls.admission_files={p.name:p.read_bytes() for p in path.parent.iterdir()}
            (cls.template/'signer.pk8').unlink();cls.test_key=None

    @classmethod
    def tearDownClass(cls):fixture.RealSourceBackendTests.tearDownClass.__func__(cls)

    def setUp(self):
        fixture.RealSourceBackendTests.setUp(self)
        self.sibling=m.accounting.submission.handoff.storage(self.home,create=True).parent
        for name,raw in self.admission_files.items():m.backup.write_bytes(self.sibling/name,raw)
        self.parent=Path(self.tmp.name)/'snapshots';self.parent.mkdir(mode=0o700);self.snapshot=self.parent/'first'
        self.c=SimpleNamespace(e=self.e,package=deepcopy(self.package),signed=self.signed,path=self.sibling/'entry.admission.sqlite')
        self.net=patch('socket.socket',side_effect=AssertionError('network'));self.net.start()
        self.key=patch('core.signer',side_effect=AssertionError('signing key'));self.key.start()

    def tearDown(self):
        self.key.stop();self.net.stop();fixture.RealSourceBackendTests.tearDown(self)

    def clock(self):return self.stamp
    def capture(self):return m.capture(self.home,self.wallet,self.pool,self.snapshot,clock=self.clock)
    def verify(self):return m.verify(self.snapshot,self.wallet,self.pool,clock=self.clock)
    def source_bytes(self):
        return {str(p):p.read_bytes() for root in (self.home,self.sibling) for p in root.rglob('*') if p.is_file()}
    def submit(self,**kw):
        return m.accounting.submission.submit(self.home,self.wallet,self.pool,allow_devnet_submit=True,opener=FakeOpener(self.c,**kw),clock=self.clock)
    def collect(self,**kw):
        self.submit()
        return m.accounting.submission.recover(self.home,self.wallet,self.pool,opener=FakeOpener(self.c,**kw),clock=self.clock)
    def settle(self):return m.accounting.apply(self.home,self.wallet,self.pool,clock=self.clock)
    def edit_db(self,fn,path=None):
        db=sqlite3.connect(path or self.c.path,isolation_level=None)
        try:fn(db)
        finally:db.close()

    def test_settled_restore_exact_no_key_read_network_or_source_mutation(self):
        self.collect();self.settle()
        m.backup.write_bytes(self.home/'signer.pk8',b'disposable private sentinel')
        before=self.source_bytes();read=m.private_file
        def no_keys(path,cap):
            self.assertNotEqual(Path(path).suffix,'.pk8');return read(path,cap)
        with patch.object(m,'private_file',side_effect=no_keys),patch.object(m.backup,'private_file',side_effect=no_keys):
            a=self.capture();b=self.verify()
        self.assertEqual(a['manifestSha256'],b['manifestSha256'])
        self.assertEqual(a['settlement']['state'],'entry-position-open')
        self.assertEqual(before,self.source_bytes());self.assertEqual(list(self.snapshot.rglob('*.pk8')),[])
        self.assertEqual(list(self.snapshot.glob('.admission-restore-check-*')),[])
        self.assertFalse(a['reservationReleased']);self.assertFalse(a['executionApproved'])

    def test_unknown_submission_preserved_not_reported_as_failed(self):
        self.submit(lost=True);a=self.capture()
        self.assertEqual(a['transport']['state'],'submission-unknown')
        self.assertFalse(a['settlement']['accountingRecorded']);self.assertEqual(self.verify()['transport'],a['transport'])

    def test_failed_entry_retains_accounting_and_commitments(self):
        self.collect(package=failed(self.c.package));self.settle();a=self.capture()
        self.assertEqual(a['settlement']['state'],'entry-failed-held')
        v=json.loads((self.snapshot/m.MANIFEST).read_text())
        self.assertEqual(v['projection']['reservedPrincipalAtomic'],'1000')
        self.assertFalse(a['reservationReleased']);self.assertEqual(self.verify()['settlement'],a['settlement'])

    def test_unknown_signing_without_ack_preserved_without_repair(self):
        self.edit_db(lambda db:db.execute('DELETE FROM admission_events WHERE seq>3'))
        for name in ('signer-attempt.json','signer-ack.json'):(self.sibling/name).unlink()
        before=self.source_bytes();a=self.capture()
        self.assertEqual(a['admissionState'],'signing-unknown');self.assertIsNone(a['transport'])
        self.assertFalse(a['signerAcknowledgmentPreserved']);self.assertEqual(before,self.source_bytes())

    def test_saved_ack_before_parent_response_is_preserved_not_applied(self):
        self.edit_db(lambda db:db.execute('DELETE FROM admission_events WHERE seq>3'))
        a=self.capture();self.assertEqual(a['admissionState'],'signing-unknown')
        self.assertTrue(a['signerAcknowledgmentPreserved']);self.assertIsNone(a['settlement'])
        self.assertEqual(self.verify()['admissionState'],'signing-unknown')

    def test_quarantined_submission_preserved_as_quarantined(self):
        self.submit(send=self.wallet);a=self.capture()
        self.assertEqual(a['transport']['state'],'quarantined')
        self.assertFalse(a['settlement']['accountingUsable']);self.assertEqual(self.verify()['transport'],a['transport'])

    def test_existing_stop_preserved_and_not_cleared(self):
        m.backup.write_bytes(self.home/'STOP',b'operator stop')
        a=self.capture();self.assertTrue(a['restoredCopyStopped'])
        self.assertEqual((self.snapshot/m.SOURCE/'STOP').read_bytes(),b'operator stop')

    def test_wrong_historical_binding_rejected_even_with_rehashed_admission(self):
        def mutate(db):
            previous=''
            for seq,at,raw in db.execute('SELECT seq,at_ms,value FROM admission_events ORDER BY seq').fetchall():
                v=json.loads(raw);v['ledgerHeadSha256']='0'*64
                h=digest(dict(seq=seq,atMs=at,value=v,previousHash=previous))
                db.execute('UPDATE admission_events SET value=?,previous_hash=?,hash=? WHERE seq=?',(encoded(v),previous,h,seq));previous=h
        self.edit_db(mutate)
        with self.assertRaisesRegex(ValueError,'admission-history-mismatch'):self.capture()
        self.assertFalse(self.snapshot.exists())

    def test_ack_mismatch_refused_and_no_seal(self):
        p=self.sibling/'signer-ack.json';v=json.loads(p.read_text());v['wireSha256']='0'*64;p.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'signer-ack-wire-hash'):self.capture()
        self.assertFalse(self.snapshot.exists())

    def test_sqlite_sidecars_and_unknown_sibling_files_refused_preserved(self):
        for name in ('entry.admission.sqlite-wal','entry.admission.sqlite-journal','private.pk8','extra.json'):
            with self.subTest(name=name):
                p=self.sibling/name;m.backup.write_bytes(p,b'keep')
                with self.assertRaises(ValueError):self.capture()
                self.assertEqual(p.read_bytes(),b'keep');p.unlink()
        self.assertFalse(self.snapshot.exists())

    def test_symlink_hardlink_and_permissions_refused(self):
        p=self.sibling/'signer-ack.json';raw=p.read_bytes();p.unlink();p.symlink_to(self.home/'wallet.json')
        with self.assertRaises(ValueError):self.capture()
        p.unlink();os.link(self.home/'wallet.json',p)
        with self.assertRaises(ValueError):self.capture()
        p.unlink();m.backup.write_bytes(p,raw);p.chmod(0o644)
        with self.assertRaises(ValueError):self.capture()

    def test_duplicate_destination_and_both_source_overlaps_refused(self):
        self.capture();seal=(self.snapshot/m.MANIFEST).read_bytes()
        with self.assertRaises(ValueError):self.capture()
        self.assertEqual((self.snapshot/m.MANIFEST).read_bytes(),seal)
        for source in (self.home,self.sibling):
            with self.assertRaisesRegex(ValueError,'snapshot-source-overlap'):
                m.capture(self.home,self.wallet,self.pool,source/'nested',clock=self.clock)

    def test_caps_fail_closed_before_snapshot(self):
        with patch.dict(m.ADMISSION_CAPS,{'entry.admission.sqlite':1}):
            with self.assertRaisesRegex(ValueError,'admission-file-cap'):self.capture()
        with patch.object(m,'MAX_TOTAL',1):
            with self.assertRaisesRegex(ValueError,'combined-snapshot-byte-cap'):self.capture()
        self.assertFalse(self.snapshot.exists())

    def test_copy_failure_preserves_unsealed_directory_and_refuses_reuse(self):
        with patch.object(m,'copy_admission',side_effect=OSError('copy failure')):
            with self.assertRaises(OSError):self.capture()
        self.assertTrue(self.snapshot.exists());self.assertFalse((self.snapshot/m.MANIFEST).exists())
        with self.assertRaises(ValueError):self.verify()
        with self.assertRaises(ValueError):self.capture()

    def test_source_change_during_copy_refuses_completion(self):
        copy=m.copy_admission
        def changed(source,target,inv):
            copy(source,target,inv)
            p=self.sibling/'signer-attempt.json';p.write_bytes(p.read_bytes()+b' ')
        with patch.object(m,'copy_admission',changed):
            with self.assertRaisesRegex(ValueError,'sources-changed-during-capture'):self.capture()
        self.assertFalse((self.snapshot/m.MANIFEST).exists())

    def test_source_lock_and_sqlite_shared_lock_exclude_writers(self):
        with m.backup.r.cycles.c.source_lock(self.home,self.wallet):
            with self.assertRaises(BlockingIOError):self.capture()
        copy=m.copy_admission;seen=[]
        def compete(source,target,inv):
            if source==self.sibling:
                db=sqlite3.connect(self.c.path,timeout=0,isolation_level=None)
                try:
                    with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):db.execute('BEGIN EXCLUSIVE')
                    seen.append(True)
                finally:db.close()
            copy(source,target,inv)
        with patch.object(m,'copy_admission',compete):self.capture()
        self.assertEqual(seen,[True])

    def test_tampered_inventory_or_manifest_path_never_extracted(self):
        self.capture();p=self.snapshot/m.MANIFEST;v=json.loads(p.read_text())
        v['inventories'][m.SIBLING]['files']['../../escape.json']={'bytes':0,'sha256':m.backup.sha(b'')}
        p.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'snapshot-integrity-mismatch'):self.verify()
        self.assertFalse((self.parent/'escape.json').exists())

    def test_rehashed_manifest_cannot_hide_settlement_tampering(self):
        self.collect();self.settle();self.capture()
        path=self.snapshot/m.SIBLING/'entry.admission.sqlite'
        def mutate(db):
            v=json.loads(db.execute('SELECT value FROM admission_entry_accounting').fetchone()[0]);v['accounting']['ownedAcquiredAtomic']='123456'
            db.execute('UPDATE admission_entry_accounting SET value=?,hash=?',(encoded(v),digest(v)))
        self.edit_db(mutate,path)
        p=self.snapshot/m.MANIFEST;v=json.loads(p.read_text())
        v['inventories']=m.inventories(self.snapshot/m.SOURCE,self.snapshot/m.SIBLING);p.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'entry-accounting-source-conflict'):self.verify()
        self.assertEqual(list(self.snapshot.glob('.admission-restore-check-*')),[])

    def test_isolated_verification_works_without_original_and_cli_is_private(self):
        self.collect();self.settle();a=self.capture();text=json.dumps(a)
        for private in (self.wallet,self.pool,str(self.home),self.signed['signedTransactionBase64']):self.assertNotIn(private,text)
        self.home.rename(self.home.with_name('original-unavailable'));self.sibling.rename(self.sibling.with_name('admission-unavailable'))
        out=self.parent/'report.gz';cmd=[sys.executable,'-E','-s',str(HERE/'admission_recovery_cli.py'),'--action','verify',
            '--snapshot',str(self.snapshot),'--wallet',self.wallet,'--pool',self.pool,'--output',str(out)]
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=45);self.assertEqual(r.returncode,0,r.stderr)
        raw=out.read_bytes();v=json.loads(gzip.decompress(raw));self.assertEqual(v['manifestSha256'],a['manifestSha256'])
        self.assertEqual(out.stat().st_mode&0o777,0o600)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
        cmd[-1]=str(self.snapshot/'unsafe-report.gz')
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)


if __name__=='__main__':unittest.main()
