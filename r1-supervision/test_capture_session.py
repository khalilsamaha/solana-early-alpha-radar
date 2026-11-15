import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import manifest_supervisor as v
import capture_session as session
r=v.r;m=v.m;p=v.p;s=p.s


class CaptureSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.registry=self.root/'registry';self.registry.mkdir(mode=0o700)
        self.paths={role:str(self.root/role) for role in s.ROLES}
        for path in self.paths.values():Path(path).mkdir(mode=0o700)
        self.config={k:None for k in m.CONFIG};self.policy={k:None for k in m.POLICY}
        self.config.update(registry_path=str(self.registry),endpoint_path=str(self.registry/'discovery.sock'),capture_path=self.paths['capture'])
        self.policy.update(raw_bytes=65536,database_bytes=262144,journal_bytes=65536,receipt_bytes=65536,
            retained_runs=1,quarantined_runs=1,headroom_bytes=1000,research_seconds=2,
            service_seconds=3,setup_seconds=3,shutdown_seconds=3,memory_bytes=512*1024**2,cpu_seconds=5,open_files=64)
        self.manifest=m.build(self.config,self.policy);self.plan=self.root/'plan';self.sha=m.freeze(self.plan,self.manifest)
        self.prepared=p.prepare(self.plan,self.sha,self.paths)
        self.assertEqual(self.prepared['outcome'],'preparation-complete-live-blocked')

    def run_session(self,mode='session-normal'):return v.run(self.plan,self.sha,mode=mode)
    def recover(self):return v.inspect(self.registry,self.sha)
    def files(self):
        return {str(f.relative_to(self.root)):f.read_bytes() for f in self.root.rglob('*') if f.is_file()}

    def test_actual_capture_and_journal_under_manifest_limits(self):
        row=self.run_session();self.assertEqual(row['outcome'],v.SUCCESS)
        proof=row['terminal']['session_evidence']
        self.assertTrue(proof['capture_thread_joined']);self.assertTrue(proof['local_upstream_closed'])
        self.assertTrue(proof['discovery_continued_after_retirement'])
        self.assertEqual(proof['research_cleanup'],'unsubscribed')
        self.assertEqual(proof['synthetic_upstream_attempts'],1)
        self.assertEqual(proof['transport'],'in-process-fixture')
        self.assertFalse(proof['peer_uid_verified']);self.assertFalse(proof['provider_connection_opened'])
        cap=session.capture.verify(session.directory(self.manifest)/'capture')
        self.assertEqual(cap['raw_rows'],4)
        self.assertEqual(row['terminal']['profile']['wall_seconds'],9)
        before=self.files()
        with patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')),\
             patch.object(s,'observe',side_effect=AssertionError('sample')),\
             patch.object(p,'write_at',side_effect=AssertionError('write')),\
             patch.object(session.capture,'verify',side_effect=AssertionError('lock')),\
             patch.object(session.measurement,'replay',side_effect=AssertionError('lock')):
            self.assertEqual(self.recover(),row)
        self.assertEqual(before,self.files())

    def test_cleanup_failure_is_retained_not_promoted_to_clean_unsubscribe(self):
        row=self.run_session('session-cleanup-failure');self.assertEqual(row['outcome'],v.SUCCESS)
        proof=row['terminal']['session_evidence']
        self.assertEqual(proof['research_cleanup'],'upstream-aborted')
        self.assertFalse(proof['discovery_continued_after_retirement'])
        self.assertEqual(self.recover(),row)
        self.assertNotIn(session.fixtures.SECRET.encode(),b''.join(self.files().values()))

    def test_operator_stop_has_closed_upstream_and_no_rearm(self):
        row=self.run_session('session-operator-stop');self.assertEqual(row['outcome'],v.SUCCESS)
        self.assertFalse(row['terminal']['session_evidence']['discovery_continued_after_retirement'])
        self.assertTrue(row['terminal']['session_evidence']['local_upstream_closed'])
        self.assertEqual(row['terminal']['session_evidence']['research_cleanup'],'upstream-aborted')
        with self.assertRaises(ValueError):self.run_session()

    def test_fresh_capacity_loss_prevents_capture(self):
        original=s.sample
        with patch.object(s,'sample',side_effect=lambda fd:{**original(fd),'available_bytes':0}),\
             patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')):
            with self.assertRaisesRegex(ValueError,'runtime-session-storage'):self.run_session()
        self.assertFalse(session.directory(self.manifest).exists())
        self.assertEqual(self.recover()['outcome'],'supervision-unresolved')
        with self.assertRaises(FileExistsError):self.run_session()

    def test_capture_preexists_cannot_resume(self):
        session.directory(self.manifest).mkdir(mode=0o700)
        row=self.run_session();self.assertEqual(row['outcome'],'worker-failed')
        self.assertTrue(row['worker_reaped']);self.assertIsNone(row['terminal'])
        self.assertEqual(self.recover(),row)

    def test_missing_duration_or_insufficient_resources_reject_before_claim(self):
        for key,value in (('research_seconds',None),('open_files',16),('memory_bytes',64*1024**2)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                session.limits(m.build(self.config,{**self.policy,key:value}))
        self.assertFalse((self.registry/v.CLAIM).exists())

    def test_artifact_change_rejects_historical_success(self):
        row=self.run_session();self.assertEqual(row['outcome'],v.SUCCESS)
        journal=session.directory(self.manifest)/'session.jsonl'
        journal.write_bytes(journal.read_bytes()+b'changed\n')
        with self.assertRaisesRegex(ValueError,'runtime-success-binding'):self.recover()

    def test_missing_storage_gate_rejects_historical_success(self):
        row=self.run_session();self.assertEqual(row['outcome'],v.SUCCESS)
        (self.registry/'supervision-storage.json').unlink()
        with self.assertRaises(FileNotFoundError):self.recover()

    def test_parent_independent_replay_failure_cannot_confirm_worker(self):
        with patch.object(session.measurement,'replay',side_effect=ValueError('private-diagnostic')):
            row=self.run_session()
        self.assertEqual(row['outcome'],'worker-failed');self.assertTrue(row['worker_reaped'])
        self.assertIsNone(row['terminal']);self.assertEqual(self.recover(),row)
        self.assertNotIn(b'private-diagnostic',b''.join(self.files().values()))

    def test_lost_terminal_preserves_capture_but_leaves_supervision_unresolved(self):
        original=p.write_at
        def write(fd,name,row):
            if name==v.RESULT:raise OSError('interrupted')
            return original(fd,name,row)
        with patch.object(p,'write_at',side_effect=write):
            with self.assertRaises(OSError):self.run_session()
        self.assertTrue((session.directory(self.manifest)/'stopped.json').exists())
        self.assertEqual(self.recover()['outcome'],'supervision-unresolved')
        self.assertIsNone(self.recover()['worker_reaped'])

    def test_storage_gate_durability_failure_prevents_spawn(self):
        original=p.write_at
        def write(fd,name,row):
            if name=='supervision-storage.json':raise OSError('durability')
            return original(fd,name,row)
        with patch.object(p,'write_at',side_effect=write),\
             patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')):
            with self.assertRaises(OSError):self.run_session()
        self.assertEqual(self.recover()['outcome'],'supervision-unresolved')
        self.assertFalse(session.directory(self.manifest).exists())

    def test_historical_inspection_preserves_missing_capture_lock(self):
        row=self.run_session();self.assertEqual(row['outcome'],v.SUCCESS)
        lock=session.directory(self.manifest)/'capture/capture.lock';lock.unlink()
        self.assertEqual(self.recover(),row)
        self.assertFalse(lock.exists())

    def test_receipt_budget_and_authority_tampering_refuse(self):
        row=self.run_session();self.assertEqual(row['outcome'],v.SUCCESS)
        reduced=m.build(self.config,{**self.policy,'receipt_bytes':1})
        # Direct assessor must refuse a manifest outside the recorded storage gate.
        with self.assertRaises(ValueError):session.expected_terminal(reduced,'session-normal')
        path=session.directory(self.manifest)/'stopped.json';stopped=m.parse(path.read_bytes())
        stopped['live_launch_authorized']=True;path.write_bytes(m.raw(stopped))
        with self.assertRaisesRegex(ValueError,'session-terminal-admission'):self.recover()


if __name__=='__main__':unittest.main()
