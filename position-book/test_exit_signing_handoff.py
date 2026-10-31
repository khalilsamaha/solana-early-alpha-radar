"""Durable handoff corruption, concurrency, lost acknowledgments and CLI checks."""
import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import exit_signing_handoff as m
from exit_signing_handoff_checks import ready,dispatch,status,recover
from contract import digest
from pre_sign_admission import encoded

HERE=Path(__file__).resolve().parent


class HandoffTests(unittest.TestCase):
    def test_cli_and_portable_cases(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'check.gz';cmd=[sys.executable,'-E','-s',str(HERE/'exit_signing_handoff_cli.py'),'--output',str(out)]
            p=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
            raw=out.read_bytes();r=json.loads(gzip.decompress(raw));self.assertEqual(r['casesPassed'],21)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
            for flag in ('--directory','--wallet','--execute','--allow-devnet-submit','--evidence'):
                self.assertNotEqual(subprocess.run(cmd+[flag],capture_output=True).returncode,0)

    def test_source_change_and_current_admission_change_refused(self):
        for kind in ('source','admission'):
            with self.subTest(kind=kind),ready() as c:
                if kind=='source':
                    c.e['costInputs']['reservations']['ledgerHeadSha256']='0'*64
                else:
                    b=c.book()
                    try:
                        b.change(lambda s,now:dict(s,extra='unexpected'),enforce_deadline=False)
                    finally:b.close()
                before=c.path.read_bytes()
                with self.assertRaises(ValueError):dispatch(c)
                self.assertEqual(c.path.read_bytes(),before)

    def test_wallet_lock_held_and_committed_request_visible_during_adapter(self):
        with ready() as c:
            def adapter(request):
                with self.assertRaises(BlockingIOError):dispatch(c)
                db=sqlite3.connect(c.path.as_uri()+'?mode=ro',uri=True)
                try:self.assertEqual(db.execute('SELECT COUNT(*) FROM admission_exit_signing').fetchone()[0],1)
                finally:db.close()
                request['quantityAtomic']='999' # callback receives its own deep copy
                return c.exit_wire
            self.assertEqual(dispatch(c,adapter)['state'],'exit-signed-recorded')

    def test_sqlite_writer_excluded_during_boundary_validation(self):
        with ready() as c:
            original=m.current;calls=[]
            def current(*args):
                db=sqlite3.connect(c.path,timeout=0,isolation_level=None)
                try:
                    with self.assertRaises(sqlite3.OperationalError):db.execute('BEGIN IMMEDIATE')
                finally:db.close()
                calls.append(True);return original(*args)
            with patch.object(m,'current',side_effect=current):dispatch(c)
            self.assertEqual(calls,[True])

    def test_stop_or_expiry_after_committed_boundary_never_calls_adapter(self):
        for kind in ('stop','expiry'):
            with self.subTest(kind=kind),ready() as c:
                original=m.read;called=[]
                def read(book,now):
                    r=original(book,now)
                    if r is not None and not book.db.in_transaction:
                        if kind=='stop':(c.home/'STOP').touch(mode=0o600)
                        else:c.now+=30000
                    return r
                with patch.object(m,'read',side_effect=read):
                    with self.assertRaises(ValueError):dispatch(c,lambda _:called.append(True))
                self.assertEqual(called,[]);self.assertTrue(status(c)['boundaryRecorded'])
                self.assertEqual(dispatch(c)['signerAdapterCallsThisRun'],0)

    def test_response_recorded_when_stop_arrives_in_adapter(self):
        with ready() as c:
            def adapter(_):
                (c.home/'STOP').touch(mode=0o600);c.now+=30000;return c.exit_wire
            r=dispatch(c,adapter);self.assertTrue(r['acknowledgmentRecorded']);self.assertTrue(r['stopRequested'])
            self.assertFalse(r['validForSubmission'])

    def rewrite(self,c,mutate):
        b=c.book()
        try:
            rows=b.db.execute('SELECT * FROM admission_exit_signing ORDER BY seq').fetchall();previous=''
            for row in rows:
                v=json.loads(row['value']);mutate(row['seq'],v)
                h=digest(dict(seq=row['seq'],atMs=row['at_ms'],value=v,previousHash=previous))
                b.db.execute('UPDATE admission_exit_signing SET value=?,previous_hash=?,hash=? WHERE seq=?',(encoded(v),previous,h,row['seq']));previous=h
        finally:b.close()

    def test_rehashed_request_and_signed_response_rejected(self):
        for kind in ('request','wire','admission-head','transition'):
            with self.subTest(kind=kind),ready() as c:
                dispatch(c)
                def corrupt(seq,v):
                    if kind=='request' and seq==1:
                        v['request']['quantityAtomic']='999';v['requestSha256']=digest(v['request'])
                    if kind=='wire' and seq==2:
                        v['signedWireBase64']=c.signed['signedTransactionBase64']
                    if kind=='admission-head' and seq==1:v['admissionHeadSha256']='0'*64
                    if kind=='transition' and seq==2:v.update(state='exit-signing-unknown')
                self.rewrite(c,corrupt)
                with self.assertRaises(ValueError):status(c)

    def test_malformed_and_oversized_rows_fail_before_acceptance(self):
        with ready() as c:
            dispatch(c)
            with patch.object(m,'MAX_ROW',1):
                with self.assertRaises(ValueError):status(c)
            b=c.book()
            try:b.db.execute('UPDATE admission_exit_signing SET value=? WHERE seq=1',('{',))
            finally:b.close()
            with self.assertRaises(ValueError):status(c)

    def test_missing_verifier_does_not_turn_infrastructure_error_into_quarantine(self):
        with ready() as c:
            with patch.object(m,'verify_wire',side_effect=ValueError('node-runtime-unavailable')):
                with self.assertRaisesRegex(ValueError,'node-runtime-unavailable'):dispatch(c)
            self.assertEqual(status(c)['state'],'exit-signing-unknown')
            self.assertEqual(recover(c,c.exit_wire)['state'],'exit-signed-recorded')

    def test_clock_regression_refused(self):
        with ready() as c:
            dispatch(c);c.now-=1
            with self.assertRaises(ValueError):status(c)


if __name__=='__main__':unittest.main()
