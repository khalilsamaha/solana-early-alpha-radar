"""Fail-closed mutation scope and process integration tests; no Docker daemon needed."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import integrated_common as common
from capture import CaptureError, canonical, digest
import lifecycle
from integrated_backend import Actor, Backend, line, reap


class MutationTests(unittest.TestCase):
    def actor(self):
        a=Actor.__new__(Actor)
        a.role='direct';a.policy='unless-stopped';a.transitions=[];a.pipe_only=False;a.stopped=False
        a.process=Mock();a.process.poll.return_value=None
        a.container=Mock();a.container.cid='a'*64
        return a

    def test_policy_update_is_exact_owned_id_and_verified_before_after(self):
        a=self.actor();a.container.identify.side_effect=[{'running':True,'restart':'unless-stopped'}, {'running':True,'restart':'no'}]
        a.container.command.return_value=(a.container.cid+'\n').encode()
        a.set_restart('no')
        a.container.command.assert_called_once_with('update','--restart=no',a.container.cid)
        self.assertEqual(a.container.identify.call_args_list, [((a.container.cid,),),((a.container.cid,),)])
        self.assertEqual(a.policy,'no');self.assertFalse(a.transitions[0]['simulated'])

    def test_wrong_ownership_prevents_policy_mutation(self):
        a=self.actor();a.container.identify.side_effect=CaptureError('unowned')
        with self.assertRaises(CaptureError): a.set_restart('no')
        a.container.command.assert_not_called()

    def test_changed_policy_or_stopped_container_prevents_update(self):
        for row in ({'running':True,'restart':'always'},{'running':False,'restart':'unless-stopped'}):
            a=self.actor();a.container.identify.return_value=row
            with self.assertRaises(CaptureError): a.set_restart('no')
            a.container.command.assert_not_called()

    def test_wrong_update_ack_or_after_state_never_confirms(self):
        for ack,after in ((b'wrong',{'running':True,'restart':'no'}), (b'a'*64,{'running':True,'restart':'unless-stopped'})):
            a=self.actor();a.container.identify.side_effect=[{'running':True,'restart':'unless-stopped'},after]
            a.container.command.return_value=ack
            with self.assertRaises(CaptureError): a.set_restart('no')
            self.assertEqual(a.transitions,[]);self.assertEqual(a.policy,'unless-stopped')

    def test_policy_allowlist_and_role(self):
        for role,policy in (('consumer','no'),('direct','always'),('direct','on-failure')):
            a=self.actor();a.role=role
            with self.assertRaises(CaptureError): a.set_restart(policy)
            a.container.command.assert_not_called()

    def test_stop_refuses_enabled_restart_or_wrong_ownership(self):
        a=self.actor()
        with self.assertRaises(CaptureError): a.stop_direct()
        a.container.command.assert_not_called()
        a.policy='no';a.container.identify.side_effect=CaptureError('unowned')
        with self.assertRaises(CaptureError): a.stop_direct()
        a.container.command.assert_not_called()

    def test_stop_ack_is_exact_id(self):
        a=self.actor();a.policy='no';a.container.identify.return_value={'restart':'no','running':True}
        a.container.command.return_value=b'other'
        with self.assertRaises(CaptureError): a.stop_direct()
        a.container.command.assert_called_once_with('stop','-t','1',a.container.cid)
        self.assertFalse(a.stopped)

    def test_container_direct_args_keep_isolation_and_fixed_script(self):
        # Exercise real create_args/staging; mock only daemon execution and attached process.
        with tempfile.TemporaryDirectory(prefix='r1-args-') as tmp:
            root=Path(tmp);control=root/'control';control.mkdir(mode=0o700)
            ipc=root/'ipc';ipc.mkdir(mode=0o700)
            a=Actor(control,'direct',ipc)
            with patch('integrated_backend.host.trusted_local_docker'), \
                 patch('container_boundary.os.getuid',return_value=1000), \
                 patch('container_boundary.os.geteuid',return_value=1000), \
                 patch('container_boundary.os.getgid',return_value=1000), \
                 patch('container_boundary.os.getegid',return_value=1000), \
                 patch.object(a.container,'command',side_effect=CaptureError('stop-before-daemon')) as command:
                with self.assertRaises(CaptureError): a.start()
            args=command.call_args.args
            self.assertIn('--network=none',args);self.assertIn('--restart=no',args)
            self.assertIn('--pull=never',args);self.assertIn('--read-only',args)
            self.assertEqual(args[-2:],('node','/r1-code/r1-service/direct_fixture.mjs'))
            self.assertEqual(sum('readonly' in x for x in args),2)
            self.assertNotIn('solana-early-alpha-radar-radar-1',args)


class ProcessTests(unittest.TestCase):
    def test_normal_and_failed_cleanup_full_process_sequence(self):
        from check_integrated import scenario
        with tempfile.TemporaryDirectory(prefix='r1-integrated-test-') as tmp:
            for name in ('normal','cleanup-failure'):
                r,j=scenario(Path(tmp),name,digest(canonical(common.pins()).encode()),[],pipe_only=True)
                self.assertEqual(lifecycle.replay(j['claim'],j['journal'].encode()),r['state'])
                self.assertEqual(r['state']['records'],16)
                a=r['adapter'];self.assertEqual(a['max_simultaneous_synthetic_owners'],1)
                self.assertTrue(a['broker_reaped']);self.assertTrue(all(x['process_reaped'] for x in a['actors']))
                self.assertTrue(a['restart_policy_simulated'])
                self.assertEqual(a['worker']['shared']['owner']['upstream_attempts'],1)
                self.assertEqual(a['worker']['capture']['messages'],4)
                self.assertTrue(a['worker']['credential_descriptor_closed'])
                self.assertFalse(a['worker']['real_credential_used'])

    def prepare(self,root):
        ipc=root/'ipc';ipc.mkdir(mode=0o700)
        backend=Backend(root,ipc,'normal',pipe_only=True)
        backend.prepare();backend.perform('disable_direct_restart','x',{})
        backend.perform('stop_direct','x',{});backend.bind()
        return backend

    def test_bound_broker_never_starts_upstream_without_peer(self):
        with tempfile.TemporaryDirectory(prefix='r1-no-peer-') as tmp:
            b=self.prepare(Path(tmp))
            try:
                with self.assertRaises(CaptureError): b.perform('start_owner','x',{})
                self.assertEqual(b.protocol,[{'event':'bound','upstream_attempts':0,'credential_descriptor_closed':True}])
                self.assertFalse(b.active)
            finally: b.close()

    def test_broker_refuses_out_of_order_start_and_is_reaped(self):
        with tempfile.TemporaryDirectory(prefix='r1-order-') as tmp:
            b=self.prepare(Path(tmp))
            try:
                with self.assertRaises(CaptureError): b.command('start')
                b.broker.wait(timeout=2);self.assertNotEqual(b.broker.returncode,0)
                self.assertFalse((Path(tmp)/'broker/capture').exists())
            finally: b.close()

    def test_consumer_death_prevents_upstream_start_and_rollback(self):
        with tempfile.TemporaryDirectory(prefix='r1-dead-consumer-') as tmp:
            b=self.prepare(Path(tmp))
            try:
                b.perform('start_consumer','x',{})
                reap(b.consumer.process)
                with self.assertRaises(CaptureError): b.perform('start_owner','x',{})
                with self.assertRaises(CaptureError): b.perform('restore_direct','x',{})
                self.assertEqual(b.restore_calls,0);self.assertFalse(b.active)
            finally: b.close()

    def test_uncertain_shared_stop_cannot_restore_direct(self):
        with tempfile.TemporaryDirectory(prefix='r1-uncertain-') as tmp:
            b=self.prepare(Path(tmp))
            try:
                b.perform('start_consumer','x',{});b.perform('start_owner','x',{})
                reap(b.broker)
                with self.assertRaises(CaptureError): b.perform('stop_shared','x',{})
                with self.assertRaises(CaptureError): b.perform('restore_direct','x',{})
                self.assertEqual(b.restore_calls,0)
            finally: b.close()

    def test_worker_profile_enforces_resources_and_no_network_or_children(self):
        code="""import os,sys,resource,socket,subprocess
