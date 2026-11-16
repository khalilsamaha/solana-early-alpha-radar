import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import admission as a
import production_control as pc
from test_production_control import Backend
from test_manifest import inputs
from test_observed_target import fixture,PINS
import readiness
c=pc.c


def evidence():
    report=fixture();meta=report['observation']['context']['metadata']
    config={'User':meta['user'],'Cmd':['node','src/index.js'],'Entrypoint':['docker-entrypoint.sh'],'Env':['DATA_DIR=/app/data'],
            'WorkingDir':'/app','StopSignal':None,'StopTimeout':35,
            'Labels':{'com.docker.compose.project.working_dir':'/home/user/apps/radar',
                      'com.docker.compose.project.config_files':'/home/user/apps/radar/compose.yaml'}}
    host={'RestartPolicy':{'Name':'unless-stopped','MaximumRetryCount':0},'PortBindings':None,
          'Tmpfs':{'/tmp':''},'CapDrop':['ALL'],'CapAdd':None,'SecurityOpt':['no-new-privileges']}
    host.update({field:meta[key] for key,field in (('init','Init'),('readonly_rootfs','ReadonlyRootfs'),('privileged','Privileged'),('memory','Memory'),('memory_swap','MemorySwap'),('nano_cpus','NanoCpus'),('pids_limit','PidsLimit'),('network_mode','NetworkMode'))})
    mounts=[{'Type':'volume','Name':'radar_data','Source':meta['mounts'][0]['source'],
             'Destination':'/app/data','RW':True}]
    raw={'id':meta['id'],'image':meta['image'],'name':meta['name'],'config':config,'host':host,'mounts':mounts,
         'running':True,'pid':123,'started':meta['started'],'finished':'0001-01-01T00:00:00Z',
         'exit_code':0,'paused':False,'restarting':False,'dead':False,'oom':False,'error':''}
    projection={'id':raw['id'],'image':raw['image'],'started':raw['started'],'cmd':config['Cmd'],
                'entrypoint':config['Entrypoint'],'environment':config['Env'],'working_dir':'/app',
                'stop_signal':None,'stop_timeout':35,'ports':None,'tmpfs':{'/tmp':''},'caps_drop':['ALL'],
                'caps_add':None,'security':['no-new-privileges'],'mounts':mounts,
                'compose_directory':'/home/user/apps/radar','compose_files':'/home/user/apps/radar/compose.yaml'}
    # Obtain the expected fingerprint from the ACTUAL accepted producer function.
    with patch.object(readiness.diagnostics,'command',return_value=c.raw(projection)):
        produced=readiness.configuration('/fixture-only')
    report['observation']['configuration']['configuration_sha256']=produced['configuration_sha256']
    data=c.raw(report)
    return raw,data,c.digest(data)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.raw,self.data,self.sha=evidence();self.calls=[]
        def inspect(args,**kwargs):self.calls.append(args);return c.raw(self.raw)
        self.backend=a.BoundDocker(['docker-model'],self.data,self.sha,PINS,inspect)
        self.registry=self.root/'registry';self.registry.mkdir(mode=0o700)
        self.paths={k:str(self.root/k) for k in a.storage.ROLES}
        for p in self.paths.values():Path(p).mkdir(mode=0o700)
        config,policy=inputs();config.update(scanner_image=self.backend.target['image'],
            scanner_config_sha256=self.backend.admission['readiness_configuration_sha256'],
            rollback_config_sha256=self.backend.target['config_sha256'],registry_path=str(self.registry),
            endpoint_path=str(self.registry/'discovery.sock'),capture_path=self.paths['capture'])
        policy.update(raw_bytes=100,database_bytes=200,journal_bytes=300,receipt_bytes=400,
                      retained_runs=1,quarantined_runs=1,headroom_bytes=1000)
        self.plan=self.root/'plan';self.plan_sha=a.m.freeze(self.plan,a.m.build(config,policy))
        a.prep.prepare(self.plan,self.plan_sha,self.paths)
        self.model=Backend(self.registry);self.model.row=copy.deepcopy(self.backend.target)
        # Real BoundDocker type with explicitly simulated effect methods.
        self.backend.observe=self.model.observe;self.backend.mutate=self.model.mutate
        self.guard=a.Prepared(self.backend,self.plan,self.plan_sha,self.paths)
    def test_single_exact_id_inspect_binds_readiness_without_authority(self):
        self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0][-1],self.raw['id'])
        self.assertIn('inspect',self.calls[0]);self.assertFalse(self.backend.admission['activation_authorized'])
        self.assertFalse(self.backend.admission['process_namespace_reobserved'])
    def test_wrong_baseline_pin_or_configuration_refuses_binding(self):
        for alter in ('config','target','pin','hash'):
            raw=copy.deepcopy(self.raw);pins=dict(PINS);sha=self.sha
            if alter=='config':raw['config']['Env']=['DATA_DIR=/other']
            if alter=='target':raw['pid']=999
            if alter=='pin':pins[next(iter(pins))]='e'*64
            if alter=='hash':sha='e'*64
            with self.subTest(alter=alter),self.assertRaises(ValueError):a.match_snapshot(c.raw(raw),self.data,sha,pins)
    def test_resource_user_and_mount_drift_refuse_even_if_readiness_hash_unchanged(self):
        for group,key,value in (('config','User','root'),('host','Memory',1),('host','Privileged',True),('host','NetworkMode','host')):
            row=copy.deepcopy(self.raw);row[group][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'admission-container-config-drift'):
                a.match_snapshot(c.raw(row),self.data,self.sha,PINS)
        row=copy.deepcopy(self.raw);row['mounts'][0]['Source']='/different'
        with self.assertRaisesRegex(ValueError,'admission-mount-drift'):a.match_snapshot(c.raw(row),self.data,self.sha,PINS)
    def test_preparation_and_gate_files_exist_before_dispatch(self):
        original=self.model.mutate
        def mutate(action,cid):
            self.assertTrue((self.registry/'retained-admission.json').exists())
            self.assertTrue(list(self.registry.glob('retained-gate-*.json')))
            return original(action,cid)
        self.backend.mutate=mutate
        with self.guard.open() as ctrl:
            for action in pc.ACTIONS:state=ctrl.step(action)
        self.assertTrue(state['original_restored']);self.assertEqual(self.guard.gates,4)
    def test_pressure_allows_stop_but_refuses_start(self):
        original=a.storage.sample
        with self.guard.open() as ctrl:
            ctrl.step('disable_restart')
            with patch.object(a.storage,'sample',side_effect=lambda fd:{**original(fd),'available_bytes':0}):
                ctrl.step('stop')
                with self.assertRaisesRegex(ValueError,'admission-storage-insufficient'):ctrl.step('start_original')
        self.assertEqual(self.model.calls,['disable_restart','stop'])
        self.assertEqual(pc.inspect(self.registry)['pending_action'],'start_original')
    def test_missing_preparation_never_dispatches(self):
        (self.registry/a.prep.RESULT).unlink()
        with self.assertRaisesRegex(ValueError,'admission-preparation-incomplete'):self.guard.open()
        self.assertEqual(self.model.calls,[])
    def test_consumed_gate_cannot_rearm_with_new_control(self):
        with self.guard.open():pass
        with self.assertRaises(FileExistsError):self.guard.open()
        self.assertEqual(self.model.calls,[])
    def test_gate_write_failure_after_intent_refuses_dispatch(self):
        original=c.write_new
        def fail(path,data):
            if path.name.startswith('retained-gate-'):raise OSError('fixture')
            return original(path,data)
        with self.guard.open() as ctrl:
            with patch.object(c,'write_new',side_effect=fail):
                with self.assertRaises(OSError):ctrl.step('disable_restart')
        self.assertEqual(pc.inspect(self.registry)['pending_action'],'disable_restart')
        self.assertEqual(self.model.calls,[])
    def test_replaced_capture_directory_blocks_restoration(self):
        with self.guard.open() as ctrl:
            ctrl.step('disable_restart');ctrl.step('stop')
            path=Path(self.paths['capture']);path.rename(self.root/'old-capture');path.mkdir(mode=0o700)
            with self.assertRaisesRegex(ValueError,'admission-storage-replaced'):ctrl.step('start_original')
        self.assertEqual(self.model.calls,['disable_restart','stop'])
    def test_mutation_without_journal_intent_refused(self):
        with self.guard.open():
            with self.assertRaisesRegex(ValueError,'admission-intent-required'):self.guard.mutate('disable_restart',self.backend.target['id'])
        self.assertEqual(self.model.calls,[])
    def test_changed_manifest_config_and_claim_refused(self):
        with self.guard.open() as ctrl:
            self.backend.admission['readiness_configuration_sha256']='e'*64
            with self.assertRaises(ValueError):ctrl.step('disable_restart')
        self.assertEqual(self.model.calls,[])
    def test_recovery_does_not_query_docker_or_storage(self):
        with self.guard.open() as ctrl:ctrl.step('disable_restart');ctrl.step('stop')
        before={p.name:p.read_bytes() for p in self.registry.iterdir()}
        with patch.object(self.backend,'observe',side_effect=AssertionError('docker')),patch.object(a.storage,'observe',side_effect=AssertionError('storage')):
            state=pc.inspect(self.registry)
        self.assertEqual(state['state'],'locally-stopped')
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.registry.iterdir()})

if __name__=='__main__':unittest.main()
