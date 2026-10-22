"""Durable one-send devnet token pair; fixed endpoint, restricted signer, read-only recovery."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from pair_contract import (ROOT, CHILD, NAMES, SUPPLY, DECIMALS, MAX_FEE, MAX_SPEND, message,
                           intent_message, bound, native_balances, token_balances, account_states,
                           receipt, keys_check, TOKEN, SYSTEM, check, integer, GENESIS)
from core import Session, directory, private_file, write_new, sync_directory, loads, b58, account_value, context_value, received
from recorded_capture import Client
from submission import stopped, genesis, height, status as signature_status, transaction

TERMINAL=('finalized-success','finalized-failure','quarantined')
FLAGS=dict(network='devnet',executionApproved=False,productionLedgerUpdated=False,mainnetEnabled=False,
           resubmitAllowed=False,privateKeyExported=False,signedBytesExported=False)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def clock():return time.time_ns()//1000000


def signer(home,action):
    node=shutil.which('node');check(node is not None,'node-runtime-unavailable')
    p=subprocess.run([str(Path(node).resolve()),str(Path(__file__).with_name('pair_signer.mjs'))],
       input=json.dumps(dict(directory=str(home),action=action)),text=True,capture_output=True,timeout=10,env={'PATH':os.defpath})
    check(p.returncode==0 and len(p.stdout)<=1024,'restricted-pair-signer-refused')
    return loads(p.stdout)


class PairRpc(Client):
    METHODS=('getGenesisHash','getMultipleAccounts','getMinimumBalanceForRentExemption','getLatestBlockhash',
             'getFeeForMessage','simulateTransaction','getBlockHeight','getSignatureStatuses','getTransaction','sendTransaction')
    REQUEST_CAP=32
    def __init__(self,opener=None):super().__init__('devnet',opener)
    def request(self,method,params):
        item=super().request(method,params)
        if item['state']!='received':return item
        try:
            if method in ('getMultipleAccounts','simulateTransaction'):
                slot,value=context_value(item,0)
                if method=='getMultipleAccounts':
                    check(type(value) is list and len(value) in (4,5),'account-count')
                    item['result']={'context':{'slot':slot},'value':self.accounts(value)}
                else:
                    check(type(value) is dict and 'err' in value,'simulation-shape')
                    clean=dict(failed=value['err'] is not None,replacementBlockhash=None if value.get('replacementBlockhash') is None else 'present')
                    for name in ('fee','unitsConsumed'):
                        if name in value:check(integer(value[name]),'simulation-number');clean[name]=value[name]
                    for name in ('preBalances','postBalances'):
                        if name in value:
                            check(type(value[name]) is list and len(value[name])==7 and all(integer(x) for x in value[name]),'simulation-balances')
                            clean[name]=value[name]
                    if 'accounts' in value:
                        check(type(value['accounts']) is list and len(value['accounts'])==5,'simulation-account-count')
                        clean['accounts']=self.accounts(value['accounts'])
                    for name in ('preTokenBalances','postTokenBalances'):
                        if name in value:
                            check(type(value[name]) is list and len(value[name])<=2,'simulation-token-cap')
                            clean[name]=[]
                            for row in value[name]:
                                check(type(row) is dict and type(row.get('uiTokenAmount')) is dict,'simulation-token-shape')
                                clean[name].append({**{k:row[k] for k in ('accountIndex','mint','owner','programId') if k in row},
                                  'uiTokenAmount':{k:row['uiTokenAmount'][k] for k in ('amount','decimals') if k in row['uiTokenAmount']}})
                    item['result']={'context':{'slot':slot},'value':clean}
        except (ValueError,KeyError,TypeError,IndexError):
            item={'state':'invalid-pair-response'};self.calls[-1]['state']=item['state']
        return item
    @staticmethod
    def accounts(rows):
        clean=[]
        for row in rows:
            if row is None:clean.append(None);continue
            check(type(row) is dict and type(row.get('data')) is list and len(row['data'])==2
                  and row['data'][1]=='base64' and type(row['data'][0]) is str and len(row['data'][0])<=220,'account-layout-cap')
            clean.append({k:row[k] for k in ('owner','executable','lamports','data') if k in row})
        return clean


class RecoveryRpc(PairRpc):
    METHODS=('getGenesisHash','getSignatureStatuses','getTransaction','getBlockHeight','getMultipleAccounts')
    REQUEST_CAP=14


def read(child,name,maximum=32768):return loads(private_file(child/name,maximum))
def exists(child,name):return os.path.lexists(child/name)


def observations(child):
    rows=[]
    for n in sorted(child.iterdir()):
        if re.fullmatch(r'observation-\d{3}\.json',n.name):rows.append(n)
    check(len(rows)<=32,'observation-cap')
    check([p.name for p in rows]==['observation-%03d.json'%i for i in range(len(rows))],'observation-sequence')
    return [read(child,p.name) for p in rows]


def save_observation(child,state,**values):
    old=observations(child)
    if old and old[-1]['state'] in TERMINAL:return
    check(len(old)<32,'observation-cap')
    write_new(child/('observation-%03d.json'%len(old)),dict(state=state,recordedAtMs=clock(),**values))


def signed_plan(child,wallet):
    i=read(child,'plan.json');keys=read(child,'accounts.json')['accounts']
    keys_check(keys);check(keys['wallet']==wallet,'explicit-wallet-mismatch')
    s=read(child,'signed.json')
    check(s.get('intentSha256')==digest(i),'signed-intent-binding')
    v=bound(i,keys,s['wire'])
    return i,s['wire'],v


def simulation_review(i,wire,item):
    v=bound(i,i['accounts'],wire);slot,sim=context_value(item,i['contextSlot'])
    check(sim.get('failed') is False and sim.get('replacementBlockhash') is None,'pair-simulation-failed-or-replaced')
    native_balances(sim.get('preBalances'),sim.get('postBalances'),sim.get('fee'),i,True)
    check(sim.get('preTokenBalances')==[],'pair-simulation-pretoken')
    token_balances(sim.get('postTokenBalances'),i['accounts'],True)
    rows=sim.get('accounts');check(type(rows) is list and len(rows)==5,'pair-simulation-accounts')
    check(account_value(rows[0])==sim['postBalances'][0],'pair-simulation-wallet')
    states=account_states(rows[1:],i)
    return dict(state='simulation-passed-not-submitted',signature=v['signatures'][0],wireSha256=v['wireSha256'],
                messageSha256=v['wireMessageSha256'],slot=slot,feeLamports=sim['fee'],accounts=states)


def report(s,rpc,reason=None):
    result=dict(format='devnet-token-pair-report-1',state='not-started',wallet=s.wallet,reason=reason,
       submissionAttempts=0,sendRequestsThisRun=sum(x['method']=='sendTransaction' for x in rpc.calls),
       networkRequests=len(rpc.calls),requests=rpc.calls,stopRequested=stopped(s.home),
       setupPairVerified=False,controlledPoolCreated=False,**FLAGS)
    result['limitations']=['At most one application send per intact setup directory; copying/deleting state defeats that local protection.',
      'Only devnet test tokens are created. Pool creation and swaps are separate operations.',
      'Finality and account observations come from public RPC; signatures authenticate exact bytes, not consensus.',
      'The same-user local signer is not a hardware wallet or OS sandbox. Signed simulation bytes could be submitted by a holder while valid.',
      'Finalized account inventory is an as-of observation; later token use can change balances.']
    child=s.home/CHILD
    if not os.path.lexists(child):return result
    directory(child);result['state']='initialization-incomplete'
    if exists(child,'accounts.json'):result.update(state='accounts-prepared',accounts=read(child,'accounts.json')['accounts'])
    if exists(child,'plan.json'):result.update(state='intent-recorded',intent=read(child,'plan.json'))
    if exists(child,'signing-attempt.json'):result.update(state='signing-outcome-unknown')
    if exists(child,'signed.json'):
        i,wire,v=signed_plan(child,s.wallet);result.update(state='signed-not-submitted',signature=v['signatures'][0],wireSha256=v['wireSha256'])
    if exists(child,'simulation-review.json'):result.update(state='simulation-passed-not-submitted',simulation=read(child,'simulation-review.json'))
    if exists(child,'send-boundary.json'):result.update(state='submission-unknown',submissionAttempts=1)
    result['submissionAttemptsMeaning']='Durable boundary count, not proof of delivery; no repeat execute is permitted.'
    history=observations(child)
    if history:
        result['latestObservation']=history[-1];result['state']=history[-1]['state']
        result['setupPairVerified']=history[-1]['state']=='finalized-success'
    return result


def initialize_pair(s):
    child=s.home/CHILD;child.mkdir(mode=0o700);sync_directory(s.home)
    pubs=signer(s.home,'generate')['publicKeysBase64']
    check(type(pubs) is list and len(pubs)==5,'pair-generated-keys')
    keys=dict(zip(NAMES,[b58(base64.b64decode(v,validate=True)) for v in pubs]));keys_check(keys)
    check(keys['wallet']==s.wallet,'pair-generated-wallet')
    write_new(child/'accounts.json',dict(format='devnet-test-token-pair-accounts-1',network='devnet',accounts=keys))
    return child,keys


def prepare(s,child,keys,rpc):
    genesis(rpc)
    slot,rows=context_value(rpc.request('getMultipleAccounts',[[keys[n] for n in NAMES],{'encoding':'base64','commitment':'finalized'}]),0)
    check(type(rows) is list and len(rows)==5 and rows[1:]==[None]*4,'pair-accounts-already-exist')
    balance=account_value(rows[0]);rents=[]
    for size in (82,165):rents.append(received(rpc.request('getMinimumBalanceForRentExemption',[size,{'commitment':'finalized'}])))
    slot,bh=context_value(rpc.request('getLatestBlockhash',[{'commitment':'finalized','minContextSlot':slot}]),slot)
    msg=message(keys,bh['blockhash'],*rents)
    slot,fee=context_value(rpc.request('getFeeForMessage',[base64.b64encode(msg).decode(),{'commitment':'finalized','minContextSlot':slot}]),slot)
    at=clock()
    i=dict(format='devnet-token-pair-intent-1',network='devnet',genesis=GENESIS['devnet'],accounts=keys,
       supplyAtomicPerMint=str(SUPPLY),decimals=DECIMALS,mintAuthorityAfter=None,freezeAuthority=None,
       maximumFeeLamports=MAX_FEE,maximumSpendLamports=MAX_SPEND,mintRentLamports=rents[0],holderRentLamports=rents[1],
       quotedFeeLamports=fee,walletObservedLamports=balance,contextSlot=slot,blockhash=bh['blockhash'],
       lastValidBlockHeight=bh['lastValidBlockHeight'],recordedAtMs=at,expiresAtMs=at+30000,messageSha256=hashlib.sha256(msg).hexdigest())
    intent_message(i,keys);write_new(child/'plan.json',i)
    check(not stopped(s.home),'stop-requested');signer(s.home,'sign')
    i,wire,v=signed_plan(child,s.wallet);check(not stopped(s.home),'stop-requested')
    write_new(child/'simulation-request.json',dict(wireSha256=v['wireSha256'],atMs=clock()))
    item=rpc.request('simulateTransaction',[wire,dict(encoding='base64',commitment='finalized',sigVerify=True,
          replaceRecentBlockhash=False,minContextSlot=slot,accounts=dict(encoding='base64',addresses=[keys[n] for n in NAMES]))])
    write_new(child/'simulation-response.json',item);genesis(rpc)
    reviewed=simulation_review(i,wire,item);write_new(child/'simulation-review.json',reviewed)
    return i,wire,v,reviewed


def observe(s,child,rpc,*,sleeper=time.sleep):
    i,wire,v=signed_plan(child,s.wallet);plan={'intent':i}
    for turn in range(3):
        if turn:sleeper(10)
        try:
            genesis(rpc);st=signature_status(rpc,plan,v['signatures'][0])
            if st is not None and st['confirmationStatus']=='finalized':
                tx=transaction(rpc,v['signatures'][0]);genesis(rpc)
                if tx is None:
                    save_observation(child,'submission-unknown',reason='finalized-receipt-unavailable');continue
                try:checked=receipt(tx,st,i,wire)
                except (ValueError,KeyError,TypeError,IndexError) as exc:
                    missing=type(exc) is ValueError and str(exc) in ('receipt-metadata-missing','receipt-native-missing','receipt-token-missing')
                    save_observation(child,'submission-unknown' if missing else 'quarantined',
                                     reason='finalized-receipt-incomplete' if missing else 'finalized-receipt-mismatch');return
                if checked['state']=='finalized-failure':
                    save_observation(child,'finalized-failure',receipt=checked);return
                # Accounts may be observed later than the receipt; keep those clocks distinct.
                try:
                    slot,rows=context_value(rpc.request('getMultipleAccounts',[[i['accounts'][n] for n in NAMES[1:]],
                         {'encoding':'base64','commitment':'finalized','minContextSlot':st['slot']}]),st['slot'])
                    genesis(rpc)
                    if type(rows) is not list or len(rows)!=4 or any(r is None for r in rows):raise ValueError('missing-accounts')
                except (ValueError,KeyError,TypeError,IndexError):
                    save_observation(child,'finalized-success-accounts-unverified',receipt=checked,reason='account-snapshot-unavailable');return
                try:states=account_states(rows,i)
                except (ValueError,KeyError,TypeError,IndexError):
                    save_observation(child,'quarantined',receipt=checked,reason='post-setup-account-mismatch');return
                save_observation(child,'finalized-success',receipt=checked,accountSnapshotSlot=slot,accounts=states,
                                 accountEvidence=rows,accountStateCurrentOnLaterStatus=False);return
            n=height(rpc,plan);genesis(rpc)
            save_observation(child,'expired-outcome-unknown' if n>i['lastValidBlockHeight'] else 'submission-pending' if st else 'submission-unknown',
                             blockHeight=n,status=st['confirmationStatus'] if st else None)
        except (ValueError,KeyError,TypeError,IndexError):
            save_observation(child,'submission-unknown',reason='rpc-or-status-evidence-unavailable');return


def execute(home,wallet,*,opener=None,sleeper=time.sleep):
    rpc=PairRpc(opener)
    with Session(home) as s:
        check(s.wallet==wallet,'explicit-wallet-mismatch')
        if os.path.lexists(s.home/CHILD):return report(s,rpc,'existing-setup-use-status-or-recover')
        if stopped(s.home):return report(s,rpc,'stop-requested')
        child=None
        try:
            child,keys=initialize_pair(s)
            i,wire,v,sim=prepare(s,child,keys,rpc)
            genesis(rpc);check(height(rpc,{'intent':i})+5<=i['lastValidBlockHeight'],'blockhash-near-expiry')
            if signature_status(rpc,{'intent':i},v['signatures'][0]) is not None:
                save_observation(child,'quarantined',reason='signature-observed-before-send');return report(s,rpc)
            genesis(rpc)
            check(not stopped(s.home) and clock()<i['expiresAtMs'],'stopped-or-intent-expired')
            write_new(child/'send-boundary.json',dict(intentSha256=digest(i),wireSha256=v['wireSha256'],atMs=clock()))
            if stopped(s.home):return report(s,rpc,'stop-after-boundary-no-send')
            response=rpc.request('sendTransaction',[wire,dict(encoding='base64',skipPreflight=False,preflightCommitment='finalized',
                                  maxRetries=0,minContextSlot=sim['slot'])])
            write_new(child/'send-response.json',dict(state=response['state'],signatureMatched=response.get('result')==v['signatures'][0]))
            if response['state']=='received' and response.get('result')!=v['signatures'][0]:
                save_observation(child,'quarantined',reason='send-signature-mismatch')
            else:observe(s,child,rpc,sleeper=sleeper)
        except (ValueError,KeyError,TypeError,IndexError,OSError,subprocess.SubprocessError) as exc:
            if child is not None:
                save_observation(child,'submission-unknown' if exists(child,'send-boundary.json') else 'preparation-incomplete',
                                 reason='validation-or-transport-failure')
            return report(s,rpc,'validation-or-transport-failure')
        return report(s,rpc)


def recover(home,wallet,*,opener=None,sleeper=time.sleep):
    rpc=RecoveryRpc(opener)
    with Session(home) as s:
        check(s.wallet==wallet,'explicit-wallet-mismatch');r=report(s,rpc)
        if r['state'] in TERMINAL or not r['submissionAttempts']:return r
        child=s.home/CHILD;i,wire,v=signed_plan(child,s.wallet)
        boundary=read(child,'send-boundary.json')
        check(boundary.get('intentSha256')==digest(i) and boundary.get('wireSha256')==v['wireSha256'],'boundary-binding')
        expected=simulation_review(i,wire,read(child,'simulation-response.json'))
        check(read(child,'simulation-review.json')==expected,'simulation-binding')
        observe(s,child,rpc,sleeper=sleeper);return report(s,rpc)


def status(home,wallet):
    with Session(home) as s:
        check(s.wallet==wallet,'explicit-wallet-mismatch');return report(s,RecoveryRpc())
