import common as c
import copy
import os
import signal
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import envelope as e
import pipeline as p
import profile
import lifecycle
from test_lifecycle import Model


class ProfileAndJournalTests(unittest.TestCase):
    def test_finite_long_profile_does_not_grant_authority(self):
        r=profile.make(172800);self.assertEqual(r['wall_seconds'],172825)
        self.assertEqual(profile.validate(r),r);self.assertFalse(r['live_profile_approved'])
    def test_unbounded_or_forged_profile_rejected(self):
        for n in (0,-1,172801,True,1.0,None):
            with self.assertRaises(c.CaptureError):profile.make(n)
        r=profile.make(2);r['live_profile_approved']=True
        with self.assertRaises(c.CaptureError):profile.validate(r)
    def test_worker_alarm_is_enforced_and_process_reaped(self):
        with subprocess.Popen([sys.executable,'-E','-s','-B',str(c.ROOT/'profile_probe.py'),str(os.getpid()),'alarm'],
                env=c.ENVIRONMENT,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL) as child:
            output,_=child.communicate(timeout=6)
            self.assertEqual(output,b'armed\n');self.assertEqual(child.returncode,-signal.SIGALRM)
    def test_worker_cannot_open_internet_dns_or_children(self):
        result=subprocess.run([sys.executable,'-E','-s','-B',str(c.ROOT/'profile_probe.py'),str(os.getpid()),'guards'],
            env=c.ENVIRONMENT,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=6)
        self.assertEqual(result.returncode,0)
        self.assertEqual(c.strict_json(result.stdout),{'blocked':['internet','dns','child']})
    def test_all_eight_lost_confirmations_block_reuse_and_restore(self):
        for index,action in enumerate(lifecycle.ACTIONS):
            with self.subTest(action=action),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);reg=root/'r';out=root/'o';reg.mkdir(mode=0o700);out.mkdir(mode=0o700)
                model=Model()
                with lifecycle.Lifecycle(reg,out,'a'*64,'b'*64) as journal:
                    for earlier in lifecycle.ACTIONS[:index]:journal.step(earlier,model)
                    original=journal._append
                    def append(kind,*args):
                        if kind=='confirmed':raise OSError('synthetic lost confirmation')
                        return original(kind,*args)
                    with patch.object(journal,'_append',side_effect=append):
                        with self.assertRaises(c.CaptureError):journal.step(action,model)
                    calls=list(model.calls)
                    with self.assertRaises(c.CaptureError):journal.step(action,model)
                    self.assertEqual(calls,model.calls)
                state=lifecycle.inspect(reg,out)
                self.assertEqual(state['pending_action'],action)
                self.assertTrue(state['reconciliation_required']);self.assertFalse(state['automatic_resume_allowed'])


class CombinedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.umask(0o077);cls.tmp=tempfile.TemporaryDirectory(prefix='r1-combined-unit-');cls.root=Path(cls.tmp.name)
        cls.registry=cls.root/'registry';cls.registry.mkdir(mode=0o700)
        cls.output=cls.root/'normal';cls.result=p.run(cls.registry,cls.output,development=True)
        cls.archive=cls.root/'normal-envelope/evidence.zip';cls.raw=cls.archive.read_bytes()
        cls.sha=c.digest(cls.raw);cls.contents,_=e.verify(cls.raw,cls.sha)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='r1-combined-case-');self.addCleanup(self.t.cleanup);self.path=Path(self.t.name)
    def test_discovery_continues_after_clean_retirement(self):
        retired=e.row(self.contents['retired.json']);stopped=e.row(self.contents['stopped.json'])
        self.assertTrue(retired['discovery_continues']);self.assertTrue(retired['research_cannot_rearm'])
        self.assertEqual(stopped['discovery_frames'],3)
        self.assertGreater(stopped['discovery_frames'],retired['discovery_frames'])
        self.assertEqual(stopped['owner']['research_attachments'],1)
        self.assertEqual(stopped['owner']['upstream_attempts'],1)
    def test_actual_node_observes_post_retirement_creation(self):
        consumer=self.result['cleanup']['actors'][1]['result']
        self.assertEqual(consumer['creations'],2);self.assertEqual(consumer['tokens'],3)
        self.assertEqual(consumer['upstream_connections_opened'],0)
    def test_explicit_rollback_only_after_shared_shutdown(self):
        r=self.result['cleanup'];self.assertEqual(r['max_simultaneous_synthetic_owners'],1)
        self.assertEqual(r['direct_restore_calls'],1)
        self.assertLess(r['actions'].index('stop_shared'),r['actions'].index('restore_direct'))
        self.assertTrue(all(a['process_reaped'] for a in r['actors']))
    def test_registry_cannot_be_bypassed_by_new_output(self):
        with self.assertRaises(c.CaptureError):p.run(self.registry,self.root/'other',development=True)
        self.assertFalse((self.root/'other').exists())
    def test_readonly_recovery_preserves_all_bytes(self):
        before={str(f):f.read_bytes() for f in self.output.rglob('*') if f.is_file()}
        result=p.inspect(self.registry,self.output)
        self.assertFalse(result['reconciliation_required']);self.assertFalse(result['automatic_resume_allowed'])
        self.assertEqual(before,{str(f):f.read_bytes() for f in self.output.rglob('*') if f.is_file()})
    def test_missing_completion_does_not_claim_finalization(self):
        old=self.output/'completion.json';hidden=self.output/'retained-completion.json';old.rename(hidden)
        try:self.assertTrue(p.inspect(self.registry,self.output)['reconciliation_required'])
        finally:hidden.rename(old)
    def test_external_checksum_required(self):
        with self.assertRaises(c.CaptureError):e.verify(self.raw,'0'*64)
    def test_trailing_data_or_invalid_zip_refused(self):
        for raw in (self.raw+b'X',b'PK\x03\x04'+b'x'*40):
            with self.assertRaises(c.CaptureError):e.verify(raw,c.digest(raw))
    def test_rehashed_false_retirement_is_rejected(self):
        data=dict(self.contents);r=e.row(data['retired.json']);r['research_cannot_rearm']=False;data['retired.json']=c.raw(r)
        with self.assertRaises(c.CaptureError):e.assess(data)
    def test_rehashed_different_manifest_request_rejected(self):
        data=dict(self.contents);r=e.row(data['worker-manifest.json']);r['request_sha256']='0'*64;data['worker-manifest.json']=c.raw(r)
        with self.assertRaises(c.CaptureError):e.assess(data)
    def test_rehashed_foreign_actor_receipt_is_rejected(self):
        data=dict(self.contents);r=e.row(data['cleanup.json']);r['actors'][0]['identity']='f'*32
        data['cleanup.json']=c.raw(r)
        with self.assertRaises(c.CaptureError):e.assess(data)
    def test_claimed_active_actor_cannot_be_preserved(self):
        data=dict(self.contents);r=e.row(data['cleanup.json']);r['actors'][0]['process_reaped']=False;data['cleanup.json']=c.raw(r)
        with self.assertRaises(c.CaptureError):e.assess(data)
    def test_rollback_database_is_quarantined_without_repair(self):
        data=dict(self.contents);data['capture-journal']=b'retained rollback bytes'
        # No terminal receipts: interrupted evidence must retain rollback bytes.
        for key in ('worker.json','retired.json','stopped.json'):data.pop(key)
        result=e.assess(data)
        self.assertEqual(result['classification'],'quarantined-incomplete-evidence')
        self.assertIn('sqlite-rollback-evidence-present',result['reasons'])
        self.assertEqual(data['capture-journal'],b'retained rollback bytes')
    def test_restore_does_not_overwrite(self):
        target=self.path/'restore';target.mkdir(mode=0o700)
        with self.assertRaises(c.CaptureError):e.restore(self.archive,self.sha,target)
    def test_low_space_prevents_remote_call(self):
        remote=p.MemoryRemote()
        with patch.object(e.shutil,'disk_usage',return_value=type('D',(),{'free':0})()):
            with self.assertRaises(c.CaptureError):e.transfer(self.archive,self.sha,self.path/'attempt',remote)
        self.assertEqual(remote.calls,[])
    def test_transfer_uncertain_upload_consumes_attempt(self):
        class Broken(p.MemoryRemote):
            def put(self,key,raw):super().put(key,raw);raise OSError('lost response')
        remote=Broken();attempt=self.path/'attempt'
        with self.assertRaises(OSError):e.transfer(self.archive,self.sha,attempt,remote)
        self.assertTrue((attempt/'intent.json').exists());self.assertFalse((attempt/'completion.json').exists())
        with self.assertRaises(c.CaptureError):e.transfer(self.archive,self.sha,attempt,remote)
        self.assertEqual(remote.calls,['put'])
    def test_corrupted_download_cannot_complete(self):
        class Broken(p.MemoryRemote):
            def get(self,key,cap):return super().get(key,cap)[:-1]
        attempt=self.path/'attempt'
        with self.assertRaises(c.CaptureError):e.transfer(self.archive,self.sha,attempt,Broken())
        self.assertTrue((attempt/'upload.json').exists());self.assertFalse((attempt/'completion.json').exists())
    def test_failed_restore_cannot_complete(self):
        attempt=self.path/'attempt'
        with patch.object(e,'restore',side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):e.transfer(self.archive,self.sha,attempt,p.MemoryRemote())
        self.assertTrue((attempt/'download.zip').exists());self.assertFalse((attempt/'completion.json').exists())
    def test_failed_completion_retains_download_and_no_retry(self):
        original=c.exclusive_file;attempt=self.path/'attempt'
        def write(path,data):
            if path.name=='completion.json':raise OSError('synthetic')
            return original(path,data)
        with patch.object(c,'exclusive_file',side_effect=write):
            with self.assertRaises(OSError):e.transfer(self.archive,self.sha,attempt,p.MemoryRemote())
        self.assertTrue((attempt/'download.zip').exists());self.assertFalse((attempt/'completion.json').exists())
    def test_successful_transfer_still_denies_retention_and_live(self):
        result=e.transfer(self.archive,self.sha,self.path/'attempt',p.MemoryRemote())
        self.assertEqual(result['assessment']['classification'],'complete-replayed-evidence')
        self.assertFalse(result['retention_verified']);self.assertFalse(result['live_launch_authorized'])
    def test_active_source_lock_refuses_export(self):
        from capture import lock
        fd=lock(self.output/'runtime/broker/control/capture')
        try:
            with self.assertRaises(c.CaptureError):e.export(self.output,self.path/'export')
        finally:os.close(fd)
