import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import manifest_supervisor as v
import native_scanner as native
m=v.m;p=v.p;s=p.s


def fixture(root,registry,*,pipe=False):
    paths={role:str(root/role) for role in s.ROLES}
    for path in paths.values():Path(path).mkdir(mode=0o700)
    config={k:None for k in m.CONFIG};policy={k:None for k in m.POLICY}
    config.update(scanner_image=native.n.c.IMAGE,registry_path=str(registry),endpoint_path=str(registry/'discovery.sock'),
                  capture_path=paths['capture'],owner_source_sha256=m.digest((v.r.ROOT/'worker.py').read_bytes()))
    policy.update(raw_bytes=65536,database_bytes=262144,journal_bytes=65536,receipt_bytes=65536,
        retained_runs=1,quarantined_runs=1,headroom_bytes=1024**2,research_seconds=2,
        service_seconds=3,setup_seconds=10,shutdown_seconds=5,memory_bytes=512*1024**2,cpu_seconds=10,open_files=64)
    if pipe:policy.update(setup_seconds=3,shutdown_seconds=3)
    manifest=m.build(config,policy);plan=root/'manifest';sha=m.freeze(plan,manifest)
    return manifest,plan,sha,paths


class NativeUnixTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='r1ns-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.registry=self.root/'registry';self.registry.mkdir(mode=0o700)
        self.manifest,self.plan,self.sha,self.paths=fixture(self.root,self.registry)
        p.prepare(self.plan,self.sha,self.paths)
    def run_native(self,mode='session-native-normal'):
        return v.run(self.plan,self.sha,mode=mode,native_development=True)
    def recover(self):return v.inspect(self.registry,self.sha)

    def test_real_unix_local_node_and_kernel_peer_binding(self):
        row=self.run_native();self.assertEqual(row['outcome'],v.SUCCESS)
        peer=row['terminal']['session_evidence']['native_peer']
        self.assertTrue(peer['kernel_uid_gid_verified']);self.assertFalse(peer['container_parent_verified'])
        self.assertTrue(row['scanner']['development']);self.assertIsNone(row['scanner']['actor'])
        self.assertTrue(row['scanner']['removed']);self.assertTrue(row['scanner']['reaped'])
        self.assertEqual(row['scanner']['result']['creations'],2)
        self.assertFalse((self.registry/'discovery.sock').exists())
        before={str(f):f.read_bytes() for f in self.root.rglob('*') if f.is_file()}
        with patch.object(native.Scanner,'start',side_effect=AssertionError('start')),\
             patch.object(native.n,'proc_identity',side_effect=AssertionError('process observation')):
            self.assertEqual(self.recover(),row)
        self.assertEqual(before,{str(f):f.read_bytes() for f in self.root.rglob('*') if f.is_file()})

    def test_cleanup_failure_closes_real_unix_without_later_creation(self):
        row=self.run_native('session-native-cleanup-failure');self.assertEqual(row['outcome'],v.SUCCESS)
        self.assertEqual(row['scanner']['result']['tokens'],['pumpportal:create','pumpportal:migration'])
        self.assertEqual(row['terminal']['session_evidence']['research_cleanup'],'upstream-aborted')
        self.assertEqual(self.recover(),row)

    def test_lost_native_confirmation_keeps_failure_after_cleanup(self):
        original=native.Scanner.finish
        def lost(scanner,*args):original(scanner,*args);raise OSError('lost-return')
        with patch.object(native.Scanner,'finish',lost):row=self.run_native()
        self.assertEqual(row['outcome'],'worker-failed');self.assertIsNone(row['terminal'])
        self.assertTrue(row['scanner']['reaped']);self.assertTrue(row['scanner']['removed'])
        self.assertEqual(self.recover(),row)

    def test_retained_peer_uid_gid_and_generation_tampering_refuse(self):
        row=self.run_native();self.assertEqual(row['outcome'],v.SUCCESS)
        identity,raw=native.read(self.registry,native.IDENTITY);endpoint,endraw=native.read(self.registry,native.ENDPOINT)
        peer,peerraw=native.read(self.registry,native.PEER);claim,claimraw=native.read(self.registry,v.CLAIM)
        for mutate in (lambda x:x.update(uid=x['uid']+1),lambda x:x.update(gid=x['gid']+1),
                       lambda x:x['process_identity'].update(start_ticks=x['process_identity']['start_ticks']+1)):
            changed=copy.deepcopy(peer);mutate(changed)
            with self.assertRaises(ValueError):native.validate_peer(changed,identity,raw,endraw,claimraw,True)

    def test_missing_native_identity_cannot_confirm_retained_success(self):
        row=self.run_native();self.assertEqual(row['outcome'],v.SUCCESS)
        (self.registry/native.IDENTITY).unlink()
        with self.assertRaises(FileNotFoundError):self.recover()

    def test_uncertain_native_cleanup_retains_disposal_but_no_success(self):
        original=native.Scanner.close
        def uncertain(scanner,*args):original(scanner,*args);raise ValueError('uncertain')
        with patch.object(native.Scanner,'close',uncertain):
            with self.assertRaises(ValueError):self.run_native()
        self.assertTrue((self.registry/'native-scanner-disposal.json').exists())
        self.assertEqual(self.recover()['outcome'],'supervision-unresolved')


