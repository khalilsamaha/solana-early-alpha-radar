"""One offline combined batch; Docker/Unix required unless explicit development."""
import common as c
import argparse
from contextlib import redirect_stderr
import io
from pathlib import Path
import os
import platform
import sys
import unittest
import zipfile
import pipeline
import envelope
from check_session import DIAGNOSTIC
import check as core


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',required=True)
    parser.add_argument('--development',action='store_true')
    args=parser.parse_args();os.umask(0o077)
    output=envelope.preflight(args.output_directory);output.mkdir(mode=0o700)
    core.block_internet();log=io.StringIO();stage='tests'
    report={'schema_version':1,'status':'combined-check-failed-live-blocked','source_sha256':c.pins(),
            'python':platform.python_version(),'development':args.development,'live_launch_authorized':False,
            'production_modified':False,'provider_connection_opened':False,'remote_upload_performed':False}
    try:
        with redirect_stderr(log):
            suite=unittest.defaultTestLoader.discover(str(c.ROOT),pattern='test_*.py')
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
            report['tests']={'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}
            if not result.wasSuccessful() or result.skipped or not result.testsRun or DIAGNOSTIC.search(log.getvalue()):
                raise c.CaptureError('combined-tests')
            cases={}
            for name,scenario,interrupt in (('normal','normal',None),('cleanup-failure','cleanup-failure',None),
                                            ('shutdown-interruption','normal','stop_shared')):
                stage=name;registry=output/(name+'-registry');registry.mkdir(mode=0o700)
                cases[name]=pipeline.run(registry,output/name,scenario=scenario,development=args.development,interrupt=interrupt)
                cases[name]['read_only_recovery']=pipeline.inspect(registry,output/name)
        if DIAGNOSTIC.search(log.getvalue()) or c.pins()!=report['source_sha256']:
            raise c.CaptureError('combined-final-check')
        report.update(cases=cases,status='combined-development-passed-docker-pending' if args.development else 'combined-offline-passed-live-blocked')
        c.exclusive_file(output/'validation.log',log.getvalue().encode());c.exclusive_file(output/'report.json',c.raw(report))
        with zipfile.ZipFile(output/'acceptance.zip','x',compression=zipfile.ZIP_STORED) as z:
            for name in ('report.json','validation.log'):
                z.write(output/name,name)
            for name in cases:z.write(output/(name+'-envelope/evidence.zip'),name+'-evidence.zip')
        print(report['status']);print(output/'acceptance.zip');return 0
    except BaseException:
        report.update(failure_stage=stage,status='combined-check-failed-live-blocked')
        if not (output/'report.json').exists():c.exclusive_file(output/'report.json',c.raw(report))
        if not (output/'validation.log').exists():c.exclusive_file(output/'validation.log',log.getvalue().encode())
        print('Combined batch stopped; preserve report.json and validation.log.',file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
