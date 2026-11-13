"""One offline admission/supervision integration batch; never a live launcher."""
import argparse
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import platform
import signal
import sys
import time
import unittest
import zipfile

import admission as ad
import check_session
import check as core
from provider_wire import dependency


def main(argv=None):
    output = None
    log = io.StringIO()
    report = {'schema_version':1, 'status':'admission-check-failed-live-blocked',
              'live_launch_authorized':False, 'production_modified':False,
              'provider_connection_opened':False, 'real_credentials_loaded':False,
              'remote_upload_performed':False, 'full_gate_accepted':False}
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--output-directory', required=True)
        parser.add_argument('--development', action='store_true')
        args = parser.parse_args(argv)
        os.umask(0o077)
        output = ad.a.preflight(args.output_directory); output.mkdir(mode=0o700)
        core.block_internet()
        before = ad.pins(); started = time.monotonic()
        report.update(source_sha256=before, python=platform.python_version(), dependencies=dependency(),
                      development_endpoint=args.development)
        suite = unittest.defaultTestLoader.loadTestsFromName('test_admission')
        with redirect_stderr(log):
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        report['tests'] = {'run':result.testsRun,'errors':len(result.errors),
                           'failures':len(result.failures),'skipped':len(result.skipped)}
        if not result.wasSuccessful() or result.skipped or not result.testsRun or check_session.DIAGNOSTIC.search(log.getvalue()):
            raise ad.CaptureError('admission-check-tests')
        cases = {}; artifacts = {}
        for mode in ad.MODES:
            registry = output/(mode+'-registry'); registry.mkdir(mode=0o700)
            with redirect_stderr(log):
                case = ad.run(registry, output/mode, mode, development=args.development)
            failed = mode in ('stall','tainted-diagnostic')
            expected = 'supervised-admission-failed-live-blocked' if failed else (
                'supervised-admission-development-passed-unix-pending' if args.development
                else 'supervised-admission-offline-passed-live-blocked')
            if case['status'] != expected or not case['worker_reaped'] or not case['consumer_reaped']:
                raise ad.CaptureError('admission-check-case')
            if failed and (output/mode/'worker-result.json').exists():
                raise ad.CaptureError('admission-check-false-completion')
            if failed:
                marker = ad.a.row(ad.read_private(output/mode/'fault-ready.json',4096))
                if marker != {'request_sha256':case['request_sha256'], 'fault':mode, 'credential_descriptor_closed':True}:
                    raise ad.CaptureError('admission-check-fault-not-reached')
                if case['worker_returncode'] != (-signal.SIGALRM if mode == 'stall' else 1):
                    raise ad.CaptureError('admission-check-fault-outcome')
                artifacts[mode+'/fault-ready.json'] = ad.s.json_bytes(marker)
            recovery = ad.inspect(registry, output/mode)
            if recovery['reconciliation_required'] is not failed:
                raise ad.CaptureError('admission-check-recovery')
            cases[mode] = {'supervisor':case, 'read_only_recovery':recovery}
            for member in ('request.json','registration/contract.json','supervisor.json'):
                artifacts[mode+'/'+member] = ad.read_private(output/mode/member,65536)
            artifacts[mode+'/claim.json'] = ad.read_private(registry/'claim.json',4096)
            if not failed:
                artifacts[mode+'/worker-result.json'] = ad.read_private(output/mode/'worker-result.json',65536)
                artifacts[mode+'/archive.zip'] = ad.read_private(output/mode/'export/archive.zip',ad.a.MAX_PACKAGE)
        if before != ad.pins() or check_session.DIAGNOSTIC.search(log.getvalue()):
            raise ad.CaptureError('admission-check-source-or-diagnostics')
        report.update(cases=cases, elapsed_seconds=round(time.monotonic()-started,6),
            status='admission-development-passed-unix-pending' if args.development else 'admission-offline-passed-live-blocked')
        artifacts.update({'report.json':ad.s.json_bytes(report),'validation.log':log.getvalue().encode()})
        with zipfile.ZipFile(output/'acceptance.zip','x',compression=zipfile.ZIP_STORED) as z:
            for name,raw in sorted(artifacts.items()):
                info=zipfile.ZipInfo(name);info.create_system=3;info.external_attr=0o100600<<16
                z.writestr(info,raw)
        with (output/'acceptance.zip').open('rb') as handle: os.fsync(handle.fileno())
        ad.exclusive_file(output/'validation.log',log.getvalue().encode())
        ad.exclusive_file(output/'report.json',ad.s.json_bytes(report))
        print(report['status']);print(output/'acceptance.zip')
        return 0
    except BaseException:
        report['status']='admission-check-failed-live-blocked'
        if output is not None and output.exists():
            for name,raw in (('validation.log',log.getvalue().encode()),('report.json',ad.s.json_bytes(report))):
                if not (output/name).exists():
                    try: ad.exclusive_file(output/name,raw)
                    except Exception: pass
        print('Admission batch failed. Retain report.json and validation.log.',file=sys.stderr)
        return 1


if __name__ == '__main__': sys.exit(main())
