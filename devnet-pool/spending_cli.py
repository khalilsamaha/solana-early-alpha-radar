#!/usr/bin/env python3
"""Offline-only check of the controlled sender's durable spending reservations."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

from controlled_swap import ROOT
from spend_guard import POLICY, VERSION
sys.path.insert(0, str(ROOT / 'launch-study'))
from report import publish


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('Output unavailable')
    import test_spend_guard
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_spend_guard)
    count = suite.countTestCases()
    result = unittest.TestResult()
    suite.run(result)
    if count != 19 or result.testsRun != count or result.skipped or not result.wasSuccessful():
        raise ValueError('Spending guard offline checks failed')
    report = dict(format=VERSION + '-self-check', state='offline-checks-passed',
                  capturedAt=datetime.now(timezone.utc).isoformat(), casesPassed=count,
                  policy=POLICY, publicRpcRequests=0, liveTransactionsSent=0,
                  existingWalletAccessed=False, disposableKeysUsed=True,
                  executionApproved=False, mainnetEnabled=False,
                  mode='disposable-unfunded-wallets-synthetic-rpc',
                  limitations=['Offline integration evidence only; no network execution of this guard is established.',
                               'Existing historical swaps are not retroactively budget-enforced.'])
    publish(a.output, report)
    print('State:', report['state'])
    print('Offline cases passed:', count)
    print('No existing wallet access, public RPC requests, or live transactions.')
    print('Upload only this public report:', a.output.absolute())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Offline spending check stopped (' + type(exc).__name__ + '). No live transaction was sent.')
