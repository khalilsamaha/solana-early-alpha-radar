"""One retained, isolated native acceptance batch. No production or provider mode."""
import argparse
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import manifest_supervisor as v
import native_scanner as native
from test_native_supervision import fixture,NativeAdmissionTests,NativeUnixTests
m=v.m;p=v.p
CASES=('normal','cleanup-failure','lost-scanner-confirmation','space-before-scanner')


def run_case(out,name,development):
    root=out/name;root.mkdir(mode=0o700)
    registry=Path(tempfile.mkdtemp(prefix='r1ns-'))
    native.n.c.write_new(root/'registry-path.json',m.raw({'registry':str(registry)}))
    manifest,plan,sha,paths=fixture(root,registry,pipe=development)
    p.prepare(plan,sha,paths)
    mode=('session-scanner-' if development else 'session-native-')+('cleanup-failure' if name=='cleanup-failure' else 'normal')
    row={'case':name,'development':development,'manifest_sha256':sha,'registry':str(registry),
         'started_utc':v.stamp(),'fault_reached':False,'supervision':None,
         'activation_authorized':False,'production_modified':False,'provider_connection_opened':False}
    try:
        if name=='lost-scanner-confirmation':
            cls=v.scanner_peer.Scanner if development else native.Scanner;original=cls.finish
            def lost(scanner,*args):
                original(scanner,*args);row['fault_reached']=True
                native.n.c.write_new(root/'fault-ready.json',m.raw({'stage':'after-scanner-terminal','manifest_sha256':sha}))
                raise OSError('fixture-lost-confirmation')
            with patch.object(cls,'finish',lost):row['supervision']=v.run(plan,sha,mode=mode)
            m.check(row['fault_reached'] and row['supervision']['outcome']=='worker-failed','lost-confirmation-disposition')
        elif name=='space-before-scanner':
            original=p.s.sample
            def pressure(fd):return {**original(fd),'available_bytes':0}
            try:
                with patch.object(p.s,'sample',side_effect=pressure):v.run(plan,sha,mode=mode)
            except ValueError as exc:m.check(str(exc)=='runtime-session-storage','space-fault-disposition');row['fault_reached']=True
            else:raise ValueError('space-fault-missed')
        else:
            row['supervision']=v.run(plan,sha,mode=mode)
            m.check(row['supervision']['outcome']==v.SUCCESS,'native-completion')
        before={f.name:f.read_bytes() for f in registry.iterdir() if f.is_file()}
        row['recovery']=v.inspect(registry,sha)
        m.check(before=={f.name:f.read_bytes() for f in registry.iterdir() if f.is_file()},'native-recovery-write')
        if row['supervision'] is not None:
            m.check(row['recovery']==row['supervision'],'native-recovery-mismatch')
            scanner=row['supervision']['scanner']
            m.check(row['supervision']['worker_reaped'] and scanner['reaped'],'native-reaping')
            if not development:m.check(scanner['removed'] and scanner['actor']['removed'],'native-removal')
        else:m.check(row['recovery']['outcome']=='supervision-unresolved','native-space-recovery')
        row['finished_utc']=v.stamp()
    finally:native.n.c.write_new(root/'result.json',m.raw(row))
    return row


def bundle(out):
    with zipfile.ZipFile(out/'acceptance.zip','x',compression=zipfile.ZIP_STORED) as z:
        for name in ('report.json','validation.log'):z.write(out/name,name)
        for case in CASES:
            root=out/case
            if not root.exists():continue
            files=['registry-path.json','manifest/manifest.json','result.json','fault-ready.json']
            files+=['capture/supervised-session/'+name for name in v.session.FILES]
            for name in files:
                path=root/name
                if path.is_file():
                    m.check(not path.is_symlink() and path.stat().st_size<=p.BOUND,'bundle-artifact-bound');z.write(path,case+'/'+name)
            location=root/'registry-path.json'
            if location.is_file():
                registry=Path(m.parse(location.read_bytes())['registry'])
                for name in (p.CLAIM,p.RESULT,v.CLAIM,v.RESULT,'supervision-storage.json',native.ENDPOINT,native.INTENT,
                             native.IDENTITY,native.PEER,'native-scanner-disposal.json'):
                    path=registry/name
                    if path.is_file():
                        m.check(not path.is_symlink() and path.stat().st_size<=p.BOUND,'bundle-registry-bound')
                        z.write(path,case+'/registry/'+name)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',required=True);parser.add_argument('--development',action='store_true')
    args=parser.parse_args();os.umask(0o077);out=Path(args.output_directory).absolute()
    m.check(not out.exists() and all(not x.is_symlink() for x in (out,*out.parents)),'output-already-present-or-linked')
    out.mkdir(mode=0o700);log=io.StringIO();stage='source'
    report={'schema':1,'status':'native-supervision-failed-live-blocked','started_utc':v.stamp(),
            'development':args.development,'cases':[],'activation_authorized':False,
            'production_modified':False,'provider_connection_opened':False}
    try:
        report['source_sha256']=v.r.pins()
        if not args.development:m.check(not native.n.image.c.git('status','--porcelain').strip(),'dirty-source')
        with redirect_stderr(log):
            stage='tests'
            suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(NativeAdmissionTests)])
            if args.development:
                import test_supervision,test_capture_session,test_scanner_peer
                for module in (test_supervision,test_capture_session,test_scanner_peer):
                    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
                report['unix_tests_not_run']='Workspace AF_UNIX socket creation denied; native acceptance remains pending.'
            else:suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(NativeUnixTests))
            tests=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
            report['tests']={'run':tests.testsRun,'errors':len(tests.errors),'failures':len(tests.failures),'skipped':len(tests.skipped)}
            m.check(tests.wasSuccessful() and not tests.skipped and not native.n.image.DIAGNOSTIC.search(log.getvalue()),'tests')
            for name in CASES:
                stage=name;report['cases'].append(run_case(out,name,args.development))
        m.check(v.r.pins()==report['source_sha256'],'source-changed')
        if not args.development:m.check(not native.n.image.c.git('status','--porcelain').strip(),'dirty-source-after')
        report['status']='native-supervision-development-passed-native-pending' if args.development else 'native-supervision-offline-passed-live-blocked'
    except BaseException as exc:
        report.update(failure_stage=stage,failure_type=type(exc).__name__)
    finally:
        report['finished_utc']=v.stamp()
        (out/'report.json').write_bytes(m.raw(report));(out/'validation.log').write_text(log.getvalue());bundle(out)
    print(report['status']);print(out/'acceptance.zip')
    return 0 if report['status']!='native-supervision-failed-live-blocked' else 1


if __name__=='__main__':raise SystemExit(main())
