"""Combined retained-original/native-session acceptance; owned offline actors only."""
import argparse
from contextlib import ExitStack
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import shared_session as shared
import owned_fixture
import session_evidence as evidence
a=shared.a;c=shared.c;pc=shared.control;v=shared.supervisor
retained=owned_fixture.retained
CASES=('normal','cleanup-failure','lost-shared-confirmation','lost-restore-response',
       'invalid-credential','changed-capture','space-before-shared')


def pins():
    return {**shared.pins(),**retained.pins(),
            'scripts/r1-combined-control-kali.sh':c.digest((pc.ROOT/'scripts/r1-combined-control-kali.sh').read_bytes())}


def prepare(root,registry,backend,development):
    paths={role:str(root/role) for role in a.storage.ROLES}
    for path in paths.values():Path(path).mkdir(mode=0o700)
    config={k:None for k in a.m.CONFIG};policy={k:None for k in a.m.POLICY}
    config.update(scanner_image=backend.target['image'],scanner_config_sha256=backend.configuration_sha256,
        rollback_config_sha256=backend.target['config_sha256'],registry_path=str(registry),
        endpoint_path=str(registry/'discovery.sock'),capture_path=paths['capture'],
        owner_source_sha256=c.digest((v.r.ROOT/'worker.py').read_bytes()),credential_method='sealed-fd')
    policy.update(raw_bytes=65536,database_bytes=262144,journal_bytes=65536,receipt_bytes=65536,
        retained_runs=1,quarantined_runs=1,headroom_bytes=1024**2,research_seconds=2,service_seconds=3,
        setup_seconds=3 if development else 10,shutdown_seconds=3 if development else 5,
        memory_bytes=512*1024**2,cpu_seconds=10,open_files=64)
    plan=root/'manifest';sha=a.m.freeze(plan,a.m.build(config,policy))
    a.prep.prepare(plan,sha,paths)
    return plan,sha,paths


