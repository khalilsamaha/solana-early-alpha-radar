#!/usr/bin/env python3
"""Profile one phase of a disposable offline rehearsal; never a timing acceptance run."""
import argparse
import cProfile
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
import sys
from unittest.mock import patch

MODULE_GROUPS = {
    'canonical_replay.py': 'canonical-comparison',
    'serialization_replay.py': 'serialization-replay',
    'encoder.py': 'json-encoding', 'decoder.py': 'json-decoding',
    'base64.py': 'base64-conversion',
    'subprocess.py': 'child-process-management',
    'exit_submission.py': 'submission-validation',
    'exit_signing.py': 'signing-validation',
    'exit_read_snapshot.py': 'snapshot-validation',
    'reservation_view.py': 'reservation-replay',
}
BUILTINS = {
    "<method 'execute' of 'sqlite3.Connection' objects>": 'sqlite',
    "<method 'execute' of 'sqlite3.Cursor' objects>": 'sqlite',
    "<method 'fetchone' of 'sqlite3.Cursor' objects>": 'sqlite',
    "<method 'fetchall' of 'sqlite3.Cursor' objects>": 'sqlite',
    "<method 'commit' of 'sqlite3.Connection' objects>": 'sqlite',
    "<method 'rollback' of 'sqlite3.Connection' objects>": 'sqlite',
    "<method '__exit__' of 'sqlite3.Connection' objects>": 'sqlite',
    '<built-in method posix.fsync>': 'durable-flush',
    '<built-in method posix.waitpid>': 'child-process-wait',
    "<method 'poll' of 'select.poll' objects>": 'poll-wait',
}


def summarize(profile):
    groups = {}
    for row in profile.getstats():
        code = row.code
        if type(code) is str:
            category = BUILTINS.get(code, 'other-builtins')
        else:
            category = MODULE_GROUPS.get(Path(code.co_filename).name, 'other-python')
        group = groups.setdefault(category, dict(calls=0, selfMs=0., inclusiveMs=0.))
        group['calls'] += row.callcount
        group['selfMs'] += row.inlinetime * 1000
        group['inclusiveMs'] += row.totaltime * 1000
    for group in groups.values():
        group['selfMs'] = round(group['selfMs'], 3)
        group['inclusiveMs'] = round(group['inclusiveMs'], 3)
    return dict(sorted(groups.items(), key=lambda item: -item[1]['selfMs']))


def instrument(fn, profiles, enabled=lambda: True):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not enabled():
            return fn(*args, **kwargs)
        profile = cProfile.Profile()
        try:
            return profile.runcall(fn, *args, **kwargs)
        finally:
            profiles.append(summarize(profile))
    return wrapped


def run(stage):
    if stage not in ('collection', 'signing', 'submission'):
        raise ValueError('unknown-profile-phase')
    import continuation_exit_checks as checks
    targets = {'collection': (checks.m.continuation, 'collect_and_prepare'),
               'signing': (checks.m.handoff, 'dispatch'),
               'submission': (checks.m.submission, 'submit')}
    module, name = targets[stage]
    profiles = []
    active = [False]
    original_phase = checks.phase
    @contextmanager
    def scoped_phase(report, phase_name, **options):
        previous = active[0]
        if phase_name == 'continuation-sign-send': active[0] = True
        try:
            with original_phase(report, phase_name, **options) as row:
                yield row
        finally:
            active[0] = previous
    with checks.fixture_size(True), patch.object(checks, 'phase', scoped_phase), patch.object(module, name,
            instrument(getattr(module, name), profiles, enabled=lambda: active[0])):
        # Full connected path, with disposable predecessors, real clocks and all
        # recovery checks. Standalone fault suite is not part of this profile.
        rehearsal = checks._run(large_fixture=True, faults={})
    return dict(format='continuation-phase-cost-profile-1', profiledPhase=stage,
        capturedAt=datetime.now(timezone.utc).isoformat(), profiles=profiles,
        rehearsal=rehearsal, timingAcceptance=False, executionApproved=False,
        limitations=[
            'Profiler overhead may cause expiry; preserve partial phase data.',
            'This is not the complete fault-suite acceptance report.',
            'Inclusive function times overlap; do not sum them as wall time.',
            'Self time includes blocking inside builtins; it is not CPU usage.',
            'Child process internals are not profiled; their parent wait remains visible.',
            'No raw profiler dump, arguments, keys, SQL, or filesystem paths are exported.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('collection','signing','submission'), default='signing')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        raise ValueError('output-unavailable')
    result = run(args.phase)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
    from report import publish
    publish(args.output,result)
    print('Profile phase:',args.phase)
    print('Underlying rehearsal:',result['rehearsal']['state'])
    print('Profiled calls:',len(result['profiles']))
    print('Diagnostic only; profiler time is not acceptance evidence.')
    print('Upload:',args.output.absolute())


if __name__=='__main__':
    try:main()
    except Exception as exc:
        raise SystemExit('Offline phase profile stopped ('+type(exc).__name__+'). No complete report published.')
