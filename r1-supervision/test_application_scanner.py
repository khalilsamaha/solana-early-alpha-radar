"""New application/session contract tests; no Docker or kernel-peer claims."""
import asyncio
import copy
import io
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
import application_scanner as app
import capture_session as session
import manifest_supervisor as v
import native_scanner as native
import test_capture_session as fixture
import sys
sys.path.insert(0,str(app.r.ROOT.parent/'r1-image'))
from test_runtime import result as runtime_result
m=app.m


def result():
    row=runtime_result('normal')
    row['identity']={'status':'image-bytes-verified','manifest_sha256':app.MANIFEST,'files':60,
                     'source_tree':app.TREE,'activation_authorized':False}
    return row


def target(registry,token='a'*32):
    return {'id':'b'*64,'image':app.IMAGE,'label':token,'user':'1000:1000','network':'none',
        'readonly':True,'privileged':False,'restart':'no','memory':512*1024**2,'swap':512*1024**2,
        'pids':64,'cpus':1000000000,'init':True,'logging':'none','caps':['ALL'],
        'cmd':app.COMMAND,'entrypoint':app.n.c.ENTRY,'security':['no-new-privileges:true'],
        'running':True,'pid':123,'exit_code':0,'started':'2026-11-17T10:00:00Z','finished':'0001-01-01T00:00:00Z',
        'mounts':[{'Type':'bind','Source':str(registry),'Destination':'/r1-ipc','RW':False,'Propagation':'rprivate'},
                  {'Type':'bind','Source':str(registry/app.DATA),'Destination':'/r1-data','RW':True,'Propagation':'rprivate'}]}


