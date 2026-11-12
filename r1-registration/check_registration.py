"""Offline draft measurement contract acceptance; no live launcher or approval writer."""
import argparse
import asyncio
import io
import os
from pathlib import Path
import platform
import sys
import time
import unittest

import contract
from capture import CaptureError, canonical, digest, exclusive_file
from handoff import path_without_links
from provider_wire import dependency
from shared_rehearsal import exercise
import check as core


def tests():
    suite=unittest.TestLoader().discover(str(contract.ROOT),pattern='test_*.py')
    result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=2).run(suite)
    if not result.wasSuccessful() or not result.testsRun or result.skipped:
        raise CaptureError('contract-tests-failed')
    return {'run':result.testsRun,'failures':0,'errors':0,'skipped':0}


class Parser(argparse.ArgumentParser):
    def error(self,message):raise CaptureError('contract-arguments')


def main(argv=None):
    output=None;created=False;stage='arguments'
    report={'schema_version':1,'status':'offline-measurement-contract-failed-live-blocked',
        'provider_connection_opened':False,'credentials_loaded':False,'production_modified':False,
        'live_launch_authorized':False,'full_gate_accepted':False,'synthetic_only':True,
        'owner_approval_recorded':False,'docker_used':False}
    try:
        parser=Parser(description=__doc__);parser.add_argument('--output-directory',required=True)
        args=parser.parse_args(argv);os.umask(0o077)
        output=path_without_links(args.output_directory);output.mkdir(mode=0o700);created=True
        core.block_internet();before=contract.pins();started=time.monotonic()
        stage='regressions';report.update(python=platform.python_version(),dependencies=dependency(),
                                         core_tests=core.run_checks(),contract_tests=tests())
        stage='freeze-draft';binding=contract.freeze(output);report['contract']=binding
        cases={}
        for name,failure in (('normal',False),('cleanup-failure',True)):
            stage=name
            result=asyncio.run(exercise(output/(name+'-fixture'),transport='pipe',fail_cleanup=failure))
            evaluation=contract.review(output/'contract.json',binding['contract_sha256'],
                output/(name+'-fixture/export/session.zip'),result['session_bundle_sha256'],output/(name+'-replay'))
            expected='fail' if failure else 'insufficient'
            if evaluation['measurement_gate_verdict']!=expected or evaluation['live_launch_authorized']:
                raise CaptureError('contract-outcome-expectation')
            cases[name]=evaluation
        stage='sources'
        if before!=contract.pins():raise CaptureError('contract-sources-changed')
        report.update(status='offline-measurement-contract-passed-live-blocked',source_sha256=before,
            cases=cases,proposal=contract.proposal(),elapsed_seconds=round(time.monotonic()-started,6))
        exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
        print(report['status']);print('Upload report.json and contract.json from:');print(output)
        return 0
    except BaseException:
        report['status']='offline-measurement-contract-failed-live-blocked';report['failure_stage']=stage
        if created:
            try:exclusive_file(output/'report.json',(canonical(report)+'\n').encode())
            except Exception:pass
        print('Contract review stopped; preserve the report. No acceptance or live authority granted.',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
