"""One atomic devnet WSOL lifecycle, durable before signing and before one send."""
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
from core import (Session, Rpc, GENESIS, check, received, context_value, account_value,
                  directory, private_file, write_new, sync_directory, integer, raw58, b58, loads)
from submission import stopped, genesis, status as signature_status, height, transaction
from token_contract import message, bound, receipt, balances, AMOUNT, MAX_RENT, MAX_FEE

TERMINAL=('finalized-success','finalized-failure','quarantined')
FLAGS={'network':'devnet','executionApproved':False,'resubmitAllowed':False,'productionLedgerUpdated':False}
CHILD='token-lifecycle-v1'
APP_ID=0x52544c31


def signer(home,action,**fields):
    node=shutil.which('node');check(node is not None,'node-runtime-unavailable')
    r={'action':action,'directory':str(directory(home)),'network':'devnet',**fields}
    p=subprocess.run([str(Path(node).resolve()),str(Path(__file__).with_name('token_signer.mjs'))],
                     input=json.dumps(r),text=True,capture_output=True,timeout=10,env={'PATH':os.defpath})
    check(p.returncode==0 and len(p.stdout)<=1024,'local-token-signer-refused')
    return loads(p.stdout)


class TokenRpc(Rpc):
    METHODS=('getGenesisHash','getMultipleAccounts','getMinimumBalanceForRentExemption',
             'getLatestBlockhash','getFeeForMessage','simulateTransaction','getBlockHeight',
             'getSignatureStatuses','sendTransaction','getTransaction')
    REQUEST_CAP=30


class TokenRecoveryRpc(TokenRpc):
    METHODS=('getGenesisHash','getSignatureStatuses','getTransaction','getBlockHeight')
    REQUEST_CAP=12


