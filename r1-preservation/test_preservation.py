import copy
import fcntl
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import preserve as p
import contract
from capture import CaptureError,canonical,digest,exclusive_file
from fixture_support import make,save


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='r1-preserve-test-');self.root=Path(self.tmp.name)
        self.contract=self.root/'contract';self.contract.mkdir(mode=0o700)
        self.sha=contract.freeze(self.contract)['contract_sha256']
        self.contract_path=self.contract/'contract.json'
        self.source_digest=contract.load(self.contract_path,self.sha)['source_digest']
    def tearDown(self):self.tmp.cleanup()
    def fixture(self,mode='complete'):
        root=self.root/'input';receipt=make(root,mode,self.sha,self.source_digest);return root,receipt
    def save(self,root):return save(root,self.contract_path,self.sha,self.root/'preserved')
    def raw(self):return (self.root/'preserved/evidence.zip').read_bytes()

    def test_complete_roundtrip_preserves_every_member_and_replays(self):
        root,_=self.fixture();r=self.save(root)
        self.assertEqual(r['assessment']['classification'],'complete-replayed-evidence')
        restored=p.restore(self.root/'preserved/evidence.zip',r['archive_sha256'],self.root/'restored')
        self.assertEqual(restored['assessment'],r['assessment'])
        self.assertEqual((self.root/'restored/capture.db').read_bytes(),(root/'data/capture/ticks.db').read_bytes())
        self.assertEqual((self.root/'restored/measurement.jsonl').read_bytes(),(root/'data/session.jsonl').read_bytes())
        self.assertFalse(restored['automatic_resume_allowed'])

    def test_sigkill_partial_database_and_pending_intent_are_quarantined(self):
        root,fixture=self.fixture('interrupted');before=(root/'data/capture/ticks.db').read_bytes()
        r=self.save(root);a=r['assessment']
        self.assertTrue(fixture['writer_killed']);self.assertTrue(fixture['writer_reaped'])
        self.assertEqual(a['classification'],'quarantined-incomplete-evidence')
        self.assertEqual(a['lifecycle_state']['pending_action'],'retire_research')
        self.assertIn('complete-session-replay-unavailable',a['reasons'])
        self.assertEqual((root/'data/capture/ticks.db').read_bytes(),before)
        p.restore(self.root/'preserved/evidence.zip',r['archive_sha256'],self.root/'restored')
        self.assertEqual((self.root/'restored/capture.db').read_bytes(),before)

    def test_native_kill_during_sqlite_transaction_preserves_real_rollback_file(self):
        root,fixture=self.fixture('rollback')
        self.assertTrue(fixture['writer_killed'])
        raw=(root/'data/capture/ticks.db-journal').read_bytes();self.assertTrue(raw)
        r=self.save(root)
        self.assertIn('sqlite-rollback-evidence-present',r['assessment']['reasons'])
        p.restore(self.root/'preserved/evidence.zip',r['archive_sha256'],self.root/'restored')
        self.assertEqual((self.root/'restored/capture-journal').read_bytes(),raw)
        self.assertEqual((root/'data/capture/ticks.db-journal').read_bytes(),raw)

    def test_rollback_bytes_preserved_without_sqlite_replay(self):
        root,_=self.fixture();raw=b'partial rollback evidence\x00\xff'
        exclusive_file(root/'data/capture/ticks.db-journal',raw)
        with patch.object(p.session_bundle,'export_session',side_effect=AssertionError('must not recover')) as replay:
            r=self.save(root);replay.assert_not_called()
        self.assertEqual(r['assessment']['reasons'],['sqlite-rollback-evidence-present'])
        data,_=p.verify(self.raw());self.assertEqual(data['capture-journal'],raw)

    def test_torn_measurement_and_corrupt_database_are_not_repaired(self):
        for mode in ('torn','database'):
            with self.subTest(mode=mode):
                folder=self.root/mode;folder.mkdir(mode=0o700)
                root=folder/'input';make(root,'complete',self.sha,self.source_digest)
                target=root/('data/session.jsonl' if mode=='torn' else 'data/capture/ticks.db')
                raw=target.read_bytes()[:-7] if mode=='torn' else b'not a database'
                target.write_bytes(raw)
                r=save(root,self.contract_path,self.sha,folder/'output')
                self.assertEqual(r['assessment']['classification'],'quarantined-incomplete-evidence')
                self.assertEqual(target.read_bytes(),raw)

    def test_torn_lifecycle_is_retained_and_blocks_completion(self):
        root,_=self.fixture();path=root/'lifecycle/events.jsonl';path.write_bytes(path.read_bytes()[:-3])
        r=self.save(root);self.assertIn('lifecycle-unverifiable',r['assessment']['reasons'])
        data,_=p.verify(self.raw());self.assertEqual(data['lifecycle.jsonl'],path.read_bytes())

    def test_missing_measurement_is_recorded_not_fabricated(self):
        root,_=self.fixture();(root/'data/session.jsonl').unlink()
        r=self.save(root);self.assertIn('measurement.jsonl',r['absent'])
        self.assertIn('capture-or-measurement-missing',r['assessment']['reasons'])
        data,_=p.verify(self.raw());self.assertNotIn('measurement.jsonl',data)

    def test_contract_binding_mismatch_quarantines(self):
        root=self.root/'input';make(root,'complete','1'*64,self.source_digest)
        r=self.save(root);self.assertIn('lifecycle-contract-binding-mismatch',r['assessment']['reasons'])

    def test_active_registry_and_capture_locks_refuse_preservation(self):
        root,_=self.fixture()
        for path in (root/'registry/r1-supervisor.lock',root/'data/capture/capture.lock'):
            fd=os.open(path,os.O_RDONLY)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaises(CaptureError):self.save(root)
                self.assertFalse((self.root/'preserved').exists())
            finally:os.close(fd)

    def test_missing_source_lock_is_not_created(self):
        root,_=self.fixture();lock=root/'data/capture/capture.lock';lock.unlink()
        with self.assertRaises(FileNotFoundError):self.save(root)
        self.assertFalse(lock.exists())

    def test_symlink_hardlink_and_fifo_refused(self):
        root,_=self.fixture();path=root/'data/session.jsonl';backup=root/'data/original';path.rename(backup)
        path.symlink_to(backup)
        with self.assertRaises(CaptureError):self.save(root)
        path.unlink();os.link(backup,path)
        with self.assertRaises(CaptureError):self.save(root)
        path.unlink();os.mkfifo(path,0o600)
        with self.assertRaises(CaptureError):self.save(root)

    def test_oversized_member_and_unexpected_capture_file_refused(self):
        root,_=self.fixture();journal=root/'data/session.jsonl'
        with journal.open('r+b') as f:f.truncate(p.CAPS['measurement.jsonl']+1)
        with self.assertRaises(CaptureError):self.save(root)
        journal.write_bytes(b'')
        exclusive_file(root/'data/capture/ticks.db-wal',b'unsupported')
        with self.assertRaises(CaptureError):self.save(root)

    def test_source_change_during_snapshot_refused(self):
        root,_=self.fixture();original=p.snapshot;calls=0
        def changing(*args):
            nonlocal calls
            calls+=1
            if calls==2:
                path=root/'data/session.jsonl';path.write_bytes(path.read_bytes()+b' ')
            return original(*args)
        with patch.object(p,'snapshot',side_effect=changing):
            with self.assertRaises(CaptureError):self.save(root)
        self.assertFalse((self.root/'preserved').exists())

    def test_output_inside_source_and_output_reuse_refused(self):
        root,_=self.fixture()
        with self.assertRaises(CaptureError):save(root,self.contract_path,self.sha,root/'data/output')
        self.save(root);before=self.raw()
        with self.assertRaises(FileExistsError):self.save(root)
        self.assertEqual(self.raw(),before)

    def test_wrong_contract_and_archive_hash_refused(self):
        root,_=self.fixture()
        with self.assertRaises(CaptureError):save(root,self.contract_path,'0'*64,self.root/'wrong')
        self.save(root)
        with self.assertRaises(CaptureError):p.restore(self.root/'preserved/evidence.zip','0'*64,self.root/'restored')
        self.assertFalse((self.root/'restored').exists())

    def test_classification_cannot_be_forged(self):
        root,_=self.fixture('interrupted');self.save(root)
        contents=p.unpack(self.raw());manifest=p.strict_json(contents['manifest.json'])
        manifest['assessment']['classification']='complete-replayed-evidence'
        manifest['assessment']['reasons']=[]
        contents['manifest.json']=(canonical(manifest)+'\n').encode()
        with self.assertRaises(CaptureError):p.verify(p.pack(contents))

    def test_archive_paths_duplicates_compression_and_trailers_refused(self):
        root,_=self.fixture();self.save(root);contents=p.unpack(self.raw())
        for variant in ('path','duplicate','compression','trailer'):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as archive:
                for name,value in contents.items():
                    info=zipfile.ZipInfo('../escape' if variant=='path' and name=='capture.db' else name,date_time=(1980,1,1,0,0,0))
                    info.create_system=3;info.external_attr=(stat.S_IFREG|0o600)<<16
                    info.compress_type=zipfile.ZIP_DEFLATED if variant=='compression' else zipfile.ZIP_STORED
                    archive.writestr(info,value)
                if variant=='duplicate':
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore',UserWarning);archive.writestr('contract.json',contents['contract.json'])
            raw=stream.getvalue()+(b'extra' if variant=='trailer' else b'')
            with self.assertRaises(CaptureError):p.verify(raw)

    def test_source_pin_drift_refuses_restore(self):
        root,_=self.fixture();self.save(root);changed=p.pins();changed['r1-preservation/preserve.py']='0'*64
        with patch.object(p,'pins',return_value=changed):
            with self.assertRaises(CaptureError):p.verify(self.raw())


if __name__=='__main__':unittest.main()
