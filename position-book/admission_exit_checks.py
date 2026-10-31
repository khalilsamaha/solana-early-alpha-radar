"""Offline first-exit preparation checks using existing public signature fixtures."""
import base64
from copy import deepcopy
import hashlib
import json
from unittest.mock import patch

import admission_exit as m
from admission_submission_checks import case,FakeOpener,refuses
from admission_receipt_checks import failed
from entry_accounting_checks import collect,apply
from paired_checks import leg,NOW,edit,simulation_response
from fresh_packet import message
from contract import decode
from state_fixtures import fake_key


def fixture(c,offset=30000):
    raw=leg(True,offset);args=raw['costInputs'];capture=args['capture'];packet=args['packet']
    packet['policy']['accounts']['wallet']=c.wallet
    capture['accountKeys'][8]=c.wallet
    edit(capture,9,32,decode(c.wallet));edit(capture,10,32,decode(c.wallet))
    packet['policy']['blockhash']=fake_key('fresh-delayed-exit')
    scope=m.scope_for(packet['policy'])
    args['price']=m.derive(raw['initialPool'],scope,slippage_bps=100,now_ms=NOW+offset+200)
    msg=message(scope,packet['policy']['blockhash'])
    packet['unsignedTransactionBase64']=base64.b64encode(b'\x01'+bytes(64)+msg).decode()
    packet['feeAssertion']['messageSha256']=hashlib.sha256(msg).hexdigest()
    capture['messageSha256']=packet['feeAssertion']['messageSha256']
    sim=simulation_response(capture,args['price']['quote']['outAmount'])
    sim['value']['failed']=False;sim['value'].pop('err')
    return dict(initialPool=raw['initialPool'],packet=packet,capture=capture,price=args['price'],
        simulationItem=dict(state='received',result=sim),simulationStartedAtMs=args['simulation_started'],
        simulationReceivedAtMs=args['simulation_received'],completedAtMs=raw['completedAtMs']),args['baseline']


def prepare(c,e,b):
    snapshot=deepcopy(c.e['costInputs']['reservations'])
    snapshot.update(readStartedAtMs=c.now,observedAtMs=c.now)
    with patch.object(m,'BASELINE',b),patch.object(m.view,'read_locked',return_value=snapshot):
        return m.prepare(c.home,c.wallet,c.pool,e,clock=lambda:c.now)


def status(c,b):
    with patch.object(m,'BASELINE',b):return m.status(c.home,c.wallet,c.pool,clock=lambda:c.now)


