"""Offline complete/interrupted evidence preservation acceptance; no remote storage or production reads."""
import argparse
import io
import os
from pathlib import Path
import platform
import sys
import time
import unittest

import preserve
import contract
from capture import CaptureError,canonical,digest,exclusive_file
from handoff import path_without_links,read_private
from provider_wire import dependency
from supervisor import termination_handlers
from fixture_support import make,save
import check as core


def tests():
    suite=unittest.TestLoader().discover(str(preserve.ROOT),pattern='test_*.py')
    r=unittest.TextTestRunner(stream=io.StringIO(),verbosity=2).run(suite)
    if not r.wasSuccessful() or not r.testsRun or r.skipped:raise CaptureError('preservation-regressions')
    return {'run':r.testsRun,'errors':0,'failures':0,'skipped':0}


class Parser(argparse.ArgumentParser):
    def error(self,message):raise CaptureError('preservation-arguments')


def main(argv=None):
    output=None;created=False;stage='arguments'
    report={'schema_version':1,'status':'offline-preservation-failed-live-blocked','synthetic_only':True,
            'provider_connection_opened':False,'credentials_loaded':False,'production_modified':False,
            'docker_used':False,'remote_upload_performed':False,'retention_verified':False,
            'live_launch_authorized':False,'full_gate_accepted':False,'automatic_resume_allowed':False}
    try:
        parser=Parser(description=__doc__);parser.add_argument('--output-directory',required=True)
        args=parser.parse_args(argv);os.umask(0o077)
        output=path_without_links(args.output_directory);output.mkdir(mode=0o700);created=True
        core.block_internet();before=preserve.pins();started=time.monotonic()
        stage='regressions';report.update(python=platform.python_version(),dependencies=dependency(),
                                         core_tests=core.run_checks(),preservation_tests=tests())
        stage='contract';registration=output/'registration';registration.mkdir(mode=0o700)
        binding=contract.freeze(registration);sha=binding['contract_sha256']
        source_digest=contract.load(registration/'contract.json',sha)['source_digest'];cases={}
        with termination_handlers():
            for name in ('complete','interrupted','rollback'):
                stage=name;root=output/(name+'-source')
                fixture=make(root,name,sha,source_digest)
                preserved=save(root,registration/'contract.json',sha,output/(name+'-archive'))
                restored=preserve.restore(output/(name+'-archive/evidence.zip'),preserved['archive_sha256'],output/(name+'-restore'))
                expected='complete-replayed-evidence' if name=='complete' else 'quarantined-incomplete-evidence'
                if (preserved['assessment']!=restored['assessment'] or restored['assessment']['classification']!=expected
                        or not fixture['writer_reaped'] or not fixture['native_fixture_cleanup']['all_fixture_processes_reaped']):
                    raise CaptureError('preservation-scenario')
                raw=read_private(output/(name+'-archive/evidence.zip'),preserve.MAX_ARCHIVE)
                exclusive_file(output/(name+'-evidence.zip'),raw)
                cases[name]={'fixture':fixture,'preserved':preserved,'restored':restored}
        stage='source-verification'
        if before!=preserve.pins():raise CaptureError('preservation-sources-changed')
        report.update(status='offline-preservation-passed-live-blocked',source_sha256=before,
                      cases=cases,contract_sha256=sha,elapsed_seconds=round(time.monotonic()-started,6))
        exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
        print(report['status']);print('Upload report.json and the three *-evidence.zip archives from:');print(output)
        return 0
    except BaseException:
        report['status']='offline-preservation-failed-live-blocked';report['failure_stage']=stage
        if created:
            try:exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
            except Exception:pass
        print('Preservation stopped; retain the output and upload its report. No acceptance granted.',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
