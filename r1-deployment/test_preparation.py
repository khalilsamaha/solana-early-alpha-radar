import copy
import fcntl
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import manifest as m
import storage as s
import preparation as p
from test_manifest import inputs


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.registry=self.root/'registry';self.registry.mkdir(mode=0o700)
        self.paths={role:str(self.root/role) for role in s.ROLES}
        for path in self.paths.values():Path(path).mkdir(mode=0o700)
        config,policy=inputs()
        config.update(registry_path=str(self.registry),endpoint_path=str(self.registry/'discovery.sock'),capture_path=self.paths['capture'])
        policy.update(raw_bytes=100,database_bytes=200,journal_bytes=300,receipt_bytes=400,
                      retained_runs=1,quarantined_runs=1,headroom_bytes=1000)
        self.manifest=m.build(config,policy);self.plan=self.root/'plan';self.sha=m.freeze(self.plan,self.manifest)

    def run_preparation(self):return p.prepare(self.plan,self.sha,self.paths)
    def recover(self):return p.inspect(self.registry,self.sha)
    def files(self):return {v.name:v.read_bytes() for v in self.registry.iterdir() if v.is_file()}

    def test_complete_chain_and_read_only_recovery(self):
        result=self.run_preparation();before=self.files()
        with patch.object(s,'observe',side_effect=AssertionError('no fresh observation')):
            self.assertEqual(self.recover(),result)
        self.assertEqual(self.files(),before)
        self.assertFalse(result['activation_authorized'])
        self.assertEqual(result['observation']['remaining_blockers'],self.manifest['blockers'])

    def test_claim_durable_before_observation_and_no_rearm(self):
        original=s.observe
        def observe(*args):
            self.assertTrue((self.registry/p.CLAIM).is_file())
            self.assertEqual(self.recover()['outcome'],'preparation-unresolved')
            return original(*args)
        with patch.object(s,'observe',side_effect=observe):self.run_preparation()
        other=self.root/'other-plan';m.freeze(other,self.manifest)
        with patch.object(s,'observe',side_effect=AssertionError('retry')):
            with self.assertRaises(ValueError):p.prepare(other,self.sha,self.paths)

    def test_observer_failure_retains_no_exception_text(self):
        with patch.object(s,'observe',side_effect=OSError('credential-like-private-detail')):
            result=self.run_preparation()
        self.assertEqual(result['outcome'],'preparation-failed-reconciliation-required')
        self.assertEqual(self.recover(),result)
        self.assertNotIn(b'credential-like',b''.join(self.files().values()))

    def test_result_write_failure_remains_unresolved_and_consumed(self):
        original=p.write_at
        def write(fd,name,value):
            if name==p.RESULT:raise OSError('interrupted')
            return original(fd,name,value)
        with patch.object(p,'write_at',side_effect=write):
            with self.assertRaises(OSError):self.run_preparation()
        self.assertEqual(self.recover()['outcome'],'preparation-unresolved')
        with patch.object(s,'observe',side_effect=AssertionError('retry')):
            with self.assertRaises(FileExistsError):self.run_preparation()

    def test_claim_fsync_failure_never_observes(self):
        with patch.object(p.os,'fsync',side_effect=OSError('durability')),patch.object(s,'observe',side_effect=AssertionError('observe')):
            with self.assertRaises(OSError):self.run_preparation()
        self.assertTrue((self.registry/p.CLAIM).exists())
        with self.assertRaises(FileExistsError):self.run_preparation()

    def test_lock_concurrency_refuses_before_claim(self):
        with open(self.registry/p.LOCK,'wb') as lock:
            os.chmod(self.registry/p.LOCK,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.run_preparation()
        self.assertFalse((self.registry/p.CLAIM).exists())

    def test_registry_replacement_cannot_confirm(self):
        original=s.observe
        def observe(*args):
            row=original(*args);self.registry.rename(self.root/'old');self.registry.mkdir(mode=0o700);return row
        with patch.object(s,'observe',side_effect=observe):
            with self.assertRaisesRegex(ValueError,'preparation-registry-replaced'):self.run_preparation()
        self.assertTrue((self.root/'old'/p.CLAIM).exists())
        self.assertFalse((self.registry/p.RESULT).exists())
        self.assertFalse((self.root/'old'/p.RESULT).exists())

    def test_copied_registry_refuses(self):
        self.run_preparation();other=self.root/'copied';shutil.copytree(self.registry,other)
        with self.assertRaisesRegex(ValueError,'preparation-registry-binding'):p.inspect(other,self.sha)

    def test_capacity_replay_rejects_forged_success(self):
        original=s.sample
        def sample(fd):return {**original(fd),'available_bytes':0}
        with patch.object(s,'sample',side_effect=sample):row=self.run_preparation()
        self.assertEqual(row['outcome'],'preparation-insufficient-live-blocked');self.assertEqual(self.recover(),row)
        row['outcome']='preparation-complete-live-blocked'
        (self.registry/p.RESULT).write_bytes(m.raw(row))
        with self.assertRaisesRegex(ValueError,'preparation-outcome'):self.recover()

    def test_inconsistent_observer_result_fails_completion(self):
        original=s.observe
        def observe(*args):
            row=original(*args);row['required_bytes']=0;return row
        with patch.object(s,'observe',side_effect=observe):row=self.run_preparation()
        self.assertEqual(row['outcome'],'preparation-failed-reconciliation-required')
        self.assertEqual(self.recover(),row)

    def test_observation_authority_and_metadata_tampering_refuse(self):
        row=self.run_preparation()
        for mutate in (lambda r:r['observation'].update(activation_authorized=True),
                       lambda r:r['observation']['before']['capture'].update(mode=0o777),
                       lambda r:r.update(activation_authorized=0),
                       lambda r:r.update(schema=True),
                       lambda r:r.update(claim_sha256='0'*64)):
            changed=copy.deepcopy(row);mutate(changed);(self.registry/p.RESULT).write_bytes(m.raw(changed))
            with self.assertRaises(ValueError):self.recover()

    def test_changed_source_and_torn_receipt_refuse(self):
        self.run_preparation()
        with patch.object(p,'pins',return_value={'changed':'0'*64}):
            with self.assertRaisesRegex(ValueError,'preparation-source-binding'):self.recover()
        (self.registry/p.RESULT).write_bytes(b'{')
        with self.assertRaises(ValueError):self.recover()

    def test_retained_terminal_after_lost_return_is_historical_only(self):
        original=p.write_at
        def write(fd,name,value):
            result=original(fd,name,value)
            if name==p.RESULT:raise OSError('lost-return')
            return result
        with patch.object(p,'write_at',side_effect=write):
            with self.assertRaises(OSError):self.run_preparation()
        row=self.recover()
        self.assertIn(row['outcome'],('preparation-complete-live-blocked','preparation-insufficient-live-blocked'))
        self.assertFalse(row['activation_authorized']);self.assertFalse(row['automatic_resume_allowed'])
        with self.assertRaises(ValueError):self.run_preparation()


if __name__=='__main__':unittest.main()
