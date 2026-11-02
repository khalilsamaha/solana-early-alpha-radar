"""Composition and interrupted-stage recovery; real parsers, synthetic transport."""
import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import settled_exit as m
from settled_exit_checks import run,case,delayed


class SettledExitTests(unittest.TestCase):
    def test_portable_contract(self):self.assertEqual(run()['casesPassed'],18)

    def test_cli_is_private_exclusive_and_has_no_live_options(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(Path(__file__).with_name('settled_exit_cli.py')),'--output',str(p)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=p.read_bytes();self.assertEqual(json.loads(gzip.decompress(raw))['casesPassed'],18)
            self.assertEqual(p.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(raw,p.read_bytes())
            for flag in ('--action','--directory','--wallet','--prepare-exit','--allow-devnet-submit','--receipt'):
                other=Path(d)/'no.gz'
                self.assertNotEqual(subprocess.run(cmd[:-1]+[str(other),flag],capture_output=True).returncode,0)
                self.assertFalse(other.exists())

    def test_explicit_boolean_exit_choice_before_any_source_access(self):
        with patch.object(m.entry.submission,'recover',side_effect=AssertionError('source')):
            for flag in (1,'true',None,[]):
                with self.assertRaisesRegex(ValueError,'explicit-exit-preparation-choice'):
                    m.advance('/missing','wallet','pool',prepare_exit=flag)

    def test_complete_delayed_reconciliation_and_preparation_is_bounded_24_requests(self):
        with case() as c:
            c.run_entry()
            with delayed(c) as rpc:
                r=c.prepare()
                self.assertEqual(r['state'],'exit-prepared-research-only',r)
                self.assertEqual(r['receiptRequestsThisRun'],4);self.assertEqual(r['exitRequestsThisRun'],20)
                self.assertTrue(r['accountingAppliedThisRun']);self.assertTrue(r['exitCreatedThisRun'])
                self.assertEqual(len(rpc.calls),20);self.assertEqual(c.calls,1)
                self.assertEqual(r['networkRequests'],24);self.assertEqual(r['transactionsSent'],0)
                self.assertEqual(r['exitPreparation']['binding']['entryAccountingSha256'],r['accounting']['recordSha256'])

    def test_receipt_commit_failure_reports_attempts_and_cannot_prepare(self):
        with case() as c:
            c.run_entry();c.now+=1000
            with patch.object(m.entry.submission.Submission,'save_capture',side_effect=sqlite3.OperationalError('PRIVATE')):
                r=c.advance(prepare_exit=True)
            self.assertEqual(r['state'],'inspection-required');self.assertEqual(r['networkRequests'],4)
            self.assertEqual(r['exitRequestsThisRun'],0);self.assertNotIn('PRIVATE',json.dumps(r))
            self.assertEqual(c.inspect()['state'],'entry-accounting-pending')

    def test_accounting_failure_keeps_receipt_and_repeat_does_not_refetch(self):
        with case() as c:
            c.run_entry();c.now+=1000
            with patch.object(m.entry,'apply',side_effect=sqlite3.OperationalError('PRIVATE')):
                r=c.advance(prepare_exit=True)
            self.assertEqual(r['state'],'inspection-required');self.assertEqual(r['networkRequests'],4)
            self.assertEqual(c.transport()['state'],'entry-effects-observed')
            again=c.advance();self.assertEqual(again['networkRequests'],0);self.assertTrue(again['accountingAppliedThisRun'])

    def test_exit_write_failure_rolls_back_only_exit_and_counts_collected_requests(self):
        with case() as c:
            c.run_entry();c.now+=1000;c.advance();old=c.path.read_bytes()
            write=m.exits.exit.write_record
            def broken(book,record):write(book,record);raise OSError('PRIVATE')
            with delayed(c),patch.object(m.exits.exit,'write_record',broken):
                r=c.prepare();self.assertEqual(r['state'],'inspection-required')
                self.assertEqual(r['networkRequests'],20);self.assertTrue(r['accounting']['accountingUsable'])
                self.assertEqual(old,c.path.read_bytes())
                s=c.inspect();self.assertEqual(s['state'],'entry-settled-exit-not-prepared')
            self.assertNotIn('PRIVATE',json.dumps(r))

    def test_stop_between_settlement_and_collection_blocks_network_and_preserves_fee(self):
        with case() as c:
            c.run_entry();c.now+=1000
            apply=m.entry.apply
            def stopped(*a,**kw):
                result=apply(*a,**kw);(c.home/'STOP').touch(mode=0o600);return result
            with patch.object(m.entry,'apply',stopped):r=c.advance(prepare_exit=True)
            self.assertEqual(r['state'],'entry-settled-exit-stopped');self.assertEqual(r['exitRequestsThisRun'],0)
            self.assertEqual(r['accounting']['accounting']['entryFeePaidLamports'],'5001')

    def test_post_collection_stop_prevents_commit_with_accounting_retained(self):
        with case() as c:
            c.run_entry();c.now+=1000;c.advance();before=c.path.read_bytes()
            prepare=m.exits.exit.prepare
            def stopped(*a,**kw):
                (c.home/'STOP').touch(mode=0o600);return prepare(*a,**kw)
            with delayed(c),patch.object(m.exits.exit,'prepare',stopped):
                r=c.prepare();self.assertEqual(r['state'],'inspection-required');self.assertEqual(r['networkRequests'],20)
                self.assertEqual(c.path.read_bytes(),before)
                self.assertEqual(c.inspect()['state'],'entry-settled-exit-stopped')

    def test_identity_mismatch_in_final_projection_fails_closed(self):
        with case() as c:
            c.run_entry();c.now+=1000;c.advance()
            with delayed(c):
                c.prepare();original=m.exits.exit.public
                def mismatch(*a,**kw):
                    result=original(*a,**kw)
                    if result['recorded']:result['binding']['entryAccountingSha256']='0'*64
                    return result
                with patch.object(m.exits.exit,'public',mismatch):
                    with self.assertRaisesRegex(ValueError,'settled-exit-binding'):c.inspect()
                    r=c.prepare();self.assertEqual(r['state'],'inspection-required');self.assertEqual(r['networkRequests'],0)

    def test_status_and_terminal_advance_do_not_call_signer_sender_or_collection(self):
        with case() as c:
            c.run_entry();c.now+=1000;c.advance()
            with delayed(c):
                c.prepare();before=c.files()
                with patch.object(m.entry.submission,'submit',side_effect=AssertionError('send')),patch.object(m.fresh_signing.backend,'_invoke',side_effect=AssertionError('sign')),patch.object(m.exits.capture,'collect',side_effect=AssertionError('collect')):
                    self.assertEqual(c.inspect()['networkRequests'],0)
                    self.assertEqual(c.prepare()['networkRequests'],0)
                self.assertEqual(before,c.files())

    def test_durable_stop_allows_settlement_but_no_exit(self):
        with case() as c:
            c.run_entry();c.now+=1000
            book=m.entry.submission._open(c.home,c.wallet,c.pool,lambda:c.now)
            try:book.stop()
            finally:book.close()
            r=c.advance(prepare_exit=True)
            self.assertEqual(r['state'],'entry-settled-exit-stopped');self.assertEqual(r['exitRequestsThisRun'],0)
            self.assertTrue(r['accounting']['accountingUsable'])


if __name__=='__main__':unittest.main()
