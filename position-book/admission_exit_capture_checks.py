"""Actual bounded collectors over synthetic HTTP; no sockets or private keys."""
from copy import deepcopy
import io
import json
from unittest.mock import patch

import admission_exit_capture as m
from admission_submission_checks import case
from admission_exit_checks import fixture,prepare
from entry_accounting_checks import collect as settle,apply
from paired_checks import shift,simulation_response,NOW,edit
from preflight_checks import fixture as preflight_fixture,GENESIS,fake_key

class Clock:
    def __init__(self):self.at=NOW+30200
    def __call__(self):self.at+=1;return self.at

def replies(c):
    names=['genesisBefore','programBootstrap','poolBootstrap','accounts','blockTime']
    if c['packet'] is not None:names+=['blockhash','fee']
    names+=['genesisAfter']
    return [deepcopy(c['evidence'][n]['result']) for n in names]

class Opener:
    def __init__(self,first,e,hook=None,sim=None):
        self.calls=[];self.hook=hook
        second=e['capture'];fee=second['evidence']['fee']['result']['value']
        slot=first['evidence']['accounts']['result']['context']['slot']
        self.rows=replies(first)+[GENESIS['devnet'],{'context':{'slot':slot},'value':{
            'blockhash':fake_key('fresh-collected-exit'),'lastValidBlockHeight':200}},
            {'context':{'slot':slot},'value':fee},GENESIS['devnet']]+replies(second)+[
            sim if sim is not None else simulation_response(second,e['price']['quote']['outAmount']),GENESIS['devnet']]
    def open(self,request,timeout):
        body=json.loads(request.data);self.calls.append(body)
        if self.hook:self.hook(len(self.calls),body,self)
        row=self.rows.pop(0)
        if isinstance(row,Exception):raise row
        return io.BytesIO(json.dumps(dict(jsonrpc='2.0',id=body['id'],result=row)).encode())

def setup(c):
    e,b=fixture(c);b.update(kind='observed-devnet-deployment',observedAtMs=0)
    first,_=preflight_fixture(False);shift(first,30000,10)
    first['evidence']['blockTime']['result']=(NOW+30000)//1000
    return first,e,b

def capture(c,*,hook=None,mutate=None,clock=None,source_hook=None,sink=None):
    first,e,b=setup(c);clock=clock or Clock()
    sim=simulation_response(e['capture'],e['price']['quote']['outAmount'])
    if mutate:mutate(first,e)
    rpc=Opener(first,e,hook,sim);reads=[]
    def read(*args):
        row=deepcopy(c.e['costInputs']['reservations'])
        row.update(readStartedAtMs=clock(),observedAtMs=clock());reads.append(row)
        if source_hook:source_hook(len(reads),row)
        return row
    with patch.object(m.exit,'BASELINE',b),patch.object(m.view,'read_locked',side_effect=read):
        r=m.collect(c.home,c.wallet,c.pool,opener=rpc,clock=clock,monotonic=lambda:0,_evidence_sink=sink)
    return r,rpc

