#!/usr/bin/env python3
"""Import controlled devnet receipts into a separate historical position ledger."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import controlled
sys.path.insert(0, str(controlled.ROOT / 'launch-study'))
from report import publish


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action', choices=('self-check', 'sync'), default='self-check')
    p.add_argument('--directory', type=Path)
    p.add_argument('--wallet')
    p.add_argument('--pool')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('Output unavailable')
    if a.action == 'self-check':
        if any((a.directory, a.wallet, a.pool)):
            raise ValueError('Unexpected self-check scope')
        import unittest
        import test_controlled
        suite = unittest.defaultTestLoader.loadTestsFromModule(test_controlled)
        result = unittest.TestResult()
        suite.run(result)
        if not result.wasSuccessful() or result.skipped:
            raise ValueError('Offline checks failed')
        report = dict(format=controlled.VERSION, state='offline-checks-passed',
                      casesPassed=result.testsRun, existingWalletAccessed=False,
                      mode='disposable-unfunded-wallets-synthetic-rpc', disposableKeysUsed=True,
                      publicRpcRequests=0, liveTransactionsSent=0, executionApproved=False)
    else:
        if not all((a.directory, a.wallet, a.pool)):
            raise ValueError('Explicit journal wallet and pool required')
        report = controlled.sync(a.directory, a.wallet, a.pool)
    report['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(a.output, report)
    print('State:', report['state'])
    if 'position' in report:
        v = report['position']
        print('Residual acquired atomic:', v['lastReconciledResidualAtomic'])
        print('Net original token atomic:', v['netOriginalTokenAtomic'])
        print('Confirmed native fee lamports:', v['confirmedFeeLamports'])
        print('Ledger changed:', report['ledgerChanged'], '; events:', report['eventCount'])
    print('Upload only this public report:', a.output.absolute())
    if report['state'] == 'quarantined':
        raise SystemExit(2)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Controlled accounting stopped (' + type(exc).__name__ +
                         '). No signing, network request or transaction. Preserve the journals.')
