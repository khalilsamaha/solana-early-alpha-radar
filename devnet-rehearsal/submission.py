"""Explicit devnet-only single send boundary and observation-only recovery."""
import hashlib
import json
import os
import time
from pathlib import Path
from core import (Session, Rpc, GENESIS, MAX_FEE, check, received, context_value,
                  message, integer, verify_wire, decode_wire, prepare, directory, sync_directory)

TERMINAL=('finalized-success','finalized-failure','quarantined')
FLAGS={'network':'devnet','executionApproved':False,'resubmitAllowed':False,'productionLedgerUpdated':False}

class SubmitRpc(Rpc):
    METHODS=Rpc.METHODS+('sendTransaction','getSignatureStatuses','getTransaction','getBlockHeight')
    REQUEST_CAP=30

class RecoveryRpc(SubmitRpc):
    METHODS=('getGenesisHash','getSignatureStatuses','getTransaction','getBlockHeight')
    REQUEST_CAP=12

class Lifecycle(Session):
    def __init__(self,home):
        super().__init__(home)
        try:
            with self.tx():
                self.db.execute('CREATE TABLE IF NOT EXISTS submission (id INTEGER PRIMARY KEY CHECK(id=1), plan_id INTEGER NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL CHECK(attempts IN (0,1)), result TEXT)')
                self.db.execute('CREATE TABLE IF NOT EXISTS submission_events (seq INTEGER PRIMARY KEY, at_ms INTEGER NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL)')
        except BaseException: self.close(); raise
    def event(self,kind,detail):
        check(self.db.execute('SELECT COUNT(*) FROM submission_events').fetchone()[0]<200,'event-cap')
        self.db.execute('INSERT INTO submission_events(at_ms,kind,detail) VALUES (?,?,?)',
            (time.time_ns()//1000000,kind,json.dumps(detail,sort_keys=True,allow_nan=False)))
    def execution(self):
        row=self.db.execute('SELECT * FROM submission WHERE id=1').fetchone()
        return dict(row) if row else None
    def plan(self):
        rows=self.db.execute('SELECT * FROM plans ORDER BY id LIMIT 3').fetchall()
        check(1<=len(rows)<=2,'one-prepared-plan-required')
        if len(rows)==2: check(rows[0]['state']=='expired-unsubmitted','invalid-plan-lineage')
        row=dict(rows[-1]); row['intent']=json.loads(row['intent']); row['result']=json.loads(row['result']) if row['result'] else None
        return row
    def expire(self,plan,evidence):
        with self.tx():
            check(self.execution() is None,'submission-already-recorded')
            check(plan['id']==1 and self.plan()['state']=='simulation-passed-not-submitted','replacement-not-available')
            self.event('expired-before-tool-submission',evidence)
            self.db.execute("UPDATE plans SET state='expired-unsubmitted' WHERE id=?",(plan['id'],))
    def boundary(self,plan):
        with self.tx():
            check(self.execution() is None,'submission-already-recorded')
            check(not stopped(self.home),'stop-requested')
            self.event('submission-boundary',{'planId':plan['id']})
            self.db.execute('INSERT INTO submission(id,plan_id,state,attempts) VALUES (1,?,?,1)',(plan['id'],'submission-unknown'))
    def save(self,state,result,plan=None):
        with self.tx():
            old=self.execution()
            if old and old['state'] in TERMINAL: return
            if old is None:
                check(state=='quarantined' and plan is not None,'missing-boundary')
                self.db.execute('INSERT INTO submission(id,plan_id,state,attempts) VALUES (1,?,?,0)',(plan['id'],state))
            self.event(state,result)
            self.db.execute('UPDATE submission SET state=?,result=? WHERE id=1',(state,json.dumps(result,sort_keys=True)))
    def report(self,rpc,reason=None):
        e=self.execution()
        return {'format':'devnet-submission-1','wallet':self.wallet,
                'state':e['state'] if e else 'not-submitted','reason':reason,
                'submissionAttempts':e['attempts'] if e else 0,
                'submissionAttemptsMeaning':'Durable boundary count; a crash can happen before transport. Not proof of delivery.',
                'planId':e['plan_id'] if e else self.plan()['id'],
                'receipt':json.loads(e['result']) if e and e['result'] else None,
                'stopRequested':stopped(self.home),'requests':rpc.calls,'networkRequests':len(rpc.calls),
                'plans':self.status()['plans'],**FLAGS}

def stopped(home): return os.path.lexists(Path(home)/'STOP')

def stop(home):
    home=directory(home)
    try: fd=os.open(home/'STOP',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError: pass
    else:
        with os.fdopen(fd,'w') as f: f.write('Devnet submission stopped\n'); f.flush(); os.fsync(f.fileno())
        sync_directory(home)
    return {'format':'devnet-stop-1','state':'stop-requested','networkRequests':0,**FLAGS}

def bound(plan,wallet):
    i,r=plan['intent'],plan['result']
    check(plan['state'] in ('simulation-passed-not-submitted','expired-unsubmitted'),'plan-not-simulation-passed')
    check(isinstance(r,dict) and r.get('state')=='simulation-passed-not-submitted' and r.get('simulationPassed') is True and r.get('signed') is True,'missing-simulation-pass')
    check(i.get('network')=='devnet' and i.get('genesis')==GENESIS['devnet'] and i.get('wallet')==wallet and i.get('recipient')==wallet,'intent-wallet-or-cluster-mismatch')
    check(type(i.get('transferLamports')) is int and i['transferLamports']==1 and i.get('maximumFeeLamports')==MAX_FEE,'intent-policy-mismatch')
    check(integer(i.get('quotedFeeLamports')) and 0<i['quotedFeeLamports']<=MAX_FEE and integer(i.get('contextSlot')) and integer(i.get('lastValidBlockHeight')),'intent-numeric-fields')
    wire=plan['signed_wire']; v=verify_wire(wire); decoded=decode_wire(wire)
    check(decoded[1]==message(wallet,i['blockhash']) and hashlib.sha256(decoded[1]).hexdigest()==i.get('messageSha256'),'intent-message-mismatch')
    check(v['wallet']==wallet and v['wireSha256']==r.get('wireSha256') and v['signatures'][0]==r.get('signature'),'simulation-identity-mismatch')
    check(r.get('simulationFeeLamports')==i['quotedFeeLamports'] and integer(r.get('simulationContextSlot')) and r['simulationContextSlot']>=i['contextSlot'],'simulation-fee-or-context-mismatch')
    return v

def genesis(rpc): check(received(rpc.request('getGenesisHash',[]))==GENESIS['devnet'],'wrong-cluster')

def height(rpc,plan):
    n=received(rpc.request('getBlockHeight',[{'commitment':'finalized','minContextSlot':plan['intent']['contextSlot']}]))
    check(integer(n),'invalid-block-height'); return n

def status(rpc,plan,signature):
    slot,rows=context_value(rpc.request('getSignatureStatuses',[[signature],{'searchTransactionHistory':True}]),plan['intent']['contextSlot'])
    check(isinstance(rows,list) and len(rows)==1,'invalid-status')
    v=rows[0]
    if v is not None:
        check(isinstance(v,dict) and integer(v.get('slot')) and plan['intent']['contextSlot']<=v['slot']<=slot and 'err' in v,'invalid-status')
        check(v.get('confirmationStatus') in ('processed','confirmed','finalized'),'invalid-status')
        if v['confirmationStatus']=='finalized': check(v.get('confirmations') is None,'invalid-finality')
    return v

def transaction(rpc,signature):
    return received(rpc.request('getTransaction',[signature,{'encoding':'base64','commitment':'finalized','maxSupportedTransactionVersion':0}]))

def receipt(tx,st,plan):
    check(isinstance(tx,dict) and integer(tx.get('slot')) and tx.get('slot')==st['slot'] and tx.get('version')=='legacy','receipt-slot-or-version-mismatch')
    check(tx.get('transaction')==[plan['signed_wire'],'base64'],'receipt-wire-mismatch')
    m=tx.get('meta'); check(isinstance(m,dict) and 'err' in m,'receipt-metadata-unavailable')
    check(m['err']==st['err'],'receipt-status-disagreement')
    fee=m.get('fee'); check(integer(fee) and fee==plan['intent']['quotedFeeLamports'] and 0<fee<=MAX_FEE,'receipt-fee-mismatch')
    pre,post=m.get('preBalances'),m.get('postBalances')
    check(isinstance(pre,list) and isinstance(post,list) and len(pre)==len(post)==2 and all(integer(v) for v in pre+post),'receipt-balances-unavailable')
    check(pre[0]>=fee+(1 if m['err'] is None else 0) and post[0]==pre[0]-fee and pre[1]==post[1],'receipt-balance-mismatch')
    check(m.get('preTokenBalances')==[] and m.get('postTokenBalances')==[] and m.get('innerInstructions') in (None,[]) and m.get('loadedAddresses',{'writable':[],'readonly':[]})=={'writable':[],'readonly':[]},'receipt-unexpected-account-effects')
    return {'state':'finalized-success' if m['err'] is None else 'finalized-failure',
            'signature':plan['result']['signature'],'slot':st['slot'],'feeLamports':fee,
            'walletBeforeLamports':str(pre[0]),'walletAfterLamports':str(post[0]),
            'wireSha256':plan['result']['wireSha256'],'evidenceBasis':'RPC finalized receipt bound to locally verified exact signed bytes'}

def observe(session,rpc,plan,*,rounds=3,sleeper=time.sleep):
    check(type(rounds) is int and 1<=rounds<=3,'poll-cap')
    for turn in range(rounds):
        if turn: sleeper(10)
        try:
            genesis(rpc); st=status(rpc,plan,plan['result']['signature'])
            if st is not None and st['confirmationStatus']=='finalized':
                tx=transaction(rpc,plan['result']['signature']); genesis(rpc)
                if tx is None:
                    session.save('submission-unknown',{'reason':'finalized-receipt-unavailable'}); continue
                result=receipt(tx,st,plan); session.save(result['state'],result); return
            n=height(rpc,plan); genesis(rpc)
            state='expired-outcome-unknown' if n>plan['intent']['lastValidBlockHeight'] else 'submission-pending' if st is not None else 'submission-unknown'
            session.save(state,{'reason':'receipt-not-finalized','blockHeight':n,
                'lastValidBlockHeight':plan['intent']['lastValidBlockHeight'],
                'observedStatus':st['confirmationStatus'] if st else None})
        except (ValueError,KeyError,TypeError,IndexError) as e:
            code=str(e) if type(e) is ValueError else 'invalid-evidence'
            if code.startswith('receipt-') and code not in ('receipt-metadata-unavailable','receipt-balances-unavailable'):
                session.save('quarantined',{'reason':code}); return
            session.save('submission-unknown',{'reason':'rpc-or-receipt-evidence-unavailable'}); return

def execute(home,expected_wallet,*,allow_replace=False,opener=None,sleeper=time.sleep):
    rpc=SubmitRpc(opener); preparation_calls=[]
    with Lifecycle(home) as s:
        check(s.wallet==expected_wallet,'explicit-wallet-mismatch')
        if s.execution() is not None: return s.report(rpc,'existing-boundary-use-recover')
        if stopped(home): return s.report(rpc,'stop-requested')
        try:
            plan=s.plan(); verified=bound(plan,s.wallet)
            genesis(rpc); n=height(rpc,plan); st=status(rpc,plan,verified['signatures'][0])
            check(plan['state']!='expired-unsubmitted' or n>plan['intent']['lastValidBlockHeight'],'expired-plan-height-regressed')
            if st is not None:
                s.save('quarantined',{'reason':'signature-observed-before-tool-submission'},plan); return s.report(rpc)
            if n>plan['intent']['lastValidBlockHeight']:
                tx=transaction(rpc,verified['signatures'][0]); genesis(rpc)
                if tx is not None:
                    s.save('quarantined',{'reason':'receipt-observed-before-tool-submission'},plan); return s.report(rpc)
                if not allow_replace or plan['id']!=1: return s.report(rpc,'expired-plan-requires-explicit-replacement-or-cap-reached')
                if plan['state']!='expired-unsubmitted': s.expire(plan,{'blockHeight':n,'lastValidBlockHeight':plan['intent']['lastValidBlockHeight'],'historyStatusAbsent':True,'finalizedReceiptAbsent':True})
                check(not stopped(home),'stop-requested')
                prep=prepare(home,opener,replace_expired=True,_session=s); preparation_calls=prep['requests']
                check(prep['state']=='simulation-passed-not-submitted','replacement-preparation-incomplete')
                plan=s.plan(); verified=bound(plan,s.wallet)
            # Recheck cluster and validity after preparation. Never replace again.
            genesis(rpc); n=height(rpc,plan)
            check(n+5<=plan['intent']['lastValidBlockHeight'],'blockhash-too-close-to-expiry')
            check(status(rpc,plan,verified['signatures'][0]) is None,'signature-observed-before-send')
            check(not stopped(home),'stop-requested')
            s.boundary(plan)  # FULL-sync commit before any transport call.
            if stopped(home):
                report=s.report(rpc,'stopped-after-boundary-no-send')
                report['preparationRequests']=preparation_calls; report['networkRequests']+=len(preparation_calls)
                return report
            response=rpc.request('sendTransaction',[plan['signed_wire'],{'encoding':'base64','skipPreflight':False,
                'preflightCommitment':'finalized','maxRetries':0,'minContextSlot':plan['result']['simulationContextSlot']}])
            if response['state']=='received' and response['result']!=verified['signatures'][0]:
                s.save('quarantined',{'reason':'send-signature-mismatch'})
            else:
                s.save('submission-unknown',{'reason':'send-acknowledged' if response['state']=='received' else 'send-outcome-unknown'})
                observe(s,rpc,plan,sleeper=sleeper)
        except (ValueError,KeyError,TypeError,IndexError) as e:
            # No raw external/provider exceptions or signed bytes in public diagnostics.
            reason=str(e) if type(e) is ValueError else 'invalid-local-or-rpc-evidence'
            allowed={'wrong-cluster','rpc-evidence-unavailable','rpc-context-regressed','blockhash-too-close-to-expiry',
                'replacement-preparation-incomplete','stop-requested','signature-observed-before-send','expired-plan-height-regressed'}
            reason=reason if reason in allowed else 'local-or-rpc-validation-failed'
            if s.execution() is not None: s.save('submission-unknown',{'reason':reason})
            report=s.report(rpc,reason)
        else: report=s.report(rpc)
        report['preparationRequests']=preparation_calls; report['networkRequests']+=len(preparation_calls)
        return report

def recover(home,expected_wallet,*,opener=None,sleeper=time.sleep):
    rpc=RecoveryRpc(opener)
    with Lifecycle(home) as s:
        check(s.wallet==expected_wallet,'explicit-wallet-mismatch')
        e=s.execution()
        if e is None: return s.report(rpc,'no-submission-boundary')
        if e['state'] in TERMINAL: return s.report(rpc,'terminal-state-preserved')
        plan=s.plan(); check(plan['id']==e['plan_id'],'submission-plan-mismatch'); bound(plan,s.wallet)
        observe(s,rpc,plan,sleeper=sleeper)
        return s.report(rpc)