class NativeAdmissionTests(unittest.TestCase):
    setUp=NativeUnixTests.setUp
    run_native=NativeUnixTests.run_native
    recover=NativeUnixTests.recover

    def test_portable_peer_checks_use_fixed_recorded_credentials(self):
        claim=b'claim';proc={'pid':123,'ppid':1,'start_ticks':456};identity={'process_identity':proc}
        raw=m.raw(identity)
        endpoint={'schema':1,'kind':'private-unix-endpoint','claim_sha256':m.digest(claim),
            'manifest_sha256':self.sha,'path':self.manifest['config']['endpoint_path'],'development':False,
            'socket':{'device':1,'inode':2,'uid':1000,'gid':1000,'mode':0o600}}
        endpoint_raw=m.raw(endpoint)
        peer={'schema':1,'kind':'kernel-unix-peer','claim_sha256':m.digest(claim),
            'identity_sha256':m.digest(raw),'endpoint_sha256':m.digest(endpoint_raw),
            'pid':124,'uid':1000,'gid':1000,'process_identity':{'pid':124,'ppid':123,'start_ticks':457}}
        with patch.object(native.os,'getuid',side_effect=AssertionError('live uid')),\
             patch.object(native.os,'getgid',side_effect=AssertionError('live gid')):
            native.validate_endpoint(endpoint,claim,self.manifest,False,expected_uid=1000,expected_gid=1000)
            native.validate_peer(peer,identity,raw,endpoint_raw,claim,False,expected_uid=1000,expected_gid=1000)
            with self.assertRaises(ValueError):
                native.validate_peer({**peer,'uid':1001},identity,raw,endpoint_raw,claim,False,expected_uid=1000,expected_gid=1000)

    def test_space_gate_prevents_owned_worker_and_native_consumer(self):
        original=s.sample
        with patch.object(s,'sample',side_effect=lambda fd:{**original(fd),'available_bytes':0}),\
             patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')):
            with self.assertRaisesRegex(ValueError,'runtime-session-storage'):self.run_native()
        self.assertEqual(self.recover()['outcome'],'supervision-unresolved')
        self.assertFalse((self.registry/native.INTENT).exists())

    def test_native_manifest_must_bind_accepted_image(self):
        bad=m.build({**self.manifest['config'],'scanner_image':'sha256:'+'0'*64},self.manifest['policy'])
        with self.assertRaisesRegex(ValueError,'native-manifest-image'):v.session.validate_mode(bad,'session-native-normal')


    def test_recorded_peer_credentials_and_generation_must_match(self):
        proc=native.n.proc_identity(os.getpid());identity={'process_identity':proc}
        raw=m.raw(identity);endpoint=b'{}\n';claim=b'claim'
        row={'schema':1,'kind':'kernel-unix-peer','claim_sha256':m.digest(claim),
             'identity_sha256':m.digest(raw),'endpoint_sha256':m.digest(endpoint),
             'pid':proc['pid'],'uid':os.getuid(),'gid':os.getgid(),'process_identity':proc}
        native.validate_peer(row,identity,raw,endpoint,claim,True)
        for mutate in (lambda x:x.update(uid=x['uid']+1),lambda x:x.update(gid=x['gid']+1),
                       lambda x:x['process_identity'].update(start_ticks=x['process_identity']['start_ticks']+1),
                       lambda x:x.update(identity_sha256='0'*64)):
            changed=copy.deepcopy(row);mutate(changed)
            with self.assertRaises(ValueError):native.validate_peer(changed,identity,raw,endpoint,claim,True)

    def test_endpoint_metadata_requires_private_socket_and_exact_attempt(self):
        claim=b'claim'
        row={'schema':1,'kind':'private-unix-endpoint','claim_sha256':m.digest(claim),
             'manifest_sha256':self.sha,'path':self.manifest['config']['endpoint_path'],'development':True,
             'socket':{'device':1,'inode':1,'uid':os.getuid(),'gid':os.getgid(),'mode':0o600}}
        native.validate_endpoint(row,claim,self.manifest,True)
        for mutate in (lambda x:x['socket'].update(mode=0o666),lambda x:x.update(development=False),
                       lambda x:x.update(claim_sha256='0'*64),lambda x:x.update(path='/other/discovery.sock')):
            changed=copy.deepcopy(row);mutate(changed)
            with self.assertRaises(ValueError):native.validate_endpoint(changed,claim,self.manifest,True)


if __name__=='__main__':unittest.main()
