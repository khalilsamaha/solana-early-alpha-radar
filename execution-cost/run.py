#!/usr/bin/env python3
"""Offline cost-contract examples or a bounded caller-declared JSON scenario."""
import argparse
import gzip
import json
import os
from pathlib import Path
import stat
import tempfile
import time

from contract import evaluate, VERSION
from examples import scenarios

MAX_BYTES = 65536


def unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate-json-key')
        value[key] = item
    return value


def reject_constant(_):
    raise ValueError('nonfinite-json')


def read_packet(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError('input-type-or-size')
        raw = stream.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES:
        raise ValueError('input-size')
    return json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)


def publish(path, report):
    path = Path(path).absolute()
    raw = json.dumps(report, allow_nan=False, separators=(',', ':')).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError('output-size')
    fd, temp = tempfile.mkstemp(prefix='.cost-report-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(gzip.compress(raw, mtime=0)); stream.flush(); os.fsync(stream.fileno())
        os.link(temp, path)  # atomic, exclusive publication; no existing file replacement
    finally:
        os.unlink(temp)


def build_report(packet=None, *, now_ms=None):
    if packet is None:
        return dict(format='execution-cost-examples-1', mode='synthetic-examples-only',
                    cases=[dict(name=name, result=evaluate(value, now_ms=100000))
                           for name, value in scenarios()],
                    modelEvaluated=False, productionStateChanged=False, executionApproved=False)
    return dict(format='execution-cost-scenario-1', mode='caller-declared-scenario',
                result=evaluate(packet, now_ms=now_ms), modelEvaluated=False,
                productionStateChanged=False, executionApproved=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Optional plain JSON scenario; no database or export adapter')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.path.lexists(args.output):
        raise ValueError('output-exists')
    packet = read_packet(args.input) if args.input else None
    # JSON null cannot silently select synthetic mode.
    if args.input and packet is None:
        raise ValueError('packet-required')
    report = build_report(packet, now_ms=time.time_ns()//1_000_000)
    publish(args.output, report)
    print('Mode:', report['mode'])
    for case in report.get('cases', []):
        print(case['name'] + ': ' + case['result']['state'])
    if 'result' in report:
        print('State:', report['result']['state'])
    print('No wallet, network, scanner or frozen-study access. No execution approval.')
    print('Report:', args.output.absolute())
    if 'result' in report and report['result']['state'] != 'modeled-constraints-met':
        return 2
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RecursionError):
        raise SystemExit('Cost scenario stopped: invalid/bounded input or unavailable output. No execution occurred.') from None
