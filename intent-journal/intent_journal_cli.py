#!/usr/bin/env python3
"""Offline signed-intent journal. Default: temporary synthetic self-check; never sends."""
import argparse
import datetime as dt
from pathlib import Path

from journal import Journal
from intent_cli import read, publish
from selfcheck import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action', choices=('self-check', 'register', 'boundary', 'observe', 'status'), default='self-check')
    parser.add_argument('--journal', type=Path)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--id')
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    # Refuse conflicting arguments instead of silently ignoring them.
    if a.action == 'self-check':
        if a.journal or a.input or a.id: parser.error('self-check uses only --output')
        result = run()
    else:
        if not a.journal: parser.error('--journal required')
        if bool(a.input) != (a.action in ('register', 'observe')): parser.error('input argument mismatch')
        if bool(a.id) != (a.action in ('boundary', 'observe', 'status')): parser.error('id argument mismatch')
        j = Journal(a.journal, create=a.action == 'register')
        try:
            if a.action == 'register': result = j.register(read(a.input))
            elif a.action == 'boundary': result = j.mark_submission_boundary(a.id)
            elif a.action == 'observe': result = j.observe(a.id, read(a.input))
            else: result = j.result(a.id)
        finally:
            j.close()
        result['mode'] = 'offline-local-journal'
    result['capturedAt'] = dt.datetime.now(dt.timezone.utc).isoformat()
    publish(a.output, result)
    print('Signed intent journal:', str(result.get('casesPassed', result.get('state'))))
    print('No network requests or transactions sent. Upload:', a.output.resolve())


if __name__ == '__main__':
    try: main()
    except Exception as e:
        raise SystemExit('Intent journal stopped: ' + type(e).__name__ + '; inspect local status before retrying a mutation.')
