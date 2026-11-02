"""Fresh collection integration, independent disposable signer and failure boundaries."""
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import fresh_signing as m
from fresh_signing_checks import run,case,state
import test_restricted_signer as real_source
import test_signature_replay as pipeline_source


class FreshSigningTests(unittest.TestCase):
    def test_portable_contract(self):self.assertEqual(run()['casesPassed'],17)

    def test_cli_rejects_operational_flags_and_keeps_report_private(self):
        cli=Path(__file__).with_name('fresh_signing_cli.py')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'check.gz';cmd=[sys.executable,'-E','-s',str(cli),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(raw))['casesPassed'],17)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
            for flag in ('--directory','--wallet','--action','--allow-private-key-signing','--allow-devnet-submit'):
                target=Path(d)/'no.gz'
                self.assertNotEqual(subprocess.run(cmd[:-1]+[str(target),flag],capture_output=True).returncode,0)
                self.assertFalse(target.exists())

    def test_original_raw_validation_rejects_tampered_price_without_backend(self):
        with case() as c:
            c.e['costInputs']['price']['quote']['outAmount']='999999999'
            # Collector fixture owns this object; mutation must be caught by the
            # actual raw reviewer, not by a precomputed report success flag.
            r=c.run();self.assertFalse(r['signerAcknowledgmentValidated']);self.assertEqual(c.calls,0)
            self.assertEqual(state(c)['state'],'empty')

    def test_stop_before_dispatch_does_not_claim_signature_or_key_access(self):
        with case() as c:
            original=m.handoff.storage
            def stopped(root,**kwargs):
                path=original(root,**kwargs)
                (root/'STOP').touch(mode=0o600)
                return path
            with patch.object(m.handoff,'storage',stopped):r=c.run()
            self.assertEqual(r['state'],'stopped');self.assertEqual(r['signerInvocationAttempts'],0)
            self.assertEqual(r['signaturesCreated'],0);self.assertFalse(r['privateKeyAccessed'])

    def test_storage_failure_before_boundary_never_invokes_signer(self):
        with case() as c,patch.object(m.timing.admission,'MAX_EVENTS',2):
            r=c.run();self.assertEqual(c.calls,0);self.assertTrue(r['recoveryRequired'])
        with case() as c,patch.object(m.handoff.Admission,'stage_accounting_handoff',side_effect=OSError('disk unavailable')):
            r=c.run();self.assertEqual(c.calls,1);self.assertIsNone(r['signaturesCreated'])
            self.assertEqual(state(c)['state'],'signed-recorded');self.assertTrue(r['recoveryRequired'])

    def test_clock_and_monotonic_regression_block_backend(self):
        for mode in ('clock','monotonic'):
            with case() as c:
                c.mono=1
                original=m.handoff.Admission.mark_signing_boundary
                def regress(b,e):
                    r=original(b,e)
                    if mode=='clock':c.now-=1
                    else:c.mono=0
                    return r
                with patch.object(m.handoff.Admission,'mark_signing_boundary',regress):r=c.run()
                self.assertEqual(c.calls,0);self.assertTrue(r['recoveryRequired'])

    def test_budget_and_scope_mismatch_cannot_create_a_permit(self):
        with case() as c:
            with patch.object(m.timing.fresh_quote,'observe',side_effect=AssertionError('collection')):
                r=m._run(c.home,c.wallet,c.pool,signer_adapter=c.adapter,maximum_exit_attempts=3,
                    maximum_exit_fee_lamports='10001',maximum_total_fee_lamports='40000')
                self.assertEqual(r['state'],'unavailable');self.assertFalse(c.path.exists())
            c.e['scope']['accounts']['pool']='11111111111111111111111111111111'
            r=c.run();self.assertEqual(c.calls,0);self.assertFalse(c.path.exists())


class FullSourceSigningTests(unittest.TestCase):
    setUpClass=classmethod(real_source.RealSourceBackendTests.setUpClass.__func__)
    tearDownClass=classmethod(real_source.RealSourceBackendTests.tearDownClass.__func__)
    setUp=real_source.RealSourceBackendTests.setUp
    tearDown=real_source.RealSourceBackendTests.tearDown
    files=real_source.RealSourceBackendTests.files
    pipeline=pipeline_source.SourceReplayTests.pipeline

    def integrate(self):
        key=self.home/'signer.pk8';key.write_bytes(self.test_key);key.chmod(0o600)
        before=self.files()
        def call(*a,**kw):return m.prepare_and_sign(*a,allow_private_key_signing=True,**kw)
        with patch.object(m.timing,'observe',call):r,processes,reads,elapsed=self.pipeline()
        self.assertEqual(before,self.files())
        return r

    def test_actual_fresh_collection_independent_key_backend_and_recovery(self):
        r=self.integrate()
        self.assertEqual(r['state'],'signed-recorded',r);self.assertTrue(r['signerAcknowledgmentValidated'])
        self.assertEqual(r['networkRequests'],20);self.assertEqual(r['signerInvocationAttempts'],1)
        self.assertTrue(r['privateKeyAccessed']);self.assertTrue(r['handoff']['accountingHandoffReady'])
        self.assertEqual(r['transactionsSent'],0);self.assertTrue(r['completedWithinOriginalDeadline'])
        (self.home/'signer.pk8').unlink()
        with patch.object(m.backend,'_invoke',side_effect=AssertionError('resign')),patch.object(m.timing.fresh_quote,'observe',side_effect=AssertionError('recollect')),patch('socket.socket',side_effect=AssertionError('network')):
            recovered=m.recover(self.home,self.wallet,self.pool,clock=lambda:self._profile_stamp+20000)
            self.assertTrue(recovered['accountingHandoffReady']);self.assertFalse(recovered['privateKeyAccessedThisRun'])
            repeated=m.prepare_and_sign(self.home,self.wallet,self.pool,allow_private_key_signing=True,
                maximum_exit_attempts=2,maximum_exit_fee_lamports='10000',maximum_total_fee_lamports='30000')
            self.assertEqual(repeated['diagnosticCode'],'timing-existing-admission')
            self.assertEqual(repeated['networkRequests'],0)

    def test_lost_real_signer_response_uses_saved_ack_without_key_or_recollection(self):
        invoke=m.backend._invoke
        def lost(root,request):
            invoke(root,request)
            raise TimeoutError('lost independent signer acknowledgment')
        with patch.object(m.backend,'_invoke',side_effect=lost):r=self.integrate()
        self.assertEqual(r['state'],'fresh-signing-inspection-required',r)
        self.assertIsNone(r['signaturesCreated']);self.assertIsNone(r['privateKeyAccessed'])
        (self.home/'signer.pk8').unlink()
        with patch.object(m.backend,'_invoke',side_effect=AssertionError('resign')),patch.object(m.timing.fresh_quote,'observe',side_effect=AssertionError('recollect')),patch('socket.socket',side_effect=AssertionError('network')):
            a=m.recover(self.home,self.wallet,self.pool,clock=lambda:self._profile_stamp+20000)
            b=m.recover(self.home,self.wallet,self.pool,clock=lambda:self._profile_stamp+20000)
            self.assertEqual(a,b);self.assertTrue(a['accountingHandoffReady'])
            self.assertEqual(a['signaturesCreatedThisRun'],0)


if __name__=='__main__':unittest.main()
