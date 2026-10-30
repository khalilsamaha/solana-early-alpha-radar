"""Raw-evidence admission, atomic commitment and before-sign crash behavior."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import pre_sign_admission as m
from pre_sign_checks import fixture, run, NOW, edit

HERE=Path(__file__).resolve().parent


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.admission.sqlite'
        self.e,self.p=fixture();self.now=NOW+200
        self.pin=patch.object(m,'BASELINE',self.e['costInputs']['baseline']);self.pin.start()
        self.b=m.Admission(self.path,self.p,lambda:self.now)
    def tearDown(self):self.b.close();self.pin.stop();self.tmp.cleanup()
    def reopen(self):self.b.close();self.b=m.Admission(self.path,clock=lambda:self.now)
    def empty(self):self.assertEqual(self.b.status()['eventCount'],0)

    def test_self_check_no_network_or_signer(self):
        with patch('socket.socket',side_effect=AssertionError('network')), patch('core.signer',side_effect=AssertionError('signer')):
            r=run()
        self.assertEqual(r['casesPassed'],15);self.assertTrue(r['temporaryLedgersRemoved'])
        for k in ('executionApproved','signingApproved','liveSenderIntegrated','roundTripFundingEstablished'):self.assertFalse(r[k])

    def test_exact_raw_input_and_all_exit_caps_reserved(self):
        for n in (1,2,3):
            p=deepcopy(self.p);p.update(maximumExitAttempts=n,maximumTotalFeeLamports='40000')
            path=Path(self.tmp.name)/f'cap{n}.admission.sqlite';b=m.Admission(path,p,lambda:self.now)
            try:
                s=b.reserve(self.e);r=s['reservation']
                self.assertEqual(r['reservedFeeLamports'],str(6000+n*10000));self.assertEqual(r['reservedPrincipalAtomic'],'100')
                self.assertEqual(r['messageSha256'],self.e['costInputs']['capture']['messageSha256'])
                self.assertEqual(r['validUntilExclusiveMs'],NOW+8401)
            finally:b.close()

    def test_no_summary_baseline_override_or_price_edit(self):
        mutations=[lambda e:e.update(costInputs={'state':'consistent'}),
            lambda e:e['costInputs']['baseline'].update(id='arbitrary'),
            lambda e:e['costInputs']['price']['quote'].update(outAmount='999'),
            lambda e:e['costInputs'].update(simulation_item={'state':'consistent'}),
            lambda e:e['costInputs']['packet']['feeAssertion'].update(lamports='1')]
        for mutate in mutations:
            e=deepcopy(self.e);mutate(e)
            with self.assertRaises((ValueError,KeyError)):self.b.reserve(e)
            self.empty()

    def test_message_scope_account_and_pool_mutations(self):
        mutations=[lambda e:e['scope'].update(amountIn='1'),
            lambda e:e['entryScope']['accounts'].update(wallet=e['entryScope']['accounts']['pool']),
            lambda e:edit(e['costInputs']['capture'],4,64,(10001).to_bytes(8,'little')),
            lambda e:edit(e['costInputs']['capture'],-1,120,b'\x01'),
            lambda e:e['costInputs']['reservations'].update(nativeHeldLamports=None)]
        for mutate in mutations:
            e=deepcopy(self.e);mutate(e)
            with self.assertRaises(ValueError):self.b.reserve(e)
            self.empty()

    def test_full_budget_shortfall_rolls_back(self):
        e=deepcopy(self.e);e['costInputs']['reservations']['nativeHeldLamports']='80000'
        with self.assertRaisesRegex(ValueError,'admission-native-budget'):self.b.reserve(e)
        self.empty()
        p=deepcopy(self.p);p['maximumTotalFeeLamports']='25999'
        b=m.Admission(Path(self.tmp.name)/'short.admission.sqlite',p,lambda:self.now)
        try:
            with self.assertRaisesRegex(ValueError,'admission-total-budget'):b.reserve(self.e)
            self.assertEqual(b.status()['eventCount'],0)
        finally:b.close()

    def test_policy_schema_and_no_silent_migration(self):
        for bad in (None,False,0,4,'2',2.0):
            p=deepcopy(self.p);p['maximumExitAttempts']=bad
            with self.assertRaises(ValueError):m.validate_policy(p)
        p=deepcopy(self.p);p['maximumExitAttempts']=1
        with self.assertRaisesRegex(ValueError,'admission-immutable-policy'):m.Admission(self.path,p)
        for field in ('maximumExitFeeLamports','maximumTotalFeeLamports'):
            p=deepcopy(self.p);p[field]='40001'
            with self.assertRaises(ValueError):m.validate_policy(p)

    def test_duplicate_is_observation_not_new_signing_permission(self):
        s=self.b.reserve(self.e);self.now+=20000
        self.assertEqual(self.b.reserve(self.e),s)
        with self.assertRaises(ValueError):self.b.mark_signing_boundary(self.e)
        self.assertEqual(self.b.status(),s);self.reopen();self.assertEqual(self.b.status(),s)

    def test_evidence_changed_before_boundary_keeps_old_hold(self):
        s=self.b.reserve(self.e);e=deepcopy(self.e)
        e['costInputs']['reservations']['ledgerHeadSha256']='c'*64
        with self.assertRaisesRegex(ValueError,'admission-evidence-changed'):self.b.mark_signing_boundary(e)
        self.assertEqual(self.b.status(),s)
        with self.assertRaisesRegex(ValueError,'admission-already-reserved'):self.b.reserve(e)

    def test_only_one_boundary_unknown_persists_and_does_not_release(self):
        self.b.reserve(self.e);s=self.b.mark_signing_boundary(self.e)
        self.assertEqual(s['state'],'signing-unknown');self.reopen();self.assertEqual(self.b.status(),s)
        with self.assertRaisesRegex(ValueError,'admission-signing-blocked'):self.b.mark_signing_boundary(self.e)
        self.now+=20000;self.assertEqual(self.b.status(),s)
        self.assertEqual(self.b.reserve(self.e),s)

    def test_real_process_death_after_commit(self):
        self.b.reserve(self.e)
        code="""import os,sys
