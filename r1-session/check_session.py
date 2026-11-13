"""One offline acceptance batch: lifecycle, failure evidence, evaluation and restore."""
import argparse
import asyncio
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import platform
import re
import sys
import time
import unittest
import zipfile

import session as s
import archive as a
import fixtures
import check as core
from capture import CaptureError, digest, exclusive_file, sync_dir
from handoff import path_without_links, read_private
from provider_wire import dependency

TEST_MODULES = ('test_capture', 'test_measurement', 'test_session_bundle',
                'test_provider_wire', 'test_shared_owner', 'test_shared_session',
                'test_shared_discovery', 'test_contract', 'test_session', 'test_archive')
DIAGNOSTIC = re.compile(r'ResourceWarning|Exception ignored|unraisable|Task exception was never retrieved|was never awaited')


def tests():
    log = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromNames(TEST_MODULES)
    with redirect_stderr(log):
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    raw = log.getvalue().encode()
    accepted = result.wasSuccessful() and result.testsRun > 0 and not result.skipped and not DIAGNOSTIC.search(log.getvalue())
    counts = {'run': result.testsRun, 'errors': len(result.errors), 'failures': len(result.failures), 'skipped': len(result.skipped)}
    return accepted, counts, raw


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CaptureError('session-check-arguments')


def main(argv=None):
    output = None
    created = False
    stage = 'arguments'
    report = {'schema_version': 1, 'status': 'candidate-session-check-failed-live-blocked',
              'synthetic_upstream_only': True, 'provider_connection_opened': False,
              'real_credentials_loaded': False, 'production_modified': False, 'docker_used': False,
              'remote_upload_performed': False, 'retention_verified': False,
              'live_launch_authorized': False, 'full_gate_accepted': False}
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--output-directory', required=True)
        parser.add_argument('--development', action='store_true',
                            help='explicit simulated endpoint; cannot accept Unix IPC')
        args = parser.parse_args(argv)
        os.umask(0o077)
        output = a.preflight(args.output_directory)
        output.mkdir(mode=0o700); created = True
        core.block_internet()
        before = s.pins(); started = time.monotonic()
        report.update(source_sha256=before, python=platform.python_version(), dependencies=dependency(),
                      unix_ipc_required=not args.development, test_modules=list(TEST_MODULES))
        stage = 'regressions'
        accepted, counts, log = tests()
        exclusive_file(output/'validation.log', log)
        report['tests'] = counts
        if not accepted:
            raise CaptureError('session-check-regressions')
        cases = {}
        specifications = [(name, name, 4) for name in fixtures.MODES] + [('different-size', 'normal', 9)]
        archives = {}
        for name, mode, messages in specifications:
            stage = name
            evidence = asyncio.run(fixtures.exercise(output/name, mode, messages,
                node=not args.development and mode in ('normal', 'cleanup-failure', 'watch-expiry'),
                simulated=args.development))
            saved = a.export(output/name/'control', output/(name+'-archive'))
            restored = a.restore(output/(name+'-archive/archive.zip'), saved['archive_sha256'], output/(name+'-restore'))
            if saved['assessment'] != restored['assessment']:
                raise CaptureError('session-check-restore')
            if not args.development and not restored['assessment']['unix_peer_uid_verified']:
                raise CaptureError('session-check-real-peer-required')
            if mode in ('normal', 'watch-expiry', 'idle') and restored['assessment']['local_session_outcome'] != 'capture-stopped':
                raise CaptureError('session-check-clean-scenario')
            if mode not in ('normal', 'watch-expiry', 'idle') and restored['assessment']['local_session_outcome'] == 'capture-stopped':
                raise CaptureError('session-check-failure-hidden')
            raw = read_private(output/(name+'-archive/archive.zip'), a.MAX_PACKAGE)
            if fixtures.SECRET.encode() in raw:
                raise CaptureError('session-check-synthetic-secret-leaked')
            archives[name+'-archive.zip'] = raw
            cases[name] = {'scenario': evidence, 'archive_sha256': digest(raw), 'archive_bytes': len(raw),
                           'assessment': saved['assessment'], 'local_restore_verified': True}
        stage = 'source-verification'
        if before != s.pins():
            raise CaptureError('session-check-source-changed')
        report.update(cases=cases, elapsed_seconds=round(time.monotonic()-started, 6),
            status='candidate-session-development-passed-unix-pending' if args.development
                   else 'candidate-session-offline-passed-live-blocked')
        report_raw = s.json_bytes(report)
        # One portable handoff. Originals, logs and each isolated restore stay
        # beside it. This is a diagnostic bundle, never an executable restore.
        with zipfile.ZipFile(output/'acceptance.zip', 'x', compression=zipfile.ZIP_STORED) as target:
            for name, raw in sorted({**archives, 'report.json': report_raw, 'validation.log': log}.items()):
                info = zipfile.ZipInfo(name); info.create_system = 3; info.external_attr = 0o100600 << 16
                target.writestr(info, raw)
        with (output/'acceptance.zip').open('rb') as handle:
            os.fsync(handle.fileno())
        sync_dir(output)
        exclusive_file(output/'report.json', report_raw)
        print(report['status'])
        print('Upload acceptance.zip; retain the complete output directory:')
        print(output)
        return 0
    except BaseException:
        report['status'] = 'candidate-session-check-failed-live-blocked'
        report['failure_stage'] = stage
        if created and not (output/'report.json').exists():
            try: exclusive_file(output/'report.json', s.json_bytes(report))
            except Exception: pass
        print('Session batch stopped; retain its report and validation.log. No acceptance granted.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
