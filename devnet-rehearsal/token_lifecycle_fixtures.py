"""Synthetic transport for the fixed atomic token lifecycle. Never opens a socket."""
from contextlib import closing
import io,json,sqlite3
from urllib.error import URLError
from core import SYSTEM,GENESIS,b58


class FakeTokenRpc:
    def __init__(self,home,mode='ok',sent=False):
        self.home,self.mode,self.sent=home,mode,sent
        self.calls=[]

    def plan(self):
        with closing(sqlite3.connect(self.home/'token-lifecycle-v1/lifecycle.sqlite')) as db, db:
            db.row_factory=sqlite3.Row;r=dict(db.execute('SELECT * FROM run').fetchone())
        for k in ('intent','simulation','result'):r[k]=json.loads(r[k]) if r[k] else None
        return r

    def account(self,balance):return {'owner':SYSTEM,'executable':False,'data':['','base64'],'lamports':balance}

    def native(self):
        pre=[10000000,0,0,1,2,3];post=[9985000,0,0,1,2,3]
        return pre,post

    def open(self,request,timeout):
        p=json.loads(request.data);self.calls.append(p);m=p['method'];mode=self.mode
        if m=='getGenesisHash':v='wrong' if mode=='wrong-cluster' else GENESIS['devnet']
        elif m=='getMultipleAccounts':
            v={'context':{'slot':100},'value':[self.account(100 if mode=='low-balance' else 10000000),
                 self.account(1) if mode=='existing-account' else None,None]}
        elif m=='getMinimumBalanceForRentExemption':v=2500001 if mode=='rent-cap' else 2039280
        elif m=='getLatestBlockhash':v={'context':{'slot':100},'value':{'blockhash':b58(bytes([1])*32),'lastValidBlockHeight':200}}
        elif m=='getFeeForMessage':v={'context':{'slot':100},'value':20001 if mode=='fee-cap' else 15000}
        elif m=='simulateTransaction':
            row=self.plan();assert row['state']=='signed-not-submitted' and row['boundary']==0
            assert p['params'][0]==row['signed_wire'] and p['params'][1]['sigVerify'] and not p['params'][1]['replaceRecentBlockhash']
            pre,post=self.native()
            v={'context':{'slot':101},'value':{'err':{'InstructionError':[4,'synthetic']} if mode=='sim-failed' else None,
                'fee':15000,'preBalances':pre,'postBalances':post,'accounts':[self.account(post[0]),None,None]}}
            if mode=='sim-balance':v['value']['postBalances'][0]-=1
            if mode=='sim-missing':del v['value']['preBalances']
            if mode=='sim-account':v['value']['accounts'][1]=self.account(1)
            if mode=='sim-zero-accounts':v['value']['accounts'][1:]=[self.account(0),self.account(0)]
        elif m=='getBlockHeight':v=201 if mode=='expired' else 198 if mode=='near-expiry' else 100
        elif m=='getSignatureStatuses':
            st=None
            if self.sent or mode=='already-seen':
                st={'slot':110,'err':{'InstructionError':[4,'synthetic']} if mode=='failed' else None,
                    'confirmationStatus':'confirmed' if mode=='pending' else 'finalized',
                    'confirmations':1 if mode=='pending' else None}
            if mode in ('absent','expired'):st=None
            v={'context':{'slot':120},'value':[st]}
        elif m=='sendTransaction':
            row=self.plan();assert row['state']=='submission-unknown' and row['boundary']==1
            assert p['params'][0]==row['signed_wire'];assert p['params'][1]['maxRetries']==0 and not p['params'][1]['skipPreflight']
            self.sent=True
            if mode=='crash':raise SystemExit('synthetic abrupt exit')
            if mode in ('timeout','absent'):raise URLError('private-provider-error')
            if mode=='rejected':return io.BytesIO(json.dumps({'jsonrpc':'2.0','id':p['id'],'error':{'message':'private-provider-error'}}).encode())
            v=SYSTEM if mode=='wrong-signature' else row['simulation']['signature']
        elif m=='getTransaction':
            row=self.plan();pre,post=self.native()
            v={'slot':110,'version':'legacy','transaction':[row['signed_wire'],'base64'],
               'meta':{'err':{'InstructionError':[4,'synthetic']} if mode=='failed' else None,
                       'fee':15000,'preBalances':pre,'postBalances':post,'preTokenBalances':[],
                       'postTokenBalances':[],'innerInstructions':[], 'loadedAddresses':{'writable':[],'readonly':[]}}}
            if mode=='bad-balance':v['meta']['postBalances'][0]-=1
            if mode=='temporary-balance':v['meta']['postBalances'][1]=1
            if mode=='bad-fee':v['meta']['fee']=15001
            if mode=='bad-wire':v['transaction'][0]='bad'
            if mode=='bad-slot':v['slot']=111
            if mode=='bad-token':v['meta']['postTokenBalances']=[{}]
            if mode=='missing-balances':del v['meta']['preBalances']
            if mode=='missing-receipt':v=None
        else:raise AssertionError('Unexpected method '+m)
        return io.BytesIO(json.dumps({'jsonrpc':'2.0','id':p['id'],'result':v}).encode())
