"""Synthetic submission transport. Never opens a socket."""
import io,json,sqlite3
from urllib.error import URLError
from core import SYSTEM, GENESIS, b58
from rehearsal_fixtures import FakeRpc

class SubmissionRpc:
    def __init__(self,home,mode='ok',*,sent=False,expired=False):
        self.home,self.mode,self.sent,self.expired=home,mode,sent,expired
        self.calls=[]; self.base=FakeRpc(home=home)
    def plan(self):
        with sqlite3.connect(self.home/'rehearsal.sqlite') as db:
            row=db.execute('SELECT id,signed_wire,result FROM plans ORDER BY id DESC LIMIT 1').fetchone()
        return row[0],row[1],json.loads(row[2]) if row[2] else None
    def open(self,request,timeout):
        p=json.loads(request.data); self.calls.append(p); m=p['method']; mode=self.mode
        if m=='getGenesisHash': value='wrong' if mode=='wrong-cluster' else GENESIS['devnet']
        elif m=='getBlockHeight':
            value=130 if self.expired and self.plan()[0]==1 else 118 if mode=='near-expiry' else 100
            if mode=='height-error': raise URLError('private-error-marker')
        elif m=='getSignatureStatuses':
            st=None
            if self.sent or mode=='already-seen':
                st={'slot':110,'err':{'private-error-marker':True} if mode=='final-failed' else None,
                    'confirmationStatus':'confirmed' if mode=='pending' else 'finalized',
                    'confirmations':1 if mode=='pending' else None}
            if mode=='absent': st=None
            value={'context':{'slot':120},'value':[st]}
        elif m=='getLatestBlockhash': value={'context':{'slot':100},'value':{'blockhash':b58(bytes([1])*32),'lastValidBlockHeight':200}}
        elif m=='sendTransaction':
            with sqlite3.connect(self.home/'rehearsal.sqlite') as db:
                row=db.execute('SELECT state,attempts FROM submission').fetchone()
            assert row==('submission-unknown',1),'Boundary must be durable before transport'
            assert p['params'][0]==self.plan()[1]
            self.sent=True
            if mode=='timeout': raise URLError('private-error-marker')
            if mode=='rejected': return io.BytesIO(json.dumps({'jsonrpc':'2.0','id':p['id'],'error':{'message':'private-error-marker'}}).encode())
            value=SYSTEM if mode=='wrong-signature' else self.plan()[2]['signature']
        elif m=='getTransaction':
            value=None
            if self.sent or mode=='existing-receipt':
                value={'slot':110,'version':'legacy','transaction':[self.plan()[1],'base64'],
                    'meta':{'err':{'private-error-marker':True} if mode=='final-failed' else None,'fee':5000,
                    'preBalances':[1000000,1],'postBalances':[995000,1],
                    'preTokenBalances':[],'postTokenBalances':[],'innerInstructions':[],
                    'loadedAddresses':{'writable':[],'readonly':[]},'logMessages':['private-error-marker']}}
                if mode=='wrong-wire': value['transaction']=['bad','base64']
                if mode=='wrong-slot': value['slot']=111
                if mode=='bad-balance': value['meta']['postBalances'][0]-=1
                if mode=='bad-fee': value['meta']['fee']=10001
                if mode=='missing-balances': del value['meta']['preBalances']
                if mode=='missing-receipt': value=None
        else: return self.base.open(request,timeout)
        return io.BytesIO(json.dumps({'jsonrpc':'2.0','id':p['id'],'result':value}).encode())
