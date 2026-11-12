"""Offline credential/runtime acceptance. Generates only synthetic credentials."""
import argparse
import io
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import unittest
import uuid

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'r1-data'))
import check as core
import boundary
from capture import CaptureError,canonical,digest,exclusive_file,strict_json
from handoff import path_without_links,read_private
from provider_wire import dependency,secret_variants
from session_bundle import MAX_PACKAGE,restore_session


def runtime_tests():
    suite=unittest.TestLoader().discover(str(ROOT),pattern='test_*.py')
    result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=2).run(suite)
    if not result.wasSuccessful() or not result.testsRun or result.skipped:
        raise CaptureError('runtime-tests-failed')
    return {'run':result.testsRun,'errors':0,'failures':0,'skipped':0}


def receipt(directory,scenario):
    row=strict_json(read_private(directory/'worker-result.json',65536))
    fields={'schema_version','manifest_sha256','shared','session_bundle_sha256','session_bundle_bytes',
        'capture','measurement','credential_descriptor_closed','complete_session_replayed',
        'internet_and_dns_blocked','child_process_creation_blocked','parent_death_sigkill',
        'core_dump_limit_zero','real_credential_used','provider_connection_opened'}
    if (set(row)!=fields or type(row['schema_version']) is not int or row['schema_version']!=1
            or row['manifest_sha256']!=digest(read_private(directory/'attempt.json',65536))
            or any(row[k] is not True for k in ('credential_descriptor_closed','complete_session_replayed',
                'internet_and_dns_blocked','child_process_creation_blocked','parent_death_sigkill','core_dump_limit_zero'))
            or row['real_credential_used'] is not False or row['provider_connection_opened'] is not False):
        raise CaptureError('runtime-receipt')
    success=scenario=='normal'
    shared=row['shared'];owner=shared['owner'];cleanup=owner['cleanup']
    expected='capture-stopped' if success else 'transport-cleanup-failed'
    methods=['subscribeNewToken','subscribeMigration','subscribeTokenTrade','unsubscribeTokenTrade']
    if (owner['upstream_attempts']!=1 or owner['research_attachments']!=1 or owner['closed'] is not True
            or owner['reason']!=('owner-stop' if success else 'send-uncertain')
            or shared['research']['outcome']!=expected
            or cleanup['outcome']!=('unsubscribed' if success else 'upstream-aborted')
            or cleanup['discovery_continues'] is not success
            or shared['discovery_frames']!=(3 if success else 2)
            or shared['wire_credential_redaction_enabled'] is not True
            or [x['command']['method'] for x in owner['commands']]!=methods
            or [x['state'] for x in owner['commands']]!=['completed']*3+['completed' if success else 'uncertain']):
        raise CaptureError('runtime-shared-receipt')
    bundle=read_private(directory/'export/session.zip',MAX_PACKAGE)
    if type(row['session_bundle_bytes']) is not int or len(bundle)!=row['session_bundle_bytes'] or digest(bundle)!=row['session_bundle_sha256']:
        raise CaptureError('runtime-bundle')
    restored=restore_session(directory/'export/session.zip',row['session_bundle_sha256'],directory/'parent-restore')
    if (restored['capture']!=row['capture'] or restored['measurement']!=row['measurement']
            or row['capture']['raw_rows']!=4 or row['measurement']['session_outcome']!=expected):
        raise CaptureError('runtime-parent-replay')
    return row


class Parser(argparse.ArgumentParser):
    def error(self,message):raise CaptureError('runtime-arguments')


def main(argv=None):
    output=None;created=False;stage='arguments'
    report={'schema_version':1,'status':'offline-runtime-failed-live-blocked','synthetic_only':True,
        'real_credentials_loaded':False,'provider_connection_opened':False,'production_modified':False,
        'live_launch_authorized':False,'full_gate_accepted':False,'docker_used':False,
        'actual_rollout_or_rollback_tested':False}
    try:
        parser=Parser(description=__doc__);parser.add_argument('--output-directory',required=True)
        args=parser.parse_args(argv)
        os.umask(0o077)
        output=path_without_links(args.output_directory);output.mkdir(mode=0o700);created=True
        core.block_internet();started=time.monotonic();before=boundary.pins()
        stage='regressions'
        report.update(python=platform.python_version(),dependencies=dependency(),core_tests=core.run_checks(),
                      runtime_tests=runtime_tests())
        variants=[];cases={}
        with tempfile.TemporaryDirectory(prefix='r1-runtime-synthetic-') as tmp:
            private=Path(tmp)
            for scenario in ('normal','cleanup-failure','credential-echo','stall'):
                stage=scenario
                credential_path=private/scenario
                value='R1-SYNTHETIC-'+uuid.uuid4().hex
                exclusive_file(credential_path,value.encode());variants.extend(secret_variants(value))
                directory=output/scenario;directory.mkdir(mode=0o700)
                process=boundary.run(directory,credential_path,scenario,wall_seconds=2 if scenario=='stall' else 12)
                if (not process['worker_reaped'] or process['workers_started']!=1 or process['automatic_restart']
                        or strict_json(read_private(directory/'ready.json',4096))!={'credential_descriptor_closed':True}):
                    raise CaptureError('runtime-process')
                if scenario in {'normal','cleanup-failure'}:
                    if process['outcome']!='worker-exited' or process['forced_kill_needed']:
                        raise CaptureError('runtime-process')
                    verified=receipt(directory,scenario)
                    cases[scenario]={'process':process,'worker':verified,'parent_replay_verified':True}
                else:
                    expected='worker-deadline' if scenario=='stall' else 'worker-failed'
                    if (process['outcome']!=expected or (directory/'worker-result.json').exists()
                            or scenario=='stall' and not process['forced_kill_needed']):
                        raise CaptureError('runtime-failure-expectation')
                    cases[scenario]={'process':process,'failure_not_accepted':True}
                claim=read_private(directory/'attempt.json',65536)
                try:boundary.run(directory,credential_path,scenario)
                except FileExistsError:pass
                else:raise CaptureError('runtime-attempt-reused')
                if read_private(directory/'attempt.json',65536)!=claim:
                    raise CaptureError('runtime-attempt-changed')
                cases[scenario]['attempt_reuse_refused']=True
        stage='source-and-output-verification'
        after=boundary.pins()
        if before!=after:raise CaptureError('runtime-sources-changed')
        exclusive_file(output/'session.zip',read_private(output/'normal/export/session.zip',MAX_PACKAGE))
        for p in output.rglob('*'):
            if p.is_file() and any(v in p.read_bytes() for v in variants):
                raise CaptureError('runtime-credential-in-output')
        report.update(status='offline-runtime-boundary-passed-live-blocked',cases=cases,
            source_sha256=after,elapsed_seconds=round(time.monotonic()-started,6),
            synthetic_credential_variants_absent=True,temporary_credential_inputs_removed=True)
        raw=(canonical(report)+'\n').encode()
        if any(v in raw for v in variants):raise CaptureError('runtime-credential-in-report')
        exclusive_file(output/'report.json',raw)
        print('Offline runtime boundary passed; live remains blocked. Upload report.json and session.zip from:')
        print(output)
        return 0
    except BaseException:
        report['status']='offline-runtime-failed-live-blocked';report['failure_stage']=stage
        if created:
            try:exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
            except Exception:pass
        print('Runtime review stopped. Preserve the output directory and upload the available report. No acceptance granted.',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
