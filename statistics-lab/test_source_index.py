import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('source_index',Path(__file__).with_name('source-index.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SCHEMA='CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,id TEXT NOT NULL,at INTEGER NOT NULL,data TEXT NOT NULL,UNIQUE(kind,id));CREATE INDEX events_kind_seq ON events(kind,seq);CREATE INDEX events_at ON events(kind,at);'

class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.file=self.root/'radar.sqlite'
        self.db=sqlite3.connect(self.file,isolation_level=None);self.addCleanup(self.db.close)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.executescript(SCHEMA)
        for i,k in enumerate(m.KINDS+('snapshots',)):
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?)',(i+1,k,'id-'+str(i),1000-i,'{"test":true}'))
    def rows(self):return self.db.execute('SELECT * FROM events ORDER BY seq').fetchall()
    def apply(self,**kw):return m.run_index(self.file,True,**kw)
    def exists(self):return self.db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(m.NAME,)).fetchone()
    def test_inspection_is_read_only_and_does_not_build_index(self):
        before=self.rows();r=m.run_index(self.file)
        self.assertEqual(r['state'],'index-absent');self.assertFalse(self.exists());self.assertEqual(self.rows(),before)
    def test_apply_preserves_rows_and_is_idempotent(self):
        before=self.rows();r=self.apply()
        self.assertEqual(r['state'],'index-installed');self.assertTrue(r['applied']);self.assertEqual(r['indexedRows'],4)
        self.assertEqual(self.rows(),before)
        self.assertEqual(self.apply()['state'],'already-present');self.assertEqual(m.run_index(self.file)['state'],'already-present')
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_index_is_partial_and_tracks_future_inserts_and_retention(self):
        self.apply()
        where="kind IN ('alerts','outcomes','research-entries','research-outcomes')"
        count=lambda:self.db.execute('SELECT count(*) FROM events INDEXED BY '+m.NAME+' WHERE '+where).fetchone()[0]
        self.assertEqual(count(),4)
        self.db.execute("INSERT INTO events(kind,id,at,data) VALUES('alerts','new',900,'{}')")
        self.db.execute("INSERT INTO events(kind,id,at,data) VALUES('snapshots','another',900,'{}')")
        self.assertEqual(count(),5);self.db.execute("DELETE FROM events WHERE kind='research-outcomes'");self.assertEqual(count(),4)
    def test_same_named_wrong_index_is_preserved_and_rejected(self):
        self.db.execute('CREATE INDEX '+m.NAME+' ON events(at)');sql=self.db.execute('SELECT sql FROM sqlite_master WHERE name=?',(m.NAME,)).fetchone()[0]
        self.assertEqual(self.apply()['error'],'source-index-mismatch')
        self.assertEqual(self.db.execute('SELECT sql FROM sqlite_master WHERE name=?',(m.NAME,)).fetchone()[0],sql)
    def test_readonly_mode_checks_collision_too(self):
        self.db.execute('CREATE TABLE '+m.NAME+'(x)')
        self.assertEqual(m.run_index(self.file)['error'],'source-index-mismatch')
    def test_busy_writer_is_not_retried(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:self.assertEqual(self.apply()['error'],'source-busy')
        finally:self.db.execute('ROLLBACK')
        self.assertFalse(self.exists())
    def test_disk_reserve_refuses_without_schema_writes(self):
        self.assertEqual(self.apply(free_bytes=lambda:0)['error'],'disk-reserve-required');self.assertFalse(self.exists())
    def test_non_wal_and_wrong_schema_are_refused(self):
        self.db.execute('PRAGMA journal_mode=DELETE');self.assertEqual(self.apply()['error'],'wal-required')
        self.db.execute('DROP INDEX events_kind_seq');self.assertEqual(self.apply()['error'],'source-schema-refused')
    def test_symlinks_and_hardlinks_are_refused(self):
        symlink=self.root/'link';symlink.symlink_to(self.file)
        self.assertEqual(m.run_index(symlink,True)['error'],'source-path-refused')
        hard=self.root/'hard';hard.hardlink_to(self.file)
        self.assertEqual(self.apply()['error'],'source-path-refused')
    def test_progress_interrupt_during_actual_index_build_rolls_back(self):
        self.db.executemany("INSERT INTO events(kind,id,at,data) VALUES('research-outcomes',?,?,?)",((str(i),i,'{}') for i in range(3000)))
        before=self.rows();state={'building':False};original=sqlite3.connect
        def connect(*a,**kw):
            db=original(*a,**kw)
            db.set_trace_callback(lambda sql:state.update(building=True) if sql==m.DDL else None)
            return db
        with patch.object(m.sqlite3,'connect',connect):r=self.apply(clock=lambda:31 if state['building'] else 0)
        self.assertEqual(r['error'],'index-build-timeout');self.assertTrue(state['building']);self.assertFalse(self.exists());self.assertEqual(self.rows(),before)
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_wrong_owner_is_refused(self):
        with patch.object(m.os,'geteuid',return_value=self.file.stat().st_uid+1):r=self.apply()
        self.assertEqual(r['error'],'database-owner-required');self.assertFalse(self.exists())
    def test_schema_sql_matches_node_reader_exactly(self):
        sql=subprocess.check_output(['node','--input-type=module','-e',"import {CREATE_IDENTITY_INDEX} from './compact-store.mjs';console.log(CREATE_IDENTITY_INDEX)"],cwd=Path(__file__).parent,text=True).strip()
        self.assertEqual(sql,m.DDL)
    def test_discovery_resolves_only_one_running_writable_data_mount(self):
        calls=[]
        def run(args,**kw):
            calls.append(args)
            out='a'*64 if args[1]=='compose' else json.dumps([{'State':{'Running':True},'Mounts':[{'Destination':'/app/data','Source':str(self.root),'RW':True}]}])
            return subprocess.CompletedProcess(args,0,stdout=out)
        self.assertEqual(m.discover(self.root,run),self.file);self.assertEqual(len(calls),2)
        def duplicate(args,**kw):return subprocess.CompletedProcess(args,0,stdout='abc\ndef')
        with self.assertRaises(m.Refused):m.discover(self.root,duplicate)
    def test_changed_identity_after_lock_refuses_and_releases_lock(self):
        original=m.identity(self.file)
        with patch.object(m,'identity',side_effect=[original,(-1,-1)]):r=self.apply()
        self.assertEqual(r['error'],'source-replaced');self.assertFalse(self.exists())
        self.db.execute('BEGIN IMMEDIATE');self.db.execute('ROLLBACK')
    def test_row_limit_refuses_index_creation(self):
        self.db.execute('BEGIN')
        self.db.executemany("INSERT INTO events(kind,id,at,data) VALUES('alerts',?,1,'{}')",((str(i),) for i in range(100000)))
        self.db.execute('COMMIT')
        self.assertEqual(self.apply()['error'],'row-limit');self.assertFalse(self.exists())
    def test_launcher_runs_root_worker_for_volume_access_and_repairs_sidecar_ownership(self):
        calls=[]
        def child(args,**kw):
            calls.append((args,kw))
            return subprocess.CompletedProcess(args,0,stdout=b'{"format":"statistics-source-index-1","state":"already-present"}')
        self.assertEqual(m.worker(self.file,True,child)['state'],'already-present')
        args,kw=calls[0];self.assertEqual(args[1:5],['-E','-s','-','--worker']);self.assertEqual(args[-1],'--apply')
        self.assertEqual(kw['user'],0);self.assertEqual(kw['group'],0)
        self.assertEqual(kw['extra_groups'],[]);self.assertEqual(kw['timeout'],45);self.assertEqual(kw['input'],Path(m.__file__).read_bytes())
    def test_sidecar_ownership_repair_rejects_symlinks_and_source_replacement(self):
        target=self.root/'unrelated';target.write_text('preserve')
        journal=Path(str(self.file)+'-journal');journal.symlink_to(target)
        with self.assertRaises(OSError):m.restore_sidecar_ownership(self.file,m.identity(self.file))
        self.assertEqual(target.read_text(),'preserve');journal.unlink()
        with self.assertRaises(m.Refused):m.restore_sidecar_ownership(self.file,(-1,-1))
    def test_worker_failure_still_restores_sidecar_ownership(self):
        def child(*a,**kw):raise subprocess.TimeoutExpired('worker',45)
        with patch.object(m,'restore_sidecar_ownership') as restore:
            with self.assertRaises(subprocess.TimeoutExpired):m.worker(self.file,True,child)
        restore.assert_called_once_with(self.file,m.identity(self.file))
    def test_maintenance_restarts_exact_container_and_never_recreates_it(self):
        commands=[];runs=[]
        def command(args,**kw):commands.append(args);return subprocess.CompletedProcess(args,0,stdout='true')
        def worker(file,apply):runs.append(apply);return {'format':'statistics-source-index-1','state':'index-installed' if apply else 'index-absent'}
        r=m.maintenance(self.file,'a'*64,True,runner=command,run_worker=worker)
        self.assertEqual(runs,[False,True]);self.assertEqual([a[1] for a in commands],['stop','start','inspect'])
        self.assertTrue(all(a[-1]=='a'*64 for a in commands));self.assertTrue(r['maintenance']['restartConfirmed'])
    def test_no_maintenance_for_inspection_or_existing_index(self):
        for apply,state in [(False,'index-absent'),(True,'already-present'),(True,'stopped')]:
            with patch.object(m.subprocess,'run',side_effect=AssertionError('no docker call')):
                r=m.maintenance(self.file,'a'*64,apply,runner=lambda *a,**kw:self.fail('unexpected command'),run_worker=lambda *a:{'state':state})
            self.assertEqual(r['state'],state)
    def test_worker_failure_or_stop_failure_still_restarts(self):
        for stop_fails in (False,True):
            calls=[]
            def command(args,**kw):
                calls.append(args[1])
                if stop_fails and args[1]=='stop':raise subprocess.TimeoutExpired('stop',30)
                return subprocess.CompletedProcess(args,0,stdout='true')
            def worker(file,apply):
                if apply:raise subprocess.TimeoutExpired('worker',45)
                return {'state':'index-absent'}
            r=m.maintenance(self.file,'a'*64,True,runner=command,run_worker=worker)
            self.assertEqual(calls,['stop','start','inspect']);self.assertTrue(r['maintenance']['restartConfirmed']);self.assertEqual(r['state'],'stopped')
    def test_restart_failure_is_not_reported_as_successful_maintenance(self):
        def command(args,**kw):
            if args[1]=='start':raise subprocess.CalledProcessError(1,args)
            return subprocess.CompletedProcess(args,0,stdout='false')
        r=m.maintenance(self.file,'a'*64,True,runner=command,run_worker=lambda f,a:{'state':'index-installed' if a else 'index-absent'})
        self.assertEqual(r['error'],'scanner-restart-unconfirmed');self.assertEqual(r['indexOperationState'],'index-installed')
    def test_worker_reports_public_json_without_source_path(self):
        r=subprocess.run(['python3','-E','-s',str(Path(m.__file__)),'--worker',str(self.file)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0);self.assertEqual(json.loads(r.stdout)['state'],'index-absent');self.assertNotIn(str(self.root),r.stdout)

if __name__=='__main__':unittest.main()