sys.path.insert(0,sys.argv[1])
from broker_fixture import bootstrap
bootstrap(os.getppid())
assert resource.getrlimit(resource.RLIMIT_CORE)==(0,0)
assert resource.getrlimit(resource.RLIMIT_CPU)==(10,10)
assert resource.getrlimit(resource.RLIMIT_NOFILE)==(32,32)
assert resource.getrlimit(resource.RLIMIT_AS)==(256*1024**2,256*1024**2)
for operation in (lambda:socket.socket(socket.AF_INET),lambda:socket.socket(socket.AF_INET6),lambda:socket.getaddrinfo('localhost',80),lambda:subprocess.Popen(['/bin/true'])):
    try:operation()
    except RuntimeError:pass
    else:raise AssertionError('guard missing')
print('guarded')
"""
        result=subprocess.run([sys.executable,'-E','-s','-B','-c',code,str(common.ROOT)],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=common.ENVIRONMENT,timeout=3)
        self.assertEqual(result.returncode,0);self.assertEqual(result.stdout,b'guarded\n')

    def test_terminated_real_broker_leaves_pending_journal_and_no_restore(self):
        with tempfile.TemporaryDirectory(prefix='r1-interrupted-') as tmp:
            root=Path(tmp);ipc=root/'ipc';ipc.mkdir(mode=0o700)
            registry=root/'registry';registry.mkdir(mode=0o700)
            journal=root/'journal';journal.mkdir(mode=0o700)
            b=Backend(root,ipc,'normal',pipe_only=True)
            try:
                with lifecycle.Lifecycle(registry,journal,digest(b'interrupted'),digest(b'source')) as c:
                    b.prepare()
                    for action in lifecycle.ACTIONS[:5]: c.step(action,b)
                    reap(b.broker)
                    with self.assertRaises(CaptureError): c.step('retire_research',b)
                    calls=len(b.actions)
                    with self.assertRaises(CaptureError): c.step('retire_research',b)
                    self.assertEqual(len(b.actions),calls)
                state=lifecycle.inspect(registry,journal)
                self.assertEqual(state['pending_action'],'retire_research')
                self.assertTrue(state['reconciliation_required'])
                self.assertFalse(state['automatic_resume_allowed'])
                self.assertEqual(b.restore_calls,0)
            finally: b.close()

    def test_output_bound_and_timeout(self):
        for code,seconds in (("import os;os.write(1,b'x'*4097)",1),("import time;time.sleep(2)",0.02)):
            p=subprocess.Popen([sys.executable,'-E','-s','-B','-c',code],stdout=subprocess.PIPE,
                stdin=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=common.ENVIRONMENT,start_new_session=True)
            try:
                with self.assertRaises(CaptureError): line(p,seconds)
            finally: reap(p)


if __name__=='__main__': unittest.main()
