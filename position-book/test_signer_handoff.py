"""One-dispatch crash boundaries, private accounting outbox and receipt compatibility."""
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

import signer_handoff as m
import pre_sign_admission as admission
from locked_admission_checks import fixture, home_fixture, NOW
from signer_handoff_checks import run
from contract import TOKEN
from wire import decode_wire,b58
import book as position_book

HERE=Path(__file__).resolve().parent


def receipt(evidence,handoff):
    """Explicitly synthetic RPC receipt, never labelled or exported as chain data."""
    roles=evidence['scope']['accounts'];_,_,_,_,tx=decode_wire(handoff['signedTransactionBase64'])
    sim=evidence['costInputs']['simulation_item']['result']
    meta={k:deepcopy(sim['value'][k]) for k in ('fee','preBalances','postBalances','preTokenBalances','postTokenBalances')}
    keys=tx['transaction']['message']['accountKeys']
    def transfer(source,destination,authority,amount):
        return dict(programIdIndex=keys.index(TOKEN),accounts=[keys.index(roles[k]) for k in (source,destination,authority)],
                    data=b58(bytes([3])+int(amount).to_bytes(8,'little')))
    meta.update(err=None,innerInstructions=[dict(index=2,instructions=[
        transfer('source','inputVault','wallet',evidence['scope']['amountIn']),
        transfer('outputVault','destination','authority',evidence['costInputs']['price']['quote']['outAmount'])])])
    tx.update(meta=meta,slot=sim['context']['slot'])
    return dict(format='signed-token-evidence-1',signedTransactionBase64=handoff['signedTransactionBase64'],
        bundle=dict(format='intent-evidence-bundle-1',network='devnet',capturedAtMs=NOW+1000,
                    intent=deepcopy(handoff['intent']),rpcEvidence=dict(
                        signatureStatus=dict(state='received',result=dict(context=dict(slot=tx['slot']+1),value=[dict(slot=tx['slot'],err=None,confirmationStatus='finalized')])),
                        transaction=dict(state='received',result=tx))))


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.e,self.p,self.signed=fixture();self.now=NOW+200;self.calls=0
        self.wallet=self.p['scope']['accounts']['wallet'];self.pool=self.p['scope']['accounts']['pool']
        self.home=home_fixture(self.root/'source',self.wallet)
        self.snapshot=deepcopy(self.e['costInputs']['reservations']);self.snapshot.update(readStartedAtMs=self.now,observedAtMs=self.now)
        self.pin=patch.object(admission,'BASELINE',self.e['costInputs']['baseline']);self.pin.start()
        self.reader=patch.object(m.bridge.view,'read_locked',side_effect=lambda *a:deepcopy(self.snapshot));self.reader.start()
    def tearDown(self):self.reader.stop();self.pin.stop();self.tmp.cleanup()
    def adapter(self,req):self.calls+=1;return self.signed['signedTransactionBase64']
    def call(self,adapter=None):return m.dispatch(self.home,self.wallet,self.pool,self.e,self.p,signer_adapter=adapter or self.adapter,clock=lambda:self.now)
    def recover(self,**kw):return m.recover(self.home,self.wallet,self.pool,clock=lambda:self.now,**kw)
    def ledger(self):return admission.Admission(m.storage(self.home),clock=lambda:self.now)

    def test_portable_suite_without_network_or_keys(self):
        with patch('socket.socket',side_effect=AssertionError('network')),patch('core.signer',side_effect=AssertionError('private key')):
            r=run()
        self.assertEqual(r['casesPassed'],15);self.assertEqual(r['signaturesCreated'],0)
        self.assertFalse(r['receiptApplied']);self.assertFalse(r['allocationTransferred'])

    def test_invoke_only_after_committed_request_and_boundary(self):
        def adapter(req):
            self.assertEqual(req['format'],'entry-handoff-1-sign-request')
            with self.assertRaises(BlockingIOError):
                with m.bridge.view.cycles.c.source_lock(self.home,self.wallet):pass
            b=self.ledger()
            try:
                self.assertEqual(b.read()[0]['signingRequest'],req)
                self.assertEqual(b.status()['eventCount'],3)
                self.assertEqual(b.status()['state'],'signing-unknown')
            finally:b.close()
            return self.adapter(req)
        r=self.call(adapter);self.assertEqual(self.calls,1);self.assertEqual(r['admission']['eventCount'],5)
        self.assertTrue(r['accountingHandoffReady']);self.assertFalse(r['allocationTransferred'])
        again=self.call(lambda _:self.fail('retry'));self.assertEqual(again['signerAdapterCallsThisRun'],0)

    def test_no_adapter_before_source_and_funding_gates(self):
        self.snapshot['ledgerHeadSha256']='c'*64
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.calls,0);self.assertEqual(self.recover()['state'],'empty')

    def test_canonical_storage_rejects_symlink_and_permissions(self):
        canonical=self.home.parent/(self.home.name+'-entry-handoff-v1')
        other=self.root/'other';other.mkdir(mode=0o700);canonical.symlink_to(other)
        with self.assertRaises(ValueError):self.call()
        canonical.unlink();canonical.mkdir(mode=0o755)
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.calls,0)

    def test_changed_policy_cannot_get_a_second_dispatch_ledger(self):
        self.call();self.p['maximumTotalFeeLamports']='31000'
        with self.assertRaisesRegex(ValueError,'admission-immutable-policy'):self.call()
        self.assertEqual(self.calls,1);self.assertEqual(len(list(m.storage(self.home).parent.glob('*.sqlite'))),1)

    def test_boundary_write_failure_never_calls_adapter(self):
        with patch.object(admission,'MAX_EVENTS',2):
            with self.assertRaisesRegex(ValueError,'admission-event-cap'):self.call()
        self.assertEqual(self.calls,0);self.assertEqual(self.recover()['state'],'reserved')
        self.assertEqual(self.call()['state'],'signed-recorded');self.assertEqual(self.calls,1)

    def test_request_size_failure_rolls_back_without_poisoning_ledger(self):
        import handoff_contract
        original=handoff_contract.request
        def oversized(*a):return dict(original(*a),padding='x'*9000)
        with patch.object(handoff_contract,'request',side_effect=oversized):
            with self.assertRaisesRegex(ValueError,'admission-state-size'):self.call()
        r=self.recover();self.assertEqual(r['state'],'reserved');self.assertEqual(r['admission']['eventCount'],1)
        self.assertEqual(self.calls,0)

    def test_callback_crash_never_allows_another_invocation(self):
        def crash(req):self.calls+=1;raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.call(crash)
        self.assertEqual(self.recover()['state'],'signing-unknown')
        self.call(lambda _:self.fail('resigned'));self.assertEqual(self.calls,1)
        self.now+=20000;r=self.recover(signed_response=self.signed['signedTransactionBase64'])
        self.assertTrue(r['accountingHandoffReady']);self.assertEqual(r['signerAdapterCallsThisRun'],0)

    def test_response_and_outbox_write_failure_keep_durable_states(self):
        for limit,expected in ((3,'signing-unknown'),(4,'signed-recorded')):
            with self.subTest(limit=limit):
                self.home=home_fixture(self.root/f'limit{limit}',self.wallet)
                with patch.object(admission,'MAX_EVENTS',limit):
                    with self.assertRaisesRegex(ValueError,'admission-event-cap'):self.call()
                b=self.ledger()
                try:self.assertEqual(b.status()['state'],expected)
                finally:b.close()
                r=self.recover(signed_response=self.signed['signedTransactionBase64'])
                self.assertTrue(r['accountingHandoffReady'])
                self.assertEqual(r['admission']['reservation']['reservedFeeLamports'],'26000')

    def test_stop_at_entry_and_during_adapter_never_releases(self):
        (self.home/'STOP').touch(mode=0o600)
        r=self.call();self.assertEqual(r['state'],'stopped');self.assertEqual(self.calls,0)
        (self.home/'STOP').unlink();self.assertEqual(self.call()['state'],'stopped');self.assertEqual(self.calls,0)
        self.home=home_fixture(self.root/'later-stop',self.wallet)
        def stop(req):(self.home/'STOP').touch(mode=0o600);return self.adapter(req)
        r=self.call(stop);self.assertEqual(r['state'],'stopped');self.assertTrue(r['accountingHandoffReady'])
        self.assertEqual(r['admission']['reservation']['reservedPrincipalAtomic'],'100')

    def test_expiry_between_boundary_and_call_prevents_adapter(self):
        original=admission.Admission.mark_signing_boundary
        def expire(b,e):
            result=original(b,e);self.now=NOW+8401;return result
        with patch.object(admission.Admission,'mark_signing_boundary',expire):
            with self.assertRaisesRegex(ValueError,'handoff-deadline'):self.call()
        self.assertEqual(self.calls,0);self.assertEqual(self.recover()['state'],'signing-unknown')

    def test_expiry_during_call_does_not_discard_signed_evidence(self):
        def expire(req):self.now+=20000;return self.adapter(req)
        r=self.call(expire);self.assertTrue(r['accountingHandoffReady']);self.assertFalse(r['executionApproved'])
        self.assertEqual(r['admission']['reservation']['validUntilExclusiveMs'],NOW+8401)

    def test_adapter_mutation_is_detached_from_durable_request(self):
        def mutate(req):req['receiptIntentTemplate']['inputAtomic']='999';return self.adapter(req)
        self.call(mutate);b=self.ledger()
        try:self.assertEqual(b.private_accounting_handoff()['intent']['inputAtomic'],'100')
        finally:b.close()

    def test_conflicting_wire_quarantines_and_blocks_private_handoff(self):
        r=self.call(lambda _:self.signed['otherSignedTransactionBase64'])
        self.assertEqual(r['state'],'quarantined');self.assertFalse(r['accountingHandoffReady'])
        b=self.ledger()
        try:
            with self.assertRaisesRegex(ValueError,'handoff-not-ready'):b.private_accounting_handoff()
        finally:b.close()
        self.assertEqual(self.recover(signed_response=self.signed['signedTransactionBase64'])['state'],'quarantined')

    def test_legacy_boundary_has_no_synthetic_handoff_on_recovery(self):
        path=m.storage(self.home,create=True);b=admission.Admission(path,self.p,lambda:self.now)
        try:b.reserve(self.e);b.mark_signing_boundary(self.e);b.record_signed(self.signed['signedTransactionBase64'])
        finally:b.close()
        with self.assertRaisesRegex(ValueError,'handoff-signed-request-required'):self.recover()
        self.assertEqual(self.call()['signerAdapterCallsThisRun'],0)

    def test_private_handoff_consumed_by_existing_accounting_contract(self):
        self.call();b=self.ledger()
        try:
            handoff=b.private_accounting_handoff();before=b.status()
            pp=dict(format='position-book-policy-2',network='devnet',wallet=self.wallet,
                quoteAccount=handoff['intent']['source']['account'],quoteMint=handoff['intent']['source']['mint'],
                quoteDecimals=handoff['intent']['source']['decimals'],initialQuoteAtomic='1000',initialNativeLamports='100000',
                maximumPrincipalAtomic='100',maximumGrossLossAtomic='100',maximumTotalFeeLamports='30000',
                maximumLegFeeLamports='10000',maximumExitAttempts=2,maximumIntentAgeMs=15000)
            # Disposable consumer compatibility check, not a production transfer.
            other=position_book.Book(self.root/'consumer.positions.sqlite',pp,clock=lambda:self.now)
            try:
                reg=dict(format='signed-intent-registration-1',logicalIntentId=handoff['id'],intent=handoff['intent'],
                         signedTransactionBase64=handoff['signedTransactionBase64'])
                other.reserve('sample','entry',reg);other.boundary(handoff['id'])
                result=other.observe(handoff['id'],receipt(self.e,handoff))
                self.assertFalse(result['quarantined'],result)
                self.assertEqual(other.position('sample')['state'],'open')
                self.assertEqual(other.position('sample')['quantity'],self.e['costInputs']['price']['quote']['outAmount'])
                self.assertEqual(b.status(),before)
            finally:other.close()
        finally:b.close()

    def test_recovery_does_not_replay_source_or_invoke_signer(self):
        self.call();self.reader.stop()
        with patch.object(m.bridge.view,'read_locked',side_effect=AssertionError('source replay')),patch('core.signer',side_effect=AssertionError('key')):
            self.assertTrue(self.recover()['accountingHandoffReady'])
        self.reader.start()

    def test_real_process_death_after_callback_and_after_persistence(self):
        for persisted in (False,True):
            self.home=home_fixture(self.root/f'crash{persisted}',self.wallet)
            code="""import os,sys
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
from locked_admission_checks import fixture,NOW
import signer_handoff as m
import pre_sign_admission as a
e,p,s=fixture();r=deepcopy(e['costInputs']['reservations']);r.update(readStartedAtMs=NOW+200,observedAtMs=NOW+200)
def callback(req):
 if sys.argv[2]=='False':os._exit(73)
 return s['signedTransactionBase64']
with patch.object(a,'BASELINE',e['costInputs']['baseline']),patch.object(m.bridge.view,'read_locked',return_value=r):
 m.dispatch(Path(sys.argv[1]),p['scope']['accounts']['wallet'],p['scope']['accounts']['pool'],e,p,signer_adapter=callback,clock=lambda:NOW+200)
os._exit(73)
"""
            r=subprocess.run([sys.executable,'-E','-s','-c',code,str(self.home),str(persisted)],cwd=HERE)
            self.assertEqual(r.returncode,73)
            state=self.recover();self.assertEqual(state['state'],'signed-recorded' if persisted else 'signing-unknown')
            self.call(lambda _:self.fail('resigned after crash'))

    def test_cli_only_synthetic_private_exclusive_report(self):
        cli=HERE/'signer_handoff_cli.py';out=self.root/'report.gz'
        cmd=[sys.executable,'-E','-s',str(cli),'--output',str(out)]
        r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
        raw=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(raw))['casesPassed'],15)
        self.assertEqual(out.stat().st_mode&0o777,0o600)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
        for flag in ('--directory','--wallet','--sign','--execute','--allow-devnet-submit','--recover'):
            p=self.root/'absent.gz'
            self.assertNotEqual(subprocess.run([sys.executable,str(cli),'--output',str(p),flag],capture_output=True).returncode,0)
            self.assertFalse(p.exists())


