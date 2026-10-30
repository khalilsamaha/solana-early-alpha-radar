"""Locked raw-evidence integration and exact acknowledgment recovery boundaries."""
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

import locked_admission as m
import pre_sign_admission as admission
from locked_admission_checks import fixture, home_fixture, run, NOW
import journal

HERE=Path(__file__).resolve().parent


class LockedAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.e,self.p,self.signed=fixture();self.now=NOW+200
        self.wallet=self.p['scope']['accounts']['wallet'];self.pool=self.p['scope']['accounts']['pool']
        self.home=home_fixture(self.root/'source',self.wallet)
        self.path=self.root/'test.admission.sqlite'
        self.pin=patch.object(admission,'BASELINE',self.e['costInputs']['baseline']);self.pin.start()
        self.b=admission.Admission(self.path,self.p,lambda:self.now)
    def tearDown(self):self.b.close();self.pin.stop();self.tmp.cleanup()
    def reserve_boundary(self):self.b.reserve(self.e);self.b.mark_signing_boundary(self.e)
    def prepare(self):return m.prepare(self.home,self.wallet,self.pool,self.b,self.e,clock=lambda:self.now)
    def reader(self,*args):
        self.assertTrue(journal._READ_ONLY.get())
        with self.assertRaises(BlockingIOError):
            with m.view.cycles.c.source_lock(self.home,self.wallet):pass
        v=deepcopy(self.e['costInputs']['reservations'])
        v.update(readStartedAtMs=self.now,observedAtMs=self.now);return v

    def test_portable_checks_have_no_network_or_signer(self):
        with patch('socket.socket',side_effect=AssertionError('network')),patch('core.signer',side_effect=AssertionError('signer')):
            r=run()
        self.assertEqual(r['casesPassed'],17)
        for k in ('networkRequests','signaturesCreated','transactionsSent'):self.assertEqual(r[k],0)
        self.assertFalse(r['sourceReservationProvenanceVerified']);self.assertFalse(r['signerInvocationAllowed'])

    def test_actual_lock_covers_both_reads_and_both_durable_writes(self):
        reserve=self.b.reserve;boundary=self.b.mark_signing_boundary
        def locked(fn):
            def wrap(e):
                self.reader();return fn(e)
            return wrap
        before={p.name:p.read_bytes() for p in self.home.iterdir()}
        with patch.object(m.view,'read_locked',side_effect=self.reader) as reads,patch.object(self.b,'reserve',side_effect=locked(reserve)),patch.object(self.b,'mark_signing_boundary',side_effect=locked(boundary)):
            r=self.prepare()
        self.assertEqual(reads.call_count,2);self.assertEqual(r['admission']['state'],'signing-unknown')
        self.assertTrue(r['sourceConnectionsReadOnly']);self.assertFalse(r['signerInvocationAllowed'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.home.iterdir()})

    def test_second_read_failure_preserves_reservation_without_boundary(self):
        snapshot=deepcopy(self.e['costInputs']['reservations'])
        with patch.object(m.view,'read_locked',side_effect=[snapshot,ValueError('source-unavailable')]):
            with self.assertRaisesRegex(ValueError,'source-unavailable'):self.prepare()
        s=self.b.status();self.assertEqual(s['state'],'reserved');self.assertIsNone(s['reservation']['signingBoundaryAtMs'])

    def test_stop_during_final_validation_withholds_handoff_and_holds_budget(self):
        real=admission.review;calls=[0]
        def stop(*args):
            value=real(*args);calls[0]+=1
            if calls[0]==2:(self.home/'STOP').touch(mode=0o600)
            return value
        with patch.object(m.view,'read_locked',side_effect=self.reader),patch.object(admission,'review',side_effect=stop):
            with self.assertRaisesRegex(ValueError,'stop-marker-present'):self.prepare()
        s=self.b.status();self.assertEqual(s['state'],'stopped')
        self.assertIsNotNone(s['reservation']['signingBoundaryAtMs'])
        self.assertEqual(s['reservation']['reservedFeeLamports'],'26000')

    def test_source_path_scope_missing_and_wrong_phase_block(self):
        self.home.joinpath('session.lock').unlink()
        with self.assertRaises(OSError):self.prepare()
        self.assertEqual(self.b.status()['state'],'empty')
        self.home.joinpath('session.lock').touch(mode=0o600)
        v=deepcopy(self.e['costInputs']['reservations']);v['phase']='open'
        with patch.object(m.view,'read_locked',return_value=v):
            with self.assertRaisesRegex(ValueError,'admission-source-scope'):self.prepare()
        with self.assertRaisesRegex(ValueError,'admission-policy-source'):
            m.prepare(self.home,self.pool,self.wallet,self.b,self.e)
        nested=admission.Admission(self.home/'nested.admission.sqlite',self.p,lambda:self.now)
        try:
            with self.assertRaisesRegex(ValueError,'admission-outside-source-required'):
                m.prepare(self.home,self.wallet,self.pool,nested,self.e)
        finally:nested.close()

    def test_real_missing_journals_never_accepted_as_zero(self):
        before={p.name:p.read_bytes() for p in self.home.iterdir()}
        with self.assertRaises((ValueError,OSError)):self.prepare()
        self.assertEqual(self.b.status()['state'],'empty')
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.home.iterdir()})

    def test_handoff_completion_can_follow_cost_evaluation_without_refresh(self):
        self.e['costInputs']['now_ms']=NOW+199
        s=self.b.reserve(self.e);self.assertEqual(s['reservation']['validUntilExclusiveMs'],NOW+8401)
        for bad in (False, NOW+201):
            e=deepcopy(self.e);e['costInputs']['now_ms']=bad
            with self.assertRaises(ValueError):admission.review(e,self.p,self.now)
        e=deepcopy(self.e);e['completedAtMs']=NOW+201
        with self.assertRaises(ValueError):admission.review(e,self.p,self.now)

    def test_valid_signed_ack_reopen_and_public_redaction(self):
        self.reserve_boundary();s=self.b.record_signed(self.signed['signedTransactionBase64'])
        self.assertEqual(s['state'],'signed-recorded');self.assertEqual(s['eventCount'],3)
        self.assertNotIn(self.signed['signedTransactionBase64'],json.dumps(s))
        self.assertIn(self.signed['signedTransactionBase64'],self.b.db.execute('SELECT value FROM admission_events ORDER BY seq DESC LIMIT 1').fetchone()[0])
        self.b.close();self.now+=20000;self.b=admission.Admission(self.path,clock=lambda:self.now)
        self.assertEqual(self.b.status(),s);self.assertEqual(self.b.record_signed(self.signed['signedTransactionBase64']),s)
        with self.assertRaises(ValueError):self.b.mark_signing_boundary(self.e)

    def test_transport_failure_retains_unknown_for_later_recording(self):
        self.reserve_boundary();before=self.b.status()
        with patch.object(admission,'verify_wire',side_effect=subprocess.TimeoutExpired('node',5)):
            with self.assertRaises(subprocess.TimeoutExpired):self.b.record_signed(self.signed['signedTransactionBase64'])
        self.assertEqual(self.b.status(),before)
        self.assertEqual(self.b.record_signed(self.signed['signedTransactionBase64'])['state'],'signed-recorded')

    def test_missing_verifier_keeps_unknown_and_duplicate_needs_no_verifier(self):
        self.reserve_boundary();before=self.b.status()
        with patch.object(admission,'verify_wire',side_effect=ValueError('node-runtime-unavailable')):
            with self.assertRaisesRegex(ValueError,'node-runtime-unavailable'):
                self.b.record_signed(self.signed['signedTransactionBase64'])
        self.assertEqual(self.b.status(),before)
        s=self.b.record_signed(self.signed['signedTransactionBase64'])
        with patch.object(admission,'verify_wire',side_effect=AssertionError('duplicate reverified')):
            self.assertEqual(self.b.record_signed(self.signed['signedTransactionBase64']),s)

    def test_signed_event_write_failure_does_not_erase_unknown(self):
        self.reserve_boundary();before=self.b.status()
        with patch.object(admission,'MAX_EVENTS',2):
            with self.assertRaisesRegex(ValueError,'admission-event-cap'):self.b.record_signed(self.signed['signedTransactionBase64'])
        self.assertEqual(self.b.status(),before)

    def test_malformed_wire_is_quarantined_without_releasing_hold(self):
        self.reserve_boundary();s=self.b.record_signed('AA==')
        self.assertEqual(s['state'],'quarantined');self.assertEqual(s['reservation']['reservedFeeLamports'],'26000')
        self.assertEqual(self.b.stop(),s)
        for bad in (None, 'a'*1645):
            with self.assertRaises(ValueError):self.b.record_signed(bad)
        self.assertEqual(self.b.status(),s)

    def test_signed_ack_after_stop_is_recorded_but_remains_stopped(self):
        self.reserve_boundary();self.b.stop();self.now+=20000
        s=self.b.record_signed(self.signed['signedTransactionBase64'])
        self.assertEqual(s['state'],'stopped');self.assertIn('signature',s['reservation'])
        self.assertFalse(s['signerInvocationAllowed']);self.assertFalse(s['executionApproved'])

    def test_process_death_after_signed_ack_commit_reopens_without_resigning(self):
        self.reserve_boundary()
        code="""import os,sys
from pathlib import Path
from locked_admission_checks import fixture,NOW
from pre_sign_admission import Admission
e,p,signed=fixture()
b=Admission(Path(sys.argv[1]),clock=lambda:NOW+200)
b.record_signed(signed['signedTransactionBase64'])
os._exit(73)
"""
        r=subprocess.run([sys.executable,'-E','-s','-c',code,str(self.path)],cwd=HERE)
        self.assertEqual(r.returncode,73);self.b.close();self.b=admission.Admission(self.path,clock=lambda:self.now)
        s=self.b.status();self.assertEqual(s['state'],'signed-recorded');self.assertEqual(s['eventCount'],3)
        self.assertEqual(self.b.record_signed(self.signed['signedTransactionBase64']),s)

    def test_cli_private_exclusive_no_live_input_or_execution(self):
        cli=HERE/'locked_admission_cli.py';out=self.root/'check.gz'
        cmd=[sys.executable,'-E','-s',str(cli),'--output',str(out)]
        r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
        before=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(before))['casesPassed'],17)
        self.assertEqual(out.stat().st_mode&0o777,0o600)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),before)
        for flag in ('--directory','--execute','--allow-devnet-submit','--wallet','--evidence','--signed-wire'):
            target=self.root/'absent.gz'
            self.assertNotEqual(subprocess.run([sys.executable,str(cli),'--output',str(target),flag],capture_output=True).returncode,0)
            self.assertFalse(target.exists())


