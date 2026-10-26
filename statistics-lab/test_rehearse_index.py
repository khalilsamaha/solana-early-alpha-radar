import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('rehearse_index',Path(__file__).with_name('rehearse-index.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.backups=self.root/'backups';self.backups.mkdir()
        self.copy=self.root/'work';self.copy.mkdir()
        self.file=self.backups/'auto-20261026T010000Z-12345678.sqlite'
        db=sqlite3.connect(self.file)
        db.executescript('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,id TEXT NOT NULL,at INTEGER NOT NULL,data TEXT NOT NULL,UNIQUE(kind,id));CREATE INDEX events_kind_seq ON events(kind,seq);CREATE INDEX events_at ON events(kind,at);CREATE TABLE candidates(id);CREATE TABLE outbox(id);CREATE TABLE kv(id);')
        db.executemany('INSERT INTO events(kind,id,at,data) VALUES(?,?,?,?)',[(k,str(i),i,'x'*2048) for i,k in enumerate(m.index.KINDS+('snapshots',)*32)])
        db.commit();db.close()
        self.meta={'success':True,'state':'complete','method':'host-snapshot-v1','finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'backup':str(self.file),'bytes':self.file.stat().st_size,'counts':{'events':36,'candidates':0,'outbox':0,'kv':0}}
        self.save()
    def save(self): (self.backups/'last-run.json').write_text(json.dumps(self.meta))
    def run_copy(self,**kw):return m.run_copy(self.backups,self.copy,free_bytes=lambda:10**12,**kw)
    def test_real_copy_build_verification_preserves_original_bytes_and_schema(self):
        before=hashlib.sha256(self.file.read_bytes()).hexdigest();stamp=m.stamp(self.file)
        r=self.run_copy()
        self.assertEqual(r['state'],'completed',r);self.assertTrue(r['backupMetadataUnchanged'])
        self.assertEqual(r['installation']['deadlineSeconds'],180);self.assertEqual(r['installation']['indexedRows'],4)
        self.assertEqual(r['verifiedCounts'],self.meta['counts']);self.assertEqual(m.stamp(self.file),stamp)
        self.assertEqual(hashlib.sha256(self.file.read_bytes()).hexdigest(),before)
        with sqlite3.connect(self.file) as db:self.assertFalse(db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(m.index.NAME,)).fetchone())
        self.assertFalse(r['liveDatabaseOpened']);self.assertFalse(r['scannerStopped']);self.assertEqual(r['networkRequests'],0)
    def test_stale_failed_future_and_malformed_status_refused(self):
        cases=[{'success':False},{'state':'running'},{'finished_at':(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=2)).isoformat()},{'finished_at':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=1)).isoformat()},{'counts':{}},{'bytes':True}]
        original=self.meta.copy()
        for change in cases:
            self.meta=original|change;self.save()
            self.assertEqual(self.run_copy()['state'],'stopped');self.assertFalse((self.copy/'copy.sqlite').exists())
        (self.backups/'last-run.json').write_text('[]')
        self.assertEqual(self.run_copy()['error'],'backup-status-invalid')
    def test_external_path_symlink_hardlink_and_sidecar_refused(self):
        self.meta['backup']=str(self.root/self.file.name);self.save()
        self.assertEqual(self.run_copy()['error'],'backup-path-refused')
        self.meta['backup']=str(self.file);self.save()
        side=Path(str(self.file)+'-wal');side.touch()
        self.assertEqual(self.run_copy()['error'],'standalone-backup-required');side.unlink()
        hard=self.root/'hard';hard.hardlink_to(self.file)
        self.assertEqual(self.run_copy()['error'],'backup-path-refused');hard.unlink()
        original=self.file.rename(self.root/'original');self.file.symlink_to(original)
        self.assertEqual(self.run_copy()['error'],'backup-path-refused')
    def test_disk_reserve_and_copy_deadline(self):
        r=m.run_copy(self.backups,self.copy,free_bytes=lambda:0)
        self.assertEqual(r['error'],'rehearsal-disk-reserve-required')
        with self.assertRaisesRegex(m.Refused,'copy-timeout'):
            m.bounded_copy(self.file,self.copy/'timed',m.stamp(self.file),clock=iter([0,121]).__next__)
    def test_changed_backup_is_refused(self):
        signature=m.stamp(self.file);self.file.touch()
        with self.assertRaisesRegex(m.Refused,'backup-changed'):
            m.bounded_copy(self.file,self.copy/'changed',signature)
    def test_incorrect_counts_and_corrupt_copy_refused(self):
        self.meta['counts']['events']=37;self.save()
        self.assertEqual(self.run_copy()['error'],'copy-counts-mismatch')
        broken=self.copy/'broken.sqlite';broken.write_bytes(b'not sqlite')
        with self.assertRaises(sqlite3.Error):m.verify(broken,self.meta['counts'])
    def test_build_failure_and_backup_replacement_remain_explicit(self):
        with patch.object(m.index,'run_index',return_value={'state':'stopped','error':'index-build-timeout'}):
            r=self.run_copy()
        self.assertEqual(r['state'],'stopped');self.assertEqual(r['installation']['error'],'index-build-timeout')
        self.assertTrue(r['backupMetadataUnchanged'])
    def test_parent_success_and_timeout_remove_only_own_copy(self):
        for timeout in (False,True):
            paths=[]
            def runner(args,**kw):
                directory=Path(args[-1]);paths.append(directory)
                self.assertEqual(kw['timeout'],540);self.assertNotIn('docker',args)
                (directory/'copy.sqlite').write_bytes(b'test')
                m.write_status(directory/'status.json',{'format':'statistics-index-rehearsal-1','state':'completed','phase':'verify-after'})
                if timeout:raise subprocess.TimeoutExpired(args,540)
            r=m.orchestrate(runner=runner)
            self.assertEqual(r['state'],'stopped' if timeout else 'completed')
            self.assertTrue(r['temporaryCopyRemoved']);self.assertFalse(paths[0].exists());self.assertTrue(self.file.exists())
    def test_default_live_deadline_and_invalid_override(self):
        r=m.index.run_index(self.file)
        self.assertEqual(r['deadlineSeconds'],30)
        self.assertEqual(m.index.run_index(self.file,True,deadline_seconds=999)['error'],'deadline-refused')
    def test_public_cli_has_no_source_or_deadline_override(self):
        cli=Path(m.__file__)
        r=subprocess.run(['python3',str(cli),'--help'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0);self.assertNotIn('--source',r.stdout);self.assertNotIn('--deadline',r.stdout)

if __name__=='__main__':unittest.main()
