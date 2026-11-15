import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import coordinator as h
c=h.c
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'r1-control'))
from test_control import target,Backend

class Model:
    """Explicit offline model, not an observation-backed native adapter."""
    def __init__(self,registry,proof,cleanup='unsubscribed'):
        self.registry=registry;self.proof=proof;self.cleanup=cleanup;self.calls=[];self.fail=None;self.corrupt=None
        self.shared=False;self.consumer=False;self.direct=False;self.max_owners=0;self.restores=0
    def perform(self,action,op,known):
        assert h.inspect(self.registry)['pending_action']==action
        self.calls.append(action)
        if self.fail==(action,'before'):raise ValueError('injected-before-effect')
        row={'scope':'isolated-handoff-adapter','operation_id':op,'provider_connection_closed':False,'billing_cutoff_verified':False}
        if action=='bind_endpoint':row.update(endpoint_id='1'*64,endpoint_path=str(self.registry/'discovery.sock'))
        elif action=='start_consumer':
            self.consumer=True;row.update(endpoint_id=known['endpoint_id'],consumer_id='2'*64,image=c.IMAGE,ready=True)
        elif action=='start_owner':
            assert self.consumer and not self.direct;self.shared=True
            row.update(endpoint_id=known['endpoint_id'],consumer_id=known['consumer_id'],owner_id='3'*64,synthetic_attempts=1)
        elif action=='retire_research':row.update(owner_id=known['owner_id'],admission_closed=True,cleanup=self.cleanup,discovery_continues=self.cleanup=='unsubscribed')
        elif action=='stop_shared':
            self.shared=self.consumer=False
            row.update(owner_id=known['owner_id'],consumer_id=known['consumer_id'],owner_reaped=True,consumer_reaped=True,local_connection_closed=True)
        elif action=='restore_direct':
            assert not self.shared and not self.consumer;self.direct=True;self.restores+=1
            row.update(previous_direct_id=known['direct_id'],new_direct_id='4'*64,image=c.IMAGE,
                config_sha256=h.config_identity(self.proof['claim']['target']),restart_policy='unless-stopped',ready=True)
        self.max_owners=max(self.max_owners,int(self.shared)+int(self.direct));assert self.max_owners<=1
        if self.fail==(action,'after'):raise ValueError('injected-lost-response')
        if self.corrupt:self.corrupt(action,row)
        return row