def database(registry):
    folder=registry/app.DATA;folder.mkdir(mode=0o700,exist_ok=True)
    path=folder/'radar.sqlite'
    with closing(sqlite3.connect(path)) as db:
        db.executescript('CREATE TABLE candidates(id);CREATE TABLE launch_registry(id);'
                         'INSERT INTO candidates VALUES(1),(2),(3);INSERT INTO launch_registry VALUES(1),(2);')
        db.commit()
    path.chmod(0o600)
    return path


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.registry=Path(self.tmp.name)

    def test_identity_shutdown_statistics_and_network_are_required(self):
        good=result();app.validate_result(good)
        for key,value in (('storage_closed',False),('radar_stopped',False),('statistics_worker_succeeded',False),
                          ('upstream_attempts',1),('public_http_connections_opened',1),('discovery_messages',2),
                          ('activation_authorized',True),('identity',{**good['identity'],'files':59}),
                          ('identity',{**good['identity'],'activation_authorized':0})):
            with self.subTest(key=key),self.assertRaises(ValueError):app.validate_result({**good,key:value})

    def test_isolation_binds_separate_image_command_and_mount_authority(self):
        row=target(self.registry);app.isolation(row,row['label'],self.registry)
        for mutate in (lambda r:r.update(image=app.n.c.IMAGE),lambda r:r.update(cmd=['/app/verify.mjs']),
                       lambda r:r.update(network='host'),lambda r:r.update(privileged=True),
                       lambda r:r['mounts'][0].update(RW=True),lambda r:r['mounts'][1].update(Source='/production'),
                       lambda r:r['mounts'][1].update(Destination='/r1-ipc'),lambda r:r.update(memory=True)):
            changed=copy.deepcopy(row);mutate(changed)
            with self.assertRaises(ValueError):app.isolation(changed,row['label'],self.registry)

    def test_only_mount_order_changes_compare_equal(self):
        row=target(self.registry);changed=copy.deepcopy(row);changed['mounts'].reverse()
        self.assertEqual(app.comparable(row),app.comparable(changed))
        changed['mounts'][0]['Propagation']='shared'
        self.assertNotEqual(app.comparable(row),app.comparable(changed))

    def test_native_completion_accepts_reordered_mounts_but_no_identity_changes(self):
        database(self.registry);actor=app.Actor([],self.registry);initial=target(self.registry,actor.token)
        stopped={**initial,'running':False,'pid':0,'finished':'2026-11-17T10:00:01Z'}
        receipt={**actor.receipt(),'created':True,'ready':True,'removed':True,'client_reaped':True,
            'id':initial['id'],'initial':initial,'observations':[initial,stopped],'result':result(),
            'application_storage':app.storage_proof(self.registry),'application_capacity':{'available_bytes':4*app.MAX_STORAGE}}
        proc={'pid':123,'ppid':122,'start_ticks':456}
        row={'kind':'isolated-native-scanner','development':False,'started':1,'reaped':True,'returncode':0,
            'result':result(),'actor':receipt,'removed':True,'process_identity':proc,'activation_authorized':False}
        recorded=copy.deepcopy(initial);recorded['mounts'].reverse()
        identity={'actor':recorded,'process_identity':proc}
        with patch.object(native,'read',return_value=(identity,m.raw(identity))):
            native.validate(row,app.MODE,complete=True,registry=self.registry)
        self.assertTrue(native.same_actor_identity(recorded,initial,app.MODE))
        self.assertFalse(native.same_actor_identity(recorded,initial,'session-native-normal'))
        for mutate in (lambda x:x.update(pid=124),lambda x:x.update(image=app.n.c.IMAGE),
                       lambda x:x.update(memory=x['memory']+1),lambda x:x['mounts'][0].update(RW=False),
                       lambda x:x['mounts'][0].update(Source='/other'),lambda x:x['mounts'][0].update(Propagation='shared')):
            changed=copy.deepcopy(recorded);mutate(changed);bad={'actor':changed,'process_identity':proc}
            with patch.object(native,'read',return_value=(bad,m.raw(bad))):
                with self.assertRaisesRegex(ValueError,'native-receipt-identity'):
                    native.validate(row,app.MODE,complete=True,registry=self.registry)

    def test_exact_sqlite_replay_is_read_only_and_detects_changes(self):
        path=database(self.registry);before=path.read_bytes();proof=app.storage_proof(self.registry)
        self.assertEqual(path.read_bytes(),before);self.assertEqual(proof['sha256'],m.digest(before))
        self.assertEqual(proof['counts'],{'candidates':3,'launch_registry':2})
        with closing(sqlite3.connect(path)) as db:db.execute('DELETE FROM candidates');db.commit()
        with self.assertRaisesRegex(ValueError,'application-database-replay'):app.storage_proof(self.registry)

    def test_storage_rejects_link_extra_large_file_and_nonprivate_database(self):
        path=database(self.registry);link=path.parent/'extra';link.symlink_to(path)
        with self.assertRaisesRegex(ValueError,'application-storage-link'):app.storage_proof(self.registry)
        link.unlink();link.write_bytes(b'x'*(app.MAX_STORAGE+1))
        with self.assertRaisesRegex(ValueError,'application-storage-bound'):app.storage_proof(self.registry)
        link.unlink();path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'preparation-private-file'):app.storage_proof(self.registry)

    def test_lost_completion_never_sets_application_success(self):
        actor=app.Actor([],self.registry);actor.process=object()
        with self.assertRaisesRegex(ValueError,'application-client-unconfirmed'):
            actor.finish(time.monotonic()+1,lambda *_:(None,'timeout'))
        self.assertIsNone(actor.result);self.assertIsNone(actor.database)

    def test_stopped_generation_and_database_required_before_success(self):
        database(self.registry);actor=app.Actor([],self.registry);actor.initial=target(self.registry,actor.token)
        actor.process=object();stopped={**actor.initial,'running':False,'pid':0,'finished':'2026-11-17T10:00:01Z'}
        with patch.object(actor,'observe',return_value=stopped):
            actor.finish(time.monotonic()+1,lambda *_:(m.raw(result()),'returned'))
        self.assertEqual(actor.result,result());self.assertEqual(actor.database,app.storage_proof(self.registry))
        for key,value in (('exit_code',1),('pid',123),('started','different-generation'),('running',True)):
            with self.assertRaises(ValueError):actor.expect_stopped({**stopped,key:value})

    def test_receipt_rechecks_database_and_disposal(self):
        path=database(self.registry);actor=app.Actor([],self.registry);row=target(self.registry,actor.token)
        receipt={**actor.receipt(),'created':True,'ready':True,'removed':True,'client_reaped':True,'id':row['id'],'initial':row,
            'observations':[row,{**row,'running':False,'pid':0,'finished':'2026-11-17T10:00:01Z'}],'result':result(),'application_storage':app.storage_proof(self.registry),
            'application_capacity':{'available_bytes':4*app.MAX_STORAGE}}
        app.validate_actor_receipt(receipt,self.registry,complete=True)
        for key in ('removed','client_reaped'):
            with self.assertRaises(ValueError):app.validate_actor_receipt({**receipt,key:False},self.registry,complete=True)
        with closing(sqlite3.connect(path)) as db:db.execute('UPDATE candidates SET id=9 WHERE id=1');db.commit()
        with self.assertRaisesRegex(ValueError,'application-storage-evidence'):
            app.validate_actor_receipt(receipt,self.registry,complete=True)

    def test_full_storage_hash_detects_same_size_nonprimary_file_change(self):
        database(self.registry);extra=self.registry/app.DATA/'statistics-cache';extra.write_bytes(b'abcd');extra.chmod(0o600)
        before=app.storage_proof(self.registry);extra.write_bytes(b'abce');after=app.storage_proof(self.registry)
        self.assertEqual(before['sha256'],after['sha256']);self.assertEqual(before['counts'],after['counts'])
        self.assertEqual(before['storage_bytes'],after['storage_bytes']);self.assertNotEqual(before['file_sha256'],after['file_sha256'])

    def test_expired_deadline_prevents_create_and_remaining_time_bounds_observation(self):
        actor=app.Actor(['docker-model'],self.registry)
        with patch.object(app.time,'monotonic',return_value=100),patch.object(app.check,'run',side_effect=AssertionError('dispatch')):
            with self.assertRaisesRegex(ValueError,'application-deadline'):actor.start(99)
        self.assertFalse(actor.attempted);self.assertFalse((self.registry/app.DATA).exists())
        with patch.object(app.time,'monotonic',return_value=100),patch.object(app.check,'run',return_value=m.raw(target(self.registry,actor.token))) as run:
            actor.observe(100.25)
        self.assertEqual(run.call_args.kwargs['seconds'],.25)

    def test_expired_run_deadline_does_not_disable_owned_cleanup(self):
        actor=app.Actor(['docker-model'],self.registry);actor.attempted=True
        with patch.object(app.time,'monotonic',return_value=100),patch.object(app.check,'run',return_value=m.raw(target(self.registry,actor.token))) as run,\
             patch.object(app.n.image,'bounded',return_value=b'b'*64+b'\n'):
            with self.assertRaisesRegex(ValueError,'application-deadline'):actor.observe(99)
            actor.dispose()
        self.assertTrue(actor.removed);self.assertEqual(run.call_args.kwargs['seconds'],4)

    def test_expiry_during_create_blocks_attach_and_keeps_owned_disposal_available(self):
        actor=app.Actor(['docker-model'],self.registry);now=[100.0];calls=[]
        def command(args,**kwargs):
            calls.append((args[1],kwargs['seconds']))
            if args[1]=='create':now[0]=101;return b'b'*64+b'\n'
            return m.raw({**target(self.registry,actor.token),'running':False,'pid':0})
        with patch.object(app.time,'monotonic',side_effect=lambda:now[0]),patch.object(app.check,'run',side_effect=command),\
             patch.object(app.subprocess,'Popen',side_effect=AssertionError('late attach')),\
             patch.object(app.n.image,'bounded',return_value=b'b'*64+b'\n'):
            with self.assertRaisesRegex(ValueError,'application-deadline'):actor.start(100.5)
            self.assertTrue(actor.created);self.assertFalse(actor.ready);self.assertEqual(calls,[('create',.5)])
            actor.dispose()
        self.assertTrue(actor.removed);self.assertEqual(calls[-1],('inspect',4))

    def test_uncertain_create_uses_owned_name_for_cleanup(self):
        actor=app.Actor(['docker-model'],self.registry);calls=[]
        def command(args,**kwargs):
            calls.append(args)
            if args[1]=='create':return b'uncertain-response\n'
            self.assertEqual(args[1],'inspect');self.assertEqual(args[-1],actor.name)
            return m.raw({**target(self.registry,actor.token),'running':False,'pid':0})
        with patch.object(app.check,'run',side_effect=command),\
             patch.object(app.n.image,'bounded',return_value=b'b'*64+b'\n'):
            with self.assertRaisesRegex(ValueError,'application-create-id'):actor.start()
            self.assertIsNone(actor.cid);actor.dispose()
        self.assertTrue(actor.removed);self.assertFalse(actor.created)

    def test_modeled_full_actor_lifecycle_preserves_identity_and_requires_stopped_storage(self):
        actor=app.Actor(['docker-model'],self.registry);state=target(self.registry,actor.token)
        state.update(running=False,pid=0);calls=[]
        class Process:
            returncode=None;stdin=None;stdout=io.BytesIO()
            def poll(self):return self.returncode
            def wait(self,**kwargs):return self.returncode
        process=Process()
        def command(args,**kwargs):
            calls.append(args[1])
            if args[1]=='create':return b'b'*64+b'\n'
            if args[1]=='inspect':return m.raw(state)
            self.assertEqual(args[1:],[ 'rm','--force','b'*64]);return b'b'*64+b'\n'
        def spawn(args,**kwargs):
            self.assertEqual(args[1:],['start','--attach','b'*64])
            state.update(running=True,pid=123);return process
        def collect(*_):
            database(self.registry);process.returncode=0
            state.update(running=False,pid=0,finished='2026-11-17T10:00:01Z')
            return m.raw(result()),'returned'
        with patch.object(app.check,'run',side_effect=command),patch.object(app.subprocess,'Popen',side_effect=spawn),\
             patch.object(app.n.image,'bounded',side_effect=command):
            actor.start();actor.stable();actor.finish(time.monotonic()+1,collect);actor.dispose()
        self.assertTrue(process.stdout.closed);self.assertEqual(calls.count('create'),1);self.assertEqual(calls.count('rm'),1)
        app.validate_actor_receipt(actor.receipt(),self.registry,complete=True)

    def test_foreign_cleanup_target_is_never_removed(self):
        actor=app.Actor(['docker-model'],self.registry);actor.attempted=True
        with patch.object(app.check,'run',return_value=m.raw(target(self.registry,'f'*32))),\
             patch.object(app.n.image,'bounded',side_effect=AssertionError('remove')):
            with self.assertRaisesRegex(ValueError,'application-isolation'):actor.dispose()
        self.assertFalse(actor.removed)


