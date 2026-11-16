import copy
import io
import json
import os
from pathlib import Path
import sqlite3
import struct
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch
import check_runtime as runtime
c=runtime.c;pc=runtime.pc


def expected():
    return {'manifest_sha256':'b'*64,'manifest':{'files':{'one':'c'*64},'source_tree':'d'*40}}


def result(case):
    missing=case=='missing-endpoint';normal=case=='normal'
    return {'schema':1,'kind':'full-scanner-runtime-probe','case':case,
        'identity':{'status':'image-bytes-verified','manifest_sha256':'b'*64,'files':1,'source_tree':'d'*40,'activation_authorized':False},
        'outcome':'startup-refused-before-storage' if missing else 'application-gap-and-shutdown-confirmed',
        'application_entrypoint_started':not missing,'upstream_attempts':0,'public_http_connections_opened':0,
        'blocked_public_http_attempts':0 if missing else 1,'loopback_http_checked':not missing,
        'overall_ready':None if missing else False,'provider_enabled':None if missing else True,
        'provider_state':None if missing else 'error','discovery_messages':3 if normal else 0,
        'discovery_gaps':0 if missing else 1,'candidates':3 if normal else 0,
        'persisted_candidates':None if missing else 3 if normal else 0,'persisted_launches':None if missing else 2 if normal else 0,
        'fixture_index_prepared':not missing,'statistics_worker_succeeded':not missing,
        'storage_created':not missing,'storage_closed':not missing,'radar_stopped':not missing,'activation_authorized':False}


def row(token,ipc,data,case):
    return {'id':'a'*64,'image':c.BASE,'name':'/fixture',
        'config':{'Labels':{runtime.LABEL:token},'User':'1000:1000','Entrypoint':pc.c.ENTRY,
            'Cmd':runtime.command(case),'StopSignal':'SIGTERM','StopTimeout':35},
        'host':{'RestartPolicy':{'Name':'no','MaximumRetryCount':0},'NetworkMode':'none',
            'ReadonlyRootfs':True,'Privileged':False,'Memory':512*1024**2,'MemorySwap':512*1024**2,
            'NanoCpus':1000000000,'PidsLimit':64,'Init':True,'CapDrop':['ALL'],'OomKillDisable':False,
            'SecurityOpt':['no-new-privileges:true'],'LogConfig':{'Type':'none'},'PortBindings':None},
        'mounts':[{'Type':'bind','Source':str(ipc),'Destination':'/r1-ipc','RW':False},
                  {'Type':'bind','Source':str(data),'Destination':'/r1-data','RW':True}],
        'running':False,'pid':0,'started':'2026-11-16T17:00:00Z','finished':'2026-11-16T17:00:01Z',
        'exit_code':0,'paused':False,'restarting':False,'dead':False,'oom':False,'error':''}


