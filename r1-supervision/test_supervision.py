import copy
import os
from pathlib import Path
import shutil
import signal
import tempfile
import time
import unittest
from unittest.mock import patch
import runtime as r
import manifest_supervisor as v
m=r.m;p=r.preparation;s=p.s


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.registry=self.root/'registry';self.registry.mkdir(mode=0o700)
        self.paths={role:str(self.root/role) for role in s.ROLES}
        for path in self.paths.values():Path(path).mkdir(mode=0o700)
        self.config={k:None for k in m.CONFIG};self.policy={k:None for k in m.POLICY}
        self.config.update(registry_path=str(self.registry),endpoint_path=str(self.registry/'discovery.sock'),
                           capture_path=self.paths['capture'])
        self.policy.update(raw_bytes=100,database_bytes=200,journal_bytes=300,receipt_bytes=65536,
                           retained_runs=1,quarantined_runs=1,headroom_bytes=1000,
                           service_seconds=1,setup_seconds=1,shutdown_seconds=1,
                           memory_bytes=256*1024**2,cpu_seconds=2,open_files=32)
        self.manifest=m.build(self.config,self.policy);self.plan=self.root/'plan'
        self.sha=m.freeze(self.plan,self.manifest)
        self.prepared=p.prepare(self.plan,self.sha,self.paths)
        self.assertEqual(self.prepared['outcome'],'preparation-complete-live-blocked')

    def run_worker(self,mode='complete'):return v.run(self.plan,self.sha,mode=mode)
    def recover(self):return v.inspect(self.registry,self.sha)
    def files(self):return {f.name:f.read_bytes() for f in self.registry.iterdir() if f.is_file()}
    def write_result(self,row):
        (self.registry/v.RESULT).write_bytes(m.raw(row))

    def test_complete_actual_worker_and_read_only_recovery(self):
        row=self.run_worker();self.assertEqual(row['outcome'],v.SUCCESS)
        self.assertTrue(row['worker_reaped']);self.assertEqual(row['returncode'],0)
        self.assertEqual(row['terminal']['profile']['wall_seconds'],3)
        before=self.files()
        with patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')),\
             patch.object(s,'observe',side_effect=AssertionError('sample')),\
             patch.object(p,'write_at',side_effect=AssertionError('write')):
            self.assertEqual(self.recover(),row)
        self.assertEqual(self.files(),before)
        self.assertFalse(row['activation_authorized'])

    def test_actual_dns_guard(self):
        row=self.run_worker('dns');self.assertEqual(row['outcome'],v.SUCCESS)
        self.assertTrue(row['terminal']['guard_blocked'])

    def test_actual_socket_guard(self):
        row=self.run_worker('socket');self.assertEqual(row['outcome'],v.SUCCESS)
        self.assertTrue(row['terminal']['guard_blocked'])

    def test_actual_process_guard(self):
        row=self.run_worker('process');self.assertEqual(row['outcome'],v.SUCCESS)
        self.assertTrue(row['terminal']['guard_blocked'])

    def test_independent_parent_deadline_kills_and_reaps(self):
        started=time.monotonic();row=self.run_worker('ignore-alarm')
        self.assertEqual(row['outcome'],'deadline');self.assertTrue(row['worker_reaped'])
        self.assertEqual(row['returncode'],-signal.SIGKILL)
        self.assertLess(time.monotonic()-started,8)
        self.assertEqual(self.recover(),row)

    def test_zero_exit_with_invalid_terminal_is_failure(self):
        row=self.run_worker('tainted-output');self.assertEqual(row['outcome'],'worker-failed')
        self.assertEqual(row['returncode'],0);self.assertIsNone(row['terminal'])
        self.assertNotIn(b'not-a-terminal',b''.join(self.files().values()))
        self.assertEqual(self.recover(),row)

    def test_output_bound_terminates_and_reaps(self):
        row=self.run_worker('output-flood');self.assertEqual(row['outcome'],'output-limit')
        self.assertTrue(row['worker_reaped']);self.assertIsNone(row['terminal'])
        self.assertEqual(self.recover(),row)

    def test_missing_policy_and_ranges_refuse(self):
        for key in ('service_seconds','setup_seconds','shutdown_seconds','memory_bytes','cpu_seconds','open_files','raw_bytes'):
            policy={**self.policy,key:None}
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'runtime-policy-missing'):
                r.profile(m.build(self.config,policy))
        for key,value in (('memory_bytes',1024),('open_files',15),('open_files',4097)):
            with self.subTest(key=key,value=value),self.assertRaisesRegex(ValueError,'runtime-resource-range'):
                r.profile(m.build(self.config,{**self.policy,key:value}))

    def test_reconstructed_manifest_required(self):
        row=copy.deepcopy(self.manifest);row['activation_authorized']=True
        with self.assertRaisesRegex(ValueError,'runtime-manifest'):r.profile(row)

    def test_wrong_digest_missing_preparation_and_unknown_mode_never_spawn(self):
        with patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')):
            with self.assertRaises(ValueError):v.run(self.plan,'0'*64)
            with self.assertRaisesRegex(ValueError,'runtime-mode'):self.run_worker('live')
            (self.registry/p.RESULT).unlink()
            with self.assertRaisesRegex(ValueError,'runtime-preparation-required'):self.run_worker()
        self.assertFalse((self.registry/v.CLAIM).exists())

    def test_durable_claim_precedes_spawn_and_no_rearm(self):
        original=v.subprocess.Popen
        def spawn(*args,**kwargs):
            self.assertTrue((self.registry/v.CLAIM).exists())
            unresolved=self.recover()
            self.assertEqual(unresolved['outcome'],'supervision-unresolved')
            self.assertIsNone(unresolved['workers_started']);self.assertIsNone(unresolved['worker_reaped'])
            return original(*args,**kwargs)
        with patch.object(v.subprocess,'Popen',side_effect=spawn):
            self.assertEqual(self.run_worker()['outcome'],v.SUCCESS)
        with patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')):
            with self.assertRaises(ValueError):self.run_worker()

    def test_orphan_result_blocks_start(self):
        (self.registry/v.RESULT).write_bytes(b'{}\n')
        with patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')):
            with self.assertRaisesRegex(ValueError,'runtime-result-already-present'):self.run_worker()
        self.assertFalse((self.registry/v.CLAIM).exists())

    def test_claim_fsync_failure_cannot_spawn_or_rearm(self):
        with patch.object(p.os,'fsync',side_effect=OSError('durability')),\
             patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')):
            with self.assertRaises(OSError):self.run_worker()
        self.assertEqual(self.recover()['outcome'],'supervision-unresolved')
        with self.assertRaises(FileExistsError):self.run_worker()

    def test_spawn_failure_consumes_attempt_without_raw_exception(self):
        with patch.object(v.subprocess,'Popen',side_effect=OSError('private-detail')):row=self.run_worker()
        self.assertEqual(row['outcome'],'worker-start-failed');self.assertEqual(row['workers_started'],0)
        self.assertEqual(self.recover(),row)
        self.assertNotIn(b'private-detail',b''.join(self.files().values()))

    def test_missing_terminal_cannot_confirm_reaping_or_retry(self):
        original=p.write_at
        def write(fd,name,row):
            if name==v.RESULT:raise OSError('interrupted')
            return original(fd,name,row)
        with patch.object(p,'write_at',side_effect=write):
            with self.assertRaises(OSError):self.run_worker()
        row=self.recover();self.assertEqual(row['outcome'],'supervision-unresolved')
        self.assertIsNone(row['worker_reaped']);self.assertFalse(row['automatic_resume_allowed'])
        with self.assertRaises(FileExistsError):self.run_worker()

    def test_result_persisted_but_return_lost_replays(self):
        original=p.write_at
        def write(fd,name,row):
            data=original(fd,name,row)
            if name==v.RESULT:raise OSError('lost-return')
            return data
        with patch.object(p,'write_at',side_effect=write):
            with self.assertRaises(OSError):self.run_worker()
        row=self.recover();self.assertEqual(row['outcome'],v.SUCCESS)
        self.assertTrue(row['worker_reaped']);self.assertFalse(row['activation_authorized'])

    def test_reaping_uncertainty_never_publishes_terminal(self):
        original=v.reap
        def uncertain(process):original(process);raise ValueError('uncertain')
        with patch.object(v,'reap',side_effect=uncertain):
            with self.assertRaises(ValueError):self.run_worker()
        self.assertEqual(self.recover()['outcome'],'supervision-unresolved')

    def test_replaced_registry_cannot_publish(self):
        original=v.collect
        def collect(*args):
            row=original(*args);self.registry.rename(self.root/'old');self.registry.mkdir(mode=0o700);return row
        with patch.object(v,'collect',side_effect=collect):
            with self.assertRaisesRegex(ValueError,'preparation-registry-replaced'):self.run_worker()
        self.assertFalse((self.root/'old'/v.RESULT).exists());self.assertFalse((self.registry/v.RESULT).exists())

    def test_copied_registry_rejects_recovery(self):
        self.run_worker();other=self.root/'copied';shutil.copytree(self.registry,other)
        with self.assertRaisesRegex(ValueError,'runtime-registry-binding'):v.inspect(other,self.sha)

    def test_changed_preparation_cannot_publish(self):
        original=v.collect
        def collect(*args):
            row=original(*args);(self.registry/p.RESULT).unlink();return row
        with patch.object(v,'collect',side_effect=collect):
            with self.assertRaisesRegex(ValueError,'runtime-final-binding'):self.run_worker()
        self.assertFalse((self.registry/v.RESULT).exists())

    def test_changed_sources_or_torn_result_reject(self):
        self.run_worker()
        with patch.object(r,'pins',return_value={'changed':'0'*64}):
            with self.assertRaisesRegex(ValueError,'runtime-source-binding'):self.recover()
        (self.registry/v.RESULT).write_bytes(b'{')
        with self.assertRaises(ValueError):self.recover()

    def test_result_mutations_cannot_promote_or_hide_uncertainty(self):
        row=self.run_worker()
        mutations=(lambda x:x.update(schema=True),lambda x:x.update(activation_authorized=0),
                   lambda x:x.update(worker_reaped=False),lambda x:x.update(workers_started=True),
                   lambda x:x.update(returncode=True),lambda x:x.update(claim_sha256='0'*64),
                   lambda x:x.update(outcome='worker-failed'),lambda x:x.update(elapsed_seconds=-1),
                   lambda x:x.update(finished_utc='2000-01-01T00:00:00+00:00'),
                   lambda x:x['terminal'].update(provider_connection_opened=True),
                   lambda x:x['terminal']['profile'].update(memory_bytes=1))
        for mutate in mutations:
            changed=copy.deepcopy(row);mutate(changed);self.write_result(changed)
            with self.assertRaises(ValueError):self.recover()

    def test_receipt_links_and_public_files_reject(self):
        self.run_worker();file=self.registry/v.RESULT
        file.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'preparation-private-file'):self.recover()
        file.chmod(0o600);file.rename(self.root/'receipt');file.symlink_to(self.root/'receipt')
        with self.assertRaises(OSError):self.recover()

    def test_claim_profile_boolean_cannot_replace_numeric_limit(self):
        self.run_worker();file=self.registry/v.CLAIM;claim=m.parse(file.read_bytes())
        claim['profile']['service_seconds']=True;file.write_bytes(m.raw(claim))
        with self.assertRaisesRegex(ValueError,'runtime-input-binding'):self.recover()

    def test_claim_changed_during_worker_cannot_publish(self):
        original=v.collect
        def collect(*args):
            row=original(*args);file=self.registry/v.CLAIM
            claim=m.parse(file.read_bytes());claim['mode']='dns';file.write_bytes(m.raw(claim));return row
        with patch.object(v,'collect',side_effect=collect):
            with self.assertRaisesRegex(ValueError,'runtime-final-binding'):self.run_worker()
        self.assertFalse((self.registry/v.RESULT).exists())

    def test_collection_exception_still_reaps_without_retaining_diagnostics(self):
        children=[];original=v.subprocess.Popen
        def spawn(*args,**kwargs):
            process=original(*args,**kwargs);children.append(process);return process
        with patch.object(v.subprocess,'Popen',side_effect=spawn),\
             patch.object(v,'collect',side_effect=OSError('private-detail')):
            row=self.run_worker('ignore-alarm')
        self.assertEqual(row['outcome'],'worker-failed');self.assertTrue(row['worker_reaped'])
        self.assertEqual(len(children),1);self.assertIsNotNone(children[0].returncode)
        self.assertNotIn(b'private-detail',b''.join(self.files().values()))


if __name__=='__main__':unittest.main()
