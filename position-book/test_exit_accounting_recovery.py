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
import exit_accounting as accounting
from exit_accounting_checks import package,ReceiptRpc
import test_exit_signing_recovery as source
from test_admission_exit_recovery import delayed

class AccountingRestoreTests(unittest.TestCase):
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

    def test_full_source_exit_accounting_and_restore(self):
        import admission_exit_collection as collected
        import admission_exit_capture_checks as fixtures
        self.collect();entry_accounting=self.settle()['accounting'];self.stamp=m.view.now()
        e=delayed(self.e['costInputs']['capture'],entry_accounting,self.stamp)
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
            with source.fixture_backend_clock(self.clock) as backend_calls:
                r=backend.dispatch(self.home,self.wallet,self.pool,allow_private_key_signing=True,clock=self.clock)
            self.assertEqual(backend_calls,[self.stamp])
            self.assertEqual(r['state'],'exit-signed-recorded');self.assertTrue(r['backendInvokedThisRun'])
            self.assertFalse(r['validForSubmission']);self.assertEqual(r['transactionsSent'],0)
            b=backend.handoff.preparation.entry.submission._open(self.home,self.wallet,self.pool,self.clock)
            try:state=transport.ExitSubmission(b).signing()
            finally:b.close()
            c=SimpleNamespace(home=self.home,wallet=self.wallet,pool=self.pool,path=b.j.path,
                exit_state=state,exit_wire=state['signed']['signedWireBase64'])
            # Synthetic transport uses a deterministic clock. This is a semantic
            # integration/restore test, not a live RPC latency acceptance test.
            self.stamp=state['lastAtMs']
            self.assertLess(self.stamp,state['request']['validUntilExclusiveMs'])
            sent=transport.submit(self.home,self.wallet,self.pool,allow_devnet_submit=True,opener=FakeRpc(c),clock=self.clock)
            self.assertEqual(sent['state'],'rpc-acknowledged');self.assertEqual(sent['sendRequestsThisRun'],1)
            key.unlink();self.stamp=m.view.now()+30000
            c.now=self.stamp
            c.book=lambda:transport.transport._open(self.home,self.wallet,self.pool,self.clock)
            p,_=package(c)
            observed=transport.recover(self.home,self.wallet,self.pool,opener=ReceiptRpc(c,p),clock=self.clock)
            self.assertEqual(observed['state'],'exit-finalized-evidence')
            self.assertFalse(observed['receiptEffectsReconciled'])
            settled=accounting.apply(self.home,self.wallet,self.pool,clock=self.clock)
            self.assertTrue(settled['accountingUsable']);self.assertEqual(settled['state'],'exit-position-flat-held')
            self.assertEqual(settled['accounting']['ownedAcquiredResidualAtomic'],'0')
            self.assertFalse(settled['reservationReleased'])
            # The next read-only gate binds fresh balances to these full-source receipts.
            from exit_balance_checks import FakeRpc as BalanceRpc
            import exit_balance
            before_balances=self.source_bytes();admission_before=c.path.read_bytes()
            balances=exit_balance.collect(self.home,self.wallet,self.pool,opener=BalanceRpc(c),clock=self.clock,monotonic=lambda:0)
            self.assertEqual(balances['state'],'exit-balances-match-held',balances)
            self.assertEqual(balances['networkRequests'],4);self.assertFalse(balances['reservationReleased'])
            self.assertEqual(before_balances,self.source_bytes());self.assertEqual(admission_before,c.path.read_bytes())
            import exit_closure
            closure=exit_closure.collect_and_close(self.home,self.wallet,self.pool,opener=BalanceRpc(c),clock=self.clock,monotonic=lambda:0)
            self.assertTrue(closure['scopedCommitmentsReleased']);self.assertTrue(closure['appliedThisRun'])
            self.assertFalse(closure['fundsAvailableForNewEntry'])
            import admission_lifecycle
            admission_closed=c.path.read_bytes();sources_closed=self.source_bytes()
            lifecycle=admission_lifecycle.inspect(self.home,self.wallet,self.pool,clock=self.clock,monotonic=lambda:0)
            self.assertEqual(lifecycle['phase'],'closed',lifecycle)
            self.assertTrue(lifecycle['coherent']);self.assertFalse(lifecycle['fundsAvailableForNewEntry'])
            self.assertEqual(lifecycle['scopedAccounting']['sourceProceedsHeldAtomic'],'0')
            self.assertEqual(lifecycle['recordIdentity']['closureSha256'],closure['recordSha256'])
            self.assertEqual(admission_closed,c.path.read_bytes());self.assertEqual(sources_closed,self.source_bytes())
            (self.home/'STOP').touch(mode=0o600)
            stopped_book=c.book()
            try:stopped_book.stop()
            finally:stopped_book.close()
            admission_closed=c.path.read_bytes()
            lifecycle=admission_lifecycle.inspect(self.home,self.wallet,self.pool,clock=self.clock,monotonic=lambda:0)
            self.assertEqual(lifecycle['phase'],'closed',lifecycle);self.assertTrue(lifecycle['stopRequested'])
            self.assertEqual(admission_closed,c.path.read_bytes())
            with patch.object(backend,'_invoke',side_effect=AssertionError('backend')):
                r=backend.recover(self.home,self.wallet,self.pool,clock=self.clock)
                self.assertTrue(r['acknowledgmentRecorded']);self.assertFalse(r['privateKeyAccessedThisRun'])
            before=self.source_bytes();self.capture();self.verify();self.assertEqual(before,self.source_bytes())
            manifest=json.loads((self.snapshot/recovery.MANIFEST).read_text())
            self.assertEqual(manifest['projection']['exitTransport']['state'],'exit-finalized-evidence')
            self.assertEqual(manifest['projection']['exitAccounting']['recordSha256'],settled['recordSha256'])
            self.assertTrue(manifest['projection']['exitBackendAttemptPresent']);self.assertTrue(manifest['projection']['exitBackendAcknowledgmentPresent'])
            self.assertEqual(manifest['projection']['exitClosure']['recordSha256'],closure['recordSha256'])
            # Rehashed false closure arithmetic cannot pass isolated semantic replay.
            original_db=(self.snapshot/recovery.SIBLING/'entry.admission.sqlite').read_bytes()
            original_manifest=(self.snapshot/recovery.MANIFEST).read_bytes()
            def corrupt_closure(db):
                v=json.loads(db.execute('SELECT value FROM admission_exit_closure').fetchone()[0])
                v['settlement']['unusedFeeReleasedLamports']='999999'
                db.execute('UPDATE admission_exit_closure SET value=?,hash=?',(accounting.encoded(v),accounting.digest(v)))
            self.edit_db(corrupt_closure,self.snapshot/recovery.SIBLING/'entry.admission.sqlite')
            manifest['inventories']=recovery.inventories(self.snapshot/recovery.SOURCE,self.snapshot/recovery.SIBLING)
            (self.snapshot/recovery.MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'closure-source-conflict'):self.verify()
            (self.snapshot/recovery.SIBLING/'entry.admission.sqlite').write_bytes(original_db)
            (self.snapshot/recovery.MANIFEST).write_bytes(original_manifest)
            manifest=json.loads(original_manifest)
            # A modified accounting row fails even after rehashing every wrapper.
            def corrupt(db):
                v=json.loads(db.execute('SELECT value FROM admission_exit_accounting').fetchone()[0])
                v['accounting']['sourceProceedsHeldAtomic']='0'
                db.execute('UPDATE admission_exit_accounting SET value=?,hash=?',(accounting.encoded(v),accounting.digest(v)))
            self.edit_db(corrupt,self.snapshot/recovery.SIBLING/'entry.admission.sqlite')
            manifest['inventories']=recovery.inventories(self.snapshot/recovery.SOURCE,self.snapshot/recovery.SIBLING)
            (self.snapshot/recovery.MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'exit-accounting-source-conflict'):self.verify()
