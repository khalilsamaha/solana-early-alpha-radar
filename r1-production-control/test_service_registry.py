import copy
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import service_registry as service
from test_production_control import target
c=service.c


class RegistryTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.directory=self.root/'service';self.target=target()
        self.sha=service.provision(self.directory,self.target)
        self.run=self.root/'run-one';self.run.mkdir(mode=0o700)

    def lease(self,run=None):return service.Lease(self.directory,self.sha,self.target,'a'*64,run or self.run)

    def files(self):return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_claim_precedes_work_and_remains_consumed_after_close(self):
        with self.lease() as lease:
            claim=c.parse((self.directory/service.CLAIM).read_bytes())
            self.assertEqual(claim['run_registry'],str(self.run));lease.check()
        another=self.root/'other-output';another.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError,'service-attempt-consumed'):
            with self.lease(another):self.fail('second attempt')
        self.assertEqual(service.inspect(self.directory,self.sha)['status'],'attempt-consumed-completion-unconfirmed')

    def test_same_service_different_run_directories_contend(self):
        other=self.root/'run-two';other.mkdir(mode=0o700)
        with self.lease():
            with self.assertRaisesRegex(ValueError,'service-coordinator-active'):
                with self.lease(other):self.fail('overlap')
        self.assertFalse((other/service.CLAIM).exists())

    def test_exact_contract_target_and_directory_required(self):
        for changed in ({**self.target,'id':'f'*64},{**self.target,'config_sha256':'f'*64}):
            with self.assertRaisesRegex(ValueError,'service-target-mismatch'):
                service.Lease(self.directory,self.sha,changed,'a'*64,self.run)
        with self.assertRaisesRegex(ValueError,'service-contract-binding'):
            service.load(self.directory,'f'*64)
        with self.assertRaisesRegex(ValueError,'service-run-path-overlap'):self.lease(self.directory/'output')

    def test_missing_or_replaced_lock_is_not_recreated(self):
        path=self.directory/service.LOCK;original=path.read_bytes();path.unlink()
        with self.assertRaises(FileNotFoundError):
            with self.lease():pass
        self.assertFalse(path.exists())
        path.write_bytes(original);path.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'service-lock-replaced'):
            with self.lease():pass

    def test_lock_replacement_during_work_refuses(self):
        with self.lease() as lease:
            lock=self.directory/service.LOCK;lock.rename(self.directory/'old-lock')
            lock.write_bytes(b'');lock.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'service-identity-changed'):lease.check()

    def test_directory_replacement_and_claim_changes_refuse(self):
        with self.lease() as lease:
            path=self.directory/service.CLAIM;raw=path.read_bytes();path.write_bytes(raw+b' ')
            with self.assertRaisesRegex(ValueError,'service-claim-changed'):lease.check()
            path.write_bytes(raw)
            self.directory.rename(self.root/'old-service');self.directory.mkdir(mode=0o700)
            with self.assertRaises((ValueError,FileNotFoundError)):lease.check()

    def test_lost_claim_write_consumes_attempt_if_bytes_were_persisted(self):
        write=service.p.write_at
        def lost(fd,name,row):
            value=write(fd,name,row)
            if name==service.CLAIM:raise OSError('lost-claim-return')
            return value
        with patch.object(service.p,'write_at',side_effect=lost):
            with self.assertRaises(OSError):
                with self.lease():pass
        with self.assertRaisesRegex(ValueError,'service-attempt-consumed'):
            with self.lease():pass

    def test_failed_claim_fsync_never_opens_control(self):
        with patch.object(service.p,'write_at',side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                with self.lease():self.fail('admitted')
        # No claim means no operation could have started; the SAME Lease object
        # still consumes its attempt. A later caller must independently inspect.
        lease=self.lease()
        with lease:pass
        with self.assertRaisesRegex(ValueError,'service-lease-reuse'):
            with lease:pass

    def test_complete_assessment_is_historical_and_still_cannot_resume(self):
        with self.lease() as lease:lease.record_completion('b'*64,'c'*64)
        before=self.files()
        with patch.object(service.fcntl,'flock',side_effect=AssertionError('lock')),\
             patch.object(service,'process_identity',side_effect=AssertionError('process')):
            result=service.inspect(self.directory,self.sha)
        self.assertEqual(before,self.files());self.assertEqual(result['status'],'completion-recorded-attempt-consumed')
        self.assertFalse(result['current_lock_state_observed']);self.assertFalse(result['global_owner_exclusivity_verified'])
        with self.assertRaisesRegex(ValueError,'service-attempt-consumed'):
            with self.lease():pass

    def test_result_drift_or_orphan_never_promotes_completion(self):
        with self.lease() as lease:lease.record_completion('b'*64,'c'*64)
        path=self.directory/service.RESULT;result=c.parse(path.read_bytes());result['activation_authorized']=True
        path.write_bytes(c.raw(result))
        with self.assertRaisesRegex(ValueError,'service-result-authority'):service.inspect(self.directory,self.sha)
        (self.directory/service.CLAIM).unlink()
        with self.assertRaisesRegex(ValueError,'service-orphan-result'):service.inspect(self.directory,self.sha)

    def test_lock_descriptors_are_not_inherited_by_exec_and_fork_cannot_use_parent_lease(self):
        with self.lease() as lease:
            self.assertFalse(os.get_inheritable(lease.fd));self.assertFalse(os.get_inheritable(lease.lock))
            with patch.object(service,'process_identity',return_value={**lease.owner,'pid':lease.owner['pid']+1}):
                with self.assertRaisesRegex(ValueError,'service-process-changed'):lease.check()

    def test_real_other_process_contends_then_owner_death_does_not_rearm(self):
        code="""import sys,json
sys.path.insert(0,sys.argv[1])
import service_registry as s
with s.Lease(sys.argv[2],sys.argv[3],json.loads(sys.argv[4]),'a'*64,sys.argv[5]):
 print('claimed',flush=True)
 sys.stdin.buffer.read()
"""
        child=subprocess.Popen([sys.executable,'-E','-s','-B','-c',code,str(service.pc.ROOT/'r1-production-control'),
            str(self.directory),self.sha,c.raw(self.target).decode(),str(self.run)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout,selectors.EVENT_READ)
                self.assertTrue(selector.select(5));self.assertEqual(child.stdout.readline(),b'claimed\n')
            with self.assertRaisesRegex(ValueError,'service-coordinator-active'):
                with self.lease():pass
            child.kill();child.wait(timeout=3)
            with self.assertRaisesRegex(ValueError,'service-attempt-consumed'):
                with self.lease(self.root/'new-output'):pass
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=3)
            for stream in (child.stdin,child.stdout,child.stderr):stream.close()

    def test_symlinks_hardlinks_and_public_lock_refused(self):
        lock=self.directory/service.LOCK;os.link(lock,self.directory/'alias')
        with self.assertRaisesRegex(ValueError,'service-lock-private'):
            with self.lease():pass
        (self.directory/'alias').unlink();lock.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'service-lock-private'):
            with self.lease():pass
        lock.chmod(0o600);lock.rename(self.directory/'original');lock.symlink_to(self.directory/'original')
        with self.assertRaises(OSError):
            with self.lease():pass


if __name__=='__main__':unittest.main()
