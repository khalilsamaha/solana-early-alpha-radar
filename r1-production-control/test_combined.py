import copy
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import check_combined as combined
from test_production_control import Backend,raw_target
from test_control import target as isolated_target,TOKEN
a=combined.a;c=combined.c;pc=combined.pc;v=combined.v


def fixture_backend(registry):
    isolated=isolated_target();full=raw_target()
    full.update({k:isolated[k] for k in ('id','image','pid','started','finished','running','exit_code')})
    full['config'].update(StopTimeout=2,StopSignal='SIGTERM',Cmd=c.CMD,Entrypoint=c.ENTRY,
                          User='1000:1000',Labels={c.LABEL:TOKEN})
    full['mounts']=[]
    full['host'].update(Memory=128*1024**2,MemorySwap=128*1024**2,PidsLimit=32,NanoCpus=1000000000,
        NetworkMode='none',ReadonlyRootfs=True,Privileged=False,Init=True,CapDrop=['ALL'],
        SecurityOpt=['no-new-privileges:true'],LogConfig={'Type':'none','Config':{}})
    calls=[]
    def bounded(args,**kwargs):
        calls.append(args)
        if args[-2]==pc.FORMAT:return c.raw(full)
        return c.raw(isolated)
    backend=a.IsolatedBoundDocker(['docker-model'],isolated['id'],TOKEN,bounded)
    model=Backend(registry);model.row=copy.deepcopy(backend.target)
    backend.observe=model.observe;backend.mutate=model.mutate
    return backend,model,isolated,full,calls


class CombinedTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)

    def case(self,name):
        root=self.root/name;root.mkdir(mode=0o700)
        registry=root/'registry';registry.mkdir(mode=0o700)
        c.write_new(root/'registry-path.json',c.raw({'registry':str(registry)}))
        backend,model,*_=fixture_backend(registry)
        row=combined.exercise(root,registry,backend,name,development=True)
        self.assertTrue(row['development']);self.assertEqual(row['status'],'combined-case-passed-live-blocked')
        return root,registry,row

    def test_complete_seven_case_combined_path_with_real_worker_scanner_and_restore(self):
        for name in combined.CASES:
            with self.subTest(name=name):
                root,registry,row=self.case(name)
                self.assertEqual(row['fault_reached'],name not in ('normal','cleanup-failure'))
                self.assertEqual(pc.inspect(registry),row['control_recovery'])
                self.assertFalse(row['production_modified']);self.assertFalse(row['provider_connection_opened'])
                if name=='lost-restore-response':
                    self.assertEqual(row['control_recovery']['pending_action'],'start_original')
                    self.assertFalse(row['control_recovery']['original_restored'])
                if name=='invalid-credential':
                    self.assertEqual(c.parse((registry/'worker-credential.json').read_bytes())['status'],'refused')
                if name=='changed-capture':
                    self.assertEqual(row['preservation']['assessment']['classification'],'quarantined-incomplete-evidence')
                if name in ('normal','cleanup-failure'):
                    self.assertEqual(row['preservation']['assessment']['classification'],
                        'closed-clean-session-evidence' if name=='normal' else 'closed-failed-session-evidence')
        c.write_new(self.root/'report.json',c.raw({'development':True}))
        c.write_new(self.root/'validation.log',b'local-model-only\n')
        combined.bundle(self.root)
        with zipfile.ZipFile(self.root/'acceptance.zip') as archive:
            index=c.parse(archive.read('members.json'))
            self.assertEqual(set(archive.namelist()),set(index['members'])|{'members.json'})
            for name,meta in index['members'].items():
                data=archive.read(name)
                self.assertEqual(meta,{'bytes':len(data),'sha256':c.digest(data)})
            self.assertIn('normal/registry/worker-credential.json',index['members'])
            self.assertIn('normal/export/session/evidence.zip',index['members'])

    def test_isolated_binding_has_no_production_readiness_claim(self):
        backend,_,row,_,calls=fixture_backend(self.root)
        self.assertEqual(len(calls),3)
        self.assertTrue(all(args[-1]==row['id'] for args in calls))
        self.assertFalse(backend.admission['production_readiness_observed'])
        self.assertEqual(backend.configuration_sha256,backend.target['config_sha256'])
        self.assertNotIn('baseline_report_sha256',backend.admission)

    def test_isolated_binding_rejects_foreign_or_changed_fixture(self):
        _,_,row,full,_=fixture_backend(self.root)
        for key,value in (('network','host'),('label','e'*32),('image','sha256:'+'e'*64),('running',False)):
            changed={**row,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):
                a.IsolatedBoundDocker(['model'],row['id'],TOKEN,lambda *args,**kw:c.raw(changed))
        snapshots=iter((row,{**row,'pid':row['pid']+1}))
        def drift(args,**kwargs):return c.raw(full if args[-2]==pc.FORMAT else next(snapshots))
        with self.assertRaisesRegex(ValueError,'fixture-binding-drift'):
            a.IsolatedBoundDocker(['model'],row['id'],TOKEN,drift)

    def test_selector_must_be_exact_id_before_any_inspection(self):
        for selector in ('radar','--all','a'*63):
            with self.subTest(selector=selector),self.assertRaisesRegex(ValueError,'fixture-exact-id'):
                a.IsolatedBoundDocker(['model'],selector,TOKEN,lambda *a,**kw:self.fail('inspect'))

    def test_credential_bytes_never_enter_artifacts_and_parent_descriptor_closes(self):
        values=[];fds=[];commands=[];sealed=v.credential.sealed;popen=v.subprocess.Popen
        def record(raw):
            values.append(raw);fd=sealed(raw);fds.append(fd);return fd
        def spawn(args,**kwargs):
            commands.append((args,kwargs.get('env',{}),kwargs.get('pass_fds',())))
            return popen(args,**kwargs)
        with patch.object(v.credential,'sealed',side_effect=record),patch.object(v.subprocess,'Popen',side_effect=spawn):
            root,registry,row=self.case('cleanup-failure')
        self.assertEqual(len(values),1)
        self.assertNotIn(values[0].decode(),repr(commands))
        inherited=[passed for args,env,passed in commands if str(v.r.ROOT/'worker.py') in args]
        self.assertEqual(len(inherited),1);self.assertIn(fds[0],inherited[0])
        self.assertTrue(all(fds[0] not in passed for args,env,passed in commands if str(v.r.ROOT/'worker.py') not in args))
        for path in root.rglob('*'):
            if path.is_file():self.assertNotIn(values[0],path.read_bytes())
        for fd in fds:
            with self.assertRaises(OSError):os.fstat(fd)
        terminal=row['supervision_recovery']['terminal']
        self.assertTrue(terminal['credential_descriptor_closed'])
        self.assertEqual(terminal['credential_handoff'],'sealed-synthetic-fd')

    def test_worker_spawn_failure_closes_descriptor_and_reaps_scanner(self):
        root=self.root/'failure';root.mkdir(mode=0o700)
        registry=root/'registry';registry.mkdir(mode=0o700)
        backend,*_=fixture_backend(registry)
        plan,sha,paths=combined.prepare(root,registry,backend,True)
        popen=v.subprocess.Popen;sealed=v.credential.sealed;fds=[]
        def descriptor(raw):fd=sealed(raw);fds.append(fd);return fd
        def spawn(args,**kwargs):
            if args[0]==v.sys.executable:raise OSError('fixture-worker-start')
            return popen(args,**kwargs)
        with patch.object(v.credential,'sealed',side_effect=descriptor),patch.object(v.subprocess,'Popen',side_effect=spawn):
            row=v.run(plan,sha,mode='session-scanner-normal')
        self.assertEqual(row['outcome'],'worker-start-failed')
        self.assertTrue(row['scanner']['reaped'])
        for fd in fds:
            with self.assertRaises(OSError):os.fstat(fd)

    def test_changed_credential_receipt_invalidates_historical_success(self):
        _,registry,row=self.case('normal')
        path=registry/'worker-credential.json';data=c.parse(path.read_bytes());data['status']='refused'
        path.write_bytes(c.raw(data))
        with self.assertRaisesRegex(ValueError,'runtime-credential-consumption'):
            v.inspect(registry,row['manifest_sha256'])

    def test_linked_bundle_member_refused(self):
        (self.root/'report.json').symlink_to('/dev/null')
        with self.assertRaises(OSError):combined.bundle(self.root)

    def test_fixture_intent_failure_prevents_create_and_cleanup_dispatch(self):
        original=combined.owned_fixture.Original(['model'],self.root)
        with patch.object(combined.owned_fixture.c,'write_new',side_effect=OSError('durability')),\
             patch.object(combined.retained,'run',side_effect=AssertionError('dispatch')):
            with self.assertRaises(OSError):original.start()
            original.close()
        self.assertFalse(original.receipt['create_attempted'])

    def test_uncertain_create_disposes_only_exact_owned_fixture(self):
        original=combined.owned_fixture.Original(['model'],self.root);calls=[]
        row={**isolated_target(),'label':original.token,'running':False,'pid':0}
        def command(args,**kwargs):
            calls.append(args)
            intent=c.parse((self.root/'fixture-intent.json').read_bytes())
            self.assertEqual(intent['token'],original.token)
            if args[1]=='create':return b'unknown-create-response\n'
            if args[1]=='inspect':
                self.assertEqual(args[-1],original.name);return c.raw(row)
            self.assertEqual(args[1:],['rm','--force',row['id']]);return (row['id']+'\n').encode()
        with patch.object(combined.retained,'run',side_effect=command):
            with self.assertRaisesRegex(ValueError,'create-identity'):original.start()
            original.close()
        self.assertTrue(original.receipt['removed']);self.assertFalse(original.receipt['ready'])
        self.assertEqual([args[1] for args in calls],['create','inspect','rm'])

    def test_foreign_cleanup_target_is_never_removed(self):
        original=combined.owned_fixture.Original(['model'],self.root);original.attempted=True
        row={**isolated_target(),'label':'e'*32}
        calls=[]
        def command(args,**kwargs):calls.append(args);return c.raw(row)
        with patch.object(combined.retained,'run',side_effect=command):
            with self.assertRaises(ValueError):original.close()
        self.assertFalse(original.receipt['removed'])
        self.assertEqual([args[1] for args in calls],['inspect'])

    def test_changed_exact_id_refuses_cleanup_even_with_owned_label(self):
        original=combined.owned_fixture.Original(['model'],self.root)
        original.attempted=True;original.cid='f'*64
        row={**isolated_target(),'label':original.token};calls=[]
        def command(args,**kwargs):calls.append(args);return c.raw(row)
        with patch.object(combined.retained,'run',side_effect=command):
            with self.assertRaisesRegex(ValueError,'cleanup-identity'):original.close()
        self.assertEqual([args[1] for args in calls],['inspect'])


if __name__=='__main__':unittest.main()
