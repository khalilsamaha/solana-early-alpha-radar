"""Consolidated isolated integration. Never reads production configuration."""
import argparse
from contextlib import ExitStack, redirect_stderr
import io
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import bridge as b
m=b.m;s=b.s;p=b.p;n=b.n;h=b.h;c=b.c
CASES=('normal','space-before-owner','space-before-restore','missing-preparation-result')


def fixture(root,registry):
    paths={role:str(root/role) for role in s.ROLES}
    for path in paths.values():Path(path).mkdir(mode=0o700)
    config={key:None for key in m.CONFIG};policy={key:None for key in m.POLICY}
    config.update(scanner_image=c.IMAGE,registry_path=str(registry),endpoint_path=str(registry/'discovery.sock'),
                  capture_path=paths['capture'],owner_source_sha256=m.digest((n.ROOT/'broker.py').read_bytes()))
    policy.update(raw_bytes=1024,database_bytes=4096,journal_bytes=4096,receipt_bytes=65536,
                  retained_runs=1,quarantined_runs=1,headroom_bytes=1024**2)
    manifest=m.build(config,policy);directory=root/'manifest';sha=m.freeze(directory,manifest)
    return directory,sha,paths


def run_case(out,cli,name,development):
    root=out/name;root.mkdir(mode=0o700)
    registry=Path(tempfile.mkdtemp(prefix='r1ph-'))
    c.write_new(root/'registry-path.json',m.raw({'registry':str(registry)}))
    directory,sha,paths=fixture(root,registry)
    backend=n.Backend(root,registry,cli,'unsubscribed',development)
    guard=b.Guard(backend,directory,sha,paths)
    result={'case':name,'started_utc':c.now(),'manifest_sha256':sha,'registry':str(registry),
            'fixture_policy':True,'development':development,'fault_reached':False,
            'provider_connection_opened':False,'production_modified':False,'activation_authorized':False}
    try:
        if name=='missing-preparation-result':
            original=p.write_at
            def write(fd,filename,value):
                if filename==p.RESULT:
                    result['fault_reached']=True
                    c.write_new(root/'fault-ready.json',m.raw({'stage':'before-preparation-result','manifest_sha256':sha}))
                    raise OSError('fixture-interruption')
                return original(fd,filename,value)
            try:
                with patch.object(p,'write_at',side_effect=write):p.prepare(directory,sha,paths)
            except OSError:
                c.check(result['fault_reached'],'unexpected-preparation-failure')
            else:raise ValueError('missing-preparation-fault')
            try:guard.prepare()
            except ValueError as exc:c.check(str(exc)=='preparation-not-complete','unexpected-start-refusal')
            else:raise ValueError('unresolved-preparation-started')
            c.check(not backend.actors,'unresolved-preparation-actors')
            result['recovery']=None
        else:
            p.prepare(directory,sha,paths)
            proof=guard.prepare()
            with h.Coordinator(registry,proof,guard) as coordinator:
                backend.bind_plan(coordinator.claim)
                with ExitStack() as stack:
                    for action in h.ACTIONS:
                        if (name=='space-before-owner' and action=='start_owner' or
                                name=='space-before-restore' and action=='retire_research'):
                            original=s.sample
                            def pressure(fd):return {**original(fd),'available_bytes':0}
                            stack.enter_context(patch.object(s,'sample',side_effect=pressure))
                            result['fault_reached']=True
                            c.write_new(root/'fault-ready.json',m.raw({'stage':action,'manifest_sha256':sha}))
                        try:coordinator.step(action)
                        except ValueError as exc:
                            expected='start_owner' if name=='space-before-owner' else 'restore_direct'
                            c.check(result['fault_reached'] and action==expected and str(exc)=='storage-no-start-headroom',
                                    'unexpected-handoff-failure')
                            break
            state=h.inspect(registry);result['recovery']=state
            expected={'normal':None,'space-before-owner':'start_owner','space-before-restore':'restore_direct'}[name]
            c.check(state['pending_action']==expected and state['complete']==(name=='normal'),'handoff-disposition')
            if name=='space-before-restore':
                c.check(backend.stopped and backend.retired and backend.restores==0,'shutdown-under-pressure')
            if name=='space-before-owner':c.check(not backend.shared and not backend.restores,'owner-started-under-pressure')
        before={f.name:f.read_bytes() for f in registry.iterdir() if f.is_file()}
        result['preparation_recovery']=p.inspect(registry,sha)
        c.check(before=={f.name:f.read_bytes() for f in registry.iterdir() if f.is_file()},'preparation-recovery-write')
        result['finished_utc']=c.now()
    finally:
        try:backend.close()
        finally:
            result['adapter']=backend.receipt();result['gates']=guard.checks
            c.write_new(root/'result.json',m.raw(result))
    expected_actors={'normal':3,'space-before-owner':2,'space-before-restore':2,'missing-preparation-result':0}[name]
    c.check(len(backend.actors)==expected_actors and backend.max_owners<=1,'actor-count')
    c.check(result['adapter']['broker_reaped'] and all(v['removed'] and v['client_reaped'] for v in result['adapter']['actors']),
            'cleanup-unconfirmed')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',required=True);parser.add_argument('--development',action='store_true')
    args=parser.parse_args();os.umask(0o077);out=Path(args.output_directory).absolute()
    c.check(not out.exists() and all(not x.is_symlink() for x in (out,*out.parents)),'output')
    out.mkdir(mode=0o700);log=io.StringIO();stage='source'
    report={'schema':1,'status':'prepared-handoff-failed-live-blocked','started_utc':c.now(),
            'development':args.development,'cases':[],'production_modified':False,'provider_connection_opened':False,
            'activation_authorized':False}
    try:
        report['source_sha256']=b.pins()
        if not args.development:c.check(not n.image.c.git('status','--porcelain').strip(),'dirty-source')
        with redirect_stderr(log):
            stage='tests'
            import test_manifest,test_storage,test_preparation,test_bridge
            suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(v) for v in
                                    (test_manifest,test_storage,test_preparation,test_bridge))
            tests=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
            report['tests']={'run':tests.testsRun,'errors':len(tests.errors),'failures':len(tests.failures),'skipped':len(tests.skipped)}
            c.check(tests.wasSuccessful() and not tests.skipped and not n.image.DIAGNOSTIC.search(log.getvalue()),'tests')
            cli=[]
            if not args.development:
                stage='docker';n.image.host.trusted_local_docker()
                c.check(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,'uid')
                config=out/'empty-docker-config';config.mkdir(mode=0o700)
                cli=[n.image.host.DOCKER,'--config',str(config),'--host','unix://'+n.image.host.SOCKET]
                c.check(n.image.bounded(cli+['image','inspect','--format','{{.Id}}',c.IMAGE]).decode().strip()==c.IMAGE,'image-unavailable')
            for name in CASES:
                stage=name;report['cases'].append(run_case(out,cli,name,args.development))
        stage='final'
        c.check(b.pins()==report['source_sha256'] and not n.image.DIAGNOSTIC.search(log.getvalue()),'source-or-diagnostic')
        if not args.development:c.check(not n.image.c.git('status','--porcelain').strip(),'source-changed')
        report['status']=('prepared-handoff-development-passed-docker-pending' if args.development
                          else 'prepared-handoff-offline-passed-live-blocked')
    except BaseException as exc:
        report.update(failure_stage=stage,failure_type=type(exc).__name__,failure_code=str(exc) if type(exc) is ValueError else 'unconfirmed')
    finally:
        report['finished_utc']=c.now();(out/'report.json').write_bytes(m.raw(report));(out/'validation.log').write_text(log.getvalue())
        with zipfile.ZipFile(out/'acceptance.zip','x',compression=zipfile.ZIP_STORED) as z:
            for name in ('report.json','validation.log'):z.write(out/name,name)
            for name in CASES:
                root=out/name
                if not root.exists():continue
                allowed=['registry-path.json','manifest/manifest.json','result.json','fault-ready.json','plan.json',
                         'control/claim.json','control/events.jsonl',*[f'gate-{i:02d}.json' for i in range(5)]]
                for entry in allowed:
                    if (root/entry).is_file():z.write(root/entry,name+'/'+entry)
                if (root/'registry-path.json').is_file():
                    registry=Path(m.parse((root/'registry-path.json').read_bytes())['registry'])
                    for entry in (p.CLAIM,p.RESULT,'bridge-claim.json','handoff-claim.json','handoff-events.jsonl'):
                        if (registry/entry).is_file():z.write(registry/entry,name+'/registry/'+entry)
    print(report['status']);print(out/'acceptance.zip')
    return 0 if report['status'].endswith(('passed-docker-pending','passed-live-blocked')) else 1


if __name__=='__main__':raise SystemExit(main())
