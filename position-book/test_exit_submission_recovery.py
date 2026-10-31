"""Disposable full-source signed exit, synthetic transport and isolated restore."""
import json
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import admission_exit as m
import admission_recovery as recovery
import restricted_exit_signer as backend
import exit_submission as transport
from exit_submission_checks import FakeRpc
import test_exit_signing_recovery as source
from test_admission_exit_recovery import delayed

class SubmissionRestoreTests(unittest.TestCase):
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

    def test_full_source_exit_submission_and_restore(self):
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
            r=backend.dispatch(self.home,self.wallet,self.pool,allow_private_key_signing=True,clock=m.view.now)
            self.assertEqual(r['state'],'exit-signed-recorded');self.assertTrue(r['backendInvokedThisRun'])
            self.assertFalse(r['validForSubmission']);self.assertEqual(r['transactionsSent'],0)
            b=backend.handoff.preparation.entry.submission._open(self.home,self.wallet,self.pool,m.view.now)
            try:state=transport.ExitSubmission(b).signing()
            finally:b.close()
            c=SimpleNamespace(home=self.home,wallet=self.wallet,pool=self.pool,path=b.j.path,
                exit_state=state,exit_wire=state['signed']['signedWireBase64'])
            # Synthetic transport uses a deterministic clock. This is a semantic
            # integration/restore test, not a live RPC latency acceptance test.
            self.stamp=state['lastAtMs']
            sent=transport.submit(self.home,self.wallet,self.pool,allow_devnet_submit=True,opener=FakeRpc(c),clock=self.clock)
            self.assertEqual(sent['state'],'rpc-acknowledged');self.assertEqual(sent['sendRequestsThisRun'],1)
            key.unlink();self.stamp=m.view.now()+30000
            observed=transport.recover(self.home,self.wallet,self.pool,opener=FakeRpc(c),clock=self.clock)
            self.assertEqual(observed['state'],'exit-finalized-evidence')
            self.assertFalse(observed['receiptEffectsReconciled'])
            (self.home/'STOP').touch(mode=0o600)
            with patch.object(backend,'_invoke',side_effect=AssertionError('backend')):
                r=backend.recover(self.home,self.wallet,self.pool,clock=self.clock)
                self.assertTrue(r['acknowledgmentRecorded']);self.assertFalse(r['privateKeyAccessedThisRun'])
            before=self.source_bytes();self.capture();self.verify();self.assertEqual(before,self.source_bytes())
            manifest=json.loads((self.snapshot/recovery.MANIFEST).read_text())
            self.assertEqual(manifest['projection']['exitTransport']['state'],'exit-finalized-evidence')
            self.assertTrue(manifest['projection']['exitBackendAttemptPresent']);self.assertTrue(manifest['projection']['exitBackendAcknowledgmentPresent'])
            # A replaced marker still fails semantic replay with transport present.
            path=self.snapshot/recovery.SIBLING/backend.ATTEMPT;v=json.loads(path.read_text());v['preparationSha256']='0'*64;path.write_text(json.dumps(v))
            manifest['inventories']=recovery.inventories(self.snapshot/recovery.SOURCE,self.snapshot/recovery.SIBLING)
            (self.snapshot/recovery.MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'exit-signer-attempt-binding'):self.verify()
