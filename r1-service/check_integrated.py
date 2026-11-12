"""Isolated service integration acceptance. Default requires Docker and real Unix IPC."""
import argparse
import io
import os
from pathlib import Path
import platform
import signal
import sys
import tempfile
import time
import unittest

import integrated_common as common
from capture import CaptureError, canonical, digest, exclusive_file, strict_json
from handoff import path_without_links, read_private
from provider_wire import dependency
from supervisor import termination_handlers
from container_boundary import IMAGE, host
import check as core
import lifecycle
from integrated_backend import Backend


def checks(pattern):
    suite=unittest.TestLoader().discover(str(common.ROOT),pattern=pattern)
    result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=2).run(suite)
    if not result.wasSuccessful() or not result.testsRun or result.skipped:
        raise CaptureError('integration-regressions')
    return {'run':result.testsRun,'errors':0,'failures':0,'skipped':0}


def scenario(output,name,source_digest,backends,*,pipe_only=False):
    root=output/name;root.mkdir(mode=0o700)
    registry=root/'registry';journal=root/'journal'
    registry.mkdir(mode=0o700);journal.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix='r1-link-') as tmp:
        backend=Backend(root,Path(tmp),name,pipe_only=pipe_only);backends.append(backend)
        try:
            # Consume the durable claim before starting even the baseline fixture.
            with lifecycle.Lifecycle(registry,journal,digest(('integration:'+name).encode()),source_digest) as coordinator:
                backend.prepare()
                for action in lifecycle.ACTIONS: coordinator.step(action,backend)
        finally:
            # Repeated operator signals cannot interrupt ownership-scoped cleanup.
            previous={sig:signal.signal(sig,signal.SIG_IGN) for sig in (signal.SIGTERM,signal.SIGINT)}
            try: backend.close()
            finally:
                for sig,handler in previous.items(): signal.signal(sig,handler)
    claim=strict_json(read_private(registry/'claim.json',4096))
    raw=read_private(journal/'events.jsonl',lifecycle.MAX_LOG)
    state=lifecycle.replay(claim,raw);receipt=backend.receipt()
    if (not state['complete'] or state['reconciliation_required'] or state['automatic_resume_allowed']
            or receipt['max_simultaneous_synthetic_owners']!=1 or receipt['direct_restore_calls']!=1
            or not receipt['broker_reaped'] or len(receipt['actors'])!=3
            or any(not a['process_reaped'] for a in receipt['actors'])
            or not pipe_only and any(not a['container']['removed'] for a in receipt['actors'])):
        raise CaptureError('integration-completion')
    return ({'state':state,'adapter':receipt,'journal_sha256':digest(raw),'journal_bytes':len(raw)},
            {'claim':claim,'journal':raw.decode('ascii')})


class Parser(argparse.ArgumentParser):
    def error(self,message): raise CaptureError('integration-arguments')


def main(argv=None):
    output=None;created=False;stage='arguments';backends=[]
    report={'schema_version':1,'status':'offline-service-integration-failed-live-blocked',
            'synthetic_only':True,'provider_connection_opened':False,'real_credentials_loaded':False,
            'production_modified':False,'production_rollout_or_rollback_tested':False,
            'live_launch_authorized':False,'full_gate_accepted':False,
            'docker_boundary_tested':False,'real_unix_ipc_tested':False,'actual_restart_policy_tested':False}
    try:
        parser=Parser(description=__doc__);parser.add_argument('--output-directory',required=True)
        parser.add_argument('--host-pipe-only',action='store_true')
        args=parser.parse_args(argv);os.umask(0o077)
        output=path_without_links(args.output_directory);output.mkdir(mode=0o700);created=True
        core.block_internet();started=time.monotonic();before=common.pins()
        source_digest=digest(canonical(before).encode())
        stage='regressions'
        report.update(python=platform.python_version(),dependencies=dependency(),
                      core_tests=core.run_checks(),lifecycle_tests=checks('test_lifecycle.py'),
                      integration_tests=checks('test_integrated.py'))
        if not args.host_pipe_only:
            stage='host-identity'
            with tempfile.TemporaryDirectory(prefix='r1-docker-config-') as tmp:
                observation=host.observe(Path(tmp))
            if observation['findings'] or observation['container']['image']!=IMAGE:
                raise CaptureError('integration-host-baseline-changed')
            report['host_identity_rechecked']=True
        cases={};journals={}
        with termination_handlers():
            for name in ('normal','cleanup-failure'):
                stage=name
                cases[name],journals[name]=scenario(output,name,source_digest,backends,pipe_only=args.host_pipe_only)
        stage='evidence'
        if before!=common.pins(): raise CaptureError('integration-sources-changed')
        payload=(canonical({'schema_version':1,'scope':'offline-service-integration','cases':journals})+'\n').encode()
        exclusive_file(output/'journals.json',payload)
        # Preserve BOTH scenarios so cleanup failure can be independently replayed too.
        for name in cases:
            raw=read_private(output/name/'broker/export/session.zip',44*1024**2)
            worker=cases[name]['adapter']['worker']
            if digest(raw)!=worker['session_bundle_sha256'] or len(raw)!=worker['session_bundle_bytes']:
                raise CaptureError('integration-bundle-binding')
            exclusive_file(output/(name+'-session.zip'),raw)
        real=not args.host_pipe_only
        report.update(status='offline-service-integration-passed-live-blocked' if real else
                      'offline-service-integration-development-passed-docker-unix-pending',
                      docker_boundary_tested=real,real_unix_ipc_tested=real,actual_restart_policy_tested=real,
                      restart_policy_simulated=not real,source_sha256=before,source_digest=source_digest,
                      cases=cases,scenario_count=len(cases),journals_sha256=digest(payload),journals_bytes=len(payload),
                      elapsed_seconds=round(time.monotonic()-started,6))
        exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
        print(report['status']);print('Upload report.json, journals.json, normal-session.zip and cleanup-failure-session.zip from:');print(output)
        return 0
    except BaseException:
        report['status']='offline-service-integration-failed-live-blocked';report['failure_stage']=stage
        report['cleanup']=[b.receipt() for b in backends]
        if created:
            try: exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
            except Exception: pass
        print('Integration stopped. Preserve the directory and upload its report; no acceptance granted.',file=sys.stderr)
        return 1


if __name__=='__main__': sys.exit(main())
