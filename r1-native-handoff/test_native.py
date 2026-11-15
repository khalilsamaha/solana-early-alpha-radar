import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import native as n
from test_control import target
c=n.c

class NativeTests(unittest.TestCase):
    def test_consumer_requires_exact_command_mount_and_isolation(self):
        registry=Path('/tmp/private-test');row=target();row.update(restart='no',cmd=['--input-type=module','-e',n.CONSUMER,'--','--unix','/r1-ipc/discovery.sock'],
            mounts=[{'Type':'bind','Source':str(registry),'Destination':'/r1-ipc','RW':False}])
        n.consumer_isolation(row,row['label'],registry)
        for key,value in [('cmd',['wrong']),('restart','unless-stopped'),('network','host'),('image','sha256:'+'f'*64),('pid','12')]:
            with self.subTest(key=key),self.assertRaises(ValueError):n.consumer_isolation({**row,key:value},row['label'],registry)
        for key,value in [('Source','/wrong'),('Destination','/app'),('RW',True),('Type','volume')]:
            wrong=copy.deepcopy(row);wrong['mounts'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):n.consumer_isolation(wrong,row['label'],registry)
    def test_line_reader_bounds_timeout_and_output(self):
        for code,seconds in [('import time;time.sleep(5)',.02),('print("x"*5000)',2)]:
            p=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,stdin=subprocess.DEVNULL,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                with self.assertRaises(ValueError):n.line(p,seconds)
            finally:n.reap(p,terminate=True)
    def test_process_identity_binds_current_pid_parent_start(self):
        a=n.proc_identity(os.getpid());b=n.proc_identity(os.getpid())
        self.assertEqual(a,b);self.assertEqual(a['ppid'],os.getppid());self.assertGreater(a['start_ticks'],0)
    def test_extra_terminal_output_is_not_accepted(self):
        p=subprocess.Popen([sys.executable,'-c','print("unexpected")'],stdout=subprocess.PIPE,stdin=subprocess.DEVNULL,start_new_session=True)
        with self.assertRaises(ValueError):n.reap(p)
    def test_foreign_actor_never_removed(self):
        a=n.Actor(['docker'],'direct',Path('/tmp/no'),False);a.attempted=True;a.cid='a'*64
        with patch.object(n.image,'bounded',return_value=c.raw({**target(),'label':'f'*32})) as command:
            with self.assertRaises(ValueError):a.dispose()
        self.assertEqual(command.call_count,1);self.assertFalse(a.removed)
    def test_lost_create_cleanup_requires_matching_owned_identity(self):
        a=n.Actor(['docker'],'direct',Path('/tmp/no'),False);a.attempted=True
        row={**target(),'label':a.token}
        with patch.object(n.image,'bounded',side_effect=[c.raw(row),(row['id']+'\n').encode()]) as command:a.dispose()
        self.assertTrue(a.removed);self.assertEqual(command.call_args_list[0].args[0][-1],a.name)
    def test_bad_removal_ack_preserves_uncertainty(self):
        a=n.Actor(['docker'],'direct',Path('/tmp/no'),False);a.attempted=True;a.cid='a'*64
        with patch.object(n.image,'bounded',side_effect=[c.raw({**target(),'label':a.token}),b'wrong\n']):
            with self.assertRaises(ValueError):a.dispose()
        self.assertFalse(a.removed)

    def test_stopped_generation_requires_original_start_and_clean_exit(self):
        a=n.Actor([], 'direct',Path('/tmp/no'));a.initial=target()
        stopped={**target(),'running':False,'pid':0,'exit_code':0,'finished':'2026-11-15T09:00:00Z'}
        a.expect_stopped(stopped)
        for key,value in [('started','2026-11-15T08:59:00Z'),('id','f'*64),('pid',1),('running',True),('exit_code',137)]:
            with self.subTest(key=key),self.assertRaises(ValueError):a.expect_stopped({**stopped,key:value})
    def test_peer_process_or_endpoint_replacement_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'discovery.sock';p.write_bytes(b'fixture')
            backend=n.Backend(root,root,[],'unsubscribed');st=p.stat();backend.socket_identity=(st.st_dev,st.st_ino)
            backend.peer={'pid':os.getpid(),'process_identity':n.proc_identity(os.getpid())}
            backend.verify_peer()
            with patch.object(n,'proc_identity',return_value={'pid':os.getpid(),'ppid':0,'start_ticks':0}):
                with self.assertRaises(ValueError):backend.verify_peer()
            p.rename(root/'old');p.write_bytes(b'changed')
            with self.assertRaises(ValueError):backend.verify_peer()
    def test_adapter_cannot_dispatch_without_retained_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);backend=n.Backend(root,root,[],'unsubscribed')
            with patch.object(backend,'check_plan'),patch.object(n.subprocess,'Popen') as spawn:
                with self.assertRaises(OSError):backend.perform('bind_endpoint','a'*64,{})
                spawn.assert_not_called()
    def test_cleanup_diagnostics_are_not_discarded(self):
        p=subprocess.Popen([sys.executable,'-c','print("ResourceWarning: fixture")'],stdout=subprocess.PIPE,stdin=subprocess.DEVNULL,start_new_session=True)
        p.wait(timeout=3)
        with self.assertRaisesRegex(ValueError,'child-diagnostic'):n.reap(p,terminate=True)

if __name__=='__main__':unittest.main()
