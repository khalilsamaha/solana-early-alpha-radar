"""Fixed devnet self-transfer preparation and signed simulation. No broadcaster."""
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'recorded-chain'))
sys.path.insert(0,str(ROOT/'intent-journal'))
from recorded_capture import Client, GENESIS, SYSTEM, loads
from wire import b58, verify_wire, decode_wire
from reader import integer, base58, ALPHABET

MAX_FEE=10000
APPLICATION_ID=0x52444e31
FLAGS={'network':'devnet','transactionsSent':0,'executionApproved':False,'resubmitAllowed':False,
       'productionLedgerUpdated':False}


def check(value, reason):
    if not value: raise ValueError(reason)


def raw58(value):
    base58(value,32); n=0
    for c in value: n=n*58+ALPHABET.index(c)
    return b'\0'*(len(value)-len(value.lstrip('1'))) + n.to_bytes((n.bit_length()+7)//8,'big')


def message(wallet, blockhash):
    return bytes([1,0,1,2])+raw58(wallet)+bytes(32)+raw58(blockhash)+bytes([1,1,2,0,0,12,2,0,0,0,1,0,0,0,0,0,0,0])


def directory(path):
    p=Path(path).absolute()
    check(p.is_dir() and p.resolve()==p and not p.is_symlink(),'unsafe-directory')
    s=p.stat(); check(s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'directory-must-be-owned-0700')
    return p


def private_file(path, maximum):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd)
        check(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600
              and s.st_nlink==1 and s.st_size<=maximum,'unsafe-private-file')
        return os.read(fd,maximum+1)
    finally: os.close(fd)


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def write_new(path, value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(value,f,sort_keys=True,separators=(',',':'),allow_nan=False); f.flush(); os.fsync(f.fileno())
    sync_directory(Path(path).parent)


def signer(home, action, **fields):
    node=shutil.which('node'); check(node is not None,'node-runtime-unavailable')
    request={'action':action,'network':'devnet','directory':str(directory(home)),**fields}
    p=subprocess.run([str(Path(node).resolve()),str(Path(__file__).with_name('signer.mjs'))],
        input=json.dumps(request),text=True,capture_output=True,timeout=10,env={'PATH':os.defpath})
    check(p.returncode==0 and len(p.stdout)<=1024,'local-signer-refused')
    return loads(p.stdout)


def initialize(path):
    p=Path(path).absolute()
    check(p.parent.resolve()==p.parent and p.parent.is_dir(),'unsafe-parent')
    p.mkdir(mode=0o700)  # Refuse reuse; partial initialization is never silently replaced.
    sync_directory(p.parent)
    pub=signer(p,'generate')['publicKeyBase64']
    wallet=b58(base64.b64decode(pub,validate=True)); base58(wallet,32)
    metadata={'format':'devnet-wallet-1','network':'devnet','purpose':'fixed-self-transfer-rehearsal',
              'wallet':wallet,'createdAtMs':time.time_ns()//1000000}
    write_new(p/'wallet.json',metadata)
    with Session(p,create=True): pass
    return {'format':'devnet-wallet-report-1','wallet':wallet,'createdAtMs':metadata['createdAtMs'],
            'keyCreatedLocally':True,'privateKeyExported':False,'networkRequests':0,**FLAGS}


class Session:
    def __init__(self,home,create=False):
        self.home=directory(home); self.db=None; self.lock=None
        try:
            lock_path=self.home/'session.lock'
            if create:
                fd=os.open(lock_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); os.close(fd)
            private_file(lock_path,0)
            self.lock=os.open(lock_path,os.O_RDWR|os.O_NOFOLLOW)
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.wallet_meta=loads(private_file(self.home/'wallet.json',4096))
            check(self.wallet_meta.get('format')=='devnet-wallet-1' and self.wallet_meta.get('network')=='devnet'
                  and self.wallet_meta.get('purpose')=='fixed-self-transfer-rehearsal','wallet-format')
            self.wallet=self.wallet_meta['wallet']; base58(self.wallet,32)
            check(b58(base64.b64decode(signer(self.home,'public')['publicKeyBase64'],validate=True))==self.wallet,'wallet-key-mismatch')
            dbpath=self.home/'rehearsal.sqlite'
            if create:
                fd=os.open(dbpath,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); os.close(fd)
            else: private_file(dbpath,4*1024*1024)
            self.db=sqlite3.connect(dbpath,isolation_level=None,timeout=2)
            self.db.row_factory=sqlite3.Row
            if not create: self.validate_database()
            self.db.execute('PRAGMA trusted_schema=OFF'); self.db.execute('PRAGMA synchronous=FULL')
            check(self.db.execute('PRAGMA journal_mode=DELETE').fetchone()[0]=='delete','journal-mode')
            if create:
                with self.tx():
                    self.db.execute(f'PRAGMA application_id={APPLICATION_ID}')
                    self.db.execute('PRAGMA user_version=1')
                    self.db.execute('CREATE TABLE plans (id INTEGER PRIMARY KEY, at_ms INTEGER NOT NULL, intent TEXT NOT NULL, state TEXT NOT NULL, signed_wire TEXT, result TEXT)')
                sync_directory(self.home)
            self.validate_database()
            check([tuple(r) for r in self.db.execute('PRAGMA quick_check')]==[('ok',)],'journal-integrity')
        except BaseException:
            self.close(); raise

    def validate_database(self):
        check(self.db.execute('PRAGMA application_id').fetchone()[0]==APPLICATION_ID and
              self.db.execute('PRAGMA user_version').fetchone()[0]==1,'unrecognized-session')

    def __enter__(self): return self
    def __exit__(self,*_): self.close()
    def close(self):
        if self.db is not None: self.db.close(); self.db=None
        if self.lock is not None: os.close(self.lock); self.lock=None

    @contextlib.contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try: yield; self.db.execute('COMMIT')
        except BaseException: self.db.execute('ROLLBACK'); raise

    def record(self,intent,now,replace_expired=False):
        with self.tx():
            check(integer(now) and now>0,'invalid-clock')
            rows=self.db.execute('SELECT state FROM plans ORDER BY id LIMIT 3').fetchall()
            check(not rows or (replace_expired and len(rows)==1 and rows[0]['state']=='expired-unsubmitted'),'plan-already-recorded-use-status')
            self.db.execute('INSERT INTO plans(at_ms,intent,state) VALUES (?,?,?)',(now,json.dumps(intent,sort_keys=True),'intent-recorded'))
            return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    def attach_signature(self,plan_id,wire):
        with self.tx():
            row=self.db.execute('SELECT * FROM plans WHERE id=?',(plan_id,)).fetchone()
            check(row is not None and row['state']=='intent-recorded','plan-state-conflict')
            intent=json.loads(row['intent']); decoded=decode_wire(wire); verified=verify_wire(wire)
            check(decoded[1]==message(self.wallet,intent['blockhash']) and verified['wallet']==self.wallet,'signed-plan-disagreement')
            self.db.execute('UPDATE plans SET state=?,signed_wire=? WHERE id=?',('signed-not-submitted',wire,plan_id))
        return verified

    def complete(self,plan_id,result):
        with self.tx():
            row=self.db.execute('SELECT state FROM plans WHERE id=?',(plan_id,)).fetchone()
            check(row is not None and row['state'] in ('intent-recorded','signed-not-submitted'),'plan-state-conflict')
            self.db.execute('UPDATE plans SET state=?,result=? WHERE id=?',(result['state'],json.dumps(result,sort_keys=True),plan_id))

    def status(self):
        rows=self.db.execute('SELECT id,at_ms,intent,state,result FROM plans ORDER BY id LIMIT 3').fetchall()
        check(len(rows)<=2,'plan-cap')
        return {'format':'devnet-session-status-1','wallet':self.wallet,'plans':[
            {'id':r['id'],'recordedAtMs':r['at_ms'],'intent':json.loads(r['intent']),'state':r['state'],
             'result':json.loads(r['result']) if r['result'] else None} for r in rows],
            'networkRequests':0,'privateKeyExported':False,**FLAGS}


class Rpc(Client):
    METHODS=('getGenesisHash','getAccountInfo','getLatestBlockhash','getFeeForMessage','simulateTransaction')
    REQUEST_CAP=6
    def __init__(self,opener=None): super().__init__('devnet',opener)

    def request(self,method,params):
        r=super().request(method,params)
        if r['state']=='received' and method=='simulateTransaction':
            try:
                v=r['result']['value']; context=r['result']['context']['slot']
                check(isinstance(v,dict) and 'err' in v,'simulation-shape')
                projected={'failed':v['err'] is not None}
                for k in ('accounts','fee','preBalances','postBalances','unitsConsumed','replacementBlockhash'):
                    if k in v: projected[k]=v[k]
                r['result']={'context':{'slot':context},'value':projected}
            except (ValueError,TypeError,KeyError):
                r={'state':'invalid-simulation-response'}; self.calls[-1]['state']=r['state']
        return r


def received(r):
    check(r.get('state')=='received','rpc-evidence-unavailable'); return r['result']


def context_value(r,minimum):
    r=received(r); check(integer(r['context']['slot']) and r['context']['slot']>=minimum,'rpc-context-regressed')
    return r['context']['slot'],r['value']


def account_value(a):
    check(isinstance(a,dict) and a.get('owner')==SYSTEM and a.get('executable') is False
          and a.get('data')==['','base64'] and integer(a.get('lamports')),'unsupported-wallet-account')
    return a['lamports']


def prepare(home,opener=None,clock=None,*,replace_expired=False,_session=None):
    clock=clock or (lambda:time.time_ns()//1000000)
    rpc=Rpc(opener); plan_id=None
    result={'format':'devnet-preparation-1','state':'blocked','reason':None,'maximumFeeLamports':MAX_FEE,
            'fixedSelfTransferLamports':1,'requests':rpc.calls,'signed':False,'simulationPassed':False,**FLAGS}
    with (contextlib.nullcontext(_session) if _session is not None else Session(home)) as session:
        result['wallet']=session.wallet
        plans=session.status()['plans']
        check(not plans or (replace_expired and len(plans)==1 and plans[0]['state']=='expired-unsubmitted'),'plan-already-recorded-use-status')
        try:
            check(received(rpc.request('getGenesisHash',[]))==GENESIS['devnet'],'wrong-cluster')
            slot,a=context_value(rpc.request('getAccountInfo',[session.wallet,{'encoding':'base64','commitment':'finalized'}]),0)
            if a is None:
                result.update(state='needs-devnet-funding',reason='wallet-account-absent'); return result
            balance=account_value(a); result['walletLamports']=str(balance)
            if balance<=MAX_FEE:
                result.update(state='needs-devnet-funding',reason='insufficient-fee-buffer'); return result
            slot,bh=context_value(rpc.request('getLatestBlockhash',[{'commitment':'finalized','minContextSlot':slot}]),slot)
            base58(bh['blockhash'],32); check(integer(bh['lastValidBlockHeight']),'invalid-block-height')
            msg=message(session.wallet,bh['blockhash']); encoded=base64.b64encode(msg).decode()
            slot,fee=context_value(rpc.request('getFeeForMessage',[encoded,{'commitment':'finalized','minContextSlot':slot}]),slot)
            check(integer(fee) and 0<fee<=MAX_FEE,'fee-unavailable-or-exceeds-cap')
            intent={'format':'devnet-self-transfer-intent-1','network':'devnet','genesis':GENESIS['devnet'],
                'wallet':session.wallet,'recipient':session.wallet,'transferLamports':1,'maximumFeeLamports':MAX_FEE,
                'quotedFeeLamports':fee,'walletObservedLamports':str(balance),'contextSlot':slot,
                'blockhash':bh['blockhash'],'lastValidBlockHeight':bh['lastValidBlockHeight'],
                'messageSha256':hashlib.sha256(msg).hexdigest()}
            plan_id=session.record(intent,clock(),replace_expired=replace_expired); result['planId']=plan_id
            signature=base64.b64decode(signer(session.home,'sign',messageBase64=encoded)['signatureBase64'],validate=True)
            check(len(signature)==64,'invalid-signature-length')
            wire=base64.b64encode(bytes([1])+signature+msg).decode()
            verified=session.attach_signature(plan_id,wire); result.update(signed=True,signature=verified['signatures'][0],wireSha256=verified['wireSha256'])
            sim=rpc.request('simulateTransaction',[wire,{'encoding':'base64','commitment':'finalized',
                'sigVerify':True,'replaceRecentBlockhash':False,'minContextSlot':slot,
                'accounts':{'encoding':'base64','addresses':[session.wallet]}}])
            simslot,value=context_value(sim,slot)
            check(received(rpc.request('getGenesisHash',[]))==GENESIS['devnet'],'wrong-cluster')
            check(value.get('failed') is False,'simulation-reported-failure')
            check(value.get('replacementBlockhash') is None,'simulation-replaced-blockhash')
            check(isinstance(value.get('accounts'),list) and len(value['accounts'])==1,'simulation-account-unavailable')
            post=account_value(value['accounts'][0])
            # Only same-simulation evidence can establish its native balance changes.
            pre,after=value.get('preBalances'),value.get('postBalances')
            check(isinstance(pre,list) and isinstance(after,list) and len(pre)==len(after)==2
                  and all(integer(n) for n in pre+after),'simulation-balance-evidence-unavailable')
            check(integer(value.get('fee')) and value['fee']==fee,'simulation-fee-disagreement')
            check(pre[0]>=fee+1 and after[0]==pre[0]-fee and after[1]==pre[1] and post==after[0], 'simulation-unexpected-balance-change')
            result.update(state='simulation-passed-not-submitted',simulationPassed=True,simulationContextSlot=simslot,
                simulationFeeLamports=fee,simulationWalletBeforeLamports=str(pre[0]),simulationWalletAfterLamports=str(after[0]))
        except (ValueError,KeyError,TypeError,IndexError,OverflowError,subprocess.SubprocessError,OSError) as e:
            reason=str(e) if type(e) is ValueError else 'preparation-unavailable'
            allowed={'rpc-evidence-unavailable','wrong-cluster','rpc-context-regressed','unsupported-wallet-account',
                'invalid-block-height','fee-unavailable-or-exceeds-cap','local-signer-refused','invalid-signature-length',
                'signed-plan-disagreement','simulation-reported-failure','simulation-replaced-blockhash',
                'simulation-account-unavailable','simulation-balance-evidence-unavailable','simulation-fee-disagreement',
                'simulation-unexpected-balance-change','invalid-clock','node-runtime-unavailable'}
            result.update(state='preparation-incomplete' if plan_id else 'blocked',reason=reason if reason in allowed else 'preparation-unavailable')
        finally:
            result['networkRequests']=len(rpc.calls)
            if plan_id is not None: session.complete(plan_id,result)
    return result