from pathlib import Path
from unittest.mock import patch
import pre_sign_admission as m
from pre_sign_checks import fixture,NOW
e,p=fixture()
with patch.object(m,'BASELINE',e['costInputs']['baseline']):
 b=m.Admission(Path(sys.argv[1]),clock=lambda:NOW+200)
 b.mark_signing_boundary(e)
 os._exit(73)
"""
        r=subprocess.run([sys.executable,'-c',code,str(self.path)],cwd=HERE)
        self.assertEqual(r.returncode,73);self.reopen()
        self.assertEqual(self.b.status()['state'],'signing-unknown')
        self.assertEqual(self.b.status()['reservation']['reservedFeeLamports'],'26000')

    def test_clock_and_deadline_rechecked_after_raw_work(self):
        for end in (NOW+100,NOW+8401):
            clock=iter([NOW+200,end])
            with patch.object(self.b.j,'clock',lambda:next(clock)):
                with self.assertRaises(ValueError):self.b.reserve(self.e)
            self.empty()
        self.b.reserve(self.e);before=self.b.status();clock=iter([NOW+200,NOW+8401])
        with patch.object(self.b.j,'clock',lambda:next(clock)):
            with self.assertRaisesRegex(ValueError,'admission-deadline-elapsed'):self.b.mark_signing_boundary(self.e)
        self.assertEqual(self.b.status(),before)
        self.now=NOW+100
        with self.assertRaisesRegex(ValueError,'admission-clock-regressed'):self.b.status()

    def test_event_failure_rolls_back_boundary(self):
        self.b.reserve(self.e);s=self.b.status()
        with patch.object(m,'MAX_EVENTS',1):
            with self.assertRaisesRegex(ValueError,'admission-event-cap'):self.b.mark_signing_boundary(self.e)
        self.assertEqual(self.b.status(),s)

    def test_two_connections_share_capacity_and_boundary(self):
        other=m.Admission(self.path,clock=lambda:self.now)
        try:
            s=self.b.reserve(self.e);self.assertEqual(other.reserve(self.e),s)
            other.mark_signing_boundary(self.e)
            with self.assertRaisesRegex(ValueError,'admission-signing-blocked'):self.b.mark_signing_boundary(self.e)
            self.assertEqual(other.status(),self.b.status())
        finally:other.close()

    def test_stop_before_or_after_boundary_retains_commitments(self):
        self.b.reserve(self.e);self.b.mark_signing_boundary(self.e);s=self.b.stop()
        self.assertEqual(s['reservation']['reservedFeeLamports'],'26000')
        self.assertIsNotNone(s['reservation']['signingBoundaryAtMs'])
        self.reopen();self.assertEqual(s,self.b.status())
        with self.assertRaises(ValueError):self.b.mark_signing_boundary(self.e)
        b=m.Admission(Path(self.tmp.name)/'stopped.admission.sqlite',self.p,lambda:self.now)
        try:
            b.stop()
            with self.assertRaises(ValueError):b.reserve(self.e)
            self.assertEqual(b.status()['reservation']['reservedFeeLamports'],'0')
        finally:b.close()

    def test_replay_detects_corruption_and_rejects_other_ledger(self):
        self.b.reserve(self.e);self.b.db.execute("UPDATE admission_events SET hash=?",('0'*64,))
        with self.assertRaisesRegex(ValueError,'admission-event-integrity'):self.b.status()
        with self.assertRaisesRegex(ValueError,'admission-event-integrity'):m.Admission(self.path)
        with self.assertRaises(ValueError):m.Admission(Path(self.tmp.name)/'old.positions.sqlite',self.p)

    def test_inputs_unchanged_and_raw_size_bounded(self):
        original=deepcopy(self.e);self.b.reserve(self.e);self.assertEqual(self.e,original)
        with patch.object(m,'MAX_EVIDENCE_BYTES',1):
            with self.assertRaisesRegex(ValueError,'admission-evidence-cap'):m.review(self.e,self.p,self.now)

    def test_cli_private_exclusive_and_no_live_modes(self):
        cli=HERE/'pre_sign_cli.py';out=Path(self.tmp.name)/'check.gz'
        cmd=[sys.executable,'-E','-s',str(cli),'--output',str(out)]
        r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
        before=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(before))['casesPassed'],15)
        self.assertEqual(out.stat().st_mode&0o777,0o600)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(before,out.read_bytes())
        for flag in ('--directory','--execute','--allow-devnet-submit','--wallet','--evidence'):
            target=Path(self.tmp.name)/'absent.gz'
            self.assertNotEqual(subprocess.run([sys.executable,str(cli),'--output',str(target),flag],capture_output=True).returncode,0)
            self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