def run():
    cases={}
    with case() as c:
        collect(c);a=apply(c);e,b=fixture(c);c.now=NOW+30200
        before={p.name:p.read_bytes() for p in c.home.iterdir()}
        r=prepare(c,e,b);binding=r['binding']
        assert r['state']=='exit-prepared-research-only' and r['createdThisRun']
        assert binding['quantityAtomic']=='98' and binding['protectedInventoryAtomic']=='902'
        cases['fresh-exit-after-entry-expiry-owns-only-acquired-delta']='passed'
        assert binding['feeCommitmentRemainingLamports']=='20999' and binding['otherFeeCommitmentsHeldLamports']=='14999'
        cases['single-attempt-cap-preserves-all-other-fee-commitments']='passed'
        old=c.path.read_bytes();assert not prepare(c,e,b)['createdThisRun']
        assert c.path.read_bytes()==old and status(c,b)['recordSha256']==r['recordSha256']
        cases['same-ledger-idempotency-and-read-only-reopen']='passed'
        assert apply(c)['recordSha256']==a['recordSha256']
        assert before=={p.name:p.read_bytes() for p in c.home.iterdir()}
        cases['entry-accounting-and-historical-source-remain-unchanged']='passed'
        assert e['packet']['unsignedTransactionBase64'] not in json.dumps(r)
        assert all(r[k] is False for k in ('reservationReleased','allocationTransferred','executionApproved','signingApproved','validForSubmission','runtimeIntegrated'))
        assert r['attemptsConsumed']==0
        cases['public-report-is-not-wire-or-execution-capability']='passed'
        changed=deepcopy(e);changed['price']['quote']['outAmount']='999'
        refuses(lambda:prepare(c,changed,b));assert c.path.read_bytes()==old
        cases['prepared-evidence-cannot-be-replaced']='passed'
        c.now=NOW+60000
        assert status(c,b)['state']=='exit-preparation-expired'
        assert prepare(c,e,b)['state']=='exit-preparation-expired' and c.path.read_bytes()==old
        cases['expiry-preserves-record-and-does-not-refresh-deadline']='passed'
        (c.home/'STOP').touch(mode=0o600)
        assert status(c,b)['state']=='exit-preparation-stopped'
        refuses(lambda:prepare(c,e,b));assert c.path.read_bytes()==old
        cases['stop-blocks-preparation-without-erasing-history']='passed'
    for name,mutate in {
        'entry-blockhash-reuse':lambda e,c:e['packet']['policy'].update(blockhash=c.e['costInputs']['packet']['policy']['blockhash']),
        'different-quantity':lambda e,c:e['packet']['policy'].update(amountIn='99'),
        'different-wallet':lambda e,c:e['packet']['policy']['accounts'].update(wallet=c.pool),
        'caller-reservations':lambda e,c:e.update(reservations={'nativeHeldLamports':'0'}),
        'summary-instead-of-simulation':lambda e,c:e.update(simulationItem={'state':'success'}),
        'reused-entry-state':lambda e,c:e['initialPool'].update(startedAtMs=NOW-1000),
        'account-slot-before-receipt':lambda e,c:e['capture']['evidence']['accounts']['result']['context'].update(slot=101),
        'native-budget-shortfall':lambda e,c:e['capture']['evidence']['accounts']['result']['value'][8].update(lamports=20000),
        'owned-token-shortfall':lambda e,c:edit(e['capture'],9,64,(97).to_bytes(8,'little')),
        'invalid-blockhash':lambda e,c:e['capture']['evidence']['blockhash']['result'].update(value=False),
        'fee-response-mismatch':lambda e,c:e['capture']['evidence']['fee']['result'].update(value=6001),
        'changed-deployment':lambda e,c:edit(e['capture'],-1,120,b'\x01'),
        'changed-price':lambda e,c:e['price']['quote'].update(outAmount='999'),
        'simulation-token-mismatch':lambda e,c:e['simulationItem']['result']['value']['postTokenBalances'][0]['uiTokenAmount'].update(amount='1'),
        'stale-exit':lambda e,c:setattr(c,'now',NOW+60000),
    }.items():
        with case() as c:
            collect(c);apply(c);e,b=fixture(c);c.now=NOW+30200;mutate(e,c)
            before=c.path.read_bytes();refuses(lambda:prepare(c,e,b));assert c.path.read_bytes()==before
            cases[name+'-refused-without-write']='passed'
    for name in ('no-receipt','failed-entry','quarantined-entry','unrecorded-accounting'):
        with case() as c:
            if name=='failed-entry':collect(c,failed(c.package));apply(c)
            elif name=='quarantined-entry':c.submit(FakeOpener(c,send=c.wallet));apply(c)
            elif name=='unrecorded-accounting':collect(c)
            e,b=fixture(c);c.now=NOW+30200;old=c.path.read_bytes()
            refuses(lambda:prepare(c,e,b));assert c.path.read_bytes()==old
            cases[name+'-cannot-prepare-exit']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,temporaryLedgersRemoved=True,networkRequests=0,
        signaturesCreated=0,transactionsSent=0,privateKeyAccessed=False,productionLedgerUpdated=False,
        reservationReleased=False,allocationTransferred=False,exitAttemptsConsumed=0,
        runtimeIntegrated=False,executionApproved=False,nextCycleAuthorized=False)
