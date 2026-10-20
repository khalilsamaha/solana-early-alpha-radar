"""Disposable unfunded keys, synthetic account bytes and fake RPC. Test use only."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
from pool_contract import *
from pair_fixtures import raw_account, states as pair_states, Response, fake_key
from state import LOADER, POOL_FIELDS

RENTS={'82':1066800,'165':1488440,'637':3886200,'4075':21351240}
POINTER=fake_key('pool-test-programdata')
PROGRAM_RAW=b'\x02\0\0\0'+raw58(POINTER)
DEPLOY_RAW=b'\x03\0\0\0'+(90).to_bytes(8,'little')+b'\x01'+raw58(fake_key('upgrade-authority'))+b'\x7fELF\x02\x01\x01'+bytes(100)
PROGRAM_ROW=raw_account(PROGRAM_RAW,LOADER,100);PROGRAM_ROW['executable']=True
DEPLOY_ROW=raw_account(DEPLOY_RAW,LOADER,200)
BASE=dict(id='synthetic-pool-test',observedSlot=90,identity=dict(program=PROGRAM,programDataAddress=POINTER,
    **{k:v for k,v in deployment(DEPLOY_ROW,100).items() if k in IDENTITY_FIELDS}))


def tk(m,owner,amount,*,native=False):
    raw=bytearray(165);raw[:32]=raw58(m);raw[32:64]=raw58(owner);raw[64:72]=amount.to_bytes(8,'little');raw[108]=1
    if native:raw[109:113]=(1).to_bytes(4,'little');raw[113:121]=RENTS['165'].to_bytes(8,'little')
    return raw_account(raw,TOKEN,RENTS['165']+(amount if native else 0))


def pre_accounts(pair,balance=204844520):
    a=addresses(pair);r={n:None for n in ROLES}
    r['wallet']=raw_account(b'',SYSTEM,balance)
    pair_rows=pair_states(dict(accounts=pair,mintRentLamports=RENTS['82'],holderRentLamports=RENTS['165']))
    mapping={pair['mintA']:pair_rows[0],pair['holderA']:pair_rows[1],pair['mintB']:pair_rows[2],pair['holderB']:pair_rows[3]}
    for n in ('mint0','mint1','holder0','holder1'):r[n]=mapping[a[n]]
    raw=bytearray(236);raw[:8]=hashlib.sha256(b'account:AmmConfig').digest()[:8];raw[36:44]=(150000000).to_bytes(8,'little')
    r['config']=raw_account(raw,PROGRAM,1000)
    r['feeReceiver']=tk(NATIVE,fake_key('fee-owner'),80000000,native=True)
    for n in ('tokenProgram','associatedTokenProgram','systemProgram','compute'):
        r[n]=raw_account(b'',fake_key('loader'),1);r[n]['executable']=True
    r['rent']=raw_account(bytes(17),fake_key('sysvar-owner'),1)
    r['program']=copy.deepcopy(PROGRAM_ROW)
    return [r[n] for n in ROLES]


def post_accounts(i):
    a=i['accounts'];r=dict(zip(ROLES,copy.deepcopy(i['preAccounts'])))
    r['wallet']['lamports']-=rent_total(i['rents'])+i['creationFeeLamports']+i['quotedFeeLamports']
    for n in (0,1):
        r['holder'+str(n)]=tk(a['mint'+str(n)],a['wallet'],SUPPLY-DEPOSIT)
        r['vault'+str(n)]=tk(a['mint'+str(n)],AUTHORITY,DEPOSIT)
    raw=bytearray(82);raw[:4]=(1).to_bytes(4,'little');raw[4:36]=raw58(AUTHORITY);raw[36:44]=(DEPOSIT-100).to_bytes(8,'little');raw[44:46]=bytes([9,1])
    r['lpMint']=raw_account(raw,TOKEN,i['rents']['82']);r['lpHolder']=tk(a['lpMint'],a['wallet'],DEPOSIT-100)
    raw=bytearray(637);raw[:8]=hashlib.sha256(b'account:PoolState').digest()[:8]
    vals=dict(a,creator=a['wallet'],program0=TOKEN,program1=TOKEN)
    for n,f in enumerate(POOL_FIELDS):raw[8+32*n:40+32*n]=raw58(vals[f])
    raw[328:333]=bytes([255,0,9,6,6]);raw[333:341]=DEPOSIT.to_bytes(8,'little');raw[373:381]=(1792500000).to_bytes(8,'little')
    r['pool']=raw_account(raw,PROGRAM,i['rents']['637'])
    raw=bytearray(4075);raw[:8]=hashlib.sha256(b'account:ObservationState').digest()[:8];raw[11:43]=raw58(a['pool'])
    r['observation']=raw_account(raw,PROGRAM,i['rents']['4075'])
    pre=r['feeReceiver'];raw=base64.b64decode(pre['data'][0]);owner=b58(raw[32:64])
    r['feeReceiver']=tk(NATIVE,owner,pre['lamports']-RENTS['165']+i['creationFeeLamports'],native=True)
    return [r[n] for n in ROLES]


def balances(i,success=True):
    pre=[r['lamports'] if r else 0 for r in i['preAccounts']]
    if success:post=[r['lamports'] if r else 0 for r in post_accounts(i)]
    else:post=pre.copy();post[0]-=i['quotedFeeLamports']
    return pre,post


def token_list(i,post=False,success=True):
    a=i['accounts'];rows=post_accounts(i) if success and post else i['preAccounts'];out=[]
    for n in ('holder0','holder1','feeReceiver')+(('vault0','vault1','lpHolder') if success and post else ()):
        idx=ROLES.index(n);raw=base64.b64decode(rows[idx]['data'][0]);m=b58(raw[:32]);owner=b58(raw[32:64])
        out.append(dict(accountIndex=idx,mint=m,owner=owner,programId=TOKEN,uiTokenAmount=dict(amount=str(u64(raw,64)),decimals=9 if n in ('feeReceiver','lpHolder') else 6)))
    return out


class Transport:
    def __init__(self,home,*,change=None):
        self.home=Path(home);self.calls=[];self.change=change;self.sent=False
        self.pair=json.loads((self.home/'test-token-pair-v1/accounts.json').read_text())['accounts']
    def plan(self):return json.loads((self.home/CHILD/'plan.json').read_text())
    def wire(self):return json.loads((self.home/CHILD/'signed.json').read_text())['wire']
    def open(self,req,timeout=None):
        q=json.loads(req.data);self.calls.append(q);method=q['method'];assert req.full_url=='https://api.devnet.solana.com'
        if method=='getGenesisHash':v=GENESIS['devnet']
        elif method=='getMultipleAccounts':
            count=len(q['params'][0]);rows=pre_accounts(self.pair)+[copy.deepcopy(DEPLOY_ROW)] if count==21 else post_accounts(self.plan())
            v=dict(context={'slot':104 if self.sent else 102},value=rows)
        elif method=='getMinimumBalanceForRentExemption':v=RENTS[str(q['params'][0])]
        elif method=='getLatestBlockhash':v=dict(context={'slot':102},value=dict(blockhash=fake_key('pool-blockhash'),lastValidBlockHeight=1000))
        elif method=='getFeeForMessage':v=dict(context={'slot':102},value=5000)
        elif method=='simulateTransaction':
            i=self.plan();pre,post=balances(i);v=dict(context={'slot':102},value=dict(err=None,fee=5000,unitsConsumed=160000,
               preBalances=pre,postBalances=post,preTokenBalances=token_list(i),postTokenBalances=token_list(i,True),accounts=post_accounts(i)))
        elif method=='getBlockHeight':v=900
        elif method=='getSignatureStatuses':v=dict(context={'slot':103},value=[dict(slot=103,err=None,confirmationStatus='finalized',confirmations=None) if self.sent else None])
        elif method=='sendTransaction':self.sent=True;v=decode_wire(q['params'][0])[4]['transaction']['signatures'][0]
        elif method=='getTransaction':
            i=self.plan();pre,post=balances(i);v=dict(slot=103,version='legacy',transaction=[self.wire(),'base64'],meta=dict(err=None,fee=5000,
              preBalances=pre,postBalances=post,preTokenBalances=token_list(i),postTokenBalances=token_list(i,True),innerInstructions=[{'index':2,'instructions':[]}]))
        else:raise AssertionError(method)
        if self.change:v=self.change(q,v,self)
        return Response(json.dumps(dict(jsonrpc='2.0',id=q['id'],result=v)).encode())
