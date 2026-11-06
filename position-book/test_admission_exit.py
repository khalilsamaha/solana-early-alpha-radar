"""Fresh delayed exits: immutable evidence, atomic writes and held ownership."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import admission_exit as m
from admission_exit_checks import fixture,prepare,status,run,NOW
from admission_submission_checks import case
from entry_accounting_checks import collect,apply
from admission_receipt_checks import failed
from contract import digest
from pre_sign_admission import encoded

HERE=Path(__file__).resolve().parent


class ExitTests(unittest.TestCase):
    def ready(self,c):
        collect(c);apply(c);e,b=fixture(c);c.now=NOW+30200;return e,b

    def test_portable_checks(self):self.assertEqual(run()['casesPassed'],27)

    def test_owner_reuses_exact_signature_only_during_one_review(self):
        from signature_replay_checks import fixture
        encoded_wire=fixture()
        original=m.wire.subprocess.run
        from types import SimpleNamespace
        book=SimpleNamespace(db=object())
        source={'reservation':{'original':'source'}}
        record={'accounting':{'exitAttemptsConsumed':0,'ownedAcquiredAtomic':'1'}}
        def reviewed(book):
            m.wire.verify_wire(encoded_wire)
            m.wire.verify_wire(encoded_wire)
            return source
        with patch.object(m.entry,'review',side_effect=reviewed), \
             patch.object(m.entry,'saved',return_value=record), \
             patch.object(m.entry,'public',return_value={'accountingUsable':True,'state':'entry-position-open'}), \
             patch.object(m.wire.subprocess,'run',wraps=original) as verifier:
            self.assertEqual(m.owner(book,1),(record,source['reservation']))
            self.assertEqual(verifier.call_count,1)
            self.assertIsNone(m.wire._SIGNATURE_SCOPE.get())
            self.assertEqual(m.owner(book,1),(record,source['reservation']))
            self.assertEqual(verifier.call_count,2)
            self.assertIsNone(m.wire._SIGNATURE_SCOPE.get())

    def test_owner_failure_clears_scope_and_never_inherits_parent(self):
        from signature_replay_checks import fixture
        encoded_wire=fixture()
        original=m.wire.subprocess.run
        def failed(book):
            m.wire.verify_wire(encoded_wire)
            raise ValueError('synthetic-owner-rejected')
        with patch.object(m.entry,'review',side_effect=failed), \
             patch.object(m.wire.subprocess,'run',wraps=original) as verifier:
            with m.wire.signature_verification_scope() as parent:
                m.wire.verify_wire(encoded_wire)
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError,'synthetic-owner-rejected'):
                        m.owner(None,1)
                self.assertEqual(verifier.call_count,3)
                self.assertEqual(parent()['verificationCalls'],1)
            self.assertIsNone(m.wire._SIGNATURE_SCOPE.get())

    def test_unprepared_status_never_creates_table(self):
        with case() as c:
            before=c.path.read_bytes();self.assertEqual(status(c,c.e['costInputs']['baseline'])['state'],'exit-not-prepared')
            self.assertEqual(before,c.path.read_bytes())

    def test_rehashed_record_cannot_hide_raw_tampering(self):
        with case() as c:
            e,b=self.ready(c);prepare(c,e,b);book=c.book()
            try:
                v=json.loads(book.db.execute('SELECT value FROM admission_exit_preparation').fetchone()[0])
                v['evidence']['simulationItem']['result']['value']['fee']=1
                book.db.execute('UPDATE admission_exit_preparation SET value=?,hash=?',(encoded(v),digest(v)))
            finally:book.close()
            with self.assertRaises(ValueError):status(c,b)

    def test_rehashed_binding_and_future_timestamp_refused(self):
        for name in ('binding','clock'):
            with self.subTest(name=name),case() as c:
                e,b=self.ready(c);prepare(c,e,b);book=c.book()
                try:
                    v=json.loads(book.db.execute('SELECT value FROM admission_exit_preparation').fetchone()[0])
                    if name=='binding':v['binding']['quantityAtomic']='1'
                    else:v['recordedAtMs']=c.now+1
                    book.db.execute('UPDATE admission_exit_preparation SET value=?,hash=?',(encoded(v),digest(v)))
                finally:book.close()
                with self.assertRaises(ValueError):status(c,b)

    def test_receipt_conflict_refuses_preparation_replay(self):
        with case() as c:
            e,b=self.ready(c);prepare(c,e,b)
            m.entry.submission.receipts.observe(c.home,c.wallet,c.pool,failed(c.package),clock=lambda:c.now)
            with self.assertRaisesRegex(ValueError,'exit-open-accounting-required'):status(c,b)

    def test_durable_stop_blocks_new_preparation(self):
        with case() as c:
            e,b=self.ready(c);book=c.book()
            try:book.stop()
            finally:book.close()
            before=c.path.read_bytes()
            with self.assertRaisesRegex(ValueError,'exit-admission-stopped'):prepare(c,e,b)
            self.assertEqual(before,c.path.read_bytes())

    def test_durable_stop_preserves_existing_preparation(self):
        with case() as c:
            e,b=self.ready(c);r=prepare(c,e,b);book=c.book()
            try:book.stop()
            finally:book.close()
            self.assertEqual(status(c,b)['state'],'exit-preparation-stopped')
            self.assertEqual(status(c,b)['recordSha256'],r['recordSha256'])

    def test_real_source_identity_mismatch_refused(self):
        with case() as c:
            e,b=self.ready(c);source=deepcopy(c.e['costInputs']['reservations']);source['ledgerHeadSha256']='c'*64
            before=c.path.read_bytes()
            with patch.object(m,'BASELINE',b),patch.object(m.view,'read_locked',return_value=source):
                with self.assertRaisesRegex(ValueError,'exit-historical-source-changed'):
                    m.prepare(c.home,c.wallet,c.pool,e,clock=lambda:c.now)
            self.assertEqual(before,c.path.read_bytes())

    def test_fee_cap_cannot_borrow_other_attempts(self):
        with case() as c:
            e,b=self.ready(c);e['packet']['policy']['maxTotalFeeLamports']='10001'
            with self.assertRaises(ValueError):prepare(c,e,b)

    def test_preserved_inventory_requirement_before_simulation(self):
        with case() as c:
            e,b=self.ready(c);original=m.owner
            # Independently exercise the allocation arithmetic with a preexisting
            # balance; production owner always replays the original raw receipt.
            def with_inventory(book,now):
                record,reservation=original(book,now);record=deepcopy(record)
                record['accounting']['preexistingDestinationAtomic']='903'
                return record,reservation
            with patch.object(m,'owner',side_effect=with_inventory):
                with self.assertRaisesRegex(ValueError,'exit-owned-inventory-shortfall'):prepare(c,e,b)

    def test_validation_overrun_rolls_back_all_writes(self):
        with case() as c:
            e,b=self.ready(c);before=c.path.read_bytes();review=m.review
            def slow(*args):
                r=review(*args);c.now=NOW+60000;return r
            with patch.object(m,'review',side_effect=slow):
                with self.assertRaisesRegex(ValueError,'exit-deadline-elapsed'):prepare(c,e,b)
            self.assertEqual(before,c.path.read_bytes())

    def test_failure_after_insert_rolls_back(self):
        with case() as c:
            e,b=self.ready(c);before=c.path.read_bytes()
            with patch.object(m,'public',side_effect=RuntimeError('before commit')):
                with self.assertRaises(RuntimeError):prepare(c,e,b)
            self.assertEqual(before,c.path.read_bytes());self.assertFalse(status(c,b)['recorded'])

    def test_deadline_expires_during_write_and_rolls_back(self):
        with case() as c:
            e,b=self.ready(c);before=c.path.read_bytes();encode=m.encoded;calls=[]
            def slow_encode(v):
                value=encode(v)
                if isinstance(v,dict) and v.get('format')==m.VERSION+'-record':
                    calls.append(True)
                    if len(calls)==2:c.now=NOW+60000
                return value
            with patch.object(m,'encoded',side_effect=slow_encode):
                with self.assertRaisesRegex(ValueError,'exit-deadline-elapsed'):prepare(c,e,b)
            self.assertEqual(len(calls),2);self.assertEqual(before,c.path.read_bytes())

    def test_cooperating_and_sqlite_writers_excluded_during_validation(self):
        with case() as c:
            e,b=self.ready(c);review=m.review;seen=[]
            def compete(*args):
                with self.assertRaises(BlockingIOError):prepare(c,e,b)
                db=sqlite3.connect(c.path,timeout=0,isolation_level=None)
                try:
                    with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):db.execute('BEGIN IMMEDIATE')
                finally:db.close()
                seen.append(True);return review(*args)
            with patch.object(m,'review',side_effect=compete):prepare(c,e,b)
            self.assertEqual(seen,[True])

    def test_record_cap_before_json_parse(self):
        with case() as c:
            e,b=self.ready(c);prepare(c,e,b)
            with patch.object(m,'MAX_RECORD',1):
                with self.assertRaisesRegex(ValueError,'exit-preparation-record'):status(c,b)

    def test_recovery_case_names_exclude_noncallable_test_key(self):
        import admission_recovery_cli as cli
        from types import ModuleType
        module=ModuleType('test_admission_recovery')
        methods={'test_case_'+str(i):lambda self:None for i in range(19)}
        methods['test_key']=None
        module.RecoveryTests=type('RecoveryTests',(unittest.TestCase,),methods)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'recovery.gz'
            with patch.dict(sys.modules,{'test_admission_recovery':module}),patch.object(sys,'argv',['check','--output',str(out)]),patch('builtins.print'):
                cli.main()
            report=json.loads(gzip.decompress(out.read_bytes()))
            self.assertEqual(report['casesPassed'],19);self.assertEqual(len(report['cases']),19)
            self.assertNotIn('test_key',report['cases'])

    def test_cli_offline_only_private_exclusive_report(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'check.gz';cmd=[sys.executable,'-E','-s',str(HERE/'admission_exit_cli.py'),'--output',str(path)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=path.read_bytes();v=json.loads(gzip.decompress(raw));self.assertEqual(v['casesPassed'],27)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(path.read_bytes(),raw)
            for flag in ('--execute','--directory','--wallet','--allow-devnet-submit','--evidence'):
                self.assertNotEqual(subprocess.run(cmd+[flag],capture_output=True).returncode,0)


if __name__=='__main__':unittest.main()