# Replay the existing two-cycle fixtures through the actual reader and complete
# raw observer/admission validators. Only RPC responses and deployment pin are
# synthetic; lock, source-journal readers, prices, simulation effects and hashes
# are the real implementations.
import test_readiness as source_fixture
from test_cycle_execution import s, binding, BASE


class RealSourceAdmissionTests(unittest.TestCase):
    setUpClass=classmethod(source_fixture.ReadinessCase.setUpClass.__func__)
    tearDownClass=classmethod(source_fixture.ReadinessCase.tearDownClass.__func__)
    setUp=source_fixture.ReadinessCase.setUp
    tearDown=source_fixture.ReadinessCase.tearDown
    files=source_fixture.ReadinessCase.files

    def evidence(self):
        import fresh_quote
        from preflight_checks import edit
        from test_unsigned_simulation import SimulationOpener
        from swap_rehearsal import scope_for
        second=json.loads((self.home/binding.CYCLE/s.CHILD/'presend-preflight.json').read_text())
        edit(second,1,12,(2500).to_bytes(8,'little'))
        first=deepcopy(second);first.update(packet=None,selection='explicit-pool',messageSha256=None)
        del first['accountKeys'][8:11];del first['evidence']['accounts']['result']['value'][8:11]
        second['evidence']['fee']['result']['value']=5000
        baseline=dict(deepcopy(BASE),network='devnet',kind='observed-devnet-deployment',observedAtMs=0)
        stamp=m.view.now();raw=[]
        opener=SimulationOpener(first,second,scope_for(second['packet']['policy']))
        with patch('preflight.BASELINE',baseline),patch('preflight_capture.BASELINE',baseline):
            r=fresh_quote.observe(self.home,self.wallet,self.pool,opener=opener,clock=lambda:stamp,
                                  simulate=True,assess_costs=True,_evidence_sink=raw.append)
        self.assertEqual(r['state'],'controlled-cost-observation-consistent',r)
        self.assertEqual(len(raw),1)
        return raw[0],baseline,stamp

    def test_actual_source_and_private_observer_handoff_reach_durable_boundary(self):
        before=self.files();e,baseline,stamp=self.evidence()
        p=dict(format=admission.VERSION+'-policy',scope=deepcopy(e['scope']),maximumExitAttempts=2,
               maximumExitFeeLamports='10000',maximumTotalFeeLamports='40000')
        b=admission.Admission(Path(self.tmp.name)/'real.admission.sqlite',p,lambda:stamp)
        try:
            with patch.object(admission,'BASELINE',baseline),patch('core.signer',side_effect=AssertionError('signer')),patch('socket.socket',side_effect=AssertionError('network')):
                r=m.prepare(self.home,self.wallet,self.pool,b,e,clock=lambda:stamp)
            self.assertEqual(r['state'],'locked-admission-boundary-recorded');self.assertTrue(r['sourceReservationProvenanceVerified'])
            self.assertEqual(b.status()['state'],'signing-unknown');self.assertEqual(before,self.files())
        finally:b.close()

    def test_real_receipt_change_after_reserve_blocks_second_replay(self):
        e,baseline,stamp=self.evidence()
        p=dict(format=admission.VERSION+'-policy',scope=deepcopy(e['scope']),maximumExitAttempts=2,
               maximumExitFeeLamports='10000',maximumTotalFeeLamports='40000')
        b=admission.Admission(Path(self.tmp.name)/'changed.admission.sqlite',p,lambda:stamp)
        reserve=b.reserve
        def remove_receipt(raw):
            result=reserve(raw)
            (self.home/binding.CYCLE/s.REVERSE_CHILD/'receipt-evidence.json').unlink()
            return result
        try:
            with patch.object(admission,'BASELINE',baseline),patch.object(b,'reserve',side_effect=remove_receipt):
                with self.assertRaises((ValueError,OSError)):m.prepare(self.home,self.wallet,self.pool,b,e,clock=lambda:stamp)
            self.assertEqual(b.status()['state'],'reserved')
            self.assertIsNone(b.status()['reservation']['signingBoundaryAtMs'])
        finally:b.close()

    def test_real_source_receipt_loss_blocks_before_new_reservation(self):
        e,baseline,stamp=self.evidence()
        p=dict(format=admission.VERSION+'-policy',scope=deepcopy(e['scope']),maximumExitAttempts=2,
               maximumExitFeeLamports='10000',maximumTotalFeeLamports='40000')
        (self.home/binding.CYCLE/s.REVERSE_CHILD/'receipt-evidence.json').unlink();before=self.files()
        b=admission.Admission(Path(self.tmp.name)/'missing.admission.sqlite',p,lambda:stamp)
        try:
            with patch.object(admission,'BASELINE',baseline):
                with self.assertRaises((ValueError,OSError)):m.prepare(self.home,self.wallet,self.pool,b,e,clock=lambda:stamp)
            self.assertEqual(b.status()['state'],'empty');self.assertEqual(before,self.files())
        finally:b.close()


if __name__=='__main__':unittest.main()
