from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import launch_audit as launch

NOW=1800000000000
START=NOW-720*3600000


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.file=Path(self.temp.name)/'radar.sqlite'
        with closing(sqlite3.connect(self.file)) as db, db:
            db.executescript('CREATE TABLE launch_registry(mint TEXT PRIMARY KEY,received_at INTEGER,data TEXT);'
                            'CREATE INDEX launch_registry_received ON launch_registry(received_at);')

    def rows(self,values):
        with closing(sqlite3.connect(self.file)) as db, db:
            db.executemany('INSERT INTO launch_registry VALUES(?,?,?)',
                           ((str(i),at,'invalid payload, intentionally unread') for i,at in enumerate(values)))

    def read(self):
        with patch.object(launch.time,'time',return_value=NOW/1000):return launch.retention_audit(self.file,720)

    def test_window_boundaries_and_retained_span_preserve_source(self):
        self.rows([START-1,START,NOW-1,NOW]);before=hashlib.sha256(self.file.read_bytes()).hexdigest()
        r=self.read()
        self.assertEqual((r['retainedTotal'],r['rowsBeforeWindow'],r['receivedCreationsInWindow']),(4,1,3))
        self.assertEqual((r['earliestRetainedReceiptAt'],r['latestRetainedReceiptAt']),(START-1,NOW))
        self.assertEqual((r['firstReceiptAt'],r['lastReceiptAt']),(START,NOW))
        self.assertEqual(r['format'],'launch-retention-audit-1')
        self.assertFalse(r['payloadsRead']);self.assertFalse(r['payloadsValidated']);self.assertFalse(r['featureAvailabilityEvaluated'])
        self.assertNotIn('availability',r)
        self.assertEqual(hashlib.sha256(self.file.read_bytes()).hexdigest(),before)

    def test_empty_registry_is_explicit(self):
        r=self.read();self.assertEqual(r['retainedTotal'],0);self.assertEqual(r['receivedCreationsInWindow'],0)
        self.assertIsNone(r['earliestRetainedReceiptAt']);self.assertIsNone(r['lastReceiptAt'])

    def test_only_receipt_index_read_and_connection_closed(self):
        self.rows([NOW]);connections=[];original=sqlite3.connect
        class Connection(sqlite3.Connection):
            closed=False
            def close(self):super().close();self.closed=True
        def connect(*args,**kwargs):
            db=original(*args,**kwargs,factory=Connection);connections.append(db)
            db.set_authorizer(lambda action,table,column,*_:sqlite3.SQLITE_DENY
                if action==sqlite3.SQLITE_READ and (table!='launch_registry' or column not in ('received_at','')) else sqlite3.SQLITE_OK)
            return db
        with patch.object(launch.sqlite3,'connect',side_effect=connect):self.read()
        self.assertEqual(len(connections),1);self.assertTrue(connections[0].closed)
        with closing(original(self.file)) as db:
            plan=db.execute('EXPLAIN QUERY PLAN '+launch.RETENTION_SQL,(START,START,NOW,START,NOW,START,NOW,NOW)).fetchall()
        self.assertTrue(any('COVERING INDEX launch_registry_received' in row[3] for row in plan),plan)

    def test_missing_index_fails_without_falling_back_to_payload_table(self):
        with closing(sqlite3.connect(self.file)) as db, db:db.execute('DROP INDEX launch_registry_received')
        with self.assertRaisesRegex(ValueError,'index missing or incompatible'):self.read()
        with closing(sqlite3.connect(self.file)) as db, db:db.execute('CREATE INDEX launch_registry_received ON launch_registry(data)')
        with self.assertRaisesRegex(ValueError,'index missing or incompatible'):self.read()

    def test_invalid_and_future_timestamps_refuse_report(self):
        for value in (None,'invalid',0,-1,NOW+1):
            with self.subTest(value=value):
                with closing(sqlite3.connect(self.file)) as db, db:db.execute('DELETE FROM launch_registry')
                self.rows([value])
                with self.assertRaisesRegex(ValueError,'Invalid or future'):self.read()

    def test_full_capacity_is_complete_and_over_cap_refuses_partial(self):
        self.rows([NOW]*100000);r=self.read();self.assertEqual(r['retainedTotal'],100000)
        with closing(sqlite3.connect(self.file)) as db, db:db.execute('INSERT INTO launch_registry VALUES(?,?,?)',('extra',NOW,'{}'))
        with self.assertRaisesRegex(ValueError,'cap reached; no partial'):self.read()

    def test_deadline_failure_closes_connection(self):
        original=sqlite3.connect;connections=[]
        class Connection(sqlite3.Connection):
            closed=False
            def close(self):super().close();self.closed=True
        def connect(*args,**kwargs):
            db=original(*args,**kwargs,factory=Connection);connections.append(db);return db
        with patch.object(launch.sqlite3,'connect',side_effect=connect),patch.object(launch.time,'monotonic',side_effect=[0,11]):
            with self.assertRaisesRegex(TimeoutError,'deadline'):self.read()
        self.assertTrue(connections[0].closed)

    def test_wal_growth_refuses_report(self):
        original_exists=Path.exists;original_stat=Path.stat;wal_calls=[]
        def exists(path):return True if str(path).endswith('-wal') else original_exists(path)
        def stat(path,*args,**kwargs):
            if str(path).endswith('-wal'):
                from types import SimpleNamespace
                wal_calls.append(1);return SimpleNamespace(st_size=0 if len(wal_calls)==1 else 64*1024*1024+1)
            return original_stat(path,*args,**kwargs)
        with patch.object(Path,'exists',exists),patch.object(Path,'stat',stat):
            with self.assertRaisesRegex(ValueError,'WAL growth'):self.read()

    def test_deadline_interrupts_active_sql_instead_of_returning_counts(self):
        self.rows([NOW]*1000);ticks=[]
        def clock():
            ticks.append(1);return 0 if len(ticks)<=2 else 11
        with patch.object(launch.time,'monotonic',side_effect=clock):
            with self.assertRaisesRegex(sqlite3.OperationalError,'interrupted'):self.read()

    def test_cli_mode_is_distinct_and_missing_source_not_created(self):
        run=subprocess.run([sys.executable,'-B','-E','-s',str(Path(launch.__file__)),
                            '--database',str(self.file),'--hours','720','--retention-only'],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(json.loads(run.stdout)['format'],'launch-retention-audit-1')
        missing=self.file.parent/'missing.sqlite'
        with self.assertRaises(FileNotFoundError):launch.retention_audit(missing)
        self.assertFalse(missing.exists())

if __name__=='__main__':unittest.main()
