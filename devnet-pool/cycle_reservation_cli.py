#!/usr/bin/env python3
"""Check a refused unsigned cycle-2 reservation without key access, network or journal changes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
import cycle_binding as binding
import cycle_preparation as preparation
from core import check, directory, private_file, loads
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launch-study'))
from report import publish

FILES = {'plan.json':32768, 'execution.json':32768, 'preflight.json':4*1024*1024,
         'signing-request.json':8192, 'spending-reservation.json':4096, 'failure.json':4096}


@binding.operation
def inspect(home, wallet, pool):
    with preparation.controlled.source_lock(home, wallet) as root:
        cycle = directory(root / binding.CYCLE)
        identity = binding.load(cycle, wallet, pool)
        child = directory(cycle / preparation.submit.CHILD)
        check({p.name for p in child.iterdir()} == set(FILES), 'unsigned-failed-entry-files-required')
        raw = {name:private_file(child/name, limit) for name,limit in FILES.items()}
        values = {name:loads(data) for name,data in raw.items()}
        plan=values['plan.json']; capture=values['preflight.json']; request=values['signing-request.json']
        failure=values['failure.json']; execution=values['execution.json']; digest=preparation.controlled.digest
        check(plan.get('cycleBinding') == identity and execution.get('planSha256') == digest(plan)
              and execution.get('spendingGuardVersion') == preparation.submit.spend_guard.VERSION,
              'unsigned-entry-binding')
        check(failure.get('phase') == 'signing' and failure.get('reason') == 'execution-validation-or-transport-incomplete',
              'unsigned-signing-refusal-required')
        check(request.get('planSha256') == digest(plan) and request.get('preflightSha256') == digest(capture)
              and capture.get('packet') == plan['packet'], 'unsigned-request-binding')
        check(type(request.get('expiresAtMs')) is int and type(plan['packet']['policy']['expiresAtMs']) is int,
              'unsigned-expiry-shape')
        node=shutil.which('node');check(node is not None,'node-unavailable')
        result=subprocess.run([str(Path(node).resolve()),str(Path(__file__).with_name('cycle_reservation_audit.mjs'))],
            input=json.dumps({'directory':str(root)}),text=True,capture_output=True,timeout=15,env={'PATH':os.defpath})
        check(result.returncode==0,'independent-reservation-check-refused')
        verified=json.loads(result.stdout)
        check(verified == dict(reservationVerified=True,preparationHashBasis='sealed-file-bytes-v1'), 'audit-response-shape')
        check(all(private_file(child/name,FILES[name]) == data for name,data in raw.items()),'evidence-changed-during-audit')
        # No state transition: this reports evidence, never grants execution/replacement permission.
        return dict(format='cycle-unsigned-reservation-audit-1',state='unsigned-reservation-verified',
            cycleId=binding.CYCLE,preparationSha256=identity['preparationSha256'],
            evidenceSha256=digest({name:hashlib.sha256(data).hexdigest() for name,data in raw.items()}),
            **verified,signingAttemptPresent=False,signedTransactionPresent=False,submissionBoundaryPresent=False,
            packetExpired=int(time.time()*1000)>=min(request['expiresAtMs'],plan['packet']['policy']['expiresAtMs']),
            historicalConfirmedFeeLamports=identity['historicalSwapFeeLamports'],reservedFeeLamports='20000',
            heldEntryPrincipalAtomic='1000',networkRequests=0,privateKeyAccessed=False,signaturesCreated=0,
            transactionsSent=0,journalsChanged=False,resubmitAllowed=False,executionApproved=False,
            stopRequested=os.path.lexists(root/'STOP'),
            nextAction='review-before-designing-explicit-unsigned-plan-replacement',
            limitations=['Checks local evidence under the shared wallet lock; same-user files remain trusted.',
                         'Does not refresh balances, revalidate current deployment, release the reservation or enable another attempt.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('self-check','inspect'),default='self-check')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    check(not a.output.exists() and not a.output.is_symlink() and a.output.parent.is_dir(),'output-unavailable')
    if a.action=='self-check':
        check(not any((a.directory,a.wallet,a.pool)),'unexpected-scope')
        import test_cycle_hash
        suite=unittest.defaultTestLoader.loadTestsFromModule(test_cycle_hash)
        r=unittest.TestResult();suite.run(r)
        check(r.wasSuccessful() and not r.skipped and r.testsRun==10,'offline-checks-failed')
        result=dict(format='cycle-unsigned-reservation-audit-1',state='offline-checks-passed',casesPassed=r.testsRun,
                    publicRpcRequests=0,liveTransactionsSent=0,existingWalletAccessed=False)
    else:
        check(all((a.directory,a.wallet,a.pool)),'scope-required')
        result=inspect(a.directory,a.wallet,a.pool)
    result['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,result)
    print('State:',result['state'])
    if 'casesPassed' in result:print('Offline cases passed:',result['casesPassed'])
    print('No live signing, submission or journal changes. Upload:',a.output.absolute())


if __name__=='__main__':
    try:main()
    except Exception:
        raise SystemExit('Unsigned reservation check stopped. Preserve journals; no signing or submission was attempted.')