def run():
    cases={}
    with case() as c:
        settle(c);apply(c);old=c.path.read_bytes();source={p.name:p.read_bytes() for p in c.home.iterdir()}
        items=[];r,o=capture(c,sink=items.append)
        assert r['state']=='exit-evidence-collected-research-only',r
        assert len(o.calls)==20 and r['requestMethods']==m.METHODS and len(items)==1
        assert r['binding']['quantityAtomic']=='98' and r['binding']['protectedInventoryAtomic']=='902'
        assert r['binding']['feeCommitmentRemainingLamports']=='20999'
        cases['twenty-bounded-requests-use-acquired-quantity-and-held-fees']='passed'
        assert c.path.read_bytes()==old and source=={p.name:p.read_bytes() for p in c.home.iterdir()}
        cases['admission-and-historical-source-byte-identical']='passed'
        item=items[0];p=r['provenance']
        assert p['evidenceSha256']==m.digest(item['evidence']) and p['requestTraceSha256']==m.digest(item['requestTrace'])
        assert p['initialCaptureSha256']==m.digest(item['initialCapture']) and p['packetBuildSha256']==m.digest(item['packetBuild'])
        assert not p['durable'] and not r['preparationPersisted'] and not r['validForSubmission']
        assert item['evidence']['packet']['unsignedTransactionBase64'] not in json.dumps(r)
        assert not any(x['method'] in ('sendTransaction','requestAirdrop') for x in o.calls)
        cases['private-provenance-bound-without-public-wire-or-execution']='passed'
    for name,kwargs in {
        'initial-cluster':dict(hook=lambda n,q,o:o.rows.__setitem__(0,'wrong') if n==1 else None),
        'final-cluster':dict(hook=lambda n,q,o:o.rows.__setitem__(0,'wrong') if n==20 else None),
        'deployment-drift':dict(mutate=lambda f,e:edit(f,-1,120,b'\x01')),
        'pool-change':dict(mutate=lambda f,e:edit(e['capture'],4,64,(10001).to_bytes(8,'little'))),
        'owned-inventory-shortfall':dict(mutate=lambda f,e:edit(e['capture'],9,64,(97).to_bytes(8,'little'))),
        'held-native-shortfall':dict(mutate=lambda f,e:e['capture']['evidence']['accounts']['result']['value'][8].update(lamports=20000)),
        'blockhash-invalid':dict(mutate=lambda f,e:e['capture']['evidence']['blockhash']['result'].update(value=False)),
        'source-head-change':dict(source_hook=lambda n,r:r.update(ledgerHeadSha256='c'*64) if n==2 else None),
        'rpc-timeout':dict(hook=lambda n,q,o:o.rows.__setitem__(0,TimeoutError('PRIVATE_DETAIL')) if n==4 else None),
        'simulation-error':dict(hook=lambda n,q,o:o.rows[0]['value'].update(err={'private':'PRIVATE_DETAIL'}) if n==19 else None),
    }.items():
        with case() as c:
            settle(c);apply(c);old=c.path.read_bytes();items=[]
            r,o=capture(c,sink=items.append,**kwargs)
            assert r['state']=='unavailable' and not items,(name,r)
            assert c.path.read_bytes()==old and 'PRIVATE_DETAIL' not in json.dumps(r)
            assert len(o.calls)<=20
            cases[name+'-withholds-evidence-without-write']='passed'
    for mode in ('stop-before','stop-during','expired','clock-regression','existing-preparation','missing-accounting'):
        with case() as c:
            settle(c)
            if mode!='missing-accounting':apply(c)
            c.now=NOW+30200;clock=Clock();hook=None
            if mode=='stop-before':(c.home/'STOP').touch(mode=0o600)
            elif mode=='existing-preparation':
                e,b=fixture(c);prepare(c,e,b)
            elif mode=='stop-during':
                hook=lambda n,q,o:(c.home/'STOP').touch(mode=0o600) if n==10 else None
            elif mode=='expired':
                def hook(n,q,o):
                    if n==10:clock.at+=10001
            elif mode=='clock-regression':
                def hook(n,q,o):
                    if n==10:clock.at-=10000
            old=c.path.read_bytes();items=[];r,o=capture(c,clock=clock,hook=hook,sink=items.append)
            assert r['state']=='unavailable' and not items,(mode,r)
            assert c.path.read_bytes()==old
            if mode in ('stop-before','existing-preparation','missing-accounting'):assert len(o.calls)==0
            cases[mode+'-cannot-collect-or-refresh']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        privateKeyAccessed=False,temporaryLedgersRemoved=True,productionLedgerUpdated=False,
        preparationPersisted=False,executionApproved=False,runtimeIntegrated=False,nextCycleAuthorized=False)
