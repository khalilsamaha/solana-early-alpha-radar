import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

import admission_lifecycle as m
from admission_lifecycle_checks import inspect
from exit_balance_checks import signed_case,collect_receipt,apply
from exit_closure_checks import close

HERE=Path(__file__).resolve().parent

class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager=signed_case();cls.c=cls.manager.__enter__()
        collect_receipt(cls.c);apply(cls.c);close(cls.c)
        cls.stamp=cls.c.now;cls.before=cls.c.path.read_bytes()
    @classmethod
    def tearDownClass(cls):cls.manager.__exit__(None,None,None)
    def setUp(self):self.c.now=self.stamp;self.c.path.write_bytes(self.before)
    def tearDown(self):
        (self.c.home/'STOP').unlink(missing_ok=True);self.c.now=self.stamp

    def test_portable_cli_contract(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(HERE/'admission_lifecycle_cli.py'),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();v=json.loads(gzip.decompress(raw))
            self.assertEqual(v['casesPassed'],24);self.assertTrue(all(x=='passed' for x in v['cases'].values()))
            self.assertEqual(out.stat().st_mode&0o777,0o600);self.assertTrue(v['lifecycleInspectionReadOnly'])
            self.assertFalse(v['productionReservationsReleased']);self.assertEqual(v['realNetworkRequests'],0)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
            self.assertNotEqual(subprocess.run(cmd+['--allow-devnet-submit'],capture_output=True).returncode,0)

    def test_read_only_connections_and_shared_lock(self):
        original=m.projection;calls=[]
        def probe(book,*args):
            self.assertTrue(book.j.read_only);self.assertEqual(book.db.execute('PRAGMA query_only').fetchone()[0],1)
            with self.assertRaises(sqlite3.OperationalError):book.db.execute('CREATE TABLE forbidden (x)')
            db=sqlite3.connect(self.c.path,timeout=0,isolation_level=None)
            try:
                db.execute('BEGIN IMMEDIATE');db.execute('CREATE TABLE uncommitted (x)')
                with self.assertRaises(sqlite3.OperationalError):db.execute('COMMIT')
                db.execute('ROLLBACK')
            finally:db.close()
            calls.append(True);return original(book,*args)
        with patch.object(m,'projection',probe),patch.object(m.closure,'collect_and_close',side_effect=AssertionError('write/network')):
            r=inspect(self.c)
        self.assertTrue(r['coherent'],r);self.assertEqual(len(calls),1);self.assertEqual(self.before,self.c.path.read_bytes())

    def test_expired_read_or_clock_regression_never_returns_partial_amounts(self):
        for ticks in ((0,121),(1,0)):
            seq=iter(ticks)
            r=m.inspect(self.c.home,self.c.wallet,self.c.pool,clock=lambda:self.c.now,monotonic=lambda:next(seq))
            self.assertFalse(r['coherent']);self.assertIsNone(r['scopedAccounting'])
        original=m.projection
        def regressed(*args):
            r=original(*args);self.c.now-=1;return r
        with patch.object(m,'projection',regressed):r=inspect(self.c)
        self.assertFalse(r['coherent']);self.assertIsNone(r['originalAdmission']);self.assertEqual(self.before,self.c.path.read_bytes())

    def test_changed_source_identity_is_unavailable(self):
        original=m.view.read_locked
        def changed(*args,**kw):
            r=deepcopy(original(*args,**kw));r['ledgerHeadSha256']='0'*64;return r
        with patch.object(m.view,'read_locked',changed):r=inspect(self.c)
        self.assertFalse(r['coherent']);self.assertIsNone(r['scopedAccounting']);self.assertEqual(self.before,self.c.path.read_bytes())

    def test_conflicting_later_receipt_is_quarantined(self):
        b=self.c.book()
        try:
            t=m.exit_accounting.submission.ExitSubmission(b);ev=deepcopy(t.captures()[0]['rpcEvidence'])
            ev['transaction']['result']['meta']['err']={'InstructionError':[2,'InvalidArgument']}
            ev['signatureStatus']['result']['value'][0]['err']=ev['transaction']['result']['meta']['err']
            t.save_capture(self.c.now,ev)
        finally:b.close()
        before=self.c.path.read_bytes();r=inspect(self.c)
        self.assertFalse(r['coherent']);self.assertIsNone(r['scopedAccounting']);self.assertFalse(r['fundsAvailableForNewEntry'])
        self.assertEqual(before,self.c.path.read_bytes())

    def test_malformed_closure_is_not_zero_or_closed(self):
        b=self.c.book()
        try:b.db.execute("UPDATE admission_exit_closure SET value='{}', hash='bad'")
        finally:b.close()
        before=self.c.path.read_bytes();r=inspect(self.c)
        self.assertEqual(r['state'],'lifecycle-unavailable');self.assertIsNone(r['phase']);self.assertIsNone(r['scopedAccounting'])
        self.assertEqual(before,self.c.path.read_bytes())

if __name__=='__main__':unittest.main()
