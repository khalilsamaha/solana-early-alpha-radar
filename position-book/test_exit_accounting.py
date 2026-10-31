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
import exit_accounting as m
from exit_accounting_checks import signed_case,collect,apply,status,package,ReceiptRpc
from exit_submission_checks import submit,recover

HERE=Path(__file__).resolve().parent

class ExitAccountingTests(unittest.TestCase):
    def test_portable_cli(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'check.gz';cmd=[sys.executable,'-E','-s',str(HERE/'exit_accounting_cli.py'),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();v=json.loads(gzip.decompress(raw));self.assertEqual(v['casesPassed'],15)
            self.assertTrue(all(x=='passed' for x in v['cases'].values()));self.assertFalse(v['reservationReleased'])
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(raw,out.read_bytes())
            self.assertNotEqual(subprocess.run(cmd+['--allow-devnet-submit'],capture_output=True).returncode,0)

    def test_duplicate_terminal_capture_preserves_first_identity(self):
        with signed_case() as c:
            collect(c);r=apply(c);b=c.book()
            try:
                t=m.submission.ExitSubmission(b);ev=deepcopy(t.captures()[0]['rpcEvidence']);t.save_capture(c.now,ev)
            finally:b.close()
            before=c.path.read_bytes();again=apply(c);self.assertEqual(again['recordSha256'],r['recordSha256'])
            self.assertFalse(again['appliedThisRun']);self.assertEqual(before,c.path.read_bytes())

    def test_later_contradiction_preserves_record_but_quarantines(self):
        with signed_case() as c:
            collect(c);r=apply(c);b=c.book()
            try:
                t=m.submission.ExitSubmission(b);ev=deepcopy(t.captures()[0]['rpcEvidence'])
                ev['transaction']['result']['meta']['err']={'InstructionError':[2,'InvalidArgument']}
                ev['signatureStatus']['result']['value'][0]['err']=ev['transaction']['result']['meta']['err']
                t.save_capture(c.now,ev)
            finally:b.close()
            before=c.path.read_bytes();again=apply(c);self.assertEqual(again['state'],'quarantined')
            self.assertTrue(again['accountingRecorded']);self.assertFalse(again['accountingUsable'])
            self.assertEqual(again['recordSha256'],r['recordSha256']);self.assertEqual(before,c.path.read_bytes())

    def test_storage_failure_keeps_source_and_accounting_absent(self):
        with signed_case() as c:
            collect(c);before=c.path.read_bytes();original=m.encoded
            def fail(v):
                if isinstance(v,dict) and v.get('format')==m.VERSION+'-record':raise OSError('synthetic storage failure')
                return original(v)
            with patch.object(m,'encoded',fail):
                with self.assertRaises(OSError):apply(c)
            self.assertEqual(before,c.path.read_bytes());self.assertFalse(status(c)['accountingRecorded'])

    def test_writer_excluded_while_source_replayed(self):
        with signed_case() as c:
            collect(c);original=m.review;calls=[]
            def review(book):
                db=sqlite3.connect(c.path,timeout=0)
                try:
                    with self.assertRaises(sqlite3.OperationalError):db.execute('BEGIN IMMEDIATE')
                finally:db.close()
                calls.append(True);return original(book)
            with patch.object(m,'review',review):self.assertTrue(apply(c)['accountingUsable'])
            self.assertEqual(len(calls),1)

    def test_record_size_and_clock_bounds(self):
        with signed_case() as c:
            collect(c);apply(c);b=c.book()
            try:b.db.execute('UPDATE admission_exit_accounting SET value=?',('x'*(m.MAX_RECORD+1),))
            finally:b.close()
            with self.assertRaisesRegex(ValueError,'exit-accounting-row'):status(c)
        with signed_case() as c:
            collect(c);apply(c);b=c.book()
            try:
                v=json.loads(b.db.execute('SELECT value FROM admission_exit_accounting').fetchone()[0]);v['recordedAtMs']=c.now+1
                b.db.execute('UPDATE admission_exit_accounting SET value=?,hash=?',(m.encoded(v),m.digest(v)))
            finally:b.close()
            with self.assertRaisesRegex(ValueError,'exit-accounting-clock'):status(c)

    def test_raw_receipt_tamper_not_hidden_by_rehash(self):
        with signed_case() as c:
            collect(c);apply(c);b=c.book()
            try:
                v=json.loads(b.db.execute('SELECT value FROM admission_exit_rpc_captures').fetchone()[0])
                v['rpcEvidence']['transaction']['result']['meta']['fee']=10001
                b.db.execute('UPDATE admission_exit_rpc_captures SET value=?,hash=?',(m.encoded(v),m.digest(v)))
            finally:b.close()
            r=status(c);self.assertEqual(r['state'],'quarantined');self.assertFalse(r['accountingUsable']);self.assertFalse(r['reservationReleased'])

if __name__=='__main__':unittest.main()
