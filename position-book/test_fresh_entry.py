"""Fresh sender composition, original deadlines and independent backend tests."""
import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import fresh_entry as m
from fresh_entry_checks import run,case
import test_fresh_signing as full


class FreshEntryTests(unittest.TestCase):
    def test_portable_suite(self):self.assertEqual(run()['casesPassed'],21)

    def test_cli_is_exclusive_private_and_offline_only(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'report.gz'
            cmd=[sys.executable,'-E','-s',str(Path(__file__).with_name('fresh_entry_cli.py')),'--output',str(path)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=path.read_bytes();self.assertEqual(json.loads(gzip.decompress(raw))['casesPassed'],21)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(path.read_bytes(),raw)
            for flag in ('--action','--directory','--wallet','--allow-private-key-signing','--allow-devnet-submit','--receipt'):
                other=Path(d)/'no.gz'
                self.assertNotEqual(subprocess.run(cmd[:-1]+[str(other),flag],capture_output=True).returncode,0)
                self.assertFalse(other.exists())

    def test_changed_source_after_signing_blocks_sender_without_rpc(self):
        def change(c,n,r):
            if n==3:r['ledgerHeadSha256']='d'*64
        with case(read_hook=change) as c:
            r=c.run();self.assertEqual(r['diagnosticCode'],'fresh-entry-source-changed')
            self.assertEqual(c.calls,1);self.assertEqual(r['senderRequests'],0)
            self.assertFalse(c.transport()['applicationSendBoundaryRecorded'])

    def test_sender_identity_rechecked_under_sender_lock(self):
        with case() as c:
            state=m.submission.Submission.state
            def wrong(s):
                value,head,at=state(s);value=dict(value,validUntilExclusiveMs=value['validUntilExclusiveMs']+1)
                return value,head,at
            with patch.object(m.submission.Submission,'state',wrong):r=c.run()
            self.assertEqual(r['diagnosticCode'],'fresh-entry-identity');self.assertEqual(r['senderRequests'],0)

    def test_monotonic_regression_between_requests_blocks_send(self):
        with case() as c:
            c.mono=5
            def change(method):
                if method=='isBlockhashValid':c.mono=4
            r=c.run(rpc=c.opener(callback=change))
            self.assertEqual(r['diagnosticCode'],'fresh-signing-monotonic')
            self.assertEqual(r['senderRequests'],2);self.assertEqual(r['sendRequestsThisRun'],0)

    def test_collection_time_is_not_reset_for_sender(self):
        with case(collect_hook=lambda c,r:setattr(c,'mono',29)) as c:
            def change(method):
                if method=='getGenesisHash':c.mono=30
            r=c.run(rpc=c.opener(callback=change))
            self.assertEqual(r['senderRequests'],1);self.assertEqual(r['sendRequestsThisRun'],0)
            self.assertEqual(r['diagnosticCode'],'fresh-signing-monotonic')

    def test_commit_and_ack_failures_keep_uncertainty_without_retry(self):
        for method,sends in [('mark',0),('acknowledge',1)]:
            with case() as c,patch.object(m.submission.Submission,method,side_effect=sqlite3.OperationalError('PRIVATE')):
                r=c.run();self.assertEqual(r['state'],'fresh-entry-inspection-required')
                self.assertEqual(r['sendRequestsThisRun'],sends);self.assertIsNone(r['applicationSendBoundaryRecorded'])
                self.assertNotIn('PRIVATE',json.dumps(r));self.assertEqual(c.run()['networkRequests'],0)

    def test_stop_after_boundary_preserves_unknown_without_transport(self):
        with case() as c:
            mark=m.submission.Submission.mark
            def stop(book,proof):
                result=mark(book,proof);(c.home/'STOP').touch(mode=0o600);return result
            with patch.object(m.submission.Submission,'mark',stop):r=c.run()
            self.assertEqual(r['sendRequestsThisRun'],0);self.assertEqual(c.transport()['state'],'submission-unknown')
            self.assertEqual(c.run()['networkRequests'],0)

    def test_recovery_of_unattempted_signed_entry_never_sends(self):
        with case() as c:
            r=c.run(rpc=c.opener(valid=False));self.assertEqual(r['sendRequestsThisRun'],0)
            with patch.object(m.signing.backend,'_invoke',side_effect=AssertionError('sign')),patch.object(m.signing.timing.fresh_quote,'observe',side_effect=AssertionError('collect')):
                recovered=c.recover();self.assertEqual(recovered['state'],'not-attempted')
                self.assertEqual(recovered['networkRequestsThisRun'],0);self.assertFalse(recovered['resumesEntry'])


class FullSourceEntryTests(unittest.TestCase):
    setUpClass=full.FullSourceSigningTests.__dict__['setUpClass']
    tearDownClass=full.FullSourceSigningTests.__dict__['tearDownClass']
    setUp=full.FullSourceSigningTests.setUp
    tearDown=full.FullSourceSigningTests.tearDown
    files=full.FullSourceSigningTests.files
    pipeline=full.FullSourceSigningTests.pipeline

    def integrate(self,*,lost=False):
        from types import SimpleNamespace
        from admission_submission_checks import FakeOpener
        from admission_receipt_checks import receipt
        key=self.home/'signer.pk8';key.write_bytes(self.test_key);key.chmod(0o600)
        before=self.files();observations=[];transports=[]
        observe=m.signing.timing.fresh_quote.observe
        def collect(*args,**kw):
            sink=kw['_evidence_sink']
            def capture(e):observations.append(e);sink(e)
            return observe(*args,**dict(kw,_evidence_sink=capture))
        test=self
        class Lazy:
            def open(self,request,timeout=None):
                if not transports:
                    book=m.submission._open(test.home,test.wallet,test.pool,m.signing.view.now)
                    try:private=book.private_accounting_handoff();package=receipt(observations[0],private)
                    finally:book.close()
                    fixture=SimpleNamespace(e=observations[0],path=m.signing.handoff.storage(test.home),package=package,
                        signed={'signedTransactionBase64':private['signedTransactionBase64']})
                    transports.append(FakeOpener(fixture,lost=lost))
                return transports[0].open(request,timeout)
        def call(*args,**kw):
            # The independent Node backend timestamps its attempt with the real clock.
            # Use that same advancing clock through the parent sender.
            kw['clock']=m.signing.view.now
            return m.prepare_sign_submit(*args,**kw,allow_private_key_signing=True,allow_devnet_submit=True,submission_opener=Lazy())
        with patch.object(m.signing.timing,'observe',call),patch.object(m.signing.timing.fresh_quote,'observe',collect):
            r,_,_,_=self.pipeline()
        self.assertEqual(before,self.files());return r,transports

    def test_actual_collector_backend_exact_sender_and_keyless_receipt_recovery(self):
        r,transports=self.integrate()
        self.assertEqual(r['state'],'rpc-acknowledged',r);self.assertEqual(r['networkRequests'],25)
        self.assertTrue(r['privateKeyAccessed']);self.assertEqual(r['signaturesCreated'],1)
        self.assertTrue(r['originalDeadlineCheckedBeforeSend']);self.assertTrue(r['completedWithinOriginalDeadline'])
        (self.home/'signer.pk8').unlink();(self.home/'STOP').touch(mode=0o600)
        with patch('socket.socket',side_effect=AssertionError('network')),patch.object(m.signing.backend,'_invoke',side_effect=AssertionError('sign')),patch.object(m.signing.timing.fresh_quote,'observe',side_effect=AssertionError('collect')):
            a=m.recover(self.home,self.wallet,self.pool,opener=transports[0],clock=lambda:self._profile_stamp+20000)
            self.assertEqual(a['state'],'entry-effects-observed');self.assertEqual(a['sendRequestsThisRun'],0)
            b=m.recover(self.home,self.wallet,self.pool,opener=transports[0],clock=lambda:self._profile_stamp+20000)
            self.assertEqual(b['networkRequestsThisRun'],0);self.assertFalse(b['reservationReleased'])

    def test_actual_backend_lost_send_recovers_only_existing_signature(self):
        r,transports=self.integrate(lost=True)
        self.assertEqual(r['state'],'submission-unknown',r);self.assertEqual(r['sendRequestsThisRun'],1)
        (self.home/'signer.pk8').unlink()
        with patch('socket.socket',side_effect=AssertionError('network')):
            r=m.recover(self.home,self.wallet,self.pool,opener=transports[0],clock=lambda:self._profile_stamp+20000)
        self.assertEqual(r['state'],'entry-effects-observed');self.assertEqual(r['signaturesCreated'],0)
        self.assertEqual(sum(x['method']=='sendTransaction' for x in transports[0].requests),1)


if __name__=='__main__':unittest.main()
