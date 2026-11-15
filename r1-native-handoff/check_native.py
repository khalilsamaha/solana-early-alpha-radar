"""One complete offline native handoff batch; development pipes are explicit."""
import argparse
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import native as n
h=n.h;c=n.c
CASES=(('normal','unsubscribed',None),('cleanup-failure','upstream-aborted',None),
    ('lost-owner-start','unsubscribed','start_owner'),('lost-shared-stop','unsubscribed','stop_shared'),
    ('lost-restore','unsubscribed','restore_direct'))

def run_case(output,cli,name,cleanup,fault,development):
    root=output/name;root.mkdir(mode=0o700)
    registry=Path(tempfile.mkdtemp(prefix='r1nh-'))
    c.write_new(root/'registry-path.json',c.raw({'registry':str(registry)}))
    backend=n.Backend(root,registry,cli,cleanup,development,fault)
    result={'case':name,'started_utc':c.now(),'registry':str(registry),'development':development}
    try:
        proof=backend.prepare()
        with h.Coordinator(registry,proof,backend) as coordinator:
            backend.bind_plan(coordinator.claim)
            try:
                for action in h.ACTIONS:coordinator.step(action)
                c.check(fault is None,'fault-not-reached')
            except ValueError:
                c.check(fault is not None and backend.fault_reached,'unexpected-fault')
        before={p.name:p.read_bytes() for p in registry.iterdir() if p.is_file()}
        state=h.inspect(registry)
        c.check(before=={p.name:p.read_bytes() for p in registry.iterdir() if p.is_file()},'recovery-write')
        if fault:c.check(state['pending_action']==fault and not state['complete'],'fault-state')
        else:c.check(state['complete'] and state['research_cleanup']==cleanup,'complete-state')
        expected_restores=int(fault is None or fault=='restore_direct')
        c.check(backend.restores==expected_restores and backend.max_owners==1,'restoration-count')
        c.check(not state['production_activation_authorized'] and not state['automatic_resume_allowed'],'authority')
        result.update(recovery=state,finished_utc=c.now())
    finally:
        try:backend.close()
        finally:
            result['adapter']=backend.receipt()
            c.write_new(root/'result.json',c.raw(result))
    c.check(all(a['removed'] and a['client_reaped'] for a in result['adapter']['actors']),'cleanup-incomplete')
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-directory',required=True)
    parser.add_argument('--development',action='store_true');args=parser.parse_args();os.umask(0o077)
    out=Path(args.output_directory).absolute();c.check(not out.exists() and all(not p.is_symlink() for p in [out,*out.parents]),'output')
    out.mkdir(mode=0o700);log=io.StringIO();stage='source'
    report={'schema':1,'status':'native-handoff-failed-live-blocked','development':args.development,
        'started_utc':c.now(),'production_modified':False,'provider_connection_opened':False,
        'activation_authorized':False,'cases':[]}
    try:
        report['source_sha256']=n.pins()
        if not args.development:c.check(not n.image.c.git('status','--porcelain').strip(),'dirty-source')
        stage='tests'
        with redirect_stderr(log):
            import test_native,test_coordinator,test_control
            suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(m) for m in (test_native,test_coordinator,test_control)])
            tests=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
            report['tests']={'run':tests.testsRun,'failures':len(tests.failures),'errors':len(tests.errors),'skipped':len(tests.skipped)}
            c.check(tests.wasSuccessful() and tests.testsRun and not tests.skipped and not n.image.DIAGNOSTIC.search(log.getvalue()),'tests')
            cli=[]
            if not args.development:
                stage='docker';n.image.host.trusted_local_docker()
                c.check(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,'uid')
                config=out/'empty-docker-config';config.mkdir(mode=0o700)
                cli=[n.image.host.DOCKER,'--config',str(config),'--host','unix://'+n.image.host.SOCKET]
                c.check(n.image.bounded(cli+['image','inspect','--format','{{.Id}}',c.IMAGE]).decode().strip()==c.IMAGE,'image-unavailable')
            for name,cleanup,fault in CASES:
                stage=name;report['cases'].append(run_case(out,cli,name,cleanup,fault,args.development))
        stage='final';c.check(n.pins()==report['source_sha256'] and not n.image.DIAGNOSTIC.search(log.getvalue()),'source-or-diagnostic')
        if not args.development:c.check(not n.image.c.git('status','--porcelain').strip(),'source-changed')
        report['status']='native-handoff-development-passed-docker-pending' if args.development else 'native-handoff-offline-passed-live-blocked'
    except BaseException as e:
        report.update(failure_stage=stage,failure_type=type(e).__name__,failure_code=str(e) if type(e) is ValueError else 'unconfirmed')
    finally:
        report['finished_utc']=c.now();(out/'report.json').write_bytes(c.raw(report));(out/'validation.log').write_text(log.getvalue())
        with zipfile.ZipFile(out/'acceptance.zip','x',compression=zipfile.ZIP_STORED) as z:
            for name in ('report.json','validation.log'):z.write(out/name,name)
            for case_name,_,_ in CASES:
                root=out/case_name
                for name in ('registry-path.json','plan.json','result.json','control/claim.json','control/events.jsonl'):
                    if (root/name).is_file():z.write(root/name,case_name+'/'+name)
                if (root/'registry-path.json').is_file():
                    registry=Path(c.parse((root/'registry-path.json').read_bytes())['registry'])
                    for name in ('handoff-claim.json','handoff-events.jsonl'):
                        if (registry/name).is_file():z.write(registry/name,case_name+'/'+name)
    print(report['status']);print(out/'acceptance.zip')
    return 0 if report['status'].endswith(('passed-docker-pending','passed-live-blocked')) else 1
if __name__=='__main__':sys.exit(main())