class ApplicationSessionTests(unittest.TestCase):
    def setUp(self):
        fixture.CaptureSessionTests.setUp(self)
        self.config.update(scanner_image=app.n.c.IMAGE,shared_scanner_image=app.IMAGE,shared_scanner_manifest_sha256=app.MANIFEST)
        self.policy.update(shutdown_seconds=5,setup_seconds=10)
        self.manifest=m.build(self.config,self.policy)

    def test_profile_keeps_original_and_application_images_separate(self):
        session.validate_mode(self.manifest,app.MODE)
        self.assertNotEqual(self.manifest['config']['scanner_image'],self.manifest['config']['shared_scanner_image'])
        for key,value in (('shared_scanner_image',app.n.c.IMAGE),('shared_scanner_manifest_sha256','f'*64)):
            with self.assertRaisesRegex(ValueError,'application-manifest-image'):
                session.validate_mode(m.build({**self.config,key:value},self.policy),app.MODE)
        with self.assertRaisesRegex(ValueError,'application-mode-binding'):
            session.validate_mode(self.manifest,'session-native-normal')
        with self.assertRaisesRegex(ValueError,'application-native-only'):
            v.run(self.plan,self.sha,mode=app.MODE,native_development=True)

    def test_finite_owner_retires_once_then_delivers_third_distinct_discovery(self):
        seen=[]
        class Server(session.fixtures.TestServer):
            async def start(server):
                server.accepted=True;server.connected.set()
                async def drain():
                    try:
                        while True:
                            seen.append(await server.owner.discovery.recv());server.progress['frames_sent']+=1
                    except session.capture.CaptureError:pass
                server.task=asyncio.create_task(drain())
        with patch.object(native,'server_class',return_value=Server):
            asyncio.run(session.exercise(self.manifest,app.MODE))
        self.assertEqual(len(seen),3)
        # Use the actual discovery envelopes, not a modeled success receipt.
        self.assertEqual(len({m.parse(row)['event']['mint'] for row in seen}),3)
        root=session.directory(self.manifest)
        retired=m.parse((root/'research-retired.json').read_bytes());stopped=m.parse((root/'stopped.json').read_bytes())
        self.assertTrue(retired['research_cannot_rearm']);self.assertTrue(retired['discovery_continues'])
        self.assertEqual(stopped['owner']['research_attachments'],1);self.assertTrue(stopped['local_upstream_closed'])
        self.assertTrue(stopped['capture_thread_joined'])


if __name__=='__main__':unittest.main()
