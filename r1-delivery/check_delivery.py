"""OFFLINE receipt-complete handoff check; no Docker, credentials or remote storage."""
import argparse
import io
import os
from pathlib import Path
import platform
import sys
import time
import unittest

import delivery as d
import transfer as t
from capture import CaptureError,exclusive_file
from handoff import path_without_links,read_private
from provider_wire import dependency
from supervisor import termination_handlers
import check as core
import check_orchestration


def tests():
    suite=unittest.TestLoader().discover(str(d.ROOT),pattern='test_*.py')
    result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=2).run(suite)
    if not result.wasSuccessful() or not result.testsRun or result.skipped:raise CaptureError('delivery-regressions')
    return {'run':result.testsRun,'failures':0,'errors':0,'skipped':0}


def main(argv=None):
    output=None;created=False;stage='arguments';controls=[]
    report={'schema_version':1,'status':'offline-delivery-failed-remote-pending','synthetic_only':True,
            'provider_connection_opened':False,'real_credentials_loaded':False,'production_modified':False,
            'remote_upload_performed':False,'remote_preservation_verified':False,'retention_verified':False,
            'live_launch_authorized':False,'full_gate_accepted':False,'automatic_resume_allowed':False,
            'docker_unix_tested':False,'transport_scope':'offline-local-mirror-only'}
    try:
        parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-directory',required=True)
        args=parser.parse_args(argv);os.umask(0o077);output=path_without_links(args.output_directory)
        output.mkdir(mode=0o700);created=True;core.block_internet();started=time.monotonic();before=d.pins()
        stage='regressions';report.update(python=platform.python_version(),dependencies=dependency(),
            core_tests=core.run_checks(),orchestration_tests=check_orchestration.tests(),delivery_tests=tests())
        registration=output/'registration';registration.mkdir(mode=0o700)
        sha=d.o.contract.freeze(registration)['contract_sha256'];cases={}
        with termination_handlers():
            for scenario in d.o.SCENARIOS:
                stage=scenario;control=output/scenario;control.mkdir(mode=0o700)
                d.o.run(control,registration/'contract.json',sha,scenario,pipe_only=True)
                exported=output/(scenario+'-export');saved=d.export(control,exported)
                package=exported/'package.zip';raw=read_private(package,d.MAX_PACKAGE)
                exclusive_file(output/(scenario+'-package.zip'),raw)
                restored=d.restore(package,saved['package_sha256'],output/(scenario+'-restore'))
                mirror=output/(scenario+'-mirror');mirror.mkdir(mode=0o700)
                transfer=output/(scenario+'-transfer');transfer.mkdir(mode=0o700);controls.append(transfer)
                transport=t.LocalMirror(mirror);completion=t.rehearse(transfer,package,saved['package_sha256'],transport)
                inspected=t.inspect(transfer)
                if not inspected['finalization_complete'] or restored['reconciliation_required']!=(scenario=='shutdown-interruption'):
                    raise CaptureError('delivery-scenario-expectation')
                try:t.rehearse(transfer,package,saved['package_sha256'],transport)
                except CaptureError:pass
                else:raise CaptureError('delivery-reused-transfer')
                if t.inspect(transfer)!=inspected:raise CaptureError('delivery-reuse-mutated-evidence')
                cases[scenario]={'exported':saved,'restored':restored,'transfer_completion':completion,
                    'transfer_inspection':inspected,'transfer_calls':transport.calls,'consumed_control_reuse_refused':True}
        stage='source-verification'
        if before!=d.pins():raise CaptureError('delivery-sources-changed')
        report.update(status='offline-delivery-passed-remote-pending',source_sha256=before,contract_sha256=sha,
                      cases=cases,elapsed_seconds=round(time.monotonic()-started,6))
        exclusive_file(output/'report.json',d.json_bytes(report))
        print(report['status']);print('Upload report.json and all three *-package.zip files from:');print(output)
        return 0
    except BaseException:
        report.update(status='offline-delivery-failed-remote-pending',failure_stage=stage,
                      reconciliation={p.name:t.inspect(p) for p in controls})
        if created:
            try:exclusive_file(output/'report.json',d.json_bytes(report))
            except Exception:pass
        print('Delivery check stopped. Preserve the output and upload the report; no acceptance granted.',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
