"""Synthetic dispatcher checks using pre-existing public signatures, no signer keys."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import signer_handoff as m
import pre_sign_admission as admission
from locked_admission_checks import fixture, home_fixture, NOW
from pre_sign_checks import reject
import journal


def run():
    e,p,signed=fixture();wallet=p['scope']['accounts']['wallet'];pool=p['scope']['accounts']['pool']
    snapshot=deepcopy(e['costInputs']['reservations']);snapshot.update(readStartedAtMs=NOW+200,observedAtMs=NOW+200)
    cases={};now=[NOW+200]
    with tempfile.TemporaryDirectory() as tmp,patch.object(admission,'BASELINE',e['costInputs']['baseline']),patch.object(m.bridge.view,'read_locked',return_value=snapshot):
        root=Path(tmp)
        def home(name):return home_fixture(root/name,wallet)
        def call(h,adapter):return m.dispatch(h,wallet,pool,e,p,signer_adapter=adapter,clock=lambda:now[0])
        def recover(h,**kw):return m.recover(h,wallet,pool,clock=lambda:now[0],**kw)
        h=home('normal');calls=[]
        def adapter(request):
            assert journal._READ_ONLY.get()
            try:
                with m.bridge.view.cycles.c.source_lock(h,wallet):pass
            except BlockingIOError:pass
            else:raise AssertionError('lock not held')
            # Observe the already committed boundary from a separate connection.
            b=admission.Admission(m.storage(h),clock=lambda:now[0])
            try:
                assert b.status()['state']=='signing-unknown'
                assert b.read()[0]['signingRequest']==request
            finally:b.close()
            calls.append(request);return signed['signedTransactionBase64']
        r=call(h,adapter)
        assert len(calls)==1 and r['accountingHandoffReady'];cases['durable-request-before-one-locked-adapter-call']='passed'
        assert r['admission']['eventCount']==5;cases['same-ledger-accounting-outbox']='passed'
        assert r['admission']['reservation']['reservedFeeLamports']=='26000';cases['handoff-does-not-release-or-copy-budget']='passed'
        assert signed['signedTransactionBase64'] not in json.dumps(r) and 'receiptIntentTemplate' not in json.dumps(r)
        cases['private-request-and-wire-not-exported']='passed'
        assert call(h,adapter)['signerAdapterCallsThisRun']==0 and len(calls)==1
        cases['repeat-dispatch-never-resigns']='passed'
        now[0]+=20000
        again=recover(h);assert again['accountingHandoffReady'];cases['expired-recovery-preserves-handoff']='passed'
        b=admission.Admission(m.storage(h),clock=lambda:now[0])
        try:
            item=b.private_accounting_handoff();assert item['intent']['inputAtomic']=='100'
            assert item['intent']['maximumFeeLamports']=='6000' and item['intent']['source']['preAmountAtomic']=='1000'
            assert item['intent']['walletPreLamports']=='100000' and not item['receiptApplied']
            assert item['signedTransactionBase64']==signed['signedTransactionBase64']
            cases['receipt-template-bound-to-original-raw-balances']='passed'
        finally:b.close()
        now[0]=NOW+200;h=home('lost')
        def lost(request):raise TimeoutError('synthetic lost response')
        try:call(h,lost)
        except TimeoutError:pass
        else:raise AssertionError('missing callback failure')
        assert recover(h)['state']=='signing-unknown';cases['lost-ack-keeps-commitment']='passed'
        assert call(h,lambda _: (_ for _ in ()).throw(AssertionError('retry')))['state']=='signing-unknown'
        cases['unknown-dispatch-does-not-invoke-adapter']='passed'
        now[0]+=20000;r=recover(h,signed_response=signed['signedTransactionBase64'])
        assert r['accountingHandoffReady'] and r['signerAdapterCallsThisRun']==0
        cases['existing-ack-recovery-without-resigning']='passed'
        now[0]=NOW+200;h=home('stop')
        def stopped(request):(h/'STOP').touch(mode=0o600);return signed['signedTransactionBase64']
        r=call(h,stopped);assert r['state']=='stopped' and r['accountingHandoffReady']
        cases['stop-after-call-retains-signed-evidence']='passed'
        h=home('wrong');r=call(h,lambda _:signed['otherSignedTransactionBase64'])
        assert r['state']=='quarantined' and not r['accountingHandoffReady']
        cases['conflicting-response-blocks-accounting-handoff']='passed'
        h=home('partial')
        with patch.object(admission,'MAX_EVENTS',4):
            reject(lambda:call(h,lambda _:signed['signedTransactionBase64']))
        r=recover(h);assert r['accountingHandoffReady']
        cases['outbox-write-failure-recovers-without-callback']='passed'
        assert len(list(m.storage(h).parent.glob('*.sqlite')))==1
        cases['one-fixed-ledger-per-source']='passed'
        h=home('missing')
        try:recover(h)
        except (ValueError,OSError):pass
        else:raise AssertionError('created a recovery ledger')
        assert not (h.parent/(h.name+'-entry-handoff-v1')).exists()
        cases['recovery-never-creates-an-allocation']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,temporaryLedgersRemoved=True,
        networkRequests=0,signaturesCreated=0,transactionsSent=0,privateKeyAccessed=False,
        liveKeyBackendConnected=False,liveSenderIntegrated=False,executionApproved=False,
        productionLedgerUpdated=False,walletWideReservationsKnown=False,
        receiptApplied=False,allocationTransferred=False,automaticResigningAllowed=False)
