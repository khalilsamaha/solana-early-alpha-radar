"""Public signature checks and full-source equivalence; no live network."""
import base64
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import subprocess
import time
import unittest
from unittest.mock import patch

import admission_timing as m
import signature_replay_checks as checks
import test_reservation_view as f


class SignatureReplayTests(unittest.TestCase):
    def test_public_adversarial_contract(self):
        self.assertEqual(len(checks.run()),11)

    def test_verifier_timeout_and_invalid_output_never_memoized(self):
        encoded=checks.fixture()
        for fault in (subprocess.TimeoutExpired('node',5),OSError('unavailable')):
            with m.wire.signature_verification_scope() as stats,patch.object(m.wire.subprocess,'run',side_effect=fault) as calls:
                for _ in range(2):
                    with self.assertRaises(type(fault)):m.wire.verify_wire(encoded)
                self.assertEqual(calls.call_count,2);self.assertEqual(stats()['memoEntries'],0)
        with m.wire.signature_verification_scope() as stats,patch.object(m.wire.subprocess,'run') as calls:
            calls.return_value.returncode=0;calls.return_value.stdout='unexpected'
            for _ in range(2):
                with self.assertRaises(ValueError):m.wire.verify_wire(encoded)
            self.assertEqual(stats()['memoEntries'],0);self.assertEqual(calls.call_count,2)

    def test_other_thread_does_not_inherit_scope(self):
        from concurrent.futures import ThreadPoolExecutor
        encoded=checks.fixture();original=m.wire.subprocess.run
        with patch.object(m.wire.subprocess,'run',wraps=original) as calls,m.wire.signature_verification_scope() as stats:
            m.wire.verify_wire(encoded)
            with ThreadPoolExecutor(max_workers=1) as pool:pool.submit(m.wire.verify_wire,encoded).result()
            self.assertEqual(calls.call_count,2);self.assertEqual(stats()['verificationCalls'],1)


class SourceReplayTests(unittest.TestCase):
    setUpClass=classmethod(f.ReservationViewCase.setUpClass.__func__)
    tearDownClass=classmethod(f.ReservationViewCase.tearDownClass.__func__)
    setUp=f.ReservationViewCase.setUp
    tearDown=f.ReservationViewCase.tearDown
    files=f.ReservationViewCase.files

    def pipeline(self,*,memo=True,hook=None):
        from test_cycle_execution import BASE,s,binding
        from preflight_checks import edit
        from test_unsigned_simulation import SimulationOpener
        from swap_rehearsal import scope_for
        second=json.loads((self.home/binding.CYCLE/s.CHILD/'presend-preflight.json').read_text())
        edit(second,1,12,(2500).to_bytes(8,'little'))
        first=copy.deepcopy(second);first.update(packet=None,selection='explicit-pool',messageSha256=None)
        del first['accountKeys'][8:11];del first['evidence']['accounts']['result']['value'][8:11]
        second['evidence']['fee']['result']['value']=5000
        baseline=dict(copy.deepcopy(BASE),network='devnet',kind='observed-devnet-deployment',observedAtMs=0)
        opener=SimulationOpener(first,second,scope_for(second['packet']['policy']))
        stamp=self._profile_stamp=getattr(self,'_profile_stamp',m.view.now());read=m.view.read_locked;reads=[]
        def source(*args,**kwargs):
            result=read(*args,**kwargs);reads.append(result)
            if hook:hook(len(reads))
            return result
        @contextmanager
        def disabled():yield lambda:{'version':'disabled-for-comparison'}
        scope=m.wire.signature_verification_scope if memo else disabled
        real=m.wire.subprocess.run
        with patch.object(m.wire,'signature_verification_scope',scope),\
             patch.object(m.wire.subprocess,'run',wraps=real) as verifier,\
             patch('simulation_baseline.BASELINE',baseline),patch.object(m.admission,'BASELINE',baseline),\
             patch.object(m.view,'read_locked',source),\
             patch('socket.socket',side_effect=AssertionError('real network')),\
             patch('core.signer',side_effect=AssertionError('sign')),\
             patch.object(m.admission,'Admission',side_effect=AssertionError('write')):
            start=time.perf_counter()
            r=m.observe(self.home,self.wallet,self.pool,opener=opener,clock=lambda:stamp,
                maximum_exit_attempts=2,maximum_exit_fee_lamports='10000',maximum_total_fee_lamports='30000')
            return r,verifier.call_count,len(reads),time.perf_counter()-start

    def test_full_source_equivalence_and_reduced_processes(self):
        before=self.files();a,ac,ar,at=self.pipeline(memo=False);b,bc,br,bt=self.pipeline()
        self.assertEqual(a['state'],'entry-admission-timing-consistent',a)
        self.assertEqual(b['state'],a['state'],b)
        for key in ('networkRequests','requestMethods','assessment','sourceIdentity','rawAdmissionValidationPassed',
                    'signaturesCreated','transactionsSent','sourceStateChanged','admissionLedgerCreated'):
            self.assertEqual(a[key],b[key],key)
        self.assertEqual(ar,br);self.assertEqual(br,5)
        self.assertLess(bc,ac);self.assertGreater(b['signatureVerification']['memoHits'],0)
        self.assertEqual(before,self.files());self.assertIsNone(m.wire._SIGNATURE_SCOPE.get())
        print(json.dumps(dict(kind='synthetic-source-profile',uncachedProcesses=ac,memoProcesses=bc,
            sourceReads=br,uncachedSeconds=at,memoSeconds=bt,signatureVerification=b['signatureVerification'])),flush=True)

    def test_changed_receipt_after_warm_verification_still_refused(self):
        from test_cycle_execution import s,binding
        path=self.home/binding.CYCLE/s.REVERSE_CHILD/'receipt-evidence.json'
        def tamper(n):
            if n==3:path.write_text('{}')
        r,_,reads,_=self.pipeline(hook=tamper)
        self.assertEqual(r['state'],'unavailable',r);self.assertIsNone(r['assessment'])
        self.assertGreaterEqual(reads,3);self.assertEqual(path.read_text(),'{}')
        self.assertIsNone(m.wire._SIGNATURE_SCOPE.get())

    def test_stop_after_warm_verification_still_refused(self):
        def stop(n):
            if n==4:(self.home/'STOP').touch(mode=0o600)
        r,_,reads,_=self.pipeline(hook=stop)
        self.assertEqual(r['state'],'unavailable',r);self.assertFalse(r['rawAdmissionValidationPassed'])
        self.assertEqual(reads,4);self.assertTrue((self.home/'STOP').exists())
        self.assertIsNone(m.wire._SIGNATURE_SCOPE.get())


if __name__=='__main__':unittest.main()
