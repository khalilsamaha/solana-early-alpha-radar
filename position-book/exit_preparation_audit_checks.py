"""Public signed fixtures and disposable journals; synthetic replies only."""
import json
from unittest.mock import patch
import exit_preparation_audit as m
import fresh_exit
from fresh_exit_checks import case


def run():
    cases={}
    def audit(c,**kw):
        return m.inspect(c.home,c.wallet,c.pool,clock=lambda:c.now,monotonic=lambda:0,**kw)
    with case() as c:
        r=audit(c);assert r['coherent'] and r['state']=='exit-preparation-absent',r
        cases['settled-entry-without-preparation-remains-held']='passed'
        with patch.object(fresh_exit.handoff,'dispatch',side_effect=ValueError('exit-signing-expired')):
            stopped=c.run()
        assert stopped['stage']=='signing-validation' and stopped['diagnosticCode']=='exit-signing-expired'
        assert stopped['signerInvocationAttempts']==stopped['sendRequestsThisRun']==0
        cases['pre-sign-validation-failure-is-specific-without-invocation']='passed'
        r=audit(c);assert r['state']=='unsigned-exit-preparation-preserved',r
        deadline=r['preparation']['validUntilExclusiveMs'];identity=r['preparation']['recordSha256']
        cases['saved-unsigned-preparation-is-visible']='passed'
        before=c.path.read_bytes();source={p.name:p.read_bytes() for p in c.home.iterdir() if p.is_file()}
        c.timer.at=c.now=deadline+1;r=audit(c)
        assert r['state']=='expired-unsigned-exit-preserved' and r['preparation']['expiredByMs']==1,r
        assert r['preparation']['remainingMs']==0 and not r['signing']['recorded']
        assert not any(r['backendMarkers'].values())
        cases['expired-unsigned-state-does-not-authorize-replacement']='passed'
        assert r['scopedAccounting']['ownedAcquiredHeldAtomic']=='98' and r['scopedAccounting']['feeHeldLamports']=='20999'
        assert not any(r[k] for k in ('replacementAuthorized','retryAllowed','nextCycleAuthorized','fundsAvailableForNewEntry','executionApproved'))
        cases['owned-inventory-and-fee-holds-preserved']='passed'
        again=audit(c)
        assert again['preparation']==r['preparation'] and again['scopedAccounting']==r['scopedAccounting']
        assert c.path.read_bytes()==before
        assert source=={p.name:p.read_bytes() for p in c.home.iterdir() if p.is_file()}
        cases['repeated-read-only-inspection-preserves-source-and-ledger']='passed'
        (c.home/'STOP').touch(mode=0o600);r=audit(c)
        assert r['stopRequested'] and 'stop-present' in r['blockingReasons'] and r['preparation']['recordSha256']==identity
        cases['stop-does-not-erase-historical-preparation']='passed'
        for name,key in ((m.backend.ATTEMPT,'attemptPresent'),(m.backend.ACK,'acknowledgmentPresent')):
            marker=c.path.parent/name;marker.symlink_to(c.path.parent/'missing-private-marker')
            r=audit(c);assert r['state']=='exit-artifact-inspection-required' and r['backendMarkers'][key]
            assert c.path.read_bytes()==before;marker.unlink()
        cases['dangling-signer-markers-block-unsigned-classification']='passed'
        with patch.object(m.view,'read_locked',return_value={'phase':'changed'}):r=audit(c)
        assert not r['coherent'] and r['preparation'] is None and r['scopedAccounting'] is None
        cases['changed-source-suppresses-partial-accounting']='passed'
        b=c.book()
        try:b.db.execute("UPDATE admission_exit_preparation SET hash=?",('0'*64,))
        finally:b.close()
        damaged=c.path.read_bytes();r=audit(c)
        assert not r['coherent'] and r['preparation'] is None and c.path.read_bytes()==damaged
        cases['corrupt-preparation-remains-unavailable-and-unchanged']='passed'
    with case() as c:
        c.run();r=audit(c)
        assert r['state']=='exit-signing-or-transport-recorded' and r['signing']['recorded'],r
        assert all(r['backendMarkers'].values()) and not r['replacementAuthorized']
        assert c.exit_wire not in json.dumps(r) and 'rpcEvidence' not in json.dumps(r)
        cases['existing-signature-and-send-remain-recovery-only']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',casesPassed=len(cases),
        cases=cases,realNetworkRequests=0,privateKeyAccessed=False,signaturesCreated=0,
        transactionsSent=0,productionLedgerUpdated=False,replacementAuthorized=False,
        executionApproved=False,fixtureBasis='Public signed fixtures, synthetic replies, disposable journals')
