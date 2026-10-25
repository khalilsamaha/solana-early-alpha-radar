"""Regression for real RPC numeric spellings and read-only refused-entry inspection."""
import gzip
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import cycle_reservation_cli as audit
import test_cycle_execution as original
from test_cycle_execution import c, s, binding, Transport


class CycleHashCase(unittest.TestCase):
    setUpClass=classmethod(original.CycleExecutionCase.setUpClass.__func__)
    tearDownClass=classmethod(original.CycleExecutionCase.tearDownClass.__func__)
    setUp=original.CycleExecutionCase.setUp
    tearDown=original.CycleExecutionCase.tearDown
    entry=original.CycleExecutionCase.entry
    exit=original.CycleExecutionCase.exit

    def numeric_preparation(self, unicode=False):
        path=self.home/binding.CYCLE/'preparation.json';record=json.loads(path.read_text())
        for row in record['capture']['accounts']['result']['value']:
            row['rentEpoch']=18446744073709551615
        receipt=record['capture']['receipts'][0]['transaction']
        receipt['meta']['preTokenBalances'][0]['uiTokenAmount']['uiAmount']=1.0
        if unicode:receipt['meta']['logMessages']=['synthetic café \U0001f680']
        path.write_text(json.dumps(record,sort_keys=True,separators=(',',':')))
        (path.parent/'complete.json').write_text(json.dumps(dict(format=c.VERSION,preparationSha256=c.controlled.digest(record)),sort_keys=True,separators=(',',':')))
        return path

    def refuse(self):
        with patch.object(s.swap,'invoke_signer',side_effect=ValueError('restricted-signer-refused')):
            r=self.entry()
        self.assertEqual(r['failure']['phase'],'signing');self.assertEqual(r['sendRequestsThisRun'],0)
        return r

    def all_files(self):return {str(p):p.read_bytes() for p in self.home.rglob('*') if p.is_file()}

    def test_u64_and_integral_float_preparation_signs_and_reverses(self):
        path=self.numeric_preparation();before=path.read_bytes()
        self.assertEqual(self.entry()['state'],'finalized-success')
        self.assertEqual(self.exit()['state'],'finalized-success')
        self.assertEqual(path.read_bytes(),before)

    def test_unicode_preparation_uses_original_bytes(self):
        self.numeric_preparation(unicode=True)
        self.assertEqual(self.entry()['state'],'finalized-success')

    def test_same_js_rounded_number_changed_bytes_rejected(self):
        path=self.numeric_preparation();signer=s.swap.invoke_signer
        def sign(*args,**kw):
            before=path.read_bytes();path.write_bytes(before.replace(b'18446744073709551615',b'18446744073709551614'))
            try:
                with self.assertRaisesRegex(ValueError,'restricted-signer-refused'):signer(*args,**kw)
            finally:path.write_bytes(before)
            raise ValueError('test-refusal')
        with patch.object(s.swap,'invoke_signer',side_effect=sign):r=self.entry()
        self.assertEqual(r['sendRequestsThisRun'],0)
        self.assertFalse((self.home/binding.CYCLE/s.CHILD/'signing-attempt.json').exists())

    def test_read_only_audit_preserves_files_without_private_key(self):
        self.numeric_preparation();self.refuse();(self.home/'signer.pk8').unlink();before=self.all_files()
        r=audit.inspect(self.home,self.wallet,self.pool)
        self.assertEqual(r['state'],'unsigned-reservation-verified')
        self.assertEqual(r['preparationHashBasis'],'sealed-file-bytes-v1')
        self.assertEqual(r['reservedFeeLamports'],'20000');self.assertFalse(r['resubmitAllowed'])
        self.assertEqual(before,self.all_files())

    def test_audit_refuses_any_attempt_signature_or_boundary_marker(self):
        self.refuse();child=self.home/binding.CYCLE/s.CHILD
        for name in ('signing-attempt.json','signed.json','submission-boundary.json'):
            path=child/name;path.write_text('{}');path.chmod(0o600)
            try:
                with self.assertRaisesRegex(ValueError,'unsigned-failed-entry-files-required'):audit.inspect(self.home,self.wallet,self.pool)
            finally:path.unlink()

    def test_audit_refuses_changed_ledger_and_preserves_it(self):
        self.refuse();import sqlite3
        path=self.home/binding.CYCLE/s.spend_guard.NAME
        with sqlite3.connect(path) as db:db.execute("UPDATE spending_events SET event_hash=?",('0'*64,))
        before=self.all_files()
        with self.assertRaisesRegex(ValueError,'independent-reservation-check-refused'):audit.inspect(self.home,self.wallet,self.pool)
        self.assertEqual(before,self.all_files())

    def test_audit_refuses_wrong_scope_and_changed_seal(self):
        self.refuse()
        with self.assertRaises(ValueError):audit.inspect(self.home,self.wallet,original.fake_key('wrong-pool'))
        path=self.home/binding.CYCLE/'complete.json';path.write_text('{}')
        with self.assertRaises(ValueError):audit.inspect(self.home,self.wallet,self.pool)

    def test_expired_refusal_stays_reserved_and_execution_does_not_retry(self):
        self.refuse()
        with patch.object(audit.time,'time',return_value=9999999999):r=audit.inspect(self.home,self.wallet,self.pool)
        self.assertTrue(r['packetExpired']);self.assertFalse(r['executionApproved'])
        t=Transport(self.home,self.wallet);r=self.entry(t)
        self.assertEqual(t.calls,[]);self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000')

    def test_fresh_process_inspect_and_reject_submit_flag(self):
        self.numeric_preparation();self.refuse();(self.home/'signer.pk8').unlink()
        out=Path(self.tmp.name)/'audit.json.gz';cli=Path(__file__).with_name('cycle_reservation_cli.py')
        args=[sys.executable,'-E','-s',str(cli),'--action','inspect','--directory',str(self.home),
              '--wallet',self.wallet,'--pool',self.pool,'--output',str(out)]
        before=self.all_files();r=subprocess.run(args,capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr)
        with gzip.open(out,'rt') as f:report=json.load(f)
        self.assertEqual(report['state'],'unsigned-reservation-verified');self.assertEqual(before,self.all_files())
        out.unlink();r=subprocess.run(args+['--allow-devnet-submit'],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())

    def test_audit_refuses_changed_request_and_wrong_failure_phase(self):
        self.refuse();child=self.home/binding.CYCLE/s.CHILD
        for name,field,value in [('signing-request.json','preflightSha256','0'*64),('failure.json','phase','submission')]:
            path=child/name;before=path.read_bytes();record=json.loads(before);record[field]=value;path.write_text(json.dumps(record))
            try:
                with self.assertRaises(ValueError):audit.inspect(self.home,self.wallet,self.pool)
            finally:path.write_bytes(before)