import test_readiness as source_fixture
import test_locked_admission as locked_fixture


class RealSourceDispatchTests(unittest.TestCase):
    setUpClass=classmethod(source_fixture.ReadinessCase.setUpClass.__func__)
    tearDownClass=classmethod(source_fixture.ReadinessCase.tearDownClass.__func__)
    setUp=source_fixture.ReadinessCase.setUp
    tearDown=source_fixture.ReadinessCase.tearDown
    files=source_fixture.ReadinessCase.files
    evidence=locked_fixture.RealSourceAdmissionTests.evidence

    def test_actual_source_observer_to_one_dispatch_with_no_private_key(self):
        before=self.files();e,baseline,stamp=self.evidence();calls=[]
        p=dict(format=admission.VERSION+'-policy',scope=deepcopy(e['scope']),maximumExitAttempts=2,
               maximumExitFeeLamports='10000',maximumTotalFeeLamports='40000')
        def adapter(request):
            calls.append(request)
            self.assertEqual(request['receiptIntentTemplate']['wallet'],self.wallet)
            self.assertEqual(request['packet']['policy']['accounts']['pool'],self.pool)
            with self.assertRaises(BlockingIOError):
                with m.bridge.view.cycles.c.source_lock(self.home,self.wallet):pass
            raise TimeoutError('fixture acknowledgment absent')
        with patch.object(admission,'BASELINE',baseline),patch('core.signer',side_effect=AssertionError('key')),patch('socket.socket',side_effect=AssertionError('network')):
            with self.assertRaises(TimeoutError):
                m.dispatch(self.home,self.wallet,self.pool,e,p,signer_adapter=adapter,clock=lambda:stamp)
            r=m.dispatch(self.home,self.wallet,self.pool,e,p,signer_adapter=adapter,clock=lambda:stamp)
        self.assertEqual(len(calls),1);self.assertEqual(r['state'],'signing-unknown')
        self.assertEqual(before,self.files());self.assertFalse(r['accountingHandoffReady'])


if __name__=='__main__':unittest.main()
