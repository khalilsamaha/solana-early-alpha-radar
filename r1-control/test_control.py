import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import control as c

TOKEN='b'*32

def target():return {'id':'a'*64,'image':c.IMAGE,'label':TOKEN,'user':'1000:1000','network':'none',
    'readonly':True,'privileged':False,'restart':'unless-stopped','mounts':[],'running':True,'exit_code':0,
    'pid':123,'started':'2026-11-15T08:00:00.000000000Z','finished':'0001-01-01T00:00:00Z',
    'memory':128*1024**2,'swap':128*1024**2,'pids':32,'cpus':1000000000,'init':True,
    'logging':'none','caps':['ALL'],'security':['no-new-privileges:true'],'cmd':c.CMD,'entrypoint':c.ENTRY}

class Backend:
    def __init__(self,row):self.row=copy.deepcopy(row);self.calls=[];self.hook=None;self.lost=None;self.unknown=False;self.registry=None
    def observe(self,cid):
        if self.hook:self.hook()
        return copy.deepcopy(self.row)
    def mutate(self,action,cid):
        # At side-effect boundary the intent must already be readable from disk.
        if self.registry:
            state=c.inspect(self.registry);assert state['pending_action']==action
        self.calls.append(action)
        if action=='disable_restart':self.row['restart']='no'
        else:self.row.update(pid=0,running=False,exit_code=0,finished='2026-11-15T08:00:01.000000000Z')
        if self.unknown:self.row['started']='2026-11-15T08:00:02.000000000Z'
        if self.lost==action:raise ValueError('lost-response')
        return cid

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.root.chmod(0o700);self.b=Backend(target());self.b.registry=self.root
    def control(self):return c.Control(self.root,target(),'c'*64,self.b)
    def test_complete_chain_has_local_scope_and_reader_is_byte_preserving(self):
        with self.control() as x:x.step('disable_restart');state=x.step('stop')
        self.assertEqual(state['state'],'locally-stopped');self.assertFalse(state['shared_start_authorized'])
        self.assertFalse(state['provider_connection_closed']);self.assertFalse(state['billing_cutoff_verified'])
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(c.inspect(self.root),state)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})
    def test_lost_update_keeps_pending_and_refuses_retry(self):
        self.b.lost='disable_restart'
        with self.control() as x:
            with self.assertRaises(ValueError):x.step('disable_restart')
            with self.assertRaises(ValueError):x.step('disable_restart')
        self.assertEqual(self.b.calls,['disable_restart']);state=c.inspect(self.root)
        self.assertEqual(state['pending_action'],'disable_restart');self.assertFalse(state['local_stop_verified'])
    def test_lost_stop_is_not_confirmed_by_actual_stopped_state(self):
        self.b.lost='stop'
        with self.control() as x:
            x.step('disable_restart')
            with self.assertRaises(ValueError):x.step('stop')
        self.assertFalse(self.b.row['running']);self.assertEqual(c.inspect(self.root)['pending_action'],'stop')
    def test_stale_pid_start_image_config_and_foreign_actor_refuse_before_mutation(self):
        for key,value in [('pid',124),('started','2026-11-15T08:00:03.000000000Z'),('image','sha256:'+'f'*64),
            ('id','e'*64),('label','d'*32),('restart','no'),('network','host'),('cmd',['other'])]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);b=Backend({**target(),key:value})
                with c.Control(root,target(),'c'*64,b) as x:
                    with self.assertRaises(ValueError):x.step('disable_restart')
                self.assertEqual(b.calls,[]);self.assertEqual(c.inspect(root)['records'],0)
    def test_change_between_intent_and_mutation_stays_pending(self):
        calls=0
        def hook():
            nonlocal calls
            calls+=1
            if calls==2:self.b.row['pid']+=1
        self.b.hook=hook
        with self.control() as x:
            with self.assertRaises(ValueError):x.step('disable_restart')
        self.assertEqual(self.b.calls,[]);self.assertEqual(c.inspect(self.root)['pending_action'],'disable_restart')
    def test_post_mutation_change_stays_pending(self):
        self.b.unknown=True
        with self.control() as x:
            with self.assertRaises(ValueError):x.step('disable_restart')
        self.assertEqual(self.b.calls,['disable_restart']);self.assertEqual(c.inspect(self.root)['pending_action'],'disable_restart')
    def test_out_of_order_and_after_close_refuse(self):
        with self.control() as x:
            with self.assertRaises(ValueError):x.step('stop')
        with self.assertRaises(ValueError):x.step('disable_restart')
        self.assertEqual(self.b.calls,[])
    def test_consumed_registry_cannot_be_rearmed(self):
        with self.control():pass
        with self.assertRaises(FileExistsError):
            with self.control():pass
        self.assertEqual(self.b.calls,[])
    def test_registry_copy_cannot_be_replayed_as_another_generation(self):
        with self.control():pass
        with tempfile.TemporaryDirectory() as tmp:
            for p in self.root.iterdir():q=Path(tmp)/p.name;q.write_bytes(p.read_bytes());q.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'registry-binding'):c.inspect(tmp)
    def test_symlink_hardlink_and_torn_log_rejected(self):
        with self.control():pass
        p=self.root/'events.jsonl';p.write_bytes(b'{')
        with self.assertRaises(ValueError):c.inspect(self.root)
        p.unlink();p.symlink_to(self.root/'claim.json')
        with self.assertRaises(OSError):c.inspect(self.root)
        p.unlink();os.link(self.root/'claim.json',p)
        with self.assertRaises(ValueError):c.inspect(self.root)
    def test_rehashed_remote_claim_rejected(self):
        with self.control() as x:x.step('disable_restart')
        p=self.root/'events.jsonl';rows=[c.parse(v) for v in p.read_bytes().splitlines()]
        rows[1]['receipt']['provider_connection_closed']=True
        rows[1]['hash']=c.digest(c.raw({k:v for k,v in rows[1].items() if k!='hash'}))
        p.write_bytes(b''.join(c.raw(r) for r in rows))
        with self.assertRaisesRegex(ValueError,'remote-claim'):c.inspect(self.root)
    def test_log_replacement_before_confirmation_retains_failure(self):
        original=self.b.mutate
        def replaced(action,cid):
            ack=original(action,cid);p=self.root/'events.jsonl';data=p.read_bytes();p.rename(self.root/'saved');p.write_bytes(data);p.chmod(0o600);return ack
        self.b.mutate=replaced
        with self.control() as x:
            with self.assertRaisesRegex(ValueError,'journal-changed'):x.step('disable_restart')
        self.assertEqual(c.inspect(self.root)['pending_action'],'disable_restart')
    def test_concurrent_lock_and_step_refuse(self):
        with self.control() as x:
            with self.assertRaises(BlockingIOError):
                with self.control():pass
            x.mutex.acquire()
            try:
                with self.assertRaisesRegex(ValueError,'concurrent-operation'):x.step('disable_restart')
            finally:x.mutex.release()
        self.assertEqual(self.b.calls,[])
    def test_fsync_failure_prevents_mutation(self):
        with self.control() as x:
            with patch.object(os,'fsync',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):x.step('disable_restart')
        self.assertEqual(self.b.calls,[])
    def test_stop_with_nonzero_exit_remains_unconfirmed(self):
        original=self.b.mutate
        def failed(action,cid):
            ack=original(action,cid)
            if action=='stop':self.b.row['exit_code']=137
            return ack
        self.b.mutate=failed
        with self.control() as x:
            x.step('disable_restart')
            with self.assertRaises(ValueError):x.step('stop')
        self.assertEqual(c.inspect(self.root)['pending_action'],'stop')

    def test_clock_regression_after_intent_prevents_confirmation(self):
        with self.control() as x:
            with patch.object(c,'now',return_value='2000-01-01T00:00:00+00:00'):
                with self.assertRaisesRegex(ValueError,'clock-regressed'):x.step('disable_restart')
        self.assertEqual(self.b.calls,[])
    def test_wrong_timezone_and_source_identity_refuse(self):
        with self.assertRaises(ValueError):c.Control(self.root,target(),'not-a-hash',self.b)
        with patch.object(c,'now',return_value='2026-11-15T09:00:00+01:00'):
            with self.assertRaisesRegex(ValueError,'timestamp-zone'):self.control()

if __name__=='__main__':unittest.main()
