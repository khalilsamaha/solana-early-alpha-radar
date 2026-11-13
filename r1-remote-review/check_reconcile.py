"""Offline retained-transfer reconciliation checks; no real B2 access."""
import argparse
import io
from pathlib import Path
import platform
import sys
import tempfile
import unittest

import reconcile as q
r=q.r
import test_reconcile
import test_remote
import check as core


def main(argv=None):
    out=None
    try:
        parser=argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--accepted-directory',required=True)
        parser.add_argument('--acceptance-report',required=True)
        parser.add_argument('--output-directory',required=True)
        args=parser.parse_args(argv);core.block_internet()
        inputs=r.path_without_links(args.accepted_directory);report=r.read_private(args.acceptance_report,1024*1024)
        if r.digest(report)!=r.REPORT_SHA:raise r.CaptureError('remote-accepted-report-required')
        out=r.path_without_links(args.output_directory);out.mkdir(mode=0o700)
        before=q.pins();verified={}
        with tempfile.TemporaryDirectory(prefix='r1-remote-offline-') as tmp:
            private=Path(tmp);r.exclusive_file(private/'report.json',report)
            for name,(size,sha) in r.PROFILES.items():
                raw=r.read_private(inputs/(name+'-package.zip'),size)
                if len(raw)!=size or r.digest(raw)!=sha:raise r.CaptureError('remote-accepted-package-required')
                path=private/(name+'-package.zip');r.exclusive_file(path,raw)
                restored=r.d.restore(path,sha,private/(name+'-restore'))
                if restored!=r.d.row(report)['cases'][name]['restored']:raise r.CaptureError('remote-replay-mismatch')
                verified[name]={'sha256':sha,'bytes':size,'classification':restored['classification'],
                                'reconciliation_required':restored['reconciliation_required']}
            test_remote.INPUTS=private
            test_reconcile.INPUTS=private
            log=io.StringIO();suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(m) for m in (test_remote,test_reconcile)])
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
            r.exclusive_file(out/'validation.log',log.getvalue().encode())
            if not result.wasSuccessful() or result.skipped or result.testsRun!=35:raise r.CaptureError('remote-offline-tests')
        if q.pins()!=before:raise r.CaptureError('remote-source-changed')
        final={'schema_version':1,'status':'offline-remote-reconciliation-passed-b2-pending','python':platform.python_version(),
            'tests':{'run':result.testsRun,'failures':0,'errors':0,'skipped':0},'packages':verified,'source_sha256':before,
            'source_report_sha256':r.REPORT_SHA,'real_credentials_loaded':False,'remote_upload_performed':False,
            'remote_preservation_verified':False,'retention_verified':False,'production_modified':False,
            'live_launch_authorized':False,'full_gate_accepted':False,'transport_scope':'mocked-command-boundary-only'}
        r.d.o.write(out,'report.json',final);print(final['status']);return 0
    except BaseException:
        if out is not None:
            try:r.d.o.write(out,'failure.json',{'status':'offline-remote-reconciliation-failed','remote_upload_performed':False})
            except Exception:pass
        print('Offline remote check failed; retain report/log. No remote acceptance.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
