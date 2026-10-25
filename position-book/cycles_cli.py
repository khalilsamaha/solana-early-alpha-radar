#!/usr/bin/env python3
"""Reconcile two completed controlled devnet cycles; no signing or network access."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
import cycles
sys.path.insert(0, str(cycles.c.ROOT / 'launch-study'))
from report import publish


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action', choices=('self-check', 'sync'), default='self-check')
    p.add_argument('--directory', type=Path)
    p.add_argument('--wallet'); p.add_argument('--pool')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('output-unavailable')
    if a.action == 'self-check':
        if any((a.directory, a.wallet, a.pool)):
            raise ValueError('unexpected-scope')
        import test_cycles
        suite = unittest.defaultTestLoader.loadTestsFromModule(test_cycles)
        r = unittest.TestResult(); suite.run(r)
        if not r.wasSuccessful() or r.skipped or r.testsRun != 16:
            raise ValueError('offline-checks-failed')
        report = dict(format=cycles.VERSION, state='offline-checks-passed', casesPassed=r.testsRun,
                      existingWalletAccessed=False, publicRpcRequests=0, liveTransactionsSent=0,
                      mode='disposable-unfunded-wallets-synthetic-rpc')
    else:
        if not all((a.directory, a.wallet, a.pool)):
            raise ValueError('explicit-scope-required')
        report = cycles.sync(a.directory, a.wallet, a.pool)
    report['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(a.output, report)
    print('State:', report['state'])
    if 'casesPassed' in report: print('Offline cases passed:', report['casesPassed'])
    if 'accounting' in report:
        print('Ledger changed:', report['ledgerChanged'], '; events:', report['eventCount'])
        print('Accounting usable:', report['accounting']['accountingUsable'])
        print('Historical totals:', report['accounting']['totals'])
    print('Upload only this public report:', a.output.absolute())
    if report['state'] == 'quarantined': raise SystemExit(2)


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        raise SystemExit('Two-cycle accounting stopped (' + type(exc).__name__ +
                         '). No signing or network request. Preserve all journals.')
