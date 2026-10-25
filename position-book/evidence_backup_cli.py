#!/usr/bin/env python3
"""Create or verify a private local snapshot; never restore into active journals."""
import argparse
from pathlib import Path
import sys
import unittest
import evidence_backup as b
sys.path.insert(0, str(b.r.cycles.c.ROOT / 'launch-study'))
from report import publish


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action', choices=('self-check', 'capture', 'verify'), default='self-check')
    p.add_argument('--directory', type=Path)
    p.add_argument('--snapshot', type=Path)
    p.add_argument('--wallet'); p.add_argument('--pool')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('output-unavailable')
    for root in (a.directory, a.snapshot):
        if root and a.output.resolve().is_relative_to(root.resolve()):
            raise ValueError('report-must-be-outside-private-state')
    if a.action == 'self-check':
        if any((a.directory, a.snapshot, a.wallet, a.pool)):
            raise ValueError('unexpected-self-check-scope')
        import test_evidence_backup
        suite = unittest.defaultTestLoader.loadTestsFromModule(test_evidence_backup)
        result = unittest.TestResult(); suite.run(result)
        if not result.wasSuccessful() or result.skipped or result.testsRun != 17:
            raise ValueError('offline-checks-failed')
        report = dict(format=b.VERSION, state='offline-checks-passed', casesPassed=result.testsRun,
                      existingWalletAccessed=False, networkRequests=0, transactionsSent=0)
    else:
        if not all((a.snapshot, a.wallet, a.pool)):
            raise ValueError('explicit-scope-required')
        if a.action == 'capture':
            if a.directory is None: raise ValueError('source-directory-required')
            report = b.capture(a.directory, a.wallet, a.pool, a.snapshot)
        else:
            if a.directory is not None: raise ValueError('verification-does-not-use-active-journals')
            report = b.verify(a.snapshot, a.wallet, a.pool)
    publish(a.output, report)
    print('State:', report['state'])
    if 'casesPassed' in report: print('Offline cases passed:', report['casesPassed'])
    print('No key export, network request, signing, or submission.')
    print('Upload only this public report:', a.output.absolute())
    if a.snapshot: print('Keep the private snapshot locally; do not upload it.')


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        raise SystemExit('Private evidence check stopped (' + type(exc).__name__ +
                         '). Preserve source journals and any incomplete snapshot; no automatic retry or repair.')