def exercise(root,registry,backend,name,*,development=False):
    """Shared path for actual Docker and a local Docker model; reports distinguish them."""
    c.check(name in CASES,'combined-case')
    plan,sha,paths=prepare(root,registry,backend,development)
    mode=('session-scanner-' if development else 'session-native-')+('cleanup-failure' if name=='cleanup-failure' else 'normal')
    guard=shared.SharedPrepared(backend,plan,sha,paths,mode=mode)
    row={'case':name,'started_utc':c.now(),'development':development,'manifest_sha256':sha,
         'registry':str(registry),'fault_reached':False,'commands':[],
         'production_modified':False,'provider_connection_opened':False,'activation_authorized':False}
    dispatch=backend.mutate
    def mutate(action,cid):
        row['commands'].append(action);ack=dispatch(action,cid)
        if name=='lost-restore-response' and action=='start_original':
            reached('after-original-start-ack');raise ValueError('combined-lost-start')
        return ack
    backend.mutate=mutate
    write=c.write_new
    def reached(stage):
        c.check(not row['fault_reached'],'combined-fault-repeated')
        row['fault_reached']=True
        write(root/'fault-ready.json',c.raw({'case':name,'stage':stage,'manifest_sha256':sha}))
    def lost(path,data):
        if path.name==shared.RESULT:
            reached('after-supervisor-closed-before-bridge-confirmation')
            raise OSError('combined-lost-shared')
        return write(path,data)
    def unsealed(raw):
        fd=os.memfd_create('r1-invalid-fixture',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
        try:
            os.fchmod(fd,0o600);c.check(os.write(fd,raw)==len(raw),'credential-fixture-write')
            reached('unsealed-descriptor-handed-to-worker');return fd
        except BaseException:os.close(fd);raise
    sample=a.storage.sample
    def pressure(fd):
        if not row['fault_reached']:reached('capacity-before-shared-start')
        return {**sample(fd),'available_bytes':0}
    try:
        with guard.open() as ctrl:
            ctrl.step('disable_restart');ctrl.step('stop')
            try:
                with ExitStack() as stack:
                    if name=='lost-shared-confirmation':stack.enter_context(patch.object(c,'write_new',side_effect=lost))
                    if name=='invalid-credential':stack.enter_context(patch.object(v.credential,'sealed',side_effect=unsealed))
                    if name=='space-before-shared':stack.enter_context(patch.object(a.storage,'sample',side_effect=pressure))
                    guard.run_shared()
                if name=='changed-capture':
                    path=Path(paths['capture'])/'supervised-session/session.jsonl'
                    data=path.read_bytes();write(root/'before-corruption.jsonl',data)
                    reached('capture-journal-after-shared-close')
                    with path.open('ab') as file:file.write(b'fixture-corruption\n');file.flush();os.fsync(file.fileno())
                ctrl.step('start_original');ctrl.step('restore_restart')
            except (ValueError,OSError) as exc:
                expected={'lost-shared-confirmation':'combined-lost-shared',
                    'lost-restore-response':'combined-lost-start','invalid-credential':'shared-shutdown-unconfirmed',
                    'changed-capture':'runtime-success-binding','space-before-shared':'admission-storage-insufficient'}
                c.check(row['fault_reached'] and name in expected and exc.args==(expected[name],),'combined-unexpected-failure')
                row['expected_refusal']=expected[name]
            else:c.check(name in ('normal','cleanup-failure'),'combined-fault-missed')
        before={p.name:p.read_bytes() for p in registry.iterdir() if p.is_file()}
        state=pc.inspect(registry);row['control_recovery']=state
        c.check(before=={p.name:p.read_bytes() for p in registry.iterdir() if p.is_file()},'combined-recovery-write')
        c.check(state['original_restored'] is (name in ('normal','cleanup-failure')),'combined-restoration-disposition')
        wanted=['disable_restart','stop']
        if name in ('normal','cleanup-failure'):wanted+=['start_original','restore_restart']
        if name=='lost-restore-response':wanted+=['start_original']
        c.check(row['commands']==wanted,'combined-command-order')
        if name in ('lost-restore-response','changed-capture'):
            c.check(state['pending_action']=='start_original','combined-pending-start')
        else:c.check(state['pending_action'] is None,'combined-pending-unexpected')
        if (registry/v.CLAIM).exists():
            if name=='changed-capture':
                try:v.inspect(registry,sha)
                except ValueError as exc:c.check(exc.args==('runtime-success-binding',),'combined-corruption-refusal')
                else:raise ValueError('combined-corruption-missed')
                row['supervision_recovery']='refused-changed-capture'
            else:
                row['supervision_recovery']=v.inspect(registry,sha)
                if name=='invalid-credential':
                    consumed,_=v.native_scanner.read(registry,'worker-credential.json')
                    c.check(consumed['status']=='refused' and row['supervision_recovery']['outcome']=='worker-failed',
                            'combined-credential-fault-not-reached')
                    c.check(row['supervision_recovery']['worker_reaped'],'combined-worker-not-reaped')
                else:
                    result=row['supervision_recovery']
                    c.check(result['outcome']==v.SUCCESS and result['worker_reaped'] and result['scanner']['reaped'],
                            'combined-shared-not-reaped')
                    c.check(result['terminal']['credential_descriptor_closed'],'combined-credential-not-closed')
                    if not development:
                        c.check(result['scanner']['removed'] and not result['scanner']['development'] and
                                result['terminal']['session_evidence']['native_peer']['container_parent_verified'],
                                'combined-native-peer')
        else:c.check(name=='space-before-shared','combined-supervision-missing')
        control=Path(paths['capture'])/'supervised-session'
        if control.exists():
            exported=evidence.export(control,Path(paths['export'])/'session')
            restored=evidence.restore(Path(paths['export'])/'session/evidence.zip',exported['sha256'],Path(paths['restore'])/'session')
            c.check(restored==exported['assessment'],'combined-restore-mismatch')
            row['preservation']=exported
            classification=restored['classification']
            if name=='changed-capture':c.check(classification=='quarantined-incomplete-evidence','combined-corruption-promoted')
            else:c.check(classification in ('closed-clean-session-evidence','closed-failed-session-evidence'),'combined-export-incomplete')
        else:
            c.check(name in ('space-before-shared','invalid-credential'),'combined-capture-missing')
            row['preservation']={'classification':'no-session-started-registry-retained'}
        row['status']='combined-case-passed-live-blocked'
        return row
    finally:
        backend.mutate=dispatch
        row['finished_utc']=c.now();write(root/'result.json',c.raw(row))


def bundle(out):
    # Explicit artifacts only; never walk arbitrary mounted/provider directories.
    members={};capture_snapshots={}
    def add(path,name,cap=2*1024**2):
        try:data=c.read(path,cap)
        except FileNotFoundError:return
        members[name]=data
    for name in ('report.json','validation.log'):add(out/name,name)
    for case in CASES:
        root=out/case
        if not root.exists():continue
        control=root/'capture/supervised-session'
        if control.exists():
            try:
                with ExitStack() as stack:
                    stack.enter_context(evidence.preserve.existing_lock(control/'capture.lock'))
                    if (control/'capture').exists():
                        stack.enter_context(evidence.preserve.existing_lock(control/'capture/capture.lock'))
                    snapshot=evidence.snapshot(control)
                    c.check(all(len(data)<=2*1024**2 for data in snapshot.values()),'combined-capture-bound')
                    c.check(evidence.snapshot(control)==snapshot,'combined-capture-changed')
                    for name,data in snapshot.items():members[case+'/capture-snapshot/'+name]=data
                capture_snapshots[case]='quiescent-byte-snapshot-not-a-success-claim'
            except Exception:
                capture_snapshots[case]='unavailable-retain-originals-no-quiescence-claim'
        else:capture_snapshots[case]='session-directory-absent'
        for name in ('result.json','fixture-intent.json','fixture-disposal.json','registry-path.json','fault-ready.json',
                     'before-corruption.jsonl','manifest/manifest.json','export/session/evidence.zip',
                     'export/session/report.json','restore/session/assessment.json'):
            add(root/name,case+'/'+name)
        path=root/'registry-path.json'
        if not path.exists():continue
        registry=Path(c.parse(c.read(path,4096))['registry'])
        names=('claim.json','events.jsonl','retained-admission.json',shared.CLAIM,shared.INTENT,shared.RESULT,
               a.prep.CLAIM,a.prep.RESULT,v.CLAIM,v.RESULT,'supervision-storage.json','worker-credential.json',
               v.native_scanner.ENDPOINT,v.native_scanner.INTENT,v.native_scanner.IDENTITY,v.native_scanner.PEER,
               'native-scanner-disposal.json')
        for name in names:add(registry/name,case+'/registry/'+name)
        for path in sorted(registry.glob('retained-gate-*.json')):add(path,case+'/registry/'+path.name)
    c.check(sum(map(len,members.values()))<=32*1024**2,'combined-bundle-bound')
    index={'schema':1,'kind':'combined-offline-acceptance-members',
           'members':{name:{'bytes':len(data),'sha256':c.digest(data)} for name,data in members.items()},
           'capture_snapshots':capture_snapshots,'activation_authorized':False,
           'remote_preservation_verified':False,'retention_verified':False}
    with zipfile.ZipFile(out/'acceptance.zip','x',compression=zipfile.ZIP_STORED) as archive:
        for name,data in sorted(members.items()):archive.writestr(name,data)
        archive.writestr('members.json',c.raw(index))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',required=True)
    args=parser.parse_args();os.umask(0o077);out=Path(args.output_directory).absolute()
    c.check(not out.exists() and all(not p.is_symlink() for p in (out,*out.parents)),'combined-output')
    out.mkdir(mode=0o700);log=io.StringIO();stage='source'
    report={'schema':1,'status':'combined-control-failed-live-blocked','started_utc':c.now(),
            'cases':[],'production_modified':False,'provider_connection_opened':False,'activation_authorized':False}
    try:
        report['source_sha256']=pins()
        c.check(not retained.image.c.git('status','--porcelain').strip(),'dirty-source')
        stage='local-regressions'
        import test_combined
        suite=unittest.defaultTestLoader.loadTestsFromModule(test_combined)
        tests=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        report['tests']={'run':tests.testsRun,'errors':len(tests.errors),'failures':len(tests.failures),'skipped':len(tests.skipped)}
        c.check(tests.wasSuccessful() and tests.testsRun>0 and not tests.skipped and
                not retained.image.DIAGNOSTIC.search(log.getvalue()),'tests')
        stage='host';retained.image.host.trusted_local_docker()
        c.check(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,'uid')
        config=out/'empty-docker-config';config.mkdir(mode=0o700)
        cli=[retained.image.host.DOCKER,'--config',str(config),'--host','unix://'+retained.image.host.SOCKET]
        c.check(retained.run(cli+['image','inspect','--format','{{.Id}}',c.IMAGE]).decode().strip()==c.IMAGE,'image-unavailable')
        for name in CASES:
            stage=name;root=out/name;root.mkdir(mode=0o700)
            registry=Path(tempfile.mkdtemp(prefix='r1cs-'))
            c.write_new(root/'registry-path.json',c.raw({'registry':str(registry)}))
            original=owned_fixture.Original(cli,root)
            try:report['cases'].append(exercise(root,registry,original.start(),name))
            finally:
                try:original.close()
                finally:c.write_new(root/'fixture-disposal.json',c.raw(original.receipt))
            c.check(original.receipt['removed'] and original.receipt['client_reaped'],'combined-original-disposal')
        c.check(pins()==report['source_sha256'] and not retained.image.c.git('status','--porcelain').strip(),'source-change')
        report['status']='combined-control-offline-passed-live-blocked'
    except BaseException as exc:
        report.update(failure_stage=stage,failure_type=type(exc).__name__,failure_code=retained.diagnostic(exc))
    finally:
        report['finished_utc']=c.now()
        c.write_new(out/'report.json',c.raw(report));c.write_new(out/'validation.log',log.getvalue().encode());bundle(out)
    print(report['status']);print(out/'acceptance.zip')
    return 0 if report['status']=='combined-control-offline-passed-live-blocked' else 1


if __name__=='__main__':raise SystemExit(main())
