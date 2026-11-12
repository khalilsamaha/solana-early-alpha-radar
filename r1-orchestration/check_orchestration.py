"""Combined OFFLINE admission/handoff/finalization check. Real Docker/Unix required by default."""
import argparse
import io
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import unittest

import orchestrate as o
from capture import CaptureError,canonical,digest,exclusive_file
from handoff import path_without_links,read_private
from provider_wire import dependency
from supervisor import termination_handlers
from container_boundary import IMAGE,host
import check as core


def tests():
    suite=unittest.TestLoader().discover(str(o.ROOT),pattern='test_*.py')
    r=unittest.TextTestRunner(stream=io.StringIO(),verbosity=2).run(suite)
    if not r.wasSuccessful() or not r.testsRun or r.skipped:raise CaptureError('orchestration-regressions')
    return {'run':r.testsRun,'failures':0,'errors':0,'skipped':0}


class Parser(argparse.ArgumentParser):
    def error(self,message):raise CaptureError('orchestration-arguments')


def main(argv=None):
    output=None;created=False;stage='arguments';controls=[]
    report={'schema_version':1,'status':'offline-orchestration-failed-live-blocked','synthetic_only':True,
            'provider_connection_opened':False,'real_credentials_loaded':False,'production_modified':False,
            'remote_upload_performed':False,'retention_verified':False,'live_launch_authorized':False,
            'full_gate_accepted':False,'automatic_resume_allowed':False,'docker_unix_tested':False}
    try:
        parser=Parser(description=__doc__);parser.add_argument('--output-directory',required=True)
        parser.add_argument('--host-pipe-only',action='store_true')
        args=parser.parse_args(argv);os.umask(0o077)
        output=path_without_links(args.output_directory);output.mkdir(mode=0o700);created=True
        core.block_internet();before=o.pins();started=time.monotonic()
        stage='regressions';report.update(python=platform.python_version(),dependencies=dependency(),
                                         core_tests=core.run_checks(),orchestration_tests=tests())
        if not args.host_pipe_only:
            stage='host-identity'
            with tempfile.TemporaryDirectory(prefix='r1-orchestrate-docker-') as tmp:observation=host.observe(Path(tmp))
            if observation['findings'] or observation['container']['image']!=IMAGE:
                raise CaptureError('orchestration-host-baseline-changed')
            report['host_identity_rechecked']=True
        registration=output/'registration';registration.mkdir(mode=0o700)
        sha=o.contract.freeze(registration)['contract_sha256'];cases={};containers=0
        with termination_handlers():
            for name in o.SCENARIOS:
                stage=name;control=output/name;control.mkdir(mode=0o700);controls.append(control)
                case=o.run(control,registration/'contract.json',sha,name,pipe_only=args.host_pipe_only)
                inspection=o.inspect(control);interrupted=name=='shutdown-interruption'
                if (not inspection['finalization_complete'] or inspection['reconciliation_required']!=interrupted
                        or case['cleanup']['direct_restore_calls']!=(0 if interrupted else 1)):
                    raise CaptureError('orchestration-scenario-expectation')
                # The same stable control cannot rearm even with a new caller attempt.
                try:o.run(control,registration/'contract.json',sha,name,pipe_only=args.host_pipe_only)
                except CaptureError:pass
                else:raise CaptureError('orchestration-reuse-admitted')
                if o.inspect(control)!=inspection:raise CaptureError('orchestration-reuse-mutated-evidence')
                raw=read_private(control/'preserved/evidence.zip',o.preserve.MAX_ARCHIVE)
                if digest(raw)!=case['completion']['archive_sha256']:raise CaptureError('orchestration-archive-changed')
                exclusive_file(output/(name+'-evidence.zip'),raw)
                containers+=sum(a['container'] is not None for a in case['cleanup']['actors'])
                cases[name]={**case,'reconciliation_inspection':inspection,'consumed_control_reuse_refused':True}
        stage='source-verification'
        if before!=o.pins() or containers!=(0 if args.host_pipe_only else 8):
            raise CaptureError('orchestration-final-check')
        report.update(status='offline-orchestration-development-passed-docker-unix-pending' if args.host_pipe_only else
                      'offline-orchestration-passed-live-blocked',source_sha256=before,cases=cases,
                      contract_sha256=sha,docker_unix_tested=not args.host_pipe_only,
                      disposable_containers_removed=containers,elapsed_seconds=round(time.monotonic()-started,6))
        exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
        print(report['status']);print('Upload report.json and the three *-evidence.zip files from:');print(output)
        return 0
    except BaseException:
        report['status']='offline-orchestration-failed-live-blocked';report['failure_stage']=stage
        report['reconciliation']={p.name:o.inspect(p) for p in controls}
        observations={}
        for control in controls:
            try:observations[control.name]=o.read(control,'cleanup.json')[0]
            except Exception:pass
        report['cleanup_observations']=observations
        if created:
            try:exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
            except Exception:pass
        print('Orchestration stopped. Preserve the output and upload its report; no acceptance granted.',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
