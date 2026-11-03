import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import exit_preparation_audit as m
from exit_preparation_audit_checks import run
from fresh_exit_checks import case
import fresh_exit


class AuditTests(unittest.TestCase):
    def test_portable(self):
        r=run();self.assertEqual(r['casesPassed'],11)

    def test_read_only_and_read_deadline(self):
        with case() as c:
            original=m.lifecycle.projection
            def checking(book,*args):
                self.assertTrue(book.j.read_only)
                self.assertEqual(book.db.execute('PRAGMA query_only').fetchone()[0],1)
                with self.assertRaises(sqlite3.OperationalError):book.db.execute('CREATE TABLE forbidden(x)')
                return original(book,*args)
            before=c.path.read_bytes()
            with patch.object(m.lifecycle,'projection',side_effect=checking):
                r=m.inspect(c.home,c.wallet,c.pool,clock=c.clock,monotonic=lambda:0)
            self.assertTrue(r['coherent']);self.assertEqual(before,c.path.read_bytes())
            for ticks in ((0,121),(1,0)):
                it=iter(ticks)
                r=m.inspect(c.home,c.wallet,c.pool,clock=c.clock,monotonic=lambda:next(it))
                self.assertFalse(r['coherent']);self.assertIsNone(r['scopedAccounting'])

    def test_clock_regression(self):
        with case() as c:
            original=m.lifecycle.projection
            def regress(*args):
                result=original(*args);c.timer.at-=30000;return result
            with patch.object(m.lifecycle,'projection',side_effect=regress):
                r=m.inspect(c.home,c.wallet,c.pool,clock=c.clock,monotonic=lambda:0)
            self.assertFalse(r['coherent'])

    def test_unknown_exception_is_sanitized(self):
        with case() as c,patch.object(fresh_exit.handoff,'dispatch',side_effect=ValueError('private payload')):
            r=c.run()
            self.assertEqual(r['stage'],'signing-validation')
            self.assertEqual(r['diagnosticCode'],'fresh-exit-evidence-unavailable')
            self.assertNotIn('private payload',json.dumps(r))
            self.assertEqual(r['signerInvocationAttempts'],0)

    def test_cli_exclusive_and_no_execution_options(self):
        cli=Path(__file__).with_name('exit_preparation_audit_cli.py')
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'report.json.gz'
            cmd=[sys.executable,str(cli),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            before=out.read_bytes();report=json.loads(gzip.decompress(before))
            self.assertEqual(report['state'],'offline-checks-passed')
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(before,out.read_bytes())
            out.unlink()
            self.assertNotEqual(subprocess.run(cmd+['--allow-devnet-submit'],capture_output=True).returncode,0)
            self.assertFalse(out.exists())

    def test_cli_refuses_private_output_before_inspection(self):
        import exit_preparation_audit_cli as cli
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'source';root.mkdir()
            sibling=Path(td)/'source-entry-handoff-v1';sibling.mkdir()
            alias=Path(td)/'alias';alias.symlink_to(sibling,target_is_directory=True)
            with patch.object(cli.m,'inspect',side_effect=AssertionError('access')):
                for parent in (root,sibling,alias):
                    args=['audit','--action','inspect','--directory',str(root),'--wallet','w','--pool','p','--output',str(parent/'r.gz')]
                    with patch.object(sys,'argv',args),self.assertRaises(ValueError):cli.main()
