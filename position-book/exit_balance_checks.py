"""Public signed fixtures with synthetic account RPC; no real network or keys."""
import base64
from copy import deepcopy
import io
import json
from unittest.mock import patch

import exit_balance as m
from exit_accounting_checks import signed_case,collect as collect_receipt,apply,package
from admission_receipt_checks import failed


def fixture_rows(c):
    """Build post-state independently from raw receipt arrays, not collector expectations."""
    p,scope=package(c);tx=p['bundle']['rpcEvidence']['transaction']['result'];a=scope['accounts']
    keys=[a['wallet'],a['destination'],a['source'],a['outputMint'],a['inputMint']]
    b=c.book()
    try:cap=m.accounting.submission.handoff.preparation.saved(b,c.now)['evidence']['capture']
    finally:b.close()
    by_key=dict(zip(cap['accountKeys'],cap['evidence']['accounts']['result']['value']))
    rows=deepcopy([by_key[k] for k in keys]);txkeys=tx['transaction']['message']['accountKeys']
    rows[0]['lamports']=tx['meta']['postBalances'][txkeys.index(keys[0])]
    for i in (1,2):
        value=next(r for r in tx['meta']['postTokenBalances'] if r['accountIndex']==txkeys.index(keys[i]))['uiTokenAmount']['amount']
        raw=bytearray(base64.b64decode(rows[i]['data'][0]));raw[64:72]=int(value).to_bytes(8,'little')
        rows[i]['data']=[base64.b64encode(raw).decode(),'base64']
    return keys,rows,tx['slot']


class FakeRpc:
    def __init__(self,c,*,rows=None,slot=None,block=None,genesis=None,callback=None,error=False):
        self.c=c;self.keys,self.rows,self.slot=fixture_rows(c)
        if rows is not None:self.rows=rows
        if slot is not None:self.slot=slot
        self.block=block;self.genesis=genesis;self.callback=callback;self.error=error;self.requests=[]
    def open(self,request,timeout=None):
        q=json.loads(request.data);self.requests.append(q);i=len(self.requests)-1
        assert request.full_url==m.ENDPOINT and request.method=='POST' and 0<timeout<=10
        assert q['method']==m.METHODS[i]
        if self.callback:self.callback(q['method'])
        if q['method']=='getGenesisHash':
            assert q['params']==[];value=self.genesis or m.GENESIS['devnet']
        elif q['method']=='getMultipleAccounts':
            assert q['params']==[self.keys,dict(encoding='base64',commitment='finalized',minContextSlot=fixture_rows(self.c)[2])]
            value=dict(context=dict(slot=self.slot),value=self.rows)
        else:
            assert q['params']==[self.slot];value=self.c.now//1000 if self.block is None else self.block
        payload=dict(jsonrpc='2.0',id=q['id'],result=value)
        if self.error:payload=dict(jsonrpc='2.0',id=q['id'],error={'message':'must never export provider detail'})
        return io.BytesIO(json.dumps(payload).encode())


def observe(c,rpc=None,**kw):
    return m.collect(c.home,c.wallet,c.pool,opener=rpc or FakeRpc(c),clock=lambda:c.now,monotonic=lambda:0,**kw)


def token_change(row,offset,value,length=8):
    raw=bytearray(base64.b64decode(row['data'][0]));raw[offset:offset+length]=int(value).to_bytes(length,'little')
    row['data']=[base64.b64encode(raw).decode(),'base64']


def run():
    cases={}
    with signed_case() as c:
        rpc=FakeRpc(c);r=observe(c,rpc);assert not rpc.requests and r['diagnosticCode']=='balance-accounting-required'
        cases['unsettled-exit-does-not-request-balances']='passed'
        collect_receipt(c);apply(c);before=c.path.read_bytes();source={p.name:p.read_bytes() for p in c.home.iterdir() if p.is_file()}
        rpc=FakeRpc(c);sink=[];r=observe(c,rpc,_evidence_sink=sink.append)
        assert r['state']=='exit-balances-match-held' and r['balanceReconciliationPassed'] and len(rpc.requests)==4 and len(sink)==1
        assert r['snapshot']['ownedAcquiredResidualAtomic']=='0' and r['snapshot']['sourceProceedsHeldAtomic']=='96'
        cases['fresh-finalized-five-account-snapshot-matches-raw-receipt']='passed'
        assert c.path.read_bytes()==before and source=={p.name:p.read_bytes() for p in c.home.iterdir() if p.is_file()}
        cases['source-and-admission-files-remain-unchanged']='passed'
        assert all(r[k] is False for k in ('reservationReleased','fundsAvailableForNewEntry','nextCycleAuthorized','executionApproved','runtimeIntegrated','privateKeyAccessed','evidencePersisted'))
        assert 'data' not in r and 'evidence' not in r and c.exit_wire not in json.dumps(r)
        cases['public-summary-never-releases-funds-or-authorizes-next-entry']='passed'
        keys,rows,slot=fixture_rows(c)
        for name,kwargs in (
            ('wrong-genesis',dict(genesis=m.GENESIS['mainnet-beta'])),
            ('slot-before-receipt',dict(slot=slot-1)),
            ('old-chain-time',dict(block=c.now//1000-60)),
            ('future-chain-time',dict(block=c.now//1000+60)),
            ('provider-error',dict(error=True))):
            rpc=FakeRpc(c,**kwargs);r=observe(c,rpc)
            assert not r['balanceReconciliationPassed'] and not r['reservationReleased'] and len(rpc.requests)<=4
            assert 'must never export' not in json.dumps(r)
            cases[name+'-stays-held']='passed'
        for name,mutate in (
            ('external-wallet-credit',lambda x:x[0].update(lamports=x[0]['lamports']+1)),
            ('source-token-credit',lambda x:token_change(x[1],64,9999)),
            ('protected-inventory-debit',lambda x:token_change(x[2],64,0)),
            ('token-delegate',lambda x:token_change(x[1],72,1,4)),
            ('mint-decimals-change',lambda x:token_change(x[3],44,9,1)),
            ('account-closed',lambda x:x.__setitem__(2,None))):
            altered=deepcopy(rows);mutate(altered);r=observe(c,FakeRpc(c,rows=altered))
            assert not r['balanceReconciliationPassed'] and not r['reservationReleased'] and c.path.read_bytes()==before
            cases[name+'-stays-held']='passed'
        start=c.now
        def slow(method):
            if method=='getMultipleAccounts':c.now+=m.FRESH_MS
        rpc=FakeRpc(c,callback=slow);r=observe(c,rpc);assert r['diagnosticCode']=='balance-expired' and len(rpc.requests)==2
        c.now=start;cases['late-response-stops-without-further-requests']='passed'
        (c.home/'STOP').touch(mode=0o600);rpc=FakeRpc(c);r=observe(c,rpc)
        assert not rpc.requests and r['diagnosticCode']=='balance-stopped'
        cases['stop-blocks-collection-without-changing-history']='passed'
    with signed_case() as c:
        p,_=package(c);collect_receipt(c,failed(p));apply(c);rpc=FakeRpc(c);r=observe(c,rpc)
        assert not rpc.requests and r['diagnosticCode']=='balance-flat-exit-required'
        cases['failed-exit-with-inventory-cannot-pass-flat-balance-gate']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',casesPassed=len(cases),cases=cases,
        realNetworkRequests=0,privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,sourceStateChanged=False,
        temporaryLedgersRemoved=True,productionLedgerUpdated=False,reservationReleased=False,fundsAvailableForNewEntry=False,
        walletWideReservationsKnown=False,nextCycleAuthorized=False,executionApproved=False,runtimeIntegrated=False)