class TokenSession(Session):
    def __init__(self,home,expected_wallet,create=False):
        super().__init__(home)
        self.ledger=None
        try:
            check(self.wallet==expected_wallet,'explicit-wallet-mismatch')
            self.child=self.home/CHILD
            fresh=not os.path.lexists(self.child)
            if fresh:
                check(create,'token-session-not-initialized')
                self.child.mkdir(mode=0o700);sync_directory(self.home)
                pubs=signer(self.home,'generate')['publicKeysBase64']
                names=[b58(base64.b64decode(p,validate=True)) for p in pubs]
                check(len(names)==3 and names[0]==self.wallet,'token-key-identity')
                write_new(self.child/'accounts.json',{'format':'devnet-token-accounts-1','keys':names})
            directory(self.child)
            metadata=loads(private_file(self.child/'accounts.json',4096))
            names=[b58(base64.b64decode(p,validate=True)) for p in signer(self.home,'public')['publicKeysBase64']]
            check(metadata=={'format':'devnet-token-accounts-1','keys':names} and len(set(names))==3
                  and names[0]==self.wallet,'token-key-identity')
            self.source,self.destination=names[1:]
            dbpath=self.child/'lifecycle.sqlite'
            if fresh:
                fd=os.open(dbpath,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
            else:private_file(dbpath,1024*1024)
            self.ledger=sqlite3.connect(dbpath,isolation_level=None,timeout=2)
            self.ledger.row_factory=sqlite3.Row
            self.ledger.execute('PRAGMA trusted_schema=OFF');self.ledger.execute('PRAGMA synchronous=FULL')
            check(self.ledger.execute('PRAGMA journal_mode=DELETE').fetchone()[0]=='delete','journal-mode')
            if fresh:
                with self.token_tx():
                    self.ledger.execute(f'PRAGMA application_id={APP_ID}')
                    self.ledger.execute('PRAGMA user_version=1')
                    self.ledger.execute('CREATE TABLE run (id INTEGER PRIMARY KEY CHECK(id=1), at_ms INTEGER NOT NULL, intent TEXT NOT NULL, state TEXT NOT NULL, signed_wire TEXT, simulation TEXT, result TEXT, boundary INTEGER NOT NULL DEFAULT 0 CHECK(boundary IN (0,1)))')
                sync_directory(self.child)
            check(self.ledger.execute('PRAGMA application_id').fetchone()[0]==APP_ID
                  and self.ledger.execute('PRAGMA user_version').fetchone()[0]==1,'unrecognized-token-session')
            check([tuple(r) for r in self.ledger.execute('PRAGMA quick_check')]==[('ok',)],'journal-integrity')
        except BaseException:self.close();raise

    def close(self):
        if getattr(self,'ledger',None) is not None:self.ledger.close();self.ledger=None
        super().close()

    @contextlib.contextmanager
    def token_tx(self):
        self.ledger.execute('BEGIN IMMEDIATE')
        try:yield;self.ledger.execute('COMMIT')
        except BaseException:self.ledger.execute('ROLLBACK');raise

    def plan(self):
        r=self.ledger.execute('SELECT * FROM run WHERE id=1').fetchone()
        if r is None:return None
        p=dict(r)
        for k in ('intent','simulation','result'):p[k]=json.loads(p[k]) if p[k] else None
        return p

    def record(self,i):
        with self.token_tx():
            check(self.plan() is None,'token-plan-already-recorded')
            self.ledger.execute('INSERT INTO run(id,at_ms,intent,state) VALUES (1,?,?,?)',
                                (time.time_ns()//1000000,json.dumps(i,sort_keys=True),'intent-recorded'))

    def attach(self,wire):
        with self.token_tx():
            p=self.plan();check(p is not None and p['state']=='intent-recorded','token-plan-state')
            p['signed_wire']=wire;v=bound(p,self.wallet,self.source,self.destination)
            self.ledger.execute("UPDATE run SET signed_wire=?,state='signed-not-submitted' WHERE id=1",(wire,))
        return v

    def simulated(self,result):
        with self.token_tx():
            check(self.plan()['state']=='signed-not-submitted','token-plan-state')
            self.ledger.execute("UPDATE run SET simulation=?,state='simulation-passed-not-submitted' WHERE id=1",(json.dumps(result,sort_keys=True),))

    def boundary(self):
        with self.token_tx():
            p=self.plan()
            check(p['boundary']==0 and p['state']=='simulation-passed-not-submitted','token-submission-already-recorded')
            check(not stopped(self.home),'stop-requested')
            self.ledger.execute("UPDATE run SET boundary=1,state='submission-unknown' WHERE id=1")

    def save(self,state,result):
        with self.token_tx():
            p=self.plan();check(p is not None,'token-plan-missing')
            if p['state'] in TERMINAL:return
            self.ledger.execute('UPDATE run SET state=?,result=? WHERE id=1',(state,json.dumps(result,sort_keys=True)))

    def report(self,rpc,reason=None):
        p=self.plan()
        return {'format':'devnet-token-lifecycle-1','state':p['state'] if p else 'not-prepared',
                'reason':reason,'wallet':self.wallet,'source':self.source,'destination':self.destination,
                'intent':p['intent'] if p else None,'intentRecordedAtMs':p['at_ms'] if p else None,
                'simulation':p['simulation'] if p else None,'result':p['result'] if p else None,
                'submissionAttempts':p['boundary'] if p else 0,
                'submissionAttemptsMeaning':'Durable boundary, not proof of delivery; a crash can precede transport.',
                'sendRequestsThisRun':sum(r['method']=='sendTransaction' for r in rpc.calls),
                'requests':rpc.calls,'networkRequests':len(rpc.calls),'stopRequested':stopped(self.home),
                'privateKeyExported':False,**FLAGS,
                'limitations':['Dedicated devnet wallet only. No mainnet or swap capability.',
                    'Atomic creation, transfer and closure leave no token endpoints. Intermediate amounts are specified by the exact signed instructions, not observed balance rows.',
                    'Finality and execution outcome are RPC claims; the signature authenticates the message.',
                    'At most one application send per intact token session. No reset, replacement or resubmission; owner copying/deleting private state is outside this protection.',
                    'A local same-user signer process is not an OS sandbox or hardware wallet. Signed simulation bytes could be submitted by a holder while valid.']}


def safe_reason(exc):
    known={'wrong-cluster','rpc-evidence-unavailable','rpc-context-regressed','explicit-wallet-mismatch',
           'temporary-account-already-exists','insufficient-devnet-balance','rent-cap','fee-unavailable-or-exceeds-cap',
           'local-token-signer-refused','simulation-reported-failure','simulation-account-unavailable',
           'simulation-replaced-blockhash','simulation-wallet-balance-mismatch','blockhash-too-close-to-expiry',
           'signature-observed-before-send','stop-requested','invalid-block-height'}
    return str(exc) if type(exc) is ValueError and str(exc) in known else 'local-or-rpc-validation-failed'


def prepare(s,rpc):
    genesis(rpc)
    slot,accounts=context_value(rpc.request('getMultipleAccounts',[[s.wallet,s.source,s.destination],
                    {'encoding':'base64','commitment':'finalized'}]),0)
    check(isinstance(accounts,list) and len(accounts)==3,'account-response')
    balance=account_value(accounts[0])
    check(accounts[1:]==[None,None],'temporary-account-already-exists')
    rent=received(rpc.request('getMinimumBalanceForRentExemption',[165,{'commitment':'finalized'}]))
    check(integer(rent) and 0<rent<=MAX_RENT,'rent-cap')
    check(balance>=2*rent+AMOUNT+MAX_FEE,'insufficient-devnet-balance')
    slot,bh=context_value(rpc.request('getLatestBlockhash',[{'commitment':'finalized','minContextSlot':slot}]),slot)
    check(integer(bh['lastValidBlockHeight']),'invalid-block-height')
    msg=message(s.wallet,s.source,s.destination,bh['blockhash'],rent)
    encoded=base64.b64encode(msg).decode()
    slot,fee=context_value(rpc.request('getFeeForMessage',[encoded,{'commitment':'finalized','minContextSlot':slot}]),slot)
    check(integer(fee) and 0<fee<=MAX_FEE,'fee-unavailable-or-exceeds-cap')
    i={'format':'devnet-token-lifecycle-intent-1','network':'devnet','genesis':GENESIS['devnet'],
       'wallet':s.wallet,'source':s.source,'destination':s.destination,'amountLamports':AMOUNT,
       'rentPerAccountLamports':rent,'maximumRentPerAccountLamports':MAX_RENT,
       'maximumFeeLamports':MAX_FEE,'quotedFeeLamports':fee,'walletObservedLamports':str(balance),
       'contextSlot':slot,'blockhash':bh['blockhash'],'lastValidBlockHeight':bh['lastValidBlockHeight'],
       'messageSha256':hashlib.sha256(msg).hexdigest()}
    s.record(i)  # FULL-sync before the separate signer sees the message.
    check(not stopped(s.home),'stop-requested')
    signatures=signer(s.home,'sign',rent=rent,blockhashBase64=base64.b64encode(raw58(bh['blockhash'])).decode(),messageBase64=encoded)['signaturesBase64']
    decoded=[base64.b64decode(v,validate=True) for v in signatures]
    check(len(decoded)==3 and all(len(v)==64 for v in decoded),'signature-count')
    wire=base64.b64encode(bytes([3])+b''.join(decoded)+msg).decode()
    v=s.attach(wire)
    check(not stopped(s.home),'stop-requested')
    simslot,sim=context_value(rpc.request('simulateTransaction',[wire,{'encoding':'base64','commitment':'finalized',
          'sigVerify':True,'replaceRecentBlockhash':False,'minContextSlot':slot,
          'accounts':{'encoding':'base64','addresses':[s.wallet,s.source,s.destination]}}]),slot)
    genesis(rpc)
    check(sim.get('failed') is False,'simulation-reported-failure')
    check(sim.get('replacementBlockhash') is None,'simulation-replaced-blockhash')
    balances(sim.get('preBalances'),sim.get('postBalances'),sim.get('fee'),i,True)
    accounts=sim.get('accounts')
    check(isinstance(accounts,list) and len(accounts)==3,'simulation-account-unavailable')
    snapshots=[]
    for account in accounts[1:]:
        if account is None:snapshots.append('absent')
        else:
            check(account_value(account)==0 and account.get('space',0)==0,'simulation-account-unavailable')
            snapshots.append('zero-empty-system-account')
    check(account_value(accounts[0])==sim['postBalances'][0],'simulation-wallet-balance-mismatch')
    s.simulated({'state':'simulation-passed-not-submitted','signature':v['signatures'][0],
                 'signatures':v['signatures'],'wireSha256':v['wireSha256'],'messageSha256':v['wireMessageSha256'],
                 'contextSlot':simslot,'feeLamports':fee,'walletBeforeLamports':str(sim['preBalances'][0]),
                 'walletAfterLamports':str(sim['postBalances'][0]),'temporaryAccountSnapshots':snapshots})


def verified_plan(s):
    p=s.plan();check(p is not None and p['signed_wire'] is not None,'signed-token-plan-required')
    v=bound(p,s.wallet,s.source,s.destination)
    sim=p['simulation'];check(isinstance(sim,dict) and sim.get('state')=='simulation-passed-not-submitted'
          and sim.get('signatures')==v['signatures'] and sim.get('wireSha256')==v['wireSha256']
          and sim.get('messageSha256')==v['wireMessageSha256'] and sim.get('feeLamports')==p['intent']['quotedFeeLamports']
          and integer(sim.get('contextSlot')) and sim['contextSlot']>=p['intent']['contextSlot'],'simulation-identity')
    return p,v


def observe(s,rpc,sleeper=time.sleep):
    p,v=verified_plan(s)
    for turn in range(3):
        if turn:sleeper(10)
        try:
            genesis(rpc);st=signature_status(rpc,p,v['signatures'][0])
            if st is not None and st['confirmationStatus']=='finalized':
                tx=transaction(rpc,v['signatures'][0]);genesis(rpc)
                if tx is None:
                    s.save('submission-unknown',{'reason':'finalized-receipt-unavailable'});continue
                result=receipt(tx,st,p);s.save(result['state'],result);return
            n=height(rpc,p);genesis(rpc)
            state='expired-outcome-unknown' if n>p['intent']['lastValidBlockHeight'] else 'submission-pending' if st else 'submission-unknown'
            s.save(state,{'reason':'receipt-not-finalized','blockHeight':n,'observedStatus':st['confirmationStatus'] if st else None})
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            # Contradictory receipts are sticky; missing evidence remains unknown.
            code=str(exc) if type(exc) is ValueError else ''
            mismatch=code.startswith('receipt-') and code not in ('receipt-metadata-unavailable','receipt-balances-unavailable',
                                                               'receipt-fee-unavailable','receipt-token-evidence-unavailable')
            s.save('quarantined' if mismatch else 'submission-unknown',{'reason':code if mismatch else 'rpc-or-receipt-evidence-unavailable'})
            return


def execute(home,wallet,*,opener=None,sleeper=time.sleep):
    rpc=TokenRpc(opener)
    with TokenSession(home,wallet,create=True) as s:
        if s.plan() is not None:return s.report(rpc,'existing-plan-use-status-or-recover')
        if stopped(home):return s.report(rpc,'stop-requested')
        try:
            prepare(s,rpc);p,v=verified_plan(s)
            genesis(rpc);check(height(rpc,p)+5<=p['intent']['lastValidBlockHeight'],'blockhash-too-close-to-expiry')
            check(signature_status(rpc,p,v['signatures'][0]) is None,'signature-observed-before-send')
            check(not stopped(home),'stop-requested');s.boundary()
            if stopped(home):return s.report(rpc,'stopped-after-boundary-no-send')
            r=rpc.request('sendTransaction',[p['signed_wire'],{'encoding':'base64','skipPreflight':False,
                 'preflightCommitment':'finalized','maxRetries':0,'minContextSlot':p['simulation']['contextSlot']}])
            if r['state']=='received' and r['result']!=v['signatures'][0]:
                s.save('quarantined',{'reason':'send-signature-mismatch'})
            else:observe(s,rpc,sleeper)
        except (ValueError,KeyError,TypeError,IndexError,OverflowError,OSError,subprocess.SubprocessError) as exc:
            p=s.plan();reason=safe_reason(exc)
            if p is not None:s.save('submission-unknown' if p['boundary'] else 'preparation-incomplete',{'reason':reason})
            return s.report(rpc,reason)
        return s.report(rpc)


def recover(home,wallet,*,opener=None,sleeper=time.sleep):
    rpc=TokenRecoveryRpc(opener)
    with TokenSession(home,wallet) as s:
        p=s.plan()
        if p is None or not p['boundary']:return s.report(rpc,'no-submission-boundary')
        verified_plan(s)
        if p['state'] in TERMINAL:return s.report(rpc,'terminal-state-preserved')
        observe(s,rpc,sleeper);return s.report(rpc)


def status(home,wallet):
    with TokenSession(home,wallet) as s:return s.report(TokenRecoveryRpc())
