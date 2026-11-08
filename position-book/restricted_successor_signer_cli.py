#!/usr/bin/env python3
"""Offline successor key-backend checks with disposable keys; no live actions."""
import argparse
from datetime import datetime,timezone
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    node=shutil.which('node')
    if node is None:raise ValueError('node-runtime-unavailable')
    run=subprocess.run([str(Path(node).resolve()),str(Path(__file__).with_name('successor_signer_checks.mjs'))],
        text=True,capture_output=True,timeout=60,env={'PATH':os.defpath})
    if run.returncode!=0 or len(run.stdout)>16384:raise ValueError('independent-backend-check-failed')
    independent=json.loads(run.stdout)
    from test_restricted_successor_signer import SuccessorBackendTests
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SuccessorBackendTests)
    with patch.object(socket.socket,'connect',side_effect=AssertionError('network-disabled')):
        result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=0).run(suite)
    passed=result.wasSuccessful() and result.testsRun>0 and not result.skipped
    successful=max(0,result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped))
    report=dict(format='restricted-successor-signer-check-1',capturedAt=datetime.now(timezone.utc).isoformat(),
        state='offline-checks-passed' if passed else 'offline-checks-failed',
        casesRun=independent['casesPassed']+result.testsRun,casesPassed=independent['casesPassed']+successful,
        independentBackend=independent,recoveryCasesRun=result.testsRun,recoveryCasesPassed=successful,
        failedCases=[t.id() for t,_ in result.errors+result.failures],skippedCases=[t.id() for t,_ in result.skipped],
        userPrivateKeysAccessed=False,userJournalsOpened=False,ephemeralTestKeysCreated=True,
        networkRequests=0,transactionsSent=0,scannerRuntimeChanged=False,
        liveExecutionExposed=False,liveSenderConnected=False,executionApproved=False,
        limitations=['Independent process checks use disposable keys and synthetic committed ledgers.',
            'Recovery tests replay semantic retired-source fixtures and verify real disposable signatures.',
            'No complete live collection-to-signing timing or target-route execution is established.',
            'Retired fees and inventory remain held. A missing acknowledgment never permits re-signing.'])
    publish(a.output,report)
    print('State:',report['state']);print('Offline cases passed:',report['casesPassed'])
    print('Independent backend:',independent['casesPassed'],'; recovery:',successful)
    print('Disposable keys only; no user wallet, RPC, transaction or runtime changes.')
    print('Upload:',a.output.absolute())
    return 0 if passed else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Offline successor backend check stopped ('+type(exc).__name__+').')
