#!/usr/bin/env python3
"""Default offline boundaries, or one explicitly authorized devnet continuation."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import controlled_continuation as m
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action', choices=('check', 'inspect', 'execute'), default='check')
    p.add_argument('--directory', type=Path); p.add_argument('--wallet'); p.add_argument('--pool')
    p.add_argument('--expected-original-sha256');p.add_argument('--expected-current-sha256')
    for flag in ('unsigned-continuation', 'private-key-signing', 'devnet-submit'):
        p.add_argument('--allow-'+flag, action='store_true')
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('output-unavailable')
    scope = (a.directory, a.wallet, a.pool)
    flags = dict(expected_original_sha256=a.expected_original_sha256,expected_current_sha256=a.expected_current_sha256,
        allow_unsigned_continuation=a.allow_unsigned_continuation,
        allow_private_key_signing=a.allow_private_key_signing,
        allow_devnet_submit=a.allow_devnet_submit)
    if a.action == 'check':
        if any(x is not None for x in scope) or (a.expected_original_sha256 is not None or a.expected_current_sha256 is not None) or any(
                flags[k] for k in flags if k.startswith('allow_')):
            raise ValueError('check-has-no-operational-scope')
        from controlled_continuation_checks import run
        r = run(); code = 0
    else:
        if any(x is None for x in scope): raise ValueError('explicit-scope-required')
        if a.action=='inspect':
            if any(flags[k] for k in flags if k.startswith('allow_')):raise ValueError('inspection-has-no-execution-opt-ins')
            m.identities(a.expected_original_sha256,a.expected_current_sha256)
        else:m.validate(**flags)
        root = a.directory.resolve(); out = a.output.resolve()
        for private in (root, root.parent/(root.name+'-entry-handoff-v1'),
                        root.parent/(root.name+'-unsigned-admission-rehearsal-v1')):
            if out.is_relative_to(private): raise ValueError('output-inside-private-source')
        if a.action=='inspect':
            r=m.inspect(*scope,expected_original_sha256=a.expected_original_sha256,expected_current_sha256=a.expected_current_sha256)
            code=0 if r['eligibleNow'] else 2
        else:
            r = m.execute(*scope, **flags); code = m.exit_code(r)
    r['capturedAt'] = datetime.now(timezone.utc).isoformat(); publish(a.output, r)
    print('State:', r['state'])
    if a.action == 'check':
        print('Command boundary checks:', r['casesPassed'])
        print('Offline boundary tests only; no user wallet, signing or real network.')
    elif a.action=='inspect':
        print('Eligible now:',r['eligibleNow'],'; diagnostic:',r['diagnosticCode'])
        print('Read-only local facts only. Inspection is not execution approval.')
    else:
        print('Result:', r['result'])
        print('Do not repeat execute. Preserve journals and use existing status/recovery actions.')
    print('Upload only this public report:', a.output.absolute())
    return code


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Controlled continuation stopped ('+type(exc).__name__+
            '). Effects may have been committed. Preserve journals; never repeat execute to retry.')
