#!/usr/bin/env python3
"""Read-only launch study; publish a complete replayable report or no report."""
import argparse
import gzip
import json
import os
import sys
import tempfile
from pathlib import Path

from analyze import analyze
from capture import capture, CaptureError

MAX_REPORT_BYTES = 64 * 1024 * 1024


def read_capture(path):
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError('Report byte cap reached')
    report = json.loads(raw)
    if report.get('format') != 'launch-study-report-1':
        raise ValueError('Unsupported replay report')
    return report['capture']


def publish(path, report):
    """Atomic exclusive publication; no overwrite of earlier evidence."""
    path = Path(path).absolute()
    raw = json.dumps(report, separators=(',', ':'), allow_nan=False).encode()
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError('Report byte cap reached; narrow --hours')
    fd, temporary = tempfile.mkstemp(prefix='.launch-study-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            with gzip.GzipFile(fileobj=stream, mode='wb', mtime=0) as archive:
                archive.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if os.geteuid() == 0 and os.environ.get('SUDO_UID', '').isdigit() and os.environ.get('SUDO_GID', '').isdigit():
            os.chown(temporary, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
        os.link(temporary, path)  # fails rather than overwriting an existing path
    finally:
        os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--project', type=Path)
    source.add_argument('--database', type=Path)
    source.add_argument('--input', type=Path, help='Replay a saved report without opening a database')
    parser.add_argument('--hours', type=int, default=6, choices=range(1, 25))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input:
        captured = read_capture(args.input)
    else:
        path = args.database
        if args.project:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'operations-tools'))
            from launch_audit import database
            path = database(args.project.resolve(strict=True))
        captured = capture(path, hours=args.hours)
    analysis = analyze(captured)
    report = {'format': 'launch-study-report-1', 'capture': captured, 'analysis': analysis}
    publish(args.output, report)
    print(json.dumps({'sourceIdentity': captured['sourceIdentity'], 'cutoffAt': captured['cutoffAt'],
        'windowStartAt': captured['windowStartAt'], 'readSeconds': captured['readSeconds'],
        'mode': analysis['mode'], 'sourceEntries': analysis['sourceEntries'],
        'analyzedEntries': analysis['analyzedEntries'], 'excludedEntries': len(analysis['excludedEntries']),
        'cohorts': analysis['cohorts']}, indent=2, allow_nan=False))
    print('Upload: ' + str(args.output.absolute()))


if __name__ == '__main__':
    try:
        main()
    except CaptureError as exc:
        print('Launch study stopped: '+json.dumps(exc.diagnostic,separators=(',',':')),file=sys.stderr)
        raise SystemExit('No partial report published. Send the diagnostic above; the scanner was not modified.')
    except Exception as exc:
        raise SystemExit('Launch study stopped (' + type(exc).__name__ + '). No partial report published; check input, caps and output permissions.')
