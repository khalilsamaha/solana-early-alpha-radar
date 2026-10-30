"""Opt-in backend binding and actual source-to-signer integration in test directories."""
from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import restricted_signer as m
import pre_sign_admission as admission
import test_readiness as source_fixture
import test_locked_admission as locked_fixture
from locked_admission_checks import fixture, home_fixture, NOW
from core import write_new
from contract import digest
from restricted_signer_cli import run

HERE = Path(__file__).resolve().parent


class BackendTests(unittest.TestCase):
    def test_disposable_independent_backend_checks(self):
        r=run()
        self.assertEqual(r['casesPassed'],19)
        self.assertEqual(r['signaturesCreated'],1);self.assertEqual(r['ephemeralTestKeysCreated'],2)
        self.assertFalse(r['productionWalletAccessed']);self.assertEqual(r['transactionsSent'],0)

    def test_default_refuses_before_key_or_source_access(self):
        with patch.object(m.handoff,'dispatch',side_effect=AssertionError('dispatch')):
            with self.assertRaisesRegex(ValueError,'explicit-private-key-opt-in-required'):
                m.dispatch('/missing','wallet','pool',{}, {})

    def test_cli_refuses_live_arguments_and_preserves_private_output(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'check.gz';cmd=[sys.executable,'-E','-s',str(HERE/'restricted_signer_cli.py'),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(raw))['casesPassed'],19)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),raw)
            for flag in ('--directory','--wallet','--execute','--allow-devnet-submit','--sign'):
                self.assertNotEqual(subprocess.run(cmd+[flag],capture_output=True).returncode,0)

    def test_saved_ack_recovery_has_no_key_or_backend_calls(self):
        e,p,signed=fixture();wallet=p['scope']['accounts']['wallet'];pool=p['scope']['accounts']['pool']
        snapshot=deepcopy(e['costInputs']['reservations']);snapshot.update(readStartedAtMs=NOW+200,observedAtMs=NOW+200)
        with tempfile.TemporaryDirectory() as d,patch.object(admission,'BASELINE',e['costInputs']['baseline']),patch.object(m.handoff.bridge.view,'read_locked',return_value=snapshot):
            home=home_fixture(Path(d)/'source',wallet)
            def lost(request): raise TimeoutError('test lost reply')
            with self.assertRaises(TimeoutError):
                m.handoff.dispatch(home,wallet,pool,e,p,signer_adapter=lost,clock=lambda:NOW+200)
            b=admission.Admission(m.handoff.storage(home),clock=lambda:NOW+200)
            try:
                state,_,head,_=b.read()
                import base64,hashlib
                write_new(b.j.path.parent/'signer-attempt.json',dict(format='admission-signer-attempt-1',requestSha256=state['signingRequestSha256'],admissionHeadSha256=head,atMs=NOW+200))
                write_new(b.j.path.parent/'signer-ack.json',dict(format='admission-signer-ack-1',requestSha256=state['signingRequestSha256'],signedTransactionBase64=signed['signedTransactionBase64'],wireSha256=hashlib.sha256(base64.b64decode(signed['signedTransactionBase64'])).hexdigest()))
            finally:b.close()
            with patch.object(m,'_invoke',side_effect=AssertionError('backend')),patch('core.signer',side_effect=AssertionError('key')),patch('socket.socket',side_effect=AssertionError('network')):
                r=m.recover(home,wallet,pool,clock=lambda:NOW+30000)
                self.assertTrue(r['accountingHandoffReady']);self.assertFalse(r['backendInvokedThisRun'])
                self.assertEqual(r,m.recover(home,wallet,pool,clock=lambda:NOW+30000))
            attempt=b.j.path.parent/'signer-attempt.json';data=json.loads(attempt.read_text());data['admissionHeadSha256']='0'*64;attempt.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'signer-attempt-boundary'):m.recover(home,wallet,pool,clock=lambda:NOW+30000)


class RealSourceBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Capture only the synthetic fixture key immediately before that fixture
        # deliberately removes it. No user wallet is accessed by the test suite.
        original=Path.unlink;captured={}
        def unlink(p,*args,**kw):
            if p.name=='signer.pk8' and p.exists():
                meta=json.loads((p.parent/'wallet.json').read_text());captured[meta['wallet']]=p.read_bytes()
            return original(p,*args,**kw)
        with patch.object(Path,'unlink',unlink):source_fixture.ReadinessCase.setUpClass.__func__(cls)
        cls.test_key=captured[cls.wallet]
    @classmethod
    def tearDownClass(cls):
        cls.test_key=None;source_fixture.ReadinessCase.tearDownClass.__func__(cls)
    setUp=source_fixture.ReadinessCase.setUp
    tearDown=source_fixture.ReadinessCase.tearDown
    files=source_fixture.ReadinessCase.files
    evidence=locked_fixture.RealSourceAdmissionTests.evidence

    def test_real_source_admission_independent_signer_and_saved_ack(self):
        key=self.home/'signer.pk8';key.write_bytes(self.test_key);key.chmod(0o600)
        before=self.files();e,baseline,stamp=self.evidence()
        p=dict(format=admission.VERSION+'-policy',scope=deepcopy(e['scope']),maximumExitAttempts=2,
               maximumExitFeeLamports='10000',maximumTotalFeeLamports='40000')
        with patch.object(admission,'BASELINE',baseline),patch('socket.socket',side_effect=AssertionError('network')):
            r=m.dispatch(self.home,self.wallet,self.pool,e,p,allow_private_key_signing=True)
        self.assertEqual(r['state'],'signed-recorded');self.assertTrue(r['backendInvokedThisRun'])
        self.assertTrue(r['accountingHandoffReady']);self.assertFalse(r['executionApproved'])
        # Continue the actual signed wire into the receipt gate using explicitly
        # synthetic RPC claims; this is not a submitted transaction or chain fill.
        import admission_receipt
        from admission_receipt_checks import receipt
        b=admission.Admission(m.handoff.storage(self.home))
        try:package=receipt(e,b.private_accounting_handoff())
        finally:b.close()
        package['bundle']['capturedAtMs']=m.handoff.bridge.view.now()
        observed=admission_receipt.observe(self.home,self.wallet,self.pool,package)
        self.assertEqual(observed['state'],'entry-effects-observed')
        self.assertFalse(observed['submissionProvenanceVerified']);self.assertFalse(observed['reservationReleased'])
        self.assertEqual(before,self.files())
        with patch.object(m,'_invoke',side_effect=AssertionError('second backend')):
            again=m.dispatch(self.home,self.wallet,self.pool,e,p,allow_private_key_signing=True)
        self.assertFalse(again['backendInvokedThisRun'])
        key.unlink()
        with patch('core.signer',side_effect=AssertionError('key')):
            recovered=m.recover(self.home,self.wallet,self.pool)
        self.assertTrue(recovered['accountingHandoffReady']);self.assertFalse(recovered['privateKeyAccessedThisRun'])

    def prepare(self):
        key=self.home/'signer.pk8';key.write_bytes(self.test_key);key.chmod(0o600)
        e,baseline,stamp=self.evidence()
        p=dict(format=admission.VERSION+'-policy',scope=deepcopy(e['scope']),maximumExitAttempts=2,
               maximumExitFeeLamports='10000',maximumTotalFeeLamports='40000')
        return e,p,baseline

    def test_lost_parent_response_recovers_actual_saved_signature_without_key(self):
        e,p,baseline=self.prepare();invoke=m._invoke
        def lost(root,request):
            invoke(root,request)
            raise TimeoutError('synthetic parent acknowledgment loss')
        with patch.object(admission,'BASELINE',baseline),patch.object(m,'_invoke',side_effect=lost):
            with self.assertRaises(TimeoutError):
                m.dispatch(self.home,self.wallet,self.pool,e,p,allow_private_key_signing=True)
        b=admission.Admission(m.handoff.storage(self.home))
        try:self.assertEqual(b.status()['state'],'signing-unknown')
        finally:b.close()
        (self.home/'signer.pk8').unlink()
        with patch.object(m,'_invoke',side_effect=AssertionError('resign')):
            r=m.recover(self.home,self.wallet,self.pool)
            self.assertTrue(r['accountingHandoffReady']);self.assertEqual(r['signaturesCreatedThisRun'],0)

    def test_concurrent_independent_backend_processes_create_only_one_ack(self):
        from concurrent.futures import ThreadPoolExecutor
        e,p,baseline=self.prepare();results=[]
        def competing(request):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures=[executor.submit(m._invoke,self.home,request) for _ in range(2)]
                for f in futures:
                    try:results.append(('signed',f.result()))
                    except ValueError:results.append(('refused',None))
            self.assertEqual([state for state,_ in results].count('signed'),1)
            self.assertEqual([state for state,_ in results].count('refused'),1)
            return next(wire for state,wire in results if state=='signed')
        with patch.object(admission,'BASELINE',baseline):
            r=m.handoff.dispatch(self.home,self.wallet,self.pool,e,p,signer_adapter=competing)
        self.assertTrue(r['accountingHandoffReady'])
        self.assertEqual(len(list(m.handoff.storage(self.home).parent.glob('signer-ack.json'))),1)


if __name__=='__main__':unittest.main()
