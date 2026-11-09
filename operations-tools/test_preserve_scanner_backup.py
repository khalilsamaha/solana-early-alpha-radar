from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import launch_audit
import preserve_scanner_backup as preservation


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.backups=self.root/'backups';self.backups.mkdir()
        self.source=self.backups/'radar.sqlite';self.output=self.root/'preserved'
        with closing(sqlite3.connect(self.source)) as db, db:
            db.executescript('CREATE TABLE kv(key TEXT PRIMARY KEY,data TEXT);'
                'CREATE TABLE launch_registry(mint TEXT PRIMARY KEY,received_at INTEGER,data TEXT);'
                'CREATE INDEX launch_registry_received ON launch_registry(received_at);')
            now=int(time.time()*1000)-86400000
            row={'version':'launch-registry-1','mint':'mint','receivedAt':now,'availableAt':now,'fields':{}}
            db.execute('INSERT INTO launch_registry VALUES(?,?,?)',('mint',now,json.dumps(row)))
        os.chmod(self.source,0o640);self.age()
        s=self.source.stat();self.identity=f'{s.st_dev}:{s.st_ino}'

    def age(self):os.utime(self.source,(time.time()-600,time.time()-600))
    def run_copy(self):return preservation.preserve(self.backups,self.identity,self.output)

    def test_independent_verified_copy_survives_original_removal_and_supports_audit(self):
        original=self.source.read_bytes();before=preservation.fingerprint(self.source.stat())
        r=self.run_copy();target=Path(r['preservedDatabase'])
        self.assertEqual(r['sha256'],hashlib.sha256(original).hexdigest())
        self.assertEqual(target.read_bytes(),original);self.assertEqual(r['sourceBytes'],len(original))
        self.assertNotEqual(target.stat().st_ino,self.source.stat().st_ino)
        self.assertEqual(preservation.fingerprint(self.source.stat()),before)
        self.assertEqual(self.source.stat().st_mode&0o777,0o640)
        self.assertEqual(target.stat().st_mode&0o777,0o600);self.assertEqual(self.output.stat().st_mode&0o777,0o700)
        self.assertEqual(json.loads((self.output/'preservation.json').read_text()),r)
        self.assertFalse(r['payloadsValidated']);self.assertFalse(r['sqliteIntegrityChecked'])
        self.source.unlink()
        self.assertEqual(launch_audit.audit(target,hours=720)['receivedCreationsInWindow'],1)

    def test_existing_destination_is_never_replaced(self):
        self.output.mkdir();marker=self.output/'keep';marker.write_text('original')
        with self.assertRaises(FileExistsError):self.run_copy()
        self.assertEqual(marker.read_text(),'original')

    def test_wrong_or_ambiguous_identity_and_symlink_source_refused(self):
        with self.assertRaisesRegex(ValueError,'exactly one'):preservation.locate(self.backups,'1:2')
        alias=self.backups/'alias.sqlite';os.link(self.source,alias)
        with self.assertRaisesRegex(ValueError,'exactly one'):self.run_copy()
        alias.unlink();renamed=self.backups/'original.bin';self.source.rename(renamed);self.source.symlink_to(renamed)
        with self.assertRaisesRegex(ValueError,'exactly one'):self.run_copy()

    def test_sidecars_recent_and_future_sources_refused(self):
        for suffix in ('-wal','-shm','-journal'):
            p=Path(str(self.source)+suffix);p.touch()
            with self.assertRaisesRegex(ValueError,'sidecars'):self.run_copy()
            p.unlink()
        for age in (0,-600):
            os.utime(self.source,(time.time()-age,time.time()-age))
            with self.assertRaisesRegex(ValueError,'too recent'):self.run_copy()

    def test_byte_and_space_caps_refuse_before_creating_output(self):
        with patch.object(preservation,'MAX_BYTES',1):
            with self.assertRaisesRegex(ValueError,'byte cap'):self.run_copy()
        from types import SimpleNamespace
        with patch.object(preservation.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError,'space'):self.run_copy()
        self.assertFalse(self.output.exists())

    def test_copy_deadline_cannot_publish_completion(self):
        with patch.object(preservation.time,'monotonic',side_effect=[0,181]):
            with self.assertRaisesRegex(TimeoutError,'deadline'):self.run_copy()
        self.assertFalse((self.output/'preservation.json').exists())
        self.assertTrue((self.output/'scanner.sqlite.incomplete').exists())

    def test_corrupt_copy_is_detected_by_independent_reread(self):
        original_open=Path.open
        def open_file(path,*args,**kwargs):
            if path.name=='scanner.sqlite.incomplete':
                with original_open(path,'r+b') as f:f.write(b'corruption')
            return original_open(path,*args,**kwargs)
        with patch.object(Path,'open',open_file):
            with self.assertRaisesRegex(ValueError,'hash mismatch'):self.run_copy()
        self.assertFalse((self.output/'preservation.json').exists())

    def test_source_change_during_copy_prevents_completion(self):
        original_sync=os.fsync;changed=[]
        def sync(fd):
            original_sync(fd)
            if not changed:
                changed.append(True)
                with self.source.open('ab') as f:f.write(b'changed')
        with patch.object(preservation.os,'fsync',side_effect=sync):
            with self.assertRaisesRegex(ValueError,'changed during copy'):self.run_copy()
        self.assertFalse((self.output/'preservation.json').exists())

    def test_directory_cap_and_symlink_output_parent_refused(self):
        for i in range(512):(self.backups/str(i)).touch()
        with self.assertRaisesRegex(ValueError,'directory cap'):self.run_copy()
        for i in range(512):(self.backups/str(i)).unlink()
        alias=self.root/'alias';alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'output parent'):preservation.preserve(self.backups,self.identity,alias/'new')

if __name__=='__main__':unittest.main()
