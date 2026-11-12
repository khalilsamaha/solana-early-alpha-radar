import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from capture import CaptureError, canonical, digest, exclusive_file
import lifecycle as l
from offline_backend import Backend


class Model:
    """Pure callback model for journal fault injection; native cases are separate."""
    def __init__(self):self.calls=[]
    def perform(self,action,op,known):
        self.calls.append(action)
        values={
          'disable_direct_restart':{'direct_id':'1'*32,'restart_disabled':True},
          'stop_direct':{'direct_id':'1'*32,'direct_reaped':True,'connection_closed':True},
          'bind_endpoint':{'endpoint_id':'2'*32,'endpoint_ready':True},
          'start_consumer':{'endpoint_id':'2'*32,'consumer_id':'3'*32,'consumer_ready':True},
          'start_owner':{'consumer_id':'3'*32,'owner_id':'4'*32,'upstream_attempts':1},
          'retire_research':{'owner_id':'4'*32,'admission_closed':True,'cleanup':'unsubscribed'},
          'stop_shared':{'owner_id':'4'*32,'consumer_id':'3'*32,'owner_reaped':True,'consumer_reaped':True,'connection_closed':True},
          'restore_direct':{'previous_direct_id':'1'*32,'new_direct_id':'5'*32,'restart_policy_restored':True},
        }
        return {**values[action],'operation_id':op,'scope':'synthetic-process-lifecycle'}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='r1-lifecycle-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.registry=self.root/'registry';self.output=self.root/'output'
        self.registry.mkdir(mode=0o700);self.output.mkdir(mode=0o700)
        self.model=Model()
    def coordinator(self):return l.Lifecycle(self.registry,self.output,'a'*64,'b'*64)
    def completed(self):
        with self.coordinator() as c:
            for action in l.ACTIONS:c.step(action,self.model)
        return json.loads((self.registry/'claim.json').read_bytes()),(self.output/'events.jsonl').read_bytes()

    def test_complete_replay_and_no_automatic_resume(self):
        claim,raw=self.completed();r=l.replay(claim,raw)
        self.assertEqual(r['state'],'rolled_back');self.assertEqual(r['records'],16)
        self.assertTrue(r['complete']);self.assertFalse(r['automatic_resume_allowed'])
        self.assertEqual(self.model.calls,list(l.ACTIONS))

    def test_backend_observes_durable_intent_before_side_effect(self):
        model=self.model;registry=self.registry;output=self.output
        class Inspecting:
            def perform(self,action,op,known):
                self_state=l.inspect(registry,output)
                if self_state['pending_action']!=action:raise AssertionError('intent missing')
                return model.perform(action,op,known)
        with self.coordinator() as c:c.step(l.ACTIONS[0],Inspecting())

    def test_claim_consumes_registry_even_with_new_output_and_registration(self):
        self.completed();other=self.root/'other';other.mkdir(mode=0o700)
        with self.assertRaises(FileExistsError):
            with l.Lifecycle(self.registry,other,'c'*64,'d'*64):pass
        self.assertFalse((other/'events.jsonl').exists())

    def test_registry_lock_rejects_concurrent_coordinator(self):
        with self.coordinator():
            with self.assertRaises(CaptureError):
                with self.coordinator():pass

    def test_wrong_order_never_calls_backend(self):
        for action in l.ACTIONS[1:]:
            with tempfile.TemporaryDirectory() as t:
                registry=Path(t)/'r';output=Path(t)/'o';registry.mkdir(mode=0o700);output.mkdir(mode=0o700)
                model=Model()
                with l.Lifecycle(registry,output,'a'*64,'b'*64) as c:
                    with self.assertRaises(CaptureError):c.step(action,model)
                self.assertEqual(model.calls,[])

    def test_each_interrupted_operation_is_pending_and_not_retryable(self):
        for index in range(len(l.ACTIONS)):
            with self.subTest(action=l.ACTIONS[index]),tempfile.TemporaryDirectory() as t:
                registry=Path(t)/'r';output=Path(t)/'o';registry.mkdir(mode=0o700);output.mkdir(mode=0o700)
                model=Model()
                class Failing:
                    def perform(self,action,op,known):
                        model.perform(action,op,known);raise OSError('do-not-export')
                with l.Lifecycle(registry,output,'a'*64,'b'*64) as c:
                    for a in l.ACTIONS[:index]:c.step(a,model)
                    with self.assertRaises(CaptureError):c.step(l.ACTIONS[index],Failing())
                    calls=len(model.calls)
                    with self.assertRaises(CaptureError):c.step(l.ACTIONS[index],model)
                    self.assertEqual(len(model.calls),calls)
                r=l.inspect(registry,output);self.assertEqual(r['pending_action'],l.ACTIONS[index])
                self.assertTrue(r['reconciliation_required']);self.assertFalse(r['automatic_resume_allowed'])
                self.assertNotIn(b'do-not-export',(output/'events.jsonl').read_bytes())

    def test_uncertain_owner_shutdown_blocks_direct_restore(self):
        with self.coordinator() as c:
            for a in l.ACTIONS[:6]:c.step(a,self.model)
            model=self.model
            class Unconfirmed:
                def perform(self,a,op,k):
                    r=model.perform(a,op,k);r['owner_reaped']=False;return r
            with self.assertRaises(CaptureError):c.step('stop_shared',Unconfirmed())
            with self.assertRaises(CaptureError):c.step('restore_direct',self.model)
        self.assertNotIn('restore_direct',self.model.calls)

    def test_receipt_from_other_operation_rejected(self):
        model=self.model
        class Wrong:
            def perform(self,a,op,k):
                r=model.perform(a,op,k);r['operation_id']='f'*64;return r
        with self.coordinator() as c:
            with self.assertRaises(CaptureError):c.step(l.ACTIONS[0],Wrong())

    def test_stale_actor_identity_rejected(self):
        model=self.model
        class Wrong:
            def perform(self,a,op,k):
                r=model.perform(a,op,k);r['direct_id']='f'*32;return r
        with self.coordinator() as c:
            c.step(l.ACTIONS[0],model)
            with self.assertRaises(CaptureError):c.step(l.ACTIONS[1],Wrong())

    def test_duplicate_actor_identity_rejected(self):
        with self.coordinator() as c:
            for a in l.ACTIONS[:2]:c.step(a,self.model)
            model=self.model
            class Alias:
                def perform(self,a,op,k):
                    r=model.perform(a,op,k);r['endpoint_id']=k['direct_id'];return r
            with self.assertRaises(CaptureError):c.step('bind_endpoint',Alias())

    def test_extra_receipt_fields_and_nonboolean_proofs_rejected(self):
        row=self.model.perform(l.ACTIONS[0],'a'*64,{})
        for change in ({'secret':'do-not-export'},{'restart_disabled':1},{'scope':'live'}):
            with self.assertRaises(CaptureError):l.validate_receipt(l.ACTIONS[0],{**row,**change},'a'*64,{})

    def test_intent_sync_failure_prevents_backend_execution(self):
        with self.coordinator() as c:
            with patch.object(l.os,'fsync',side_effect=OSError('fixture')):
                with self.assertRaises(CaptureError):c.step(l.ACTIONS[0],self.model)
        self.assertEqual(self.model.calls,[])

    def test_confirmation_failure_leaves_pending_operation(self):
        with self.coordinator() as c:
            original=c._append
            def append(kind,*args):
                if kind=='confirmed':raise OSError('fixture')
                return original(kind,*args)
            with patch.object(c,'_append',side_effect=append):
                with self.assertRaises(CaptureError):c.step(l.ACTIONS[0],self.model)
        self.assertEqual(l.inspect(self.registry,self.output)['pending_action'],l.ACTIONS[0])
        self.assertEqual(self.model.calls,[l.ACTIONS[0]])

    def test_replaced_journal_is_never_appended(self):
        with self.coordinator() as c:
            p=self.output/'events.jsonl';p.unlink();exclusive_file(p,b'')
            with self.assertRaises(CaptureError):c.step(l.ACTIONS[0],self.model)
        self.assertEqual(self.model.calls,[])

    def test_concurrent_step_is_refused_without_duplicate_callback(self):
        entered=threading.Event();release=threading.Event();errors=[];model=self.model
        class Blocking:
            def perform(self,a,op,k):entered.set();release.wait(2);return model.perform(a,op,k)
        with self.coordinator() as c:
            def run():
                try:c.step(l.ACTIONS[0],Blocking())
                except BaseException as e:errors.append(type(e).__name__)
            thread=threading.Thread(target=run);thread.start()
            try:
                self.assertTrue(entered.wait(1))
                with self.assertRaises(CaptureError):c.step(l.ACTIONS[0],model)
            finally:release.set();thread.join(timeout=2)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(model.calls,[l.ACTIONS[0]])

    def test_corrupt_reordered_duplicate_and_torn_records_rejected(self):
        claim,raw=self.completed();lines=raw.splitlines(keepends=True)
        for corrupt in (raw[:-1],raw+b'x',b''.join(lines[1:]),lines[0]+raw,
                        raw.replace(b'rolled',b'bad'),raw.replace(b'"seq":1,',b'"seq":0,',1)):
            if corrupt==raw:continue
            with self.assertRaises(CaptureError):l.replay(claim,corrupt)

    def test_claim_mismatch_and_oversized_log_rejected(self):
        claim,raw=self.completed()
        with self.assertRaises(CaptureError):l.replay({**claim,'registration_id':'c'*64},raw)
        with self.assertRaises(CaptureError):l.replay(claim,b'x'*(l.MAX_LOG+1))

    def test_truncated_valid_prefix_still_cannot_resume(self):
        claim,raw=self.completed();prefix=b''.join(raw.splitlines(keepends=True)[:10]);r=l.replay(claim,prefix)
        self.assertFalse(r['complete']);self.assertTrue(r['reconciliation_required']);self.assertFalse(r['automatic_resume_allowed'])

    def test_recovery_is_read_only_and_missing_log_never_created(self):
        self.completed();before={p:p.read_bytes() for p in (self.registry/'claim.json',self.output/'events.jsonl')}
        l.inspect(self.registry,self.output)
        self.assertTrue(all(p.read_bytes()==v for p,v in before.items()))
        (self.output/'events.jsonl').unlink()
        with self.assertRaises(OSError):l.inspect(self.registry,self.output)
        self.assertFalse((self.output/'events.jsonl').exists())

    def test_native_process_handoff_and_cleanup_failure_never_overlap(self):
        for failure in (False,True):
            with tempfile.TemporaryDirectory() as t:
                registry=Path(t)/'r';output=Path(t)/'o';registry.mkdir(mode=0o700);output.mkdir(mode=0o700)
                backend=Backend(cleanup_failure=failure)
                try:
                    with l.Lifecycle(registry,output,'a'*64,'b'*64) as c:
                        for a in l.ACTIONS:c.step(a,backend)
                finally:backend.close()
                r=backend.receipt();self.assertTrue(r['all_fixture_processes_reaped'])
                self.assertEqual(r['max_simultaneous_owner_processes'],1)
                self.assertEqual(r['direct_restore_calls'],1)
                self.assertEqual(l.inspect(registry,output)['state'],'rolled_back')

    def test_changed_claim_blocks_side_effect_before_intent(self):
        with self.coordinator() as c:
            p=self.registry/'claim.json'
            changed={**c.claim,'registration_id':'c'*64}
            p.write_bytes((canonical(changed)+'\n').encode())
            with self.assertRaises(CaptureError):c.step(l.ACTIONS[0],self.model)
        self.assertEqual(self.model.calls,[])
