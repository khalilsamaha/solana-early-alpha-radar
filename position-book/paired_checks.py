"""Synthetic raw evidence for independent-leg fee scenarios; no RPC or keys."""
import base64
from copy import deepcopy
import hashlib
import fresh_quote
from preflight_checks import fixture as preflight_fixture, edit, NOW
from unsigned_simulation_checks import simulation_response
from swap_rehearsal import scope_for
from fresh_packet import message
from cpmm_quote import derive
import paired_cost


def shift(value,offset,slots):
    if isinstance(value,dict):
        for k,v in value.items():
            if type(v) is int and (k.endswith('AtMs') or k=='now_ms'):value[k]=v+offset
            elif type(v) is int and k in ('slot','blockTimeSlot'):value[k]=v+slots
            else:shift(v,offset,slots)
    elif isinstance(value,list):
        for v in value:shift(v,offset,slots)


def leg(reverse=False,offset=0):
    c,baseline=preflight_fixture(True); initial,_=preflight_fixture(False)
    original=scope_for(c['packet']['policy']);scope=deepcopy(original)
    initial['startedAtMs']=NOW-1600;initial['finishedAtMs']=NOW-1100
    initial['evidence']['blockTime']['result']=(NOW-1100)//1000
    for item in initial['evidence'].values():item['receivedAtMs']=NOW-1100
    shift(c,offset,10 if reverse else 0);shift(initial,offset,10 if reverse else 0)
    c['evidence']['blockTime']['result']+=offset//1000
    initial['evidence']['blockTime']['result']+=offset//1000
    raw,_=fresh_quote.preflight.split_capture(initial)
    if reverse:
        entry_price=derive(raw,original,slippage_bps=100,now_ms=NOW+offset+200)
        for left,right in (('source','destination'),('inputMint','outputMint'),('inputVault','outputVault')):
            scope['accounts'][left],scope['accounts'][right]=scope['accounts'][right],scope['accounts'][left]
        scope['amountIn']=entry_price['quote']['outAmount']
        edit(c,10,64,(1000).to_bytes(8,'little'))
        c['accountKeys'][9],c['accountKeys'][10]=c['accountKeys'][10],c['accountKeys'][9]
        rows=c['evidence']['accounts']['result']['value'];rows[9],rows[10]=rows[10],rows[9]
    price=derive(raw,scope,slippage_bps=100,now_ms=NOW+offset+200)
    scope['minimumAmountOut']=price['quote']['minimumOutAmount']
    c['packet']['policy'].update({k:v for k,v in scope.items() if k!='format'})
    msg=message(scope,c['packet']['policy']['blockhash'])
    c['packet']['unsignedTransactionBase64']=base64.b64encode(b'\x01'+bytes(64)+msg).decode()
    c['packet']['feeAssertion']['messageSha256']=hashlib.sha256(msg).hexdigest()
    c['messageSha256']=c['packet']['feeAssertion']['messageSha256']
    response=simulation_response(c,price['quote']['outAmount'])
    response['value']['failed']=False;response['value'].pop('err')
    a=original['accounts'];r=dict(phase='closed',wallet=a['wallet'],pool=a['pool'],nativeHeldLamports='0',
        tokenAccounts=[dict(account=a['source'],mint=a['inputMint'],heldAtomic='0'),
                       dict(account=a['destination'],mint=a['outputMint'],heldAtomic='0')],
        ledgerHeadSha256='a'*64,cycleBindingSha256='b'*64,
        readStartedAtMs=NOW+offset+130,observedAtMs=NOW+offset+150)
    args=dict(packet=c['packet'],capture=c,price=price,simulation_item=dict(state='received',result=response),
        reservations=r,baseline=baseline,simulation_started=NOW+offset+10,
        simulation_received=NOW+offset+100,simulation_finished=NOW+offset+120,now_ms=NOW+offset+200)
    return dict(costInputs=args,initialPool=raw,entryScope=original,scope=scope,completedAtMs=NOW+offset+200)


def fixture():
    return leg(),leg(True,4000)


def run():
    entry,reverse=fixture();baseline=entry['costInputs']['baseline']
    def evaluate(a,b):return paired_cost.assess(a,b,baseline=baseline,failed_exit_attempts=1)
    good=evaluate(entry,reverse)
    if good['state']!='independent-leg-costs-consistent':raise ValueError('paired-self-check')
    cases={'independent-raw-costs-with-failure-scenario':'passed'}
    mutations={
        'summary-is-not-raw-evidence':lambda a,b:b['costInputs'].update(simulation_item={'state':'success'}),
        'missing-fee':lambda a,b:b['costInputs']['simulation_item']['result']['value'].pop('fee'),
        'different-ledger':lambda a,b:b['costInputs']['reservations'].update(ledgerHeadSha256='c'*64),
        'unknown-reservation':lambda a,b:b['costInputs']['reservations'].update(nativeHeldLamports=None),
        'wrong-quantity':lambda a,b:b['scope'].update(amountIn='1'),
        'wrong-baseline':lambda a,b:b['costInputs']['baseline'].update(id='other'),
        'expired-entry':lambda a,b:a.update(completedAtMs=NOW+20000),
        'pool-price-mismatch':lambda a,b:edit(b['initialPool'],4,64,(10001).to_bytes(8,'little')),
        'post-hoc-quote-edit':lambda a,b:a['costInputs']['price']['quote'].update(outAmount='99'),
    }
    for name,mutate in mutations.items():
        a,b=deepcopy(entry),deepcopy(reverse);mutate(a,b)
        r=evaluate(a,b)
        if r['state']!='unavailable' or r['calculation'] is not None:raise ValueError('paired-rejection-self-check')
        cases[name]='rejected'
    return dict(format=paired_cost.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        executionApproved=False,productionStateChanged=False)
