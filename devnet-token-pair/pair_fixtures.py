"""Synthetic RPC and disposable unfunded keys only. Never contacts public endpoints."""
import base64
import copy
import io
import json
from pathlib import Path
import sys
from pair_contract import ROOT, NAMES, TOKEN, SYSTEM, SUPPLY, DECIMALS, CHILD
from core import raw58, decode_wire, GENESIS
sys.path.insert(0,str(ROOT/'swap-contract'))
from swap_fixtures import fake_key


def raw_account(data,owner=TOKEN,lamports=1):
    return dict(data=[base64.b64encode(data).decode(),'base64'],owner=owner,lamports=lamports,executable=False)


def states(i):
    k=i['accounts'];rows=[]
    for suffix in ('A','B'):
        mint=bytearray(82);mint[36:44]=(1000000000).to_bytes(8,'little');mint[44]=6;mint[45]=1
        holder=bytearray(165);holder[:32]=raw58(k['mint'+suffix]);holder[32:64]=raw58(k['wallet'])
        holder[64:72]=(1000000000).to_bytes(8,'little');holder[108]=1
        rows.extend([raw_account(mint,lamports=i['mintRentLamports']),raw_account(holder,lamports=i['holderRentLamports'])])
    return rows


def balances(i,success=True):
    pre=[i['walletObservedLamports'],0,0,0,0,1,1];post=pre.copy();post[0]-=i['quotedFeeLamports']
    if success:
        post[1:5]=[i['mintRentLamports'],i['holderRentLamports']]*2;post[0]-=sum(post[1:5])
    return pre,post


def token_rows(i):
    return [dict(accountIndex=idx,mint=i['accounts']['mint'+suffix],owner=i['accounts']['wallet'],programId=TOKEN,
                 uiTokenAmount=dict(amount='1000000000',decimals=6)) for idx,suffix in ((2,'A'),(4,'B'))]


class Response(io.BytesIO):
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class Transport:
    def __init__(self,home,*,change=None):self.home=Path(home);self.calls=[];self.change=change;self.sent=False
    def plan(self):return json.loads((self.home/CHILD/'plan.json').read_text())
    def wire(self):return json.loads((self.home/CHILD/'signed.json').read_text())['wire']
    def open(self,req,timeout=None):
        q=json.loads(req.data);self.calls.append(q);method=q['method']
        assert req.full_url=='https://api.devnet.solana.com'
        if method=='getGenesisHash':value=GENESIS['devnet']
        elif method=='getMultipleAccounts':
            if len(q['params'][0])==5:value=dict(context={'slot':100},value=[raw_account(b'',SYSTEM,9980000)]+[None]*4)
            else:value=dict(context={'slot':104},value=states(self.plan()))
        elif method=='getMinimumBalanceForRentExemption':value={82:1066800,165:1488440}[q['params'][0]]
        elif method=='getLatestBlockhash':value=dict(context={'slot':100},value=dict(blockhash=fake_key('pair-blockhash'),lastValidBlockHeight=1000))
        elif method=='getFeeForMessage':value=dict(context={'slot':101},value=25000)
        elif method=='simulateTransaction':
            i=self.plan();pre,post=balances(i)
            value=dict(context={'slot':102},value=dict(err=None,fee=25000,unitsConsumed=60000,
              preBalances=pre,postBalances=post,preTokenBalances=[],postTokenBalances=token_rows(i),
              accounts=[raw_account(b'',SYSTEM,post[0])]+states(i)))
        elif method=='getBlockHeight':value=900
        elif method=='getSignatureStatuses':
            value=dict(context={'slot':103},value=[dict(slot=103,err=None,confirmationStatus='finalized',confirmations=None) if self.sent else None])
        elif method=='sendTransaction':
            self.sent=True;value=decode_wire(q['params'][0])[4]['transaction']['signatures'][0]
        elif method=='getTransaction':
            i=self.plan();pre,post=balances(i)
            value=dict(slot=103,version='legacy',transaction=[self.wire(),'base64'],
               meta=dict(err=None,fee=25000,preBalances=pre,postBalances=post,preTokenBalances=[],postTokenBalances=token_rows(i),innerInstructions=[]))
        else:raise AssertionError('Unexpected method '+method)
        if self.change:value=self.change(q,value,self)
        return Response(json.dumps(dict(jsonrpc='2.0',id=q['id'],result=value)).encode())
