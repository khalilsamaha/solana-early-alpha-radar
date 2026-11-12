"""Synthetic Docker boundary acceptance; no production rollout or provider access."""
import argparse
import asyncio
import io
import os
from pathlib import Path
import platform
import signal
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO / 'r1-data'))
import check as core
import check_shared
from capture import CaptureError, canonical, digest, exclusive_file
from handoff import path_without_links
from provider_wire import dependency
from shared_rehearsal import exercise
from container_boundary import Consumer, IMAGE, host, missing_endpoint


def pins():
    result = check_shared.source_pins()
    files = [*ROOT.glob('*.py'), ROOT / 'README.md', REPO / 'scanner/package.json',
             *[REPO / 'r1-host-review' / n for n in ('check.py', 'test_check.py', 'README.md')]]
    result.update({str(p.relative_to(REPO)): digest(p.read_bytes()) for p in files})
    return dict(sorted(result.items()))


def tests():
    suite = unittest.TestLoader().discover(str(ROOT), pattern='test_*.py')
    r = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    if not r.wasSuccessful() or not r.testsRun or r.skipped:
        raise CaptureError('container-regression-failed')
    return {'run': r.testsRun, 'failures': 0, 'errors': 0, 'skipped': 0}


async def docker_cases(output, consumers):
    loop = asyncio.get_running_loop()
    current = asyncio.current_task()
    # Let TERM/INT unwind owner and disposable-container cleanup. Avoid competing
    # with SIGALRM used by the separate baseline regression suite.
    def cancel_once():
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: None)
        current.cancel()
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    for sig in previous:
        loop.add_signal_handler(sig, cancel_once)
    try:
        results = {}
        for name, failure in (('normal', False), ('cleanup_failure', True)):
            control = output / (name + '-container')
            control.mkdir(mode=0o700)
            consumer = Consumer(control)
            consumers.append(consumer)
            try:
                result = await exercise(output / name, fail_cleanup=failure, launcher=consumer)
            finally:
                await consumer.cleanup()
            result['container'] = consumer.receipt()
            if result['container']['exit_code'] != 0 or not consumer.removed:
                raise CaptureError('container-completion-unconfirmed')
            results[name] = result
        control = output / 'missing-endpoint-container'
        control.mkdir(mode=0o700)
        consumer = Consumer(control)
        consumers.append(consumer)
        with tempfile.TemporaryDirectory(prefix='r1-absent-ipc-') as tmp:
            try:
                results['missing_endpoint'] = await missing_endpoint(consumer, Path(tmp))
            finally:
                await consumer.cleanup()
        if consumer.exit_code != 1 or not consumer.removed:
            raise CaptureError('container-startup-rejection-unconfirmed')
        return results
    finally:
        for sig, handler in previous.items():
            loop.remove_signal_handler(sig)
            signal.signal(sig, handler)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CaptureError('container-check-arguments')


def main(argv=None):
    output = None
    output_created = False
    stage = "arguments"
    consumers = []
    report = {'schema_version': 1, 'status': 'offline-container-failed-live-blocked',
        'synthetic_only': True, 'provider_connection_opened': False,
        'credentials_loaded': False, 'production_modified': False,
        'live_launch_authorized': False, 'full_gate_accepted': False,
        'actual_rollout_or_rollback_tested': False, 'container_boundary_tested': False}
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--output-directory', required=True)
        parser.add_argument('--offline-only', action='store_true')
        args = parser.parse_args(argv)
        os.umask(0o077)
        output = path_without_links(args.output_directory)
        output.mkdir(mode=0o700)
        output_created = True
        stage = "offline-checks"
        started = time.monotonic()
        core.block_internet()
        before = pins()
        report.update(python=platform.python_version(), dependencies=dependency(),
                      core_tests=core.run_checks(), boundary_tests=tests(), scanner_tests=check_shared.node_checks())
        if args.offline_only:
            report['normal'] = asyncio.run(exercise(output / 'normal', transport='pipe'))
            report['cleanup_failure'] = asyncio.run(exercise(output / 'cleanup_failure', transport='pipe', fail_cleanup=True))
            report['status'] = 'offline-container-controls-passed-docker-pending'
        else:
            stage = "host-identity"
            with tempfile.TemporaryDirectory(prefix='r1-empty-docker-config-') as tmp:
                observation = host.observe(Path(tmp))
            if observation['findings'] or observation['container']['image'] != IMAGE:
                raise CaptureError('container-host-baseline-changed')
            report['host_identity_rechecked'] = True
            stage = 'container-scenarios'
            report.update(asyncio.run(docker_cases(output, consumers)))
            report['container_boundary_tested'] = True
            report['status'] = 'offline-container-boundary-passed-live-blocked'
        stage = "source-verification"
        after = pins()
        if before != after:
            raise CaptureError('container-sources-changed')
        report.update(source_sha256=after, elapsed_seconds=round(time.monotonic() - started, 6))
        stage = 'evidence-publication'
        exclusive_file(output / 'session.zip', (output / 'normal/export/session.zip').read_bytes())
        exclusive_file(output / 'report.json', (canonical(report) + '\n').encode())
        print('Synthetic boundary review completed; live remains blocked. Upload report.json and session.zip from:')
        print(output)
        return 0
    except BaseException:
        # Preserve fixed diagnostics and only our generated cleanup identities.
        # No daemon stderr, credential values or arbitrary exception strings.
        report['status'] = 'offline-container-failed-live-blocked'
        report['failure_stage'] = stage
        report['cleanup'] = [c.receipt() for c in consumers]
        if output_created and output is not None and output.is_dir() and not (output / 'report.json').exists():
            try:
                exclusive_file(output / 'report.json', (canonical(report) + '\n').encode())
            except Exception:
                pass
        print('Boundary check stopped. Preserve the output directory and upload report.json if present. No acceptance granted.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
