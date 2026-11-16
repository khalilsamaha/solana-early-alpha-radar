import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import shared_session as shared
import test_admission as fixtures
from test_production_control import Backend
a=shared.a;c=shared.c;pc=shared.control;v=shared.supervisor


class SharedSessionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        raw,data,sha=fixtures.evidence()
        self.backend=a.BoundDocker(['docker-model'],data,sha,fixtures.PINS,lambda *_,**kw:c.raw(raw))
        self.registry=self.root/'registry';self.registry.mkdir(mode=0o700)
        self.paths={k:str(self.root/k) for k in a.storage.ROLES}
        for path in self.paths.values():Path(path).mkdir(mode=0o700)
        config,policy=fixtures.inputs()
        config.update(scanner_image=self.backend.target['image'],
            scanner_config_sha256=self.backend.admission['readiness_configuration_sha256'],
            rollback_config_sha256=self.backend.target['config_sha256'],registry_path=str(self.registry),
            endpoint_path=str(self.registry/'discovery.sock'),capture_path=self.paths['capture'])
        policy.update(raw_bytes=65536,database_bytes=262144,journal_bytes=65536,receipt_bytes=65536,
            retained_runs=1,quarantined_runs=1,headroom_bytes=1000,research_seconds=2,
            service_seconds=3,setup_seconds=3,shutdown_seconds=3,memory_bytes=512*1024**2,cpu_seconds=5,open_files=64)
        self.plan=self.root/'plan';self.sha=a.m.freeze(self.plan,a.m.build(config,policy))
        a.prep.prepare(self.plan,self.sha,self.paths)
        self.model=Backend(self.registry);self.model.row=copy.deepcopy(self.backend.target)
        self.backend.observe=self.model.observe;self.backend.mutate=self.model.mutate
        self.guard=shared.SharedPrepared(self.backend,self.plan,self.sha,self.paths)

    def stopped(self,ctrl):ctrl.step('disable_restart');ctrl.step('stop')

    def test_actual_worker_node_scanner_and_same_original_roundtrip(self):
        run=v.run
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            def during(*args,**kwargs):
                self.assertFalse(self.model.row['running'])
                self.assertTrue((self.registry/shared.INTENT).exists())
                with self.assertRaisesRegex(ValueError,'concurrent-operation'):ctrl.step('start_original')
                return run(*args,**kwargs)
            with patch.object(v,'run',side_effect=during):result=self.guard.run_shared()
            self.assertTrue(result['worker_reaped']);self.assertTrue(result['scanner']['reaped'])
            self.assertEqual(result['terminal']['session_evidence']['transport'],'pipe')
            ctrl.step('start_original');state=ctrl.step('restore_restart')
        self.assertTrue(state['original_restored'])
        self.assertEqual(state['target']['id'],self.backend.target['id'])
        self.assertEqual(state['target']['config_sha256'],self.backend.target['config_sha256'])
        self.assertEqual(state['target']['restart'],'unless-stopped')
        self.assertFalse(c.parse((self.registry/shared.RESULT).read_bytes())['provider_connection_closed'])

    def test_upstream_abort_requires_closed_session_before_restoration(self):
        self.guard=shared.SharedPrepared(self.backend,self.plan,self.sha,self.paths,mode='session-scanner-cleanup-failure')
        with self.guard.open() as ctrl:
            self.stopped(ctrl);result=self.guard.run_shared()
            self.assertEqual(result['terminal']['session_evidence']['research_cleanup'],'upstream-aborted')
            self.assertTrue(result['terminal']['session_evidence']['local_upstream_closed'])
            ctrl.step('start_original');ctrl.step('restore_restart')

    def test_restore_without_session_leaves_pending_intent_without_start(self):
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            with self.assertRaisesRegex(ValueError,'shared-shutdown-required'):ctrl.step('start_original')
        self.assertEqual(self.model.calls,['disable_restart','stop'])
        self.assertEqual(pc.inspect(self.registry)['pending_action'],'start_original')

    def test_running_original_never_starts_session(self):
        with self.guard.open(),patch.object(v,'run',side_effect=AssertionError('spawn')):
            with self.assertRaisesRegex(ValueError,'shared-original-not-stopped'):self.guard.run_shared()
        self.assertFalse((self.registry/shared.INTENT).exists())
        self.assertEqual(self.model.calls,[])

    def test_original_drift_after_intent_prevents_session_start(self):
        write=c.write_new
        def drift(path,data):
            write(path,data)
            if path.name==shared.INTENT:self.model.row['config_sha256']='d'*64
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            with patch.object(c,'write_new',side_effect=drift),patch.object(v,'run',side_effect=AssertionError('spawn')):
                with self.assertRaises(ValueError):self.guard.run_shared()
        self.assertEqual(self.model.calls,['disable_restart','stop'])

    def test_supervisor_failure_cannot_restore_or_retry(self):
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            with patch.object(v,'run',return_value={'outcome':'worker-failed'}):
                with self.assertRaisesRegex(ValueError,'shared-shutdown-unconfirmed'):self.guard.run_shared()
            with self.assertRaisesRegex(ValueError,'consumed-or-closed'):ctrl.step('start_original')
            with self.assertRaisesRegex(ValueError,'shared-controller-closed'):self.guard.run_shared()
        self.assertIsNone(self.guard.completed);self.assertFalse((self.registry/shared.RESULT).exists())

    def test_intent_durability_failure_prevents_spawn(self):
        write=c.write_new
        def fail(path,data):
            if path.name==shared.INTENT:raise OSError('intent-failed')
            return write(path,data)
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            with patch.object(c,'write_new',side_effect=fail),patch.object(v,'run',side_effect=AssertionError('spawn')):
                with self.assertRaisesRegex(OSError,'intent-failed'):self.guard.run_shared()
            with self.assertRaises(ValueError):ctrl.step('start_original')
        self.assertEqual(self.model.calls,['disable_restart','stop'])

    def test_capacity_loss_before_shared_session_prevents_spawn(self):
        sample=a.storage.sample
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            with patch.object(a.storage,'sample',side_effect=lambda fd:{**sample(fd),'available_bytes':0}),\
                 patch.object(v,'run',side_effect=AssertionError('spawn')):
                with self.assertRaisesRegex(ValueError,'admission-storage-insufficient'):self.guard.run_shared()
        self.assertFalse((self.registry/shared.INTENT).exists())

    def test_actual_worker_failure_is_reaped_without_restoration(self):
        # Preexisting evidence causes the real worker to refuse its attempt.
        (Path(self.paths['capture'])/'supervised-session').mkdir(mode=0o700)
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            with self.assertRaisesRegex(ValueError,'shared-shutdown-unconfirmed'):self.guard.run_shared()
        result=v.inspect(self.registry,self.sha)
        self.assertEqual(result['outcome'],'worker-failed')
        self.assertTrue(result['worker_reaped']);self.assertTrue(result['scanner']['reaped'])
        self.assertEqual(self.model.calls,['disable_restart','stop'])

    def test_target_drift_during_session_refuses_completion(self):
        run=v.run
        def drift(*args,**kwargs):
            result=run(*args,**kwargs);self.model.row['config_sha256']='e'*64;return result
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            with patch.object(v,'run',side_effect=drift):
                with self.assertRaises(ValueError):self.guard.run_shared()
        self.assertIsNone(self.guard.completed);self.assertFalse((self.registry/shared.RESULT).exists())

    def test_capacity_loss_after_completion_still_refuses_restore(self):
        sample=a.storage.sample
        with self.guard.open() as ctrl:
            self.stopped(ctrl);self.guard.run_shared()
            with patch.object(a.storage,'sample',side_effect=lambda fd:{**sample(fd),'available_bytes':0}):
                with self.assertRaisesRegex(ValueError,'admission-storage-insufficient'):ctrl.step('start_original')
        self.assertEqual(self.model.calls,['disable_restart','stop'])

    def test_changed_source_or_claim_prevents_spawn(self):
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            with patch.object(shared,'pins',return_value={}),patch.object(v,'run',side_effect=AssertionError('spawn')):
                with self.assertRaisesRegex(ValueError,'shared-claim-changed'):self.guard.run_shared()
        self.assertFalse((self.registry/shared.INTENT).exists())

    def test_changed_shared_claim_refuses_first_original_mutation(self):
        with self.guard.open() as ctrl:
            path=self.registry/shared.CLAIM;path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'shared-claim-changed'):ctrl.step('disable_restart')
        self.assertEqual(self.model.calls,[])

    def test_lost_supervisor_result_preserves_artifacts_but_cannot_restore(self):
        write=v.p.write_at
        def fail(fd,name,row):
            if name==v.RESULT:raise OSError('lost-result')
            return write(fd,name,row)
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            with patch.object(v.p,'write_at',side_effect=fail):
                with self.assertRaisesRegex(OSError,'lost-result'):self.guard.run_shared()
            with self.assertRaises(ValueError):ctrl.step('start_original')
        self.assertEqual(v.inspect(self.registry,self.sha)['outcome'],'supervision-unresolved')
        self.assertTrue((Path(self.paths['capture'])/'supervised-session/stopped.json').exists())

    def test_lost_bridge_result_never_creates_in_memory_witness(self):
        write=c.write_new
        def fail(path,data):
            if path.name==shared.RESULT:raise OSError('lost-bridge-result')
            return write(path,data)
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            with patch.object(c,'write_new',side_effect=fail):
                with self.assertRaisesRegex(OSError,'lost-bridge-result'):self.guard.run_shared()
            with self.assertRaises(ValueError):ctrl.step('start_original')
        self.assertEqual(v.inspect(self.registry,self.sha)['outcome'],v.SUCCESS)
        self.assertIsNone(self.guard.completed);self.assertEqual(self.model.calls,['disable_restart','stop'])

    def test_changed_terminal_prevents_start(self):
        with self.guard.open() as ctrl:
            self.stopped(ctrl);self.guard.run_shared()
            path=Path(self.paths['capture'])/'supervised-session/stopped.json'
            row=c.parse(path.read_bytes());row['local_upstream_closed']=False;path.write_bytes(c.raw(row))
            with self.assertRaises(ValueError):ctrl.step('start_original')
        self.assertEqual(self.model.calls,['disable_restart','stop'])

    def test_changed_bridge_receipt_prevents_restart_policy_restore(self):
        with self.guard.open() as ctrl:
            self.stopped(ctrl);self.guard.run_shared();ctrl.step('start_original')
            path=self.registry/shared.RESULT;path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'shared-completion-changed'):ctrl.step('restore_restart')
        self.assertEqual(self.model.calls,['disable_restart','stop','start_original'])
        self.assertEqual(self.model.row['restart'],'no')
        self.assertEqual(pc.inspect(self.registry)['pending_action'],'restore_restart')

    def test_historical_supervisor_success_cannot_be_adopted(self):
        with self.guard.open() as ctrl:
            self.stopped(ctrl)
            historical=v.run(self.plan,self.sha,mode=self.guard.mode)
            self.assertEqual(historical['outcome'],v.SUCCESS)
            with patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')):
                with self.assertRaisesRegex(ValueError,'runtime-result-already-present'):self.guard.run_shared()
        self.assertIsNone(self.guard.completed)
        self.assertEqual(self.model.calls,['disable_restart','stop'])

    def test_existing_supervision_refuses_before_original_control_is_opened(self):
        c.write_new(self.registry/v.CLAIM,b'{}\n')
        with self.assertRaisesRegex(ValueError,'shared-registry-consumed'):self.guard.open()
        self.assertFalse((self.registry/'retained-admission.json').exists())
        self.assertEqual(self.model.calls,[])

    def test_recovery_is_read_only_and_does_not_restore(self):
        with self.guard.open() as ctrl:
            self.stopped(ctrl);self.guard.run_shared()
        before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(self.backend,'observe',side_effect=AssertionError('docker')),\
             patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')):
            self.assertEqual(pc.inspect(self.registry)['state'],'locally-stopped')
            self.assertEqual(v.inspect(self.registry,self.sha)['outcome'],v.SUCCESS)
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        with self.assertRaisesRegex(ValueError,'shared-controller-closed'):self.guard.closed()
        fresh=shared.SharedPrepared(self.backend,self.plan,self.sha,self.paths)
        with self.assertRaisesRegex(ValueError,'shared-registry-consumed'):fresh.open()


if __name__=='__main__':unittest.main()
