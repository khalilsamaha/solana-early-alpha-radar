import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

import boundary as b
import credential as c
from capture import CaptureError, exclusive_file
from provider_wire import secret_variants


def fixture(root):
    p=root/'credential'; value=('R1-SYNTHETIC-'+uuid.uuid4().hex).encode()
    exclusive_file(p,value)
    return p,value



class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='r1-credential-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path,self.value=fixture(self.root)

    def test_private_input_and_sealed_descriptor_roundtrip_closes_handle(self):
        fd=c.load_descriptor(self.path)
        self.assertFalse(os.get_inheritable(fd))
        self.assertEqual(c.consume(fd),self.value.decode())
        with self.assertRaises(OSError):os.fstat(fd)
        self.assertEqual(self.path.read_bytes(),self.value)

    def test_kernel_rejects_write_resize_and_more_seals(self):
        fd=c.sealed(self.value)
        try:
            for operation in (lambda:os.write(fd,b'x'),lambda:os.ftruncate(fd,0),
                              lambda:os.ftruncate(fd,5000),lambda:fcntl.fcntl(fd,c.ADD_SEALS,c.SEALS)):
                with self.assertRaises(OSError):operation()
        finally:os.close(fd)

    def test_unsealed_anonymous_file_is_rejected_and_closed(self):
        fd=os.memfd_create('r1-test',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
        os.fchmod(fd,0o600);os.write(fd,self.value)
        with self.assertRaises(CaptureError):c.consume(fd)
        with self.assertRaises(OSError):os.fstat(fd)

    def test_regular_file_descriptor_is_not_a_handoff(self):
        fd=os.open(self.path,os.O_RDONLY)
        with self.assertRaises(CaptureError):c.consume(fd)
        with self.assertRaises(OSError):os.fstat(fd)

    def test_public_or_executable_file_rejected(self):
        for mode in (0o644,0o660,0o700):
            self.path.chmod(mode)
            with self.assertRaises(CaptureError):c.read_private(self.path)

    def test_nonprivate_parent_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(CaptureError):c.read_private(self.path)

    def test_symlink_file_and_directory_rejected(self):
        link=self.root/'link';link.symlink_to(self.path)
        with self.assertRaises(CaptureError):c.read_private(link)
        private=self.root/'private';private.mkdir(mode=0o700)
        target,_=fixture(private);alias=self.root/'alias';alias.symlink_to(private)
        with self.assertRaises(CaptureError):c.read_private(alias/target.name)

    def test_hard_link_and_fifo_rejected(self):
        os.link(self.path,self.root/'second')
        with self.assertRaises(CaptureError):c.read_private(self.path)
        fifo=self.root/'fifo';os.mkfifo(fifo,0o600)
        with self.assertRaises(CaptureError):c.read_private(fifo)

    def test_invalid_bounds_whitespace_and_unicode_rejected(self):
        for raw in (b'',b'a'*15,b'a'*4097,self.value+b'\n',b'\xff'*20,b'a b'+b'x'*20):
            self.path.write_bytes(raw)
            with self.subTest(length=len(raw)),self.assertRaises(CaptureError):c.read_private(self.path)

    def test_valid_printable_boundary_and_encoded_variants(self):
        for raw in (b'a'*16,b'a'*4096,b'"%/?'+b'x'*20):
            fd=c.sealed(raw);self.assertEqual(c.consume(fd),raw.decode())

    def test_relative_dotdot_and_setuid_context_rejected(self):
        with self.assertRaises(CaptureError):c.read_private(Path('credential'))
        with self.assertRaises(CaptureError):c.read_private(str(self.root/'..'/self.root.name/'credential'))
        with patch.object(c.os,'geteuid',return_value=os.getuid()+1):
            with self.assertRaises(CaptureError):c.read_private(self.path)

    def test_replaced_file_detected_after_open(self):
        real_read=c.os.read
        def read(fd,n):
            raw=real_read(fd,n);self.path.unlink();self.path.write_bytes(self.value);self.path.chmod(0o600)
            return raw
        with patch.object(c.os,'read',side_effect=read):
            with self.assertRaises(CaptureError):c.read_private(self.path)

    def test_credential_exception_is_fixed_and_sanitized(self):
        self.path.write_bytes(self.value+b'\n')
        with self.assertRaisesRegex(CaptureError,'^credential-load-refused$'):c.read_private(self.path)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='r1-runtime-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path,self.value=fixture(self.root)
        self.run=self.root/'run';self.run.mkdir(mode=0o700)

    def test_normal_real_worker_replays_and_keeps_discovery_after_retirement(self):
        r=b.run(self.run,self.path)
        self.assertEqual(r['outcome'],'worker-exited');self.assertTrue(r['worker_reaped'])
        receipt=json.loads((self.run/'worker-result.json').read_bytes())
        self.assertTrue(receipt['complete_session_replayed'])
        self.assertEqual(receipt['shared']['discovery_frames'],3)
        self.assertTrue(receipt['shared']['owner']['cleanup']['discovery_continues'])
        for p in self.run.rglob('*'):
            if p.is_file():
                for v in secret_variants(self.value.decode()):self.assertNotIn(v,p.read_bytes())

    def test_uncertain_cleanup_aborts_shared_owner_and_replays_failure(self):
        r=b.run(self.run,self.path,'cleanup-failure');self.assertEqual(r['outcome'],'worker-exited')
        receipt=json.loads((self.run/'worker-result.json').read_bytes())
        self.assertEqual(receipt['measurement']['session_outcome'],'transport-cleanup-failed')
        self.assertEqual(receipt['shared']['owner']['cleanup']['outcome'],'upstream-aborted')

    def test_tainted_child_output_discarded_and_failure_not_accepted(self):
        r=b.run(self.run,self.path,'credential-echo');self.assertEqual(r['outcome'],'worker-failed')
        self.assertTrue(r['worker_reaped']);self.assertFalse((self.run/'worker-result.json').exists())
        self.assertNotIn(self.value,(self.run/'supervisor.json').read_bytes())

    def test_stall_forced_kill_and_reap_without_restart(self):
        r=b.run(self.run,self.path,'stall',wall_seconds=2)
        self.assertTrue((self.run/'ready.json').exists())
        self.assertEqual(r['outcome'],'worker-deadline');self.assertTrue(r['forced_kill_needed'])
        self.assertTrue(r['worker_reaped']);self.assertEqual(r['workers_started'],1)
        self.assertFalse(r['automatic_restart'])

    def test_attempt_cannot_be_reused_after_failure(self):
        b.run(self.run,self.path,'credential-echo')
        before=(self.run/'attempt.json').read_bytes()
        with patch.object(b.subprocess,'Popen') as launch:
            with self.assertRaises(FileExistsError):b.run(self.run,self.path)
            launch.assert_not_called()
        self.assertEqual((self.run/'attempt.json').read_bytes(),before)

    def test_bad_credential_burns_attempt_without_spawning(self):
        self.path.chmod(0o644)
        with patch.object(b.subprocess,'Popen') as launch:
            r=b.run(self.run,self.path);launch.assert_not_called()
        self.assertEqual(r['workers_started'],0);self.assertTrue((self.run/'attempt.json').exists())

    def test_child_argv_env_and_pass_fds_do_not_contain_credential(self):
        original=b.subprocess.Popen
        calls=[]
        def launch(*args,**kwargs):
            calls.append((args,kwargs));return original(*args,**kwargs)
        with patch.dict(os.environ,{'PUMPPORTAL_API_KEY':'SYNTHETIC-KEY','HTTPS_PROXY':'fixture'}), \
             patch.object(b.subprocess,'Popen',side_effect=launch):
            r=b.run(self.run,self.path,'credential-echo')
        self.assertEqual(r['outcome'],'worker-failed')
        args,kw=calls[0]
        self.assertNotIn(self.value.decode(),repr(args)+repr(kw));self.assertNotIn(str(self.path),repr(args))
        self.assertEqual(kw['env'],b.ENVIRONMENT);self.assertEqual(len(kw['pass_fds']),1)
        with self.assertRaises(OSError):os.fstat(kw['pass_fds'][0])
        self.assertIs(kw['stdout'],subprocess.DEVNULL);self.assertIs(kw['stderr'],subprocess.DEVNULL)

    def test_spawn_failure_closes_descriptor_and_preserves_attempt(self):
        saved=[]
        def fail(*args,**kw):saved.extend(kw['pass_fds']);raise OSError('tainted')
        with patch.object(b.subprocess,'Popen',side_effect=fail):r=b.run(self.run,self.path)
        self.assertEqual(r['outcome'],'worker-failed');self.assertEqual(r['workers_started'],0)
        with self.assertRaises(OSError):os.fstat(saved[0])

    def test_parent_death_kills_bootstrapped_worker(self):
        # A lifeline pipe provides positive death evidence even where /proc PID
        # views differ from subprocess IDs. Before the kill it must remain open.
        import selectors
        read_fd,write_fd=os.pipe()
        code="""import sys,os,signal,subprocess,json
sys.path[:0]=sys.argv[1:3]
import boundary,credential
from capture import canonical,exclusive_file
from pathlib import Path
p=Path(sys.argv[3]);life=int(sys.argv[5])
manifest={'schema_version':1,'mode':'offline-runtime','scenario':'stall','parent_pid':os.getpid(),'source_sha256':boundary.pins()}
exclusive_file(p/'attempt.json',(canonical(manifest)+'\\n').encode())
fd=credential.load_descriptor(sys.argv[4])
child=subprocess.Popen([sys.executable,'-E','-s','-B','-W','error::ResourceWarning',str(boundary.ROOT/'worker_fixture.py'),str(p),str(os.getpid()),str(fd),'stall'],env=boundary.ENVIRONMENT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,pass_fds=(fd,life),start_new_session=True)
os.close(fd);os.close(life)
signal.pause()
"""
        parent=subprocess.Popen([sys.executable,'-E','-s','-B','-c',code,str(b.ROOT),str(b.REPO/'r1-data'),
            str(self.run),str(self.path),str(write_fd)],env=b.ENVIRONMENT,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,
            pass_fds=(write_fd,),start_new_session=True)
        os.close(write_fd)
        try:
            until=time.monotonic()+4
            while not (self.run/'ready.json').exists():
                if parent.poll() is not None or time.monotonic()>=until:self.fail('worker not ready')
                time.sleep(0.01)
            with selectors.DefaultSelector() as sel:
                sel.register(read_fd,selectors.EVENT_READ)
                self.assertFalse(sel.select(0))
                parent.kill();parent.wait(timeout=2)
                self.assertTrue(sel.select(2),'worker lifeline did not close after parent death')
                self.assertEqual(os.read(read_fd,1),b'')
        finally:
            os.close(read_fd)
            if parent.poll() is None:parent.kill();parent.wait(timeout=2)

    def test_supervisor_sigterm_unwinds_forced_worker_cleanup(self):
        code='import sys;sys.path[:0]=sys.argv[1:3];import boundary;boundary.run(sys.argv[3],sys.argv[4],"stall")'
        parent=subprocess.Popen([sys.executable,'-E','-s','-B','-c',code,str(b.ROOT),str(b.REPO/'r1-data'),
            str(self.run),str(self.path)],env=b.ENVIRONMENT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,start_new_session=True)
        try:
            until=time.monotonic()+4
            while not (self.run/'ready.json').exists():
                if parent.poll() is not None or time.monotonic()>=until:self.fail('worker not ready')
                time.sleep(0.01)
            parent.terminate();parent.wait(timeout=3)
            receipt=json.loads((self.run/'supervisor.json').read_bytes())
            self.assertEqual(receipt['outcome'],'worker-interrupted')
            self.assertTrue(receipt['worker_reaped']);self.assertTrue(receipt['forced_kill_needed'])
        finally:
            if parent.poll() is None:parent.kill();parent.wait(timeout=2)
