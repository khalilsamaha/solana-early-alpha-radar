"""Synthetic transport and ephemeral locally generated keys; never funded or sent."""
import base64
import copy
import io
import json
import time
from swap_rehearsal import scope_for, digest, decode_wire
from preflight_checks import fixture, edit
from preflight import _review
from swap_fixtures import edit_wire
from contract import decode


def scenario(wallet):
    c,b=fixture();p=c['packet'];old=p['policy']['accounts']['wallet']
    at=time.time_ns()//1000000;delta=at-c['finishedAtMs']
    for k in ('startedAtMs','finishedAtMs'):c[k]+=delta
    b['observedAtMs']+=delta
    for item in c['evidence'].values():item['receivedAtMs']+=delta
    c['evidence']['blockTime']['result']=at//1000
    for row in (c['evidence']['accounts']['result']['value'][0],c['evidence']['poolBootstrap']['result']['value'][0]):
        raw=bytearray(base64.b64decode(row['data'][0]));raw[373:381]=(at//1000-100).to_bytes(8,'little');row['data'][0]=base64.b64encode(raw).decode()
    for k in ('issuedAtMs','expiresAtMs'):p['policy'][k]+=delta
    p['feeAssertion']['observedAtMs']+=delta
    p['policy']['accounts']['wallet']=wallet
    edit_wire(p,lambda m:m['accountKeys'].__setitem__(0,wallet))
    c['accountKeys'][8]=wallet
    for i in (9,10):edit(c,i,32,decode(wallet))
    c['messageSha256']=p['feeAssertion']['messageSha256']
    c['requests']=[];c['rpcRequestsAttempted']=0
    return c,b,scope_for(p['policy'])


def simulation(c):
    p=c['packet'];a=p['policy']['accounts'];keys=decode_wire(p['unsignedTransactionBase64'])[4]['transaction']['message']['accountKeys']
    bykey=dict(zip(c['accountKeys'],c['evidence']['accounts']['result']['value']))
    before=[bykey[k]['lamports'] if k in bykey else 1 for k in keys];after=before.copy();after[0]-=int(p['feeAssertion']['lamports'])
    names=('wallet','source','destination','inputVault','outputVault')
    rows=[copy.deepcopy(bykey[a[n]]) for n in names];rows[0]['lamports']=after[0]
    deltas=(-int(p['policy']['amountIn']),int(p['policy']['minimumAmountOut']),int(p['policy']['amountIn']),-int(p['policy']['minimumAmountOut']))
    pre=[];post=[]
    for i,n in enumerate(names[1:]):
        k=a[n];raw=bytearray(base64.b64decode(rows[i+1]['data'][0]));amount=int.from_bytes(raw[64:72],'little')
        mint=a['inputMint' if i in (0,2) else 'outputMint'];owner=a['wallet' if i<2 else 'authority']
        decimals=base64.b64decode(bykey[mint]['data'][0])[44]
        for group,v in ((pre,amount),(post,amount+deltas[i])):
            group.append(dict(accountIndex=keys.index(k),mint=mint,owner=owner,programId=rows[i+1]['owner'],
                              uiTokenAmount=dict(amount=str(v),decimals=decimals)))
        raw[64:72]=(amount+deltas[i]).to_bytes(8,'little');rows[i+1]['data'][0]=base64.b64encode(raw).decode()
    return {'context':{'slot':102},'value':dict(err=None,accounts=rows,fee=int(p['feeAssertion']['lamports']),
               unitsConsumed=100000,preBalances=before,postBalances=after,preTokenBalances=pre,postTokenBalances=post)}


class Response(io.BytesIO):
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class Transport:
    def __init__(self,c,change=None):self.c=c;self.calls=[];self.change=change
    def open(self,req,timeout=None):
        request=json.loads(req.data);self.calls.append(request)
        if request['method']=='simulateTransaction':
            result=simulation(self.c)
            if self.change:self.change(result)
        elif request['method']=='getGenesisHash':
            from swap_rehearsal import GENESIS
            result=GENESIS['devnet']
        else:raise AssertionError('Unexpected method')
        return Response(json.dumps(dict(jsonrpc='2.0',id=request['id'],result=result)).encode())


def dependencies(c,b):
    return dict(collector=lambda **kw:copy.deepcopy(c),reviewer=lambda capture,now_ms:_review(capture,b,now_ms))