class RuntimeTests(unittest.TestCase):
    def test_receipt_requires_actual_application_storage_and_gap_evidence(self):
        good=result('normal');runtime.verify_result(good,expected(),'normal')
        for key,value in (('application_entrypoint_started',False),('provider_enabled',False),('overall_ready',True),
            ('upstream_attempts',1),('public_http_connections_opened',1),('persisted_launches',0),
            ('storage_closed',False),('radar_stopped',False),('statistics_worker_succeeded',False),
            ('fixture_index_prepared',False),('discovery_gaps',0),('activation_authorized',True)):
            with self.subTest(key=key),self.assertRaises(ValueError):runtime.verify_result({**good,key:value},expected(),'normal')

    def test_missing_endpoint_cannot_pass_after_storage_or_fetch_activity(self):
        good=result('missing-endpoint');runtime.verify_result(good,expected(),'missing-endpoint')
        for key,value in (('storage_created',True),('blocked_public_http_attempts',1),('candidates',1),('loopback_http_checked',True)):
            with self.subTest(key=key),self.assertRaises(ValueError):runtime.verify_result({**good,key:value},expected(),'missing-endpoint')

    def test_runtime_isolation_binds_command_mounts_identity_and_resources(self):
        ipc=Path('/tmp/fixture-ipc');data=Path('/tmp/fixture-data');good=row('token',ipc,data,'normal')
        runtime.isolation(c.raw(good),'token',c.BASE,ipc,data,'normal')
        for mutate in (lambda r:r['config'].update(Cmd=['/app/verify.mjs']),
            lambda r:r['config']['Labels'].update({runtime.LABEL:'foreign'}),
            lambda r:r['host'].update(NetworkMode='host'),lambda r:r['host'].update(Memory=0),
            lambda r:r['host'].update(PortBindings={'8787/tcp':[{'HostPort':'8787'}]}),
            lambda r:r['mounts'][0].update(RW=True),lambda r:r['mounts'][1].update(Source='/production'),
            lambda r:r.update(image='sha256:'+'f'*64)):
            changed=copy.deepcopy(good);mutate(changed)
            with self.assertRaises(ValueError):runtime.isolation(c.raw(changed),'token',c.BASE,ipc,data,'normal')

    def test_kernel_peer_requires_exact_running_container_parent(self):
        peer={'pid':123,'uid':1000,'gid':1000,'process':{'pid':123,'ppid':100,'start_ticks':999}}
        target={'running':True,'pid':100};runtime.validate_peer(peer,target)
        for changed in ({**peer,'uid':0},{**peer,'pid':124},{**peer,'process':{**peer['process'],'ppid':101}}):
            with self.assertRaises(ValueError):runtime.validate_peer(changed,target)
        with self.assertRaises(ValueError):runtime.validate_peer(peer,{'running':False,'pid':0})

    def exercise(self,name,*,foreign=False,lost_create=False,drift=False,oom_default_change=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ipc=root/'ipc';ipc.mkdir(mode=0o700);calls=[];receipts=[];state={};sent=threading.Event();started=threading.Event()
            class Conn:
                def __enter__(self):return self
                def __exit__(self,*_):pass
                def settimeout(self,_):pass
                def getsockopt(self,*_):return struct.pack('3i',123,1000,1000)
                def sendall(self,_):pass
                def shutdown(self,_):sent.set()
                def recv(self,_):return b''
            class Server:
                def settimeout(self,_):pass
                def bind(self,path):Path(path).touch(mode=0o600)
                def listen(self,_):pass
                def accept(self):
                    if not started.wait(3):raise ValueError('model-not-started')
                    return Conn(),None
                def close(self):pass
            def command(args,**kwargs):
                action=args[0];calls.append(action)
                if action=='create':
                    token=args[args.index('--label')+1].split('=',1)[1]
                    state['row']=row('foreign' if foreign else token,ipc,root/name/'data',name)
                    self.assertTrue((root/name/'create-intent.json').exists())
                    if lost_create:raise ValueError('model-lost-create')
                    return b'a'*64+b'\n'
                if action=='inspect':return c.raw(state['row'])
                if action=='start':
                    self.assertTrue((root/name/'start-intent.json').exists())
                    state['row'].update(running=True,pid=100)
                    if oom_default_change:state['row']['host']['OomKillDisable']=None
                    if drift:state['row']['config']['AttachStdout']=True
                    started.set()
                    if name!='missing-endpoint':
                        if not sent.wait(3):raise ValueError('model-not-admitted')
                        database=root/name/'data/radar.sqlite'
                        connection=sqlite3.connect(database)
                        try:
                            connection.executescript('CREATE TABLE candidates(id);CREATE TABLE launch_registry(id);')
                            if name=='normal':connection.executescript('INSERT INTO candidates VALUES(1),(2),(3);INSERT INTO launch_registry VALUES(1),(2);')
                            connection.commit()
                        finally:connection.close()
                        database.chmod(0o600)
                    state['row'].update(running=False,pid=0)
                    return c.raw(result(name))
                if action=='rm':return b'a'*64+b'\n'
                raise AssertionError(action)
            with patch.object(runtime,'run',side_effect=command),patch.object(runtime.socket,'socket',return_value=Server()),\
                 patch.object(runtime.tempfile,'mkdtemp',return_value=str(ipc)),\
                 patch.object(runtime,'proc_identity',return_value={'pid':123,'ppid':100,'start_ticks':999}):
                if foreign or lost_create or drift:
                    with self.assertRaises(ValueError):runtime.case(root,[],c.BASE,expected(),name,{'cases':receipts})
                else:runtime.case(root,[],c.BASE,expected(),name,{'cases':receipts})
            return calls,receipts

    def test_full_checker_connects_peer_dispatch_storage_replay_and_cleanup(self):
        for name in runtime.CASES:
            with self.subTest(case=name):
                calls,receipts=self.exercise(name)
                self.assertTrue(receipts[0]['removed']);self.assertTrue(receipts[0]['threads_joined'])
                self.assertTrue(receipts[0]['attach_client_completed']);self.assertIn('start',calls)

    def test_foreign_container_never_starts_or_is_removed(self):
        calls,receipts=self.exercise('missing-endpoint',foreign=True)
        self.assertNotIn('start',calls);self.assertNotIn('rm',calls);self.assertFalse(receipts[0]['removed'])

    def test_uncertain_create_only_disposes_owned_name(self):
        calls,receipts=self.exercise('missing-endpoint',lost_create=True)
        self.assertNotIn('start',calls);self.assertEqual(calls,['create','inspect','rm'])
        self.assertTrue(receipts[0]['removed']);self.assertFalse(receipts[0]['attach_client_completed'])

    def test_configuration_drift_stays_failed_but_preserves_result_and_final_observation(self):
        calls,receipts=self.exercise('normal',drift=True);r=receipts[0]
        self.assertTrue(r['removed']);self.assertTrue(r['threads_joined'])
        runtime.verify_result(r['result'],expected(),'normal')
        self.assertFalse(r['after']['running']);self.assertEqual(r['after']['exit_code'],0)
        self.assertNotEqual(r['before']['config_sha256'],r['after']['config_sha256'])
        changes=r['after_changes_from_created'];self.assertEqual(set(changes),{'/config/AttachStdout'})
        self.assertIsNone(changes['/config/AttachStdout']['before'])
        self.assertEqual(changes['/config/AttachStdout']['after']['value'],True)
        self.assertEqual(r['disposal_observation'],r['after'])

    def test_configuration_diagnostics_hash_environment_commands_and_paths(self):
        raw=row('token',Path('/tmp/private-ipc'),Path('/tmp/private-data'),'normal')
        raw['config']['Env']=['PRIVATE_VALUE=secret-fixture-sentinel'];raw['config']['Cmd']=['secret-argument-sentinel']
        fields=runtime.configuration_fields(c.raw(raw));encoded=c.raw(fields)
        self.assertNotIn(b'secret-fixture-sentinel',encoded);self.assertNotIn(b'secret-argument-sentinel',encoded)
        self.assertNotIn(b'/tmp/private',encoded)
        self.assertEqual(fields['/host/Memory']['value'],512*1024**2)
        self.assertEqual(fields['/config/Env/0']['sha256'],c.digest(c.raw(raw['config']['Env'][0])))

    def test_only_explicit_false_and_null_oom_defaults_are_equivalent(self):
        raw=row('token',Path('/tmp/ipc'),Path('/tmp/data'),'normal');before=runtime.configuration_fields(c.raw(raw))
        changed=copy.deepcopy(raw);changed['host']['OomKillDisable']=None
        after=runtime.configuration_fields(c.raw(changed));self.assertTrue(runtime.equivalent_configuration(before,after))
        for value in (True,0,'false',[],{}):
            invalid=copy.deepcopy(changed);invalid['host']['OomKillDisable']=value
            fields=runtime.configuration_fields(c.raw(invalid));self.assertFalse(runtime.equivalent_configuration(before,fields))
            with self.assertRaisesRegex(ValueError,'runtime-oom-policy'):
                runtime.isolation(c.raw(invalid),'token',c.BASE,Path('/tmp/ipc'),Path('/tmp/data'),'normal')
        missing=copy.deepcopy(raw);del missing['host']['OomKillDisable']
        self.assertFalse(runtime.equivalent_configuration(before,runtime.configuration_fields(c.raw(missing))))
        with self.assertRaisesRegex(ValueError,'runtime-oom-policy'):
            runtime.isolation(c.raw(missing),'token',c.BASE,Path('/tmp/ipc'),Path('/tmp/data'),'normal')
        changed['host']['Memory']=1
        self.assertFalse(runtime.equivalent_configuration(before,runtime.configuration_fields(c.raw(changed))))
        forged=copy.deepcopy(after);forged['/host/OomKillDisable']['sha256']='0'*64
        self.assertFalse(runtime.equivalent_configuration(before,forged))

    def test_reviewed_oom_representation_preserves_raw_hashes_and_allows_completed_case(self):
        _,receipts=self.exercise('normal',oom_default_change=True);r=receipts[0]
        self.assertTrue(r['removed']);self.assertTrue(r['result']['storage_closed'])
        self.assertNotEqual(r['before']['config_sha256'],r['after']['config_sha256'])
        self.assertEqual(set(r['after_changes_from_created']),{'/host/OomKillDisable'})
        self.assertEqual(r['configuration_comparison'],'exact-fields-except-reviewed-oom-default-false-null')

    def test_diagnostic_candidate_requires_exact_previously_verified_packaged_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/'context';staged=c.stage(destination,clean=False)
            with patch.object(c,'stage',return_value=copy.deepcopy(staged)):
                result=runtime.diagnostic_candidate(destination)
            self.assertEqual(result['manifest_sha256'],runtime.DIAGNOSTIC_MANIFEST)
            self.assertEqual(result['manifest']['source_revision'],runtime.DIAGNOSTIC_REVISION)
            changed=copy.deepcopy(staged);changed['manifest']['files']['runtime-probe.mjs']='0'*64
            with patch.object(c,'stage',return_value=changed),self.assertRaisesRegex(ValueError,'runtime-diagnostic-source-drift'):
                runtime.diagnostic_candidate(destination)

    def exercise_existing_image_mode(self,remaining):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'results';suite=unittest.TestSuite([unittest.FunctionTestCase(lambda:None)])
            image_config={'id':runtime.DIAGNOSTIC_IMAGE,'user':'1000:1000','entrypoint':pc.c.ENTRY,'cmd':['/app/verify.mjs'],'workdir':'/app'}
            flag='--remaining-existing-image' if remaining else '--diagnose-existing-image'
            with patch.object(runtime.sys,'argv',['check_runtime.py','--output-directory',str(out),flag]),\
                 patch.object(runtime,'pins',return_value={}),patch.object(c,'git',return_value=b''),\
                 patch.object(runtime.unittest.defaultTestLoader,'loadTestsFromModule',return_value=suite),\
                 patch.object(runtime,'diagnostic_candidate',return_value=expected()),\
                 patch.object(runtime.image.host,'trusted_local_docker'),\
                 patch.object(runtime,'run',side_effect=[(runtime.DIAGNOSTIC_IMAGE+'\n').encode(),c.raw(image_config)]) as command,\
                 patch.object(runtime.image,'bounded') as build,patch.object(runtime.image,'run_case') as verifier,\
                 patch.object(runtime,'case') as app,patch.object(runtime.sys,'stdout',io.StringIO()):
                self.assertEqual(runtime.main(),0)
            build.assert_not_called();verifier.assert_not_called();self.assertEqual(command.call_count,2)
            self.assertEqual([call.args[4] for call in app.call_args_list],['sequence-gap','missing-endpoint'] if remaining else ['normal'])
            self.assertTrue(all(call.args[2]==runtime.DIAGNOSTIC_IMAGE for call in app.call_args_list))
            report=json.loads((out/'report.json').read_bytes());self.assertEqual(report['diagnostic_only'],not remaining)
            self.assertEqual(report['remaining_only'],remaining)
            self.assertEqual(report['status'],'scanner-runtime-remaining-cases-passed-live-blocked' if remaining else 'scanner-runtime-diagnostic-recorded-live-blocked')
            if remaining:self.assertEqual(report['accepted_normal_evidence'],runtime.ACCEPTED_NORMAL)
            else:self.assertNotIn('accepted_normal_evidence',report)
            self.assertFalse((out/'deployment-candidate.json').exists());self.assertFalse((out/'build-intent.json').exists())

    def test_diagnostic_runs_only_normal_on_existing_image_without_build_or_candidate(self):
        self.exercise_existing_image_mode(False)

    def test_remaining_mode_runs_only_unobserved_cases_and_references_historical_normal(self):
        self.exercise_existing_image_mode(True)

    def test_failed_preparation_still_exports_indexed_evidence_without_host_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'results'
            suite=unittest.TestSuite([unittest.FunctionTestCase(lambda:None)])
            with patch.object(runtime.sys,'argv',['check_runtime.py','--output-directory',str(out)]),\
                 patch.object(runtime,'pins',return_value={}),patch.object(c,'git',return_value=b''),\
                 patch.object(runtime.unittest.defaultTestLoader,'loadTestsFromModule',return_value=suite),\
                 patch.object(runtime.shutil,'which',return_value='/fixture/node'),\
                 patch.object(runtime,'run',return_value=b'# tests 18\n# fail 0\n# cancelled 0\n# skipped 0\n') as command,\
                 patch.object(c,'stage',side_effect=ValueError('model-context-failure')),\
                 patch.object(runtime.sys,'stdout',io.StringIO()):
                self.assertEqual(runtime.main(),1)
            self.assertEqual(command.call_count,1)
            with zipfile.ZipFile(out/'acceptance.zip') as archive:
                report=json.loads(archive.read('report.json'));self.assertEqual(report['failure_stage'],'context')
                self.assertEqual(report['cases'],[]);self.assertFalse(report['activation_authorized'])
                members=json.loads(archive.read('members.json'))['members']
                self.assertEqual(set(archive.namelist()),set(members)|{'members.json'})
                for name,identity in members.items():
                    raw=archive.read(name);self.assertEqual(identity,{'bytes':len(raw),'sha256':c.digest(raw)})


if __name__=='__main__':unittest.main()
