import copy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import guarded_session as guarded
import check_combined as combined
from test_combined import fixture_backend
shared=guarded.shared;c=guarded.c;v=shared.supervisor;pc=guarded.pc


class GuardedTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.run=self.root/'first';self.run.mkdir(mode=0o700)
        self.registry=self.run/'registry';self.registry.mkdir(mode=0o700)
        self.backend,self.model,*_=fixture_backend(self.registry)
        self.service=self.root/'service';self.service_sha=guarded.service.provision(self.service,self.backend.target)
        self.plan,self.sha,self.paths=combined.prepare(self.run,self.registry,self.backend,True,service_contract_sha256=self.service_sha)
        self.now=100.0;self.phases={'disable_restart':30,'stop':30,'shared':60,'start_original':30,'restore_restart':30}
        self.guard=self.make()

    def make(self,**kw):
        return guarded.GuardedSharedPrepared(self.backend,self.plan,self.sha,self.paths,service_directory=self.service,
            service_sha256=self.service_sha,phase_seconds=self.phases,mode=kw.pop('mode','session-scanner-normal'),
            clock=kw.pop('clock',lambda:self.now),**kw)

    def stopped(self,ctrl):ctrl.step('disable_restart');ctrl.step('stop')

    def test_actual_finite_worker_and_scanner_under_guard_then_explicit_completion(self):
        self.guard=self.make(clock=time.monotonic)
        with self.guard.open() as ctrl:
            self.stopped(ctrl);result=self.guard.run_shared()
            self.assertEqual(result['outcome'],v.SUCCESS)
            ctrl.step('start_original');ctrl.step('restore_restart');receipt=self.guard.complete()
        state=guarded.service.inspect(self.service,self.service_sha)
        self.assertEqual(state['status'],'completion-recorded-attempt-consumed')
        self.assertEqual(len(receipt['timing']['events']),10)
        self.assertEqual(self.model.calls,['disable_restart','stop','start_original','restore_restart'])
        self.assertTrue(pc.inspect(self.registry)['original_restored'])
        self.assertFalse(state['global_owner_exclusivity_verified'])

    def test_omitted_completion_does_not_invent_it_on_exit(self):
        with self.guard.open() as ctrl:
            self.stopped(ctrl);self.guard.run_shared();ctrl.step('start_original');ctrl.step('restore_restart')
        self.assertFalse((self.service/guarded.service.RESULT).exists())
        self.assertFalse((self.registry/guarded.RESULT).exists())
        self.assertTrue(pc.inspect(self.registry)['original_restored'])

    def test_second_output_does_not_bypass_consumed_service(self):
        with self.guard.open() as ctrl:self.stopped(ctrl)
        root=self.root/'second';root.mkdir(mode=0o700);registry=root/'registry';registry.mkdir(mode=0o700)
        backend,model,*_=fixture_backend(registry)
        plan,sha,paths=combined.prepare(root,registry,backend,True,service_contract_sha256=self.service_sha)
        other=guarded.GuardedSharedPrepared(backend,plan,sha,paths,service_directory=self.service,
            service_sha256=self.service_sha,phase_seconds=self.phases,mode='session-scanner-normal')
        with self.assertRaisesRegex(ValueError,'service-attempt-consumed'):
            with other.open():self.fail('rearmed')
        self.assertFalse((registry/'retained-admission.json').exists());self.assertEqual(model.calls,[])

    def test_concurrent_guard_never_opens_control(self):
        other=self.make()
        with self.guard.open():
            with self.assertRaisesRegex(ValueError,'service-coordinator-active'):
                with other.open():self.fail('overlap')
        self.assertEqual(self.model.calls,[])

    def test_lock_replacement_prevents_first_mutation(self):
        with self.guard.open() as ctrl:
            lock=self.service/guarded.service.LOCK;lock.rename(self.service/'old-lock')
            lock.write_bytes(b'');lock.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'service-identity-changed'):ctrl.step('disable_restart')
        self.assertEqual(self.model.calls,[]);self.assertEqual(pc.inspect(self.registry)['records'],0)

    def test_expiry_after_ack_keeps_pending_actual_effect(self):
        mutate=self.model.mutate
        def slow(action,cid):
            ack=mutate(action,cid);self.now+=30;return ack
        self.backend.mutate=slow
        with self.guard.open() as ctrl:
            with self.assertRaisesRegex(ValueError,'budget-phase-expired'):ctrl.step('disable_restart')
            with self.assertRaises(ValueError):ctrl.step('stop')
        self.assertEqual(self.model.row['restart'],'no')
        state=pc.inspect(self.registry);self.assertEqual(state['pending_action'],'disable_restart')
        self.assertEqual(state['target']['restart'],'unless-stopped')
        self.assertFalse((self.service/guarded.service.RESULT).exists())

    def test_expiry_in_last_admission_gate_prevents_dispatch(self):
        gate=self.guard.gate
        def slow(action):
            result=gate(action)
            if action=='disable_restart':self.now+=30
            return result
        with self.guard.open() as ctrl,patch.object(self.guard,'gate',side_effect=slow):
            with self.assertRaisesRegex(ValueError,'budget-phase-expired'):ctrl.step('disable_restart')
        self.assertEqual(self.model.calls,[]);self.assertEqual(pc.inspect(self.registry)['pending_action'],'disable_restart')

    def test_expiry_after_actual_shared_close_blocks_restore(self):
        run=v.run
        def slow(*args,**kwargs):
            result=run(*args,**kwargs);self.now+=60;return result
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            with patch.object(v,'run',side_effect=slow):
                with self.assertRaisesRegex(ValueError,'budget-phase-expired'):self.guard.run_shared()
            with self.assertRaises(ValueError):ctrl.step('start_original')
        self.assertEqual(self.model.calls,['disable_restart','stop'])
        self.assertTrue(c.parse((self.registry/v.RESULT).read_bytes())['scanner']['reaped'])
        self.assertFalse((self.service/guarded.service.RESULT).exists())

    def test_lost_guard_completion_return_is_not_retried(self):
        write=c.write_new
        def lost(path,data):
            value=write(path,data)
            if path.name==guarded.RESULT:raise OSError('lost-completion')
            return value
        with self.guard.open() as ctrl:
            self.stopped(ctrl);self.guard.run_shared();ctrl.step('start_original');ctrl.step('restore_restart')
            with patch.object(c,'write_new',side_effect=lost):
                with self.assertRaises(OSError):self.guard.complete()
        self.assertTrue((self.registry/guarded.RESULT).exists())
        self.assertFalse((self.service/guarded.service.RESULT).exists())
        self.assertEqual(guarded.service.inspect(self.service,self.service_sha)['status'],'attempt-consumed-completion-unconfirmed')

    def test_completion_requires_same_open_controller_and_actual_restoration(self):
        with self.guard.open() as ctrl:
            self.stopped(ctrl);self.guard.run_shared()
            with self.assertRaisesRegex(ValueError,'guarded-restoration-required'):self.guard.complete()
        with self.assertRaisesRegex(ValueError,'service-lease-closed'):self.guard.complete()
        self.assertFalse((self.service/guarded.service.RESULT).exists())

    def test_claim_write_failure_never_opens_control_but_consumes_service(self):
        write=c.write_new
        def fail(path,data):
            if path.name==guarded.CLAIM:raise OSError('disk')
            return write(path,data)
        with patch.object(c,'write_new',side_effect=fail):
            with self.assertRaises(OSError):
                with self.guard.open():self.fail('entered')
        self.assertFalse((self.registry/'claim.json').exists());self.assertEqual(self.model.calls,[])
        self.assertTrue((self.service/guarded.service.CLAIM).exists())

    def test_guarded_claim_or_source_drift_refuses(self):
        with self.guard.open() as ctrl:
            path=self.registry/guarded.CLAIM;value=c.parse(path.read_bytes());value['activation_authorized']=True
            path.write_bytes(c.raw(value))
            with self.assertRaisesRegex(ValueError,'guarded-claim-changed'):ctrl.step('disable_restart')
        self.assertEqual(self.model.calls,[])


if __name__=='__main__':unittest.main()
