#!/usr/bin/env python3
"""Explicit controlled-devnet acceptance actions; defaults to an offline check."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import controlled_acceptance as m
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def exit_code(action, report):
    if action == 'check': return 0 if report['state']=='offline-acceptance-passed' else 2
    expected = {
        'status': {'local-scope-consistent', 'lifecycle-consistent'},
        'entry': {'rpc-acknowledged'}, 'exit': {'rpc-acknowledged'},
        'recover-entry-signature': {'signed-recorded'},
        'recover-exit-signature': {'exit-signed-recorded'},
        'settle-entry': {'entry-settled-exit-not-prepared'},
        'settle-exit': {'exit-position-flat-held', 'closed-scoped-commitments-released'},
        'close-exit': {'closed-scoped-commitments-released'},
    }
    ok = report['dispatchCompleted'] and report['state'] in expected[action]
    if action in m.SIGNING:
        ok = ok and (report.get('result') or {}).get('completedWithinOriginalDeadline') is True
    return 0 if ok else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action', choices=sorted(m.ACTIONS|{'check'}), default='check')
    p.add_argument('--directory', type=Path); p.add_argument('--wallet'); p.add_argument('--pool')
    p.add_argument('--allow-private-key-signing', action='store_true')
    p.add_argument('--allow-devnet-submit', action='store_true')
    p.add_argument('--allow-reconcile', action='store_true')
    p.add_argument('--maximum-exit-attempts', type=int)
    p.add_argument('--maximum-exit-fee-lamports'); p.add_argument('--maximum-total-fee-lamports')
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('output-unavailable')
    scope = (a.directory, a.wallet, a.pool)
    caps = {k:getattr(a,k) for k in m.CAPS if getattr(a,k) is not None}
    flags = dict(allow_private_key_signing=a.allow_private_key_signing,
                 allow_devnet_submit=a.allow_devnet_submit, allow_reconcile=a.allow_reconcile)
    if a.action == 'check':
        if any(x is not None for x in scope) or caps or any(flags.values()):
            raise ValueError('check-has-no-operational-scope')
        from controlled_acceptance_checks import run
        r = run()
    else:
        if any(x is None for x in scope): raise ValueError('explicit-scope-required')
        m.validate(a.action, **flags, **caps)
        root = a.directory.resolve(); out = a.output.resolve()
        # Do not publish reports into the source, either fixed handoff sibling,
        # or any child of those directories, even through a symlinked parent.
        for private in (root, root.parent/(root.name+'-entry-handoff-v1'),
                        root.parent/(root.name+'-unsigned-admission-rehearsal-v1')):
            if out.is_relative_to(private): raise ValueError('output-inside-private-source')
        r = m.dispatch(a.action, *scope, **flags, **caps)
    r['capturedAt'] = datetime.now(timezone.utc).isoformat(); publish(a.output, r)
    print('State:', r['state'])
    if a.action == 'check':
        print('Boundary checks:', r['boundaryChecksPassed'], '; connected lifecycle checks:', r['connectedChecksPassed'])
        print('Offline: disposable test keys and synthetic replies; no user wallet or real network.')
    else:
        print('Action:', a.action, '; result:', r['result'])
        print('Do not repeat entry/exit to retry. Preserve journals; inspect status and use the matching recovery action.')
    print('Upload only this public report:', a.output.absolute())
    # No coarse exit code is used as an execution decision or finality assertion.
    return exit_code(a.action, r)


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Controlled acceptance stopped ('+type(exc).__name__+
            '). Effects may have been committed. Preserve all journals; inspect status, never retry entry/exit automatically.')
