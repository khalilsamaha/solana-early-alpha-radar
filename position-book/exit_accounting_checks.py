"""Offline exit accounting: public signature fixtures and synthetic receipts only."""
from copy import deepcopy
import io
import json
from unittest.mock import patch

import exit_accounting as m
from exit_submission_checks import signed_case,FakeRpc,submit,recover,status as transport_status
from admission_receipt_checks import receipt,failed,other_vault
from admission_submission_checks import refuses


def package(c):
    b=c.book()
    try:
        s=m.submission.ExitSubmission(b).signing();p=m.submission.handoff.preparation.saved(b,c.now)
        private,scope=m.private_intent(b,s,p);e=p['evidence']
        v=receipt(dict(scope=scope,costInputs=dict(simulation_item=e['simulationItem'],price=e['price'])),private)
        v['bundle']['rpcEvidence']['signatureStatus']['result']['value'][0]['confirmations']=None
        return v,scope
    finally:b.close()


class ReceiptRpc(FakeRpc):
    def __init__(self,c,p):super().__init__(c);self.package=deepcopy(p)
    def open(self,request,timeout=None):
        r=json.load(super().open(request,timeout));q=json.loads(request.data)
        if q['method']=='getSignatureStatuses':r['result']=self.package['bundle']['rpcEvidence']['signatureStatus']['result']
        if q['method']=='getTransaction':
            tx=self.package['bundle']['rpcEvidence']['transaction']['result']
            r['result']=None if tx is None else dict(deepcopy(tx),transaction=[self.package['signedTransactionBase64'],'base64'])
        return io.BytesIO(json.dumps(r).encode())


def apply(c):return m.apply(c.home,c.wallet,c.pool,clock=lambda:c.now)
def status(c):return m.status(c.home,c.wallet,c.pool,clock=lambda:c.now)
def collect(c,p=None):
    submit(c);recover(c,ReceiptRpc(c,p or package(c)[0]))


def run():
    cases={}
    with signed_case() as c:
        before=c.path.read_bytes();assert not apply(c)['accountingRecorded'] and c.path.read_bytes()==before
        cases['no-submission-no-accounting']='passed'
        submit(c);before=c.path.read_bytes();assert not apply(c)['accountingRecorded'] and c.path.read_bytes()==before
        cases['send-ack-is-not-an-exit-receipt']='passed'
        p,_=package(c);recover(c,ReceiptRpc(c,p));b=c.book()
        try:entry=b.db.execute('SELECT value FROM admission_entry_accounting').fetchone()[0];original=b.read()[0]
        finally:b.close()
        r=apply(c);a=r['accounting'];assert r['state']=='exit-position-flat-held' and r['appliedThisRun']
        assert a['ownedAcquiredBeforeAtomic']==a['acquiredSpentAtomic']=='98' and a['ownedAcquiredResidualAtomic']=='0'
        cases['exact-acquired-quantity-exited-without-spending-protected-inventory']='passed'
        assert int(a['observedAcquiredAccountPostAtomic'])==int(a['protectedAcquiredInventoryAtomic'])
        assert int(a['sourceProceedsHeldAtomic'])>0
        cases['source-proceeds-and-receipt-residual-explicitly-held']='passed'
        assert int(a['originalFeeCommitmentLamports'])==int(a['totalFeePaidLamports'])+int(a['feeCommitmentRemainingLamports'])
        assert int(a['feeCommitmentRemainingLamports'])==sum(int(a[k]) for k in ('remainingAttemptFeeHeldLamports','unusedExitFeeHeldLamports','unusedEntryFeeHeldLamports'))
        cases['entry-exit-fees-and-all-remaining-commitments-conserve']='passed'
        before=c.path.read_bytes();again=apply(c);assert not again['appliedThisRun'] and again['recordSha256']==r['recordSha256'] and c.path.read_bytes()==before
        assert status(c)['accounting']==a and c.path.read_bytes()==before
        cases['idempotent-apply-and-read-only-status']='passed'
        b=c.book()
        try:assert b.db.execute('SELECT value FROM admission_entry_accounting').fetchone()[0]==entry and b.read()[0]==original
        finally:b.close()
        cases['entry-accounting-and-admission-history-remain-immutable']='passed'
        assert all(r[k] is False for k in ('reservationReleased','fundsAvailableForNewEntry','nextCycleAuthorized','currentWalletBalanceEstablished','executionApproved','allocationTransferred'))
        assert c.exit_wire not in json.dumps(r) and 'rpcEvidence' not in json.dumps(r)
        cases['public-accounting-never-authorizes-release-or-new-entry']='passed'
        c.now+=30000;(c.home/'STOP').touch(mode=0o600);r=apply(c)
        assert r['stopRequested'] and r['accounting']==a and c.path.read_bytes()==before
        cases['stop-expiry-preserve-historical-effects']='passed'
    with signed_case() as c:
        p,_=package(c);collect(c,failed(p));a=apply(c)['accounting']
        assert a['state']=='exit-failed-inventory-held' and a['acquiredSpentAtomic']=='0' and a['ownedAcquiredResidualAtomic']=='98'
        assert a['sourceProceedsHeldAtomic']=='0' and int(a['exitFeePaidLamports'])>0 and a['exitAttemptsConsumed']==1
        cases['failed-exit-retains-inventory-and-records-only-fee']='passed'
    with signed_case() as c:
        submit(c);recover(c);before=c.path.read_bytes();r=apply(c)
        assert not r['accountingRecorded'] and c.path.read_bytes()==before
        cases['finality-headers-alone-cannot-settle']='passed'
    for name in ('wrong-vault','wrong-prebalance','over-cap-fee'):
        with signed_case() as c:
            p,scope=package(c);tx=p['bundle']['rpcEvidence']['transaction']['result']
            if name=='wrong-vault':p=other_vault(p,scope)
            elif name=='wrong-prebalance':
                index=tx['transaction']['message']['accountKeys'].index(scope['accounts']['source'])
                next(t for t in tx['meta']['preTokenBalances'] if t['accountIndex']==index)['uiTokenAmount']['amount']='99999999'
            else:tx['meta']['fee']=10001
            collect(c,p);r=apply(c);assert r['state']=='quarantined' and not r['accountingRecorded']
            cases[name+'-quarantines-without-accounting']='passed'
    with signed_case() as c:
        collect(c);apply(c);b=c.book()
        try:
            v=json.loads(b.db.execute('SELECT value FROM admission_exit_accounting').fetchone()[0]);v['accounting']['ownedAcquiredResidualAtomic']='1'
            b.db.execute('UPDATE admission_exit_accounting SET value=?,hash=?',(m.encoded(v),m.digest(v)))
        finally:b.close()
        refuses(lambda:status(c));refuses(lambda:apply(c))
        cases['rehashed-accounting-tamper-refused']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',casesPassed=len(cases),cases=cases,
        networkRequests=0,transactionsSent=0,signaturesCreated=0,privateKeyAccessed=False,temporaryLedgersRemoved=True,
        productionLedgerUpdated=False,reservationReleased=False,allocationTransferred=False,fundsAvailableForNewEntry=False,
        currentWalletBalanceEstablished=False,nextCycleAuthorized=False,executionApproved=False,runtimeIntegrated=False)
