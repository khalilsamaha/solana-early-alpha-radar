"""Synthetic RPC only: no socket, chain access, faucet or broadcaster."""
import io
import json
import sqlite3
from urllib.error import URLError
from core import GENESIS, SYSTEM, MAX_FEE

class FakeRpc:
    def __init__(self,mode='ok',home=None):
        self.mode,self.home,self.calls=mode,home,[]
    def open(self,request,timeout):
        p=json.loads(request.data); self.calls.append(p)
        method,mode=p['method'],self.mode
        def account(n): return {'owner':SYSTEM,'executable':False,'data':['','base64'],'lamports':n}
        def context(v): return {'context':{'slot':100},'value':v}
        if method=='getGenesisHash':
            value='wrong' if mode=='wrong-cluster' or (mode=='last-cluster' and len(self.calls)==6) else GENESIS['devnet']
        elif method=='getAccountInfo':
            value=context(None if mode=='unfunded' else account(MAX_FEE if mode=='poor' else 1000000))
            if mode=='wrong-owner': value['value']['owner']='wrong'
        elif method=='getLatestBlockhash': value=context({'blockhash':SYSTEM,'lastValidBlockHeight':120})
        elif method=='getFeeForMessage':
            value=context(None if mode=='null-fee' else MAX_FEE+1 if mode=='high-fee' else 5000)
            if mode=='regressed-context': value['context']['slot']=99
        elif method=='simulateTransaction':
            if self.home:
                with sqlite3.connect(self.home/'rehearsal.sqlite') as db:
                    row=db.execute('SELECT state,signed_wire FROM plans').fetchone()
                assert row==('signed-not-submitted',p['params'][0]), 'Signed bytes must be committed before simulation'
            if mode=='timeout': raise URLError('private-error-marker')
            v={'err':None,'accounts':[account(995000)],'fee':5000,
               'preBalances':[1000000,1],'postBalances':[995000,1],
               'replacementBlockhash':None,'logs':['private-error-marker']}
            if mode=='sim-error': v['err']={'private-error-marker':True}
            if mode=='missing-balances': del v['preBalances']
            if mode=='replacement': v['replacementBlockhash']={'blockhash':SYSTEM}
            if mode=='fee-mismatch': v['fee']=1
            if mode=='bad-post': v['postBalances'][0]-=1
            if mode=='bad-system': v['postBalances'][1]+=1
            if mode=='missing-account': v['accounts']=[None]
            if mode=='account-mismatch': v['accounts'][0]['lamports']=999999
            if mode=='boolean-balance': v['preBalances'][0]=True
            if mode=='changed-between-reads':
                v.update(preBalances=[2000000,1],postBalances=[1995000,1],accounts=[account(1995000)])
            value=context(v)
        else: raise AssertionError('Forbidden RPC method')
        return io.BytesIO(json.dumps({'jsonrpc':'2.0','id':p['id'],'result':value}).encode())