class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);control=self.base/'control';control.mkdir(mode=0o700)
        b=Backend(target())
        with c.Control(control,target(),c.digest(c.raw(h.check_control.pins())),b) as x:
            x.step('disable_restart');x.step('stop')
        self.proof={'claim':c.parse((control/'claim.json').read_bytes()),'events':(control/'events.jsonl').read_text()}
        self.root=self.base/'handoff';self.root.mkdir(mode=0o700);self.b=Model(self.root,self.proof)
    def writer(self,backend=None):return h.Coordinator(self.root,self.proof,backend or self.b)
    def finish(self,writer):
        for action in h.ACTIONS:state=writer.step(action)
        return state
    def test_normal_chain_and_byte_preserving_recovery(self):
        with self.writer() as x:state=self.finish(x)
        self.assertEqual(state['state'],'rolled-back');self.assertEqual(state['records'],12)
        self.assertEqual(self.b.restores,1);self.assertEqual(self.b.max_owners,1)
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(h.inspect(self.root),state)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})
        for k in ('automatic_resume_allowed','production_activation_authorized','provider_connection_closed','billing_cutoff_verified'):self.assertFalse(state[k])
    def test_cleanup_failure_remains_failure_after_rollback(self):
        self.b.cleanup='upstream-aborted'
        with self.writer() as x:state=self.finish(x)
        self.assertTrue(state['complete']);self.assertEqual(state['research_cleanup'],'upstream-aborted')
    def test_all_twelve_pre_and_post_effect_fault_positions_remain_pending(self):
        for index,action in enumerate(h.ACTIONS):
            for phase in ('before','after'):
                with self.subTest(action=action,phase=phase),tempfile.TemporaryDirectory() as tmp:
                    root=Path(tmp);b=Model(root,self.proof);b.fail=(action,phase)
                    with h.Coordinator(root,self.proof,b) as x:
                        for previous in h.ACTIONS[:index]:x.step(previous)
                        with self.assertRaises(ValueError):x.step(action)
                        with self.assertRaises(ValueError):x.step(action)
                    state=h.inspect(root);self.assertEqual(state['records'],2*index+1)
                    self.assertEqual(state['pending_action'],action);self.assertTrue(state['reconciliation_required'])
                    self.assertEqual(len(b.calls),index+1)
                    if action!='restore_direct':self.assertEqual(b.restores,0)
    def test_incomplete_control_proof_never_dispatches(self):
        self.proof['events']='\n'.join(self.proof['events'].splitlines()[:3])+'\n'
        with self.assertRaisesRegex(ValueError,'direct-not-stopped'):self.writer()
        self.assertEqual(self.b.calls,[])
    def test_control_source_and_handoff_source_cannot_be_substituted(self):
        self.proof['claim']['source_sha256']='f'*64
        with self.assertRaises(ValueError):self.writer()
    def test_owner_cannot_start_before_consumer_or_after_completion(self):
        with self.writer() as x:
            with self.assertRaises(ValueError):x.step('start_owner')
        self.assertEqual(self.b.calls,[])
    def test_successful_generation_cannot_be_rearmed(self):
        with self.writer() as x:self.finish(x)
        with self.assertRaises(FileExistsError):
            with self.writer():pass
        self.assertEqual(self.b.restores,1)
    def test_wrong_generation_receipt_stays_pending(self):
        self.b.corrupt=lambda action,row:row.update(operation_id='f'*64)
        with self.writer() as x:
            with self.assertRaises(ValueError):x.step('bind_endpoint')
        self.assertEqual(h.inspect(self.root)['pending_action'],'bind_endpoint')
    def test_foreign_consumer_and_actor_alias_are_rejected(self):
        for alias in ('1'*64,self.proof['claim']['target']['id']):
            with self.subTest(alias=alias),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);b=Model(root,self.proof)
                b.corrupt=lambda a,r:r.update(consumer_id=alias) if a=='start_consumer' else None
                with h.Coordinator(root,self.proof,b) as x:
                    x.step('bind_endpoint')
                    with self.assertRaises(ValueError):x.step('start_consumer')
                self.assertEqual(b.restores,0)
    def test_changed_image_and_false_readiness_refuse_consumer(self):
        for key,value in [('image','sha256:'+'f'*64),('ready',False),('endpoint_id','f'*64)]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);b=Model(root,self.proof);b.corrupt=lambda a,r:r.update({key:value}) if a=='start_consumer' else None
                with h.Coordinator(root,self.proof,b) as x:
                    x.step('bind_endpoint')
                    with self.assertRaises(ValueError):x.step('start_consumer')
                self.assertNotIn('start_owner',b.calls)
    def test_uncertain_shutdown_cannot_restore_direct(self):
        self.b.corrupt=lambda a,r:r.update(owner_reaped=False) if a=='stop_shared' else None
        with self.writer() as x:
            for action in h.ACTIONS[:4]:x.step(action)
            with self.assertRaises(ValueError):x.step('stop_shared')
            with self.assertRaises(ValueError):x.step('restore_direct')
        self.assertEqual(self.b.restores,0)
    def test_wrong_restoration_policy_config_or_predecessor_refuses(self):
        for key,value in [('restart_policy','always'),('config_sha256','f'*64),('previous_direct_id','f'*64),('new_direct_id','3'*64)]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);b=Model(root,self.proof);b.corrupt=lambda a,r:r.update({key:value}) if a=='restore_direct' else None
                with h.Coordinator(root,self.proof,b) as x:
                    for action in h.ACTIONS[:-1]:x.step(action)
                    with self.assertRaises(ValueError):x.step('restore_direct')
                self.assertEqual(h.inspect(root)['pending_action'],'restore_direct')
    def test_remote_claims_and_missing_receipt_refuse(self):
        for field in ('provider_connection_closed','billing_cutoff_verified'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);b=Model(root,self.proof);b.corrupt=lambda a,r:r.update({field:True})
                with h.Coordinator(root,self.proof,b) as x:
                    with self.assertRaises(ValueError):x.step('bind_endpoint')
    def test_failed_cleanup_cannot_claim_continuing_discovery(self):
        self.b.cleanup='upstream-aborted';self.b.corrupt=lambda a,r:r.update(discovery_continues=True) if a=='retire_research' else None
        with self.writer() as x:
            for action in h.ACTIONS[:3]:x.step(action)
            with self.assertRaises(ValueError):x.step('retire_research')
        self.assertEqual(h.inspect(self.root)['pending_action'],'retire_research')
    def test_torn_log_and_copied_registry_refuse(self):
        with self.writer():pass
        with tempfile.TemporaryDirectory() as tmp:
            for p in self.root.iterdir():q=Path(tmp)/p.name;q.write_bytes(p.read_bytes());q.chmod(0o600)
            with self.assertRaises(ValueError):h.inspect(tmp)
        (self.root/'handoff-events.jsonl').write_bytes(b'{')
        with self.assertRaises(ValueError):h.inspect(self.root)
    def test_replaced_log_and_clock_failure_block_dispatch(self):
        with self.writer() as x:
            p=self.root/'handoff-events.jsonl';p.rename(self.root/'saved');p.write_bytes(b'');p.chmod(0o600)
            with self.assertRaises(ValueError):x.step('bind_endpoint')
        self.assertEqual(self.b.calls,[])
    def test_fsync_and_concurrent_step_fail_before_dispatch(self):
        with self.writer() as x:
            x.mutex.acquire()
            try:
                with self.assertRaises(ValueError):x.step('bind_endpoint')
            finally:x.mutex.release()
            with patch.object(os,'fsync',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):x.step('bind_endpoint')
        self.assertEqual(self.b.calls,[])
    def test_clock_regression_prevents_dispatch(self):
        with self.writer() as x:
            with patch.object(c,'now',return_value='2000-01-01T00:00:00+00:00'):
                with self.assertRaises(ValueError):x.step('bind_endpoint')
        self.assertEqual(self.b.calls,[])

    def test_completed_writer_cannot_dispatch_again(self):
        with self.writer() as x:
            self.finish(x)
            with self.assertRaises(ValueError):x.step('restore_direct')
        self.assertEqual(self.b.restores,1)
    def test_missing_receipt_cannot_confirm_clean_return(self):
        self.b.perform=lambda *args:None
        with self.writer() as x:
            with self.assertRaises(ValueError):x.step('bind_endpoint')
        self.assertEqual(h.inspect(self.root)['pending_action'],'bind_endpoint')

if __name__=='__main__':unittest.main()
