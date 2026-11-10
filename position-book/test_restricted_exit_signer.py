"""Actual isolated exit key process, saved-ack recovery and snapshot integration."""
import base64
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import admission_exit as m
import admission_recovery as recovery
import restricted_exit_signer as backend
import test_exit_signing_recovery as source
from test_admission_exit_recovery import delayed
from exit_signing_handoff_checks import ready,dispatch as fixture_dispatch
from core import write_new
from contract import digest

HERE=Path(__file__).resolve().parent

class BackendTests(unittest.TestCase):
    def test_offline_cli_with_disposable_keys(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'check.gz';cmd=[sys.executable,'-E','-s',str(HERE/'restricted_exit_signer_cli.py'),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();v=json.loads(gzip.decompress(raw));self.assertEqual(v['casesPassed'],27)
            self.assertEqual(v['signaturesCreated'],2);self.assertFalse(v['productionWalletAccessed'])
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
            for flag in ('--execute','--directory','--wallet','--allow-devnet-submit'):
                self.assertNotEqual(subprocess.run(cmd+[flag],capture_output=True).returncode,0)

    def test_default_refuses_without_access(self):
        with patch.object(backend.handoff,'dispatch',side_effect=AssertionError('dispatch')):
            with self.assertRaisesRegex(ValueError,'explicit-exit-private-key-opt-in-required'):
                backend.dispatch('/missing','wallet','pool')

    def test_saved_ack_recovery_is_keyless_and_checks_markers(self):
        with ready() as c:
            def lost(_):raise TimeoutError('synthetic lost reply')
            with self.assertRaises(TimeoutError):fixture_dispatch(c,lost)
            b=c.book()
            try:
                state=backend.handoff.read(b,c.now)
                boundary=b.db.execute('SELECT hash,at_ms FROM admission_exit_signing WHERE seq=1').fetchone()
                write_new(c.path.parent/backend.ATTEMPT,dict(format='exit-signer-attempt-1',requestSha256=state['requestSha256'],signingHeadSha256=boundary['hash'],preparationSha256=state['request']['preparationSha256'],atMs=c.now))
                wire=backend.handoff.signed_check(c.exit_wire,state['request'])
                write_new(c.path.parent/backend.ACK,dict(format='exit-signer-ack-1',requestSha256=state['requestSha256'],signedTransactionBase64=c.exit_wire,wireSha256=wire['wireSha256']))
            finally:b.close()
            c.now+=30000;(c.home/'STOP').touch(mode=0o600)
            with patch.object(backend,'_invoke',side_effect=AssertionError('key backend')):
                r=backend.recover(c.home,c.wallet,c.pool,clock=lambda:c.now)
                self.assertTrue(r['acknowledgmentRecorded']);self.assertTrue(r['stopRequested']);self.assertFalse(r['privateKeyAccessedThisRun'])
                before=c.path.read_bytes();backend.recover(c.home,c.wallet,c.pool,clock=lambda:c.now);self.assertEqual(before,c.path.read_bytes())
            path=c.path.parent/backend.ATTEMPT;v=json.loads(path.read_text());v['signingHeadSha256']='0'*64;path.write_text(json.dumps(v))
            with self.assertRaisesRegex(ValueError,'exit-signer-attempt-binding'):backend.recover(c.home,c.wallet,c.pool,clock=lambda:c.now)

class IntegratedBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):source.SigningRecoveryTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):source.SigningRecoveryTests.tearDownClass.__func__(cls)
    setUp=source.SigningRecoveryTests.setUp
    tearDown=source.SigningRecoveryTests.tearDown
    clock=source.SigningRecoveryTests.clock
    submit=source.SigningRecoveryTests.submit
    collect=source.SigningRecoveryTests.collect
    settle=source.SigningRecoveryTests.settle
    capture=source.SigningRecoveryTests.capture
    verify=source.SigningRecoveryTests.verify
    source_bytes=source.SigningRecoveryTests.source_bytes
    edit_db=source.SigningRecoveryTests.edit_db

    def exercise(self,*,expired_backend=False):
        import admission_exit_collection as collected
        import admission_exit_capture_checks as fixtures
        self.collect();accounting=self.settle()['accounting'];self.stamp=m.view.now()
        e=delayed(self.e['costInputs']['capture'],accounting,self.stamp)
        raw=e['initialPool'];first=deepcopy(e['capture'])
        first.update(packet=None,selection='explicit-pool',accountKeys=raw['accountKeys']+[first['accountKeys'][-1]])
        programdata=deepcopy(first['evidence']['accounts']['result']['value'][-1])
        first['evidence']['accounts']=deepcopy(raw['evidence']['accounts'])
        first['evidence']['accounts']['result']['value'].append(programdata)
        first['evidence']['poolBootstrap']=deepcopy(raw['evidence']['bootstrap'])
        first['evidence']['programBootstrap']['result']['context']['slot']=first['evidence']['poolBootstrap']['result']['context']['slot']
        for name in ('genesisBefore','genesisAfter','blockTime'):
            first['evidence'][name]=deepcopy(raw['evidence'][name])
        first['evidence']['blockhash']={'state':'not-requested'}
        first['evidence']['fee']={'state':'not-requested'}
        baseline=deepcopy(self.e['costInputs']['baseline'])
        baseline.update(kind='observed-devnet-deployment',observedAtMs=0)
        clock=fixtures.Clock();clock.at=m.view.now()
        rpc=fixtures.Opener(first,e)
        with patch.object(m,'BASELINE',baseline):
            prepared=collected.collect_and_prepare(self.home,self.wallet,self.pool,opener=rpc,clock=clock,monotonic=lambda:0)
            self.assertEqual(prepared['state'],'exit-prepared-research-only',prepared)
            self.assertTrue(prepared['collectionRecorded']);self.assertEqual(len(rpc.calls),20)
            key=self.home/'signer.pk8';key.write_bytes(self.ephemeral_exit_key);key.chmod(0o600)
            self.stamp=clock.at+1
            if expired_backend:
                # The same real child must reject an expired injected clock;
                # this fixture mechanism cannot bypass its deadline contract.
                expired=self.stamp+30000
                with source.fixture_backend_clock(lambda:expired) as backend_calls:
                    with self.assertRaisesRegex(ValueError,'restricted-exit-signer-refused'):
                        backend.dispatch(self.home,self.wallet,self.pool,allow_private_key_signing=True,clock=self.clock)
                self.assertEqual(backend_calls,[expired])
                storage=backend.handoff.preparation.entry.submission.handoff.storage(self.home).parent
                self.assertFalse((storage/backend.ATTEMPT).exists())
                self.assertFalse((storage/backend.ACK).exists())
                with patch.object(backend,'_invoke',side_effect=AssertionError('retry')):
                    r=backend.dispatch(self.home,self.wallet,self.pool,allow_private_key_signing=True,clock=self.clock)
                self.assertEqual(r['state'],'exit-signing-unknown')
                self.assertFalse(r['backendInvokedThisRun']);self.assertFalse(r['acknowledgmentRecorded'])
                return
            with source.fixture_backend_clock(self.clock) as backend_calls:
                r=backend.dispatch(self.home,self.wallet,self.pool,allow_private_key_signing=True,clock=self.clock)
            self.assertEqual(backend_calls,[self.stamp])
            self.assertEqual(r['state'],'exit-signed-recorded');self.assertTrue(r['backendInvokedThisRun'])
            self.assertFalse(r['validForSubmission']);self.assertEqual(r['transactionsSent'],0)
            key.unlink();self.stamp=m.view.now()+30000
            (self.home/'STOP').touch(mode=0o600)
            with patch.object(backend,'_invoke',side_effect=AssertionError('backend')):
                r=backend.recover(self.home,self.wallet,self.pool,clock=self.clock)
                self.assertTrue(r['acknowledgmentRecorded']);self.assertFalse(r['privateKeyAccessedThisRun'])
            before=self.source_bytes();self.capture();self.verify();self.assertEqual(before,self.source_bytes())
            manifest=json.loads((self.snapshot/recovery.MANIFEST).read_text())
            self.assertTrue(manifest['projection']['exitBackendAttemptPresent']);self.assertTrue(manifest['projection']['exitBackendAcknowledgmentPresent'])
            # A replaced marker fails semantic replay even with updated inventory.
            path=self.snapshot/recovery.SIBLING/backend.ATTEMPT;v=json.loads(path.read_text());v['preparationSha256']='0'*64;path.write_text(json.dumps(v))
            manifest['inventories']=recovery.inventories(self.snapshot/recovery.SOURCE,self.snapshot/recovery.SIBLING)
            (self.snapshot/recovery.MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'exit-signer-attempt-binding'):self.verify()

    def test_real_source_to_independent_backend_and_keyless_restore(self):self.exercise()

    def test_fixed_fixture_clock_preserves_backend_expiry_and_no_retry(self):self.exercise(expired_backend=True)


if __name__=='__main__':unittest.main()
