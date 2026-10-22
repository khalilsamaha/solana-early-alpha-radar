"""Bounded one-send pool initialization; inspect is repeatable and recovery never signs."""
import base64
import copy
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time
from pool_contract import *
from core import Session, directory, private_file, write_new, sync_directory, loads, context_value, received
from recorded_capture import Client
from submission import stopped, genesis, height, status as signature_status, transaction
import pair_workflow as pair_work

TERMINAL=('finalized-success','finalized-failure','quarantined')
FLAGS=dict(network='devnet',executionApproved=False,mainnetEnabled=False,productionLedgerUpdated=False,
           resubmitAllowed=False,privateKeyExported=False,signedBytesExported=False)
clock=pair_work.clock
digest=pair_work.digest
exists=pair_work.exists
# Full legacy executable account data belongs to the signed evidence. Keep it,
# with consistent bounded readers across preparation, simulation and recovery.
UNSIGNED_ARCHIVE=CHILD+'-unsigned-size-archive-v1'
UNSIGNED_REPLACEMENT=CHILD+'-unsigned-size-replacement-v1.json'
JOURNAL_BYTES=524288
ACCOUNT_SET_BYTES=500000
LEGACY_PROGRAM_BASE64=262144
JOURNAL_NAMES=('plan.json','signing-attempt.json','signed.json','simulation-request.json',
               'simulation-response.json','simulation-review.json','send-boundary.json','send-response.json')


def observations(child):
    rows=sorted(p for p in child.iterdir() if re.fullmatch(r'observation-\d{3}\.json',p.name))
    check(len(rows)<=32,'observation-cap')
    check([p.name for p in rows]==['observation-%03d.json'%i for i in range(len(rows))],'observation-sequence')
    return [read(child,p.name) for p in rows]


def save_observation(child,state,**values):
    old=observations(child)
    if old and old[-1]['state'] in TERMINAL:return
    check(len(old)<32,'observation-cap')
    value=dict(state=state,recordedAtMs=clock(),**values)
    check(len(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())<=JOURNAL_BYTES,'pool-journal-cap')
    write_new(child/('observation-%03d.json'%len(old)),value)


class PoolRpc(Client):
    METHODS=('getGenesisHash','getMultipleAccounts','getMinimumBalanceForRentExemption','getLatestBlockhash',
             'getFeeForMessage','simulateTransaction','getBlockHeight','getSignatureStatuses','getTransaction','sendTransaction')
    REQUEST_CAP=40
    def __init__(self,opener=None):super().__init__('devnet',opener)
    @staticmethod
    def accounts(rows,large=False):
        check(type(rows) is list and len(rows)<=21,'pool-response-account-count')
        clean=[]
        for index,row in enumerate(rows):
            if row is None:clean.append(None);continue
            check(type(row) is dict and type(row.get('data')) is list and len(row['data'])==2
                  and row['data'][1]=='base64' and type(row['data'][0]) is str
                  and len(row['data'][0])<=(2800000 if large and (len(rows)==2 or index==20)
                      else LEGACY_PROGRAM_BASE64 if len(rows) in (20,21) and index==ROLES.index('associatedTokenProgram')
                      and row.get('executable') is True else 6000),'pool-response-account-cap')
            clean.append({k:row[k] for k in ('owner','executable','lamports','data') if k in row})
        bounded=clean[:-1] if len(clean)==21 else clean
        if len(clean) in (20,21):
            check(len(json.dumps(bounded,separators=(',',':')).encode())<=ACCOUNT_SET_BYTES,'pool-account-set-cap')
        return clean
    def request(self,method,params):
        item=super().request(method,params)
        if item['state']!='received':return item
        try:
            if method in ('getMultipleAccounts','simulateTransaction'):
                slot,v=context_value(item,0)
                if method=='getMultipleAccounts':
                    check(len(v)==len(params[0]),'pool-response-count')
                    item['result']={'context':{'slot':slot},'value':self.accounts(v,large=len(v) in (2,21))}
                else:
                    check(type(v) is dict and 'err' in v,'simulation-shape')
                    clean=dict(failed=v['err'] is not None,replacementBlockhash=None if v.get('replacementBlockhash') is None else 'present')
                    for k in ('fee','unitsConsumed'):
                        if k in v:check(integer(v[k]),'simulation-number');clean[k]=v[k]
                    for k in ('preBalances','postBalances'):
                        if k in v:
                            check(type(v[k]) is list and len(v[k])==len(ROLES) and all(integer(n) for n in v[k]),'simulation-balances')
                            clean[k]=v[k]
                    if 'accounts' in v:clean['accounts']=self.accounts(v['accounts'])
                    for k in ('preTokenBalances','postTokenBalances'):
                        if k in v:
                            check(type(v[k]) is list and len(v[k])<=6,'simulation-token-count');clean[k]=[]
                            for row in v[k]:
                                check(type(row) is dict and type(row.get('uiTokenAmount')) is dict,'simulation-token-shape')
                                clean[k].append({**{f:row[f] for f in ('accountIndex','mint','owner','programId') if f in row},
                                    'uiTokenAmount':{f:row['uiTokenAmount'][f] for f in ('amount','decimals') if f in row['uiTokenAmount']}})
                    item['result']={'context':{'slot':slot},'value':clean}
        except (ValueError,TypeError,KeyError,IndexError):
            item={'state':'invalid-pool-response'};self.calls[-1]['state']=item['state']
        return item


class InspectRpc(PoolRpc):
    METHODS=('getGenesisHash','getMultipleAccounts','getMinimumBalanceForRentExemption')
    REQUEST_CAP=7


class RecoveryRpc(PoolRpc):
    METHODS=('getGenesisHash','getMultipleAccounts','getSignatureStatuses','getTransaction','getBlockHeight')
    REQUEST_CAP=14


def pair_accounts(s):
    child=s.home/pair_work.CHILD;directory(child)
    i,wire,v=pair_work.signed_plan(child,s.wallet)
    history=pair_work.observations(child)
    check(history and history[-1]['state']=='finalized-success','verified-test-pair-required')
    check(history[-1]['receipt']['signature']==v['signatures'][0],'pair-receipt-binding')
    from pair_contract import account_states as pair_states
    check(pair_states(history[-1]['accountEvidence'],i)==history[-1]['accounts'],'pair-account-evidence')
    return i['accounts']


def capture(rpc,pair,*,baseline=None):
    baseline=BASELINE if baseline is None else baseline
    start=clock();a=addresses(pair);genesis(rpc)
    keys=[a[n] for n in ROLES]+[baseline['identity']['programDataAddress']]
    slot,rows=context_value(rpc.request('getMultipleAccounts',[keys,{'encoding':'base64','commitment':'finalized'}]),baseline['observedSlot'])
    check(type(rows) is list and len(rows)==21,'pool-capture-count')
    identity=pin([rows[ROLES.index('program')],rows[-1]],slot,baseline)
    rents={}
    for size in SIZES:rents[str(size)]=received(rpc.request('getMinimumBalanceForRentExemption',[size,{'commitment':'finalized'}]))
    fee=config_fee(rows[ROLES.index('config')]);pre_state(rows[:-1],pair,rents,fee);genesis(rpc)
    check(0<=clock()-start<=10000,'pool-capture-stale')
    estimate=rent_total(rents)+fee+MAX_FEE;check(estimate<=MAX_SPEND,'pool-spend-cap')
    balance=rows[0]['lamports']
    return dict(accounts=a,pairAccounts=pair,preAccounts=rows[:-1],contextSlot=slot,observedAtMs=start,
       rents=rents,creationFeeLamports=fee,walletLamports=balance,estimatedRequiredLamports=estimate,
       estimatedShortfallLamports=max(0,estimate-balance),fundingSufficient=balance>=estimate,
       deploymentIdentity=identity,baselineId=baseline['id'])


def inspect(home,wallet,*,opener=None):
    rpc=InspectRpc(opener)
    with Session(home) as s:
        check(s.wallet==wallet,'explicit-wallet-mismatch')
        r=dict(format='devnet-pool-inspect-1',state='unavailable',wallet=wallet,transactionsSent=0,signaturesCreated=0,**FLAGS)
        try:
            pair=pair_accounts(s);c=capture(rpc,pair)
            r.update(state='funding-ready' if c['fundingSufficient'] else 'funding-required',**c)
        except (ValueError,TypeError,KeyError,IndexError,OSError):r['reason']='pool-preflight-unavailable-or-unsupported'
        return dict(r,networkRequests=len(rpc.calls),requests=rpc.calls)


def read(child,name):return loads(private_file(child/name,JOURNAL_BYTES))


def signer(home):
    node=shutil.which('node');check(node is not None,'node-runtime-unavailable')
    p=subprocess.run([str(Path(node).resolve()),str(Path(__file__).with_name('pool_signer.mjs'))],
        input=json.dumps(dict(directory=str(home),action='sign')),text=True,capture_output=True,timeout=10,env={'PATH':os.defpath})
    check(p.returncode==0 and len(p.stdout)<=1024,'restricted-pool-signer-refused');return loads(p.stdout)


def signed_plan(child,wallet):
    i=read(child,'plan.json');check(i['pairAccounts']['wallet']==wallet,'explicit-wallet-mismatch')
    s=read(child,'signed.json');check(s.get('intentSha256')==digest(i),'pool-signed-intent-binding')
    return i,s['wire'],bound(i,i['pairAccounts'],s['wire'])


def simulation_review(i,wire,item):
    v=bound(i,i['pairAccounts'],wire);slot,sim=context_value(item,i['contextSlot'])
    check(sim.get('failed') is False and sim.get('replacementBlockhash') is None,'pool-simulation-failed-or-replaced')
    check(integer(sim.get('unitsConsumed')) and sim['unitsConsumed']<=COMPUTE_UNITS,'pool-simulation-compute')
    native_balances(sim.get('preBalances'),sim.get('postBalances'),sim.get('fee'),i,True)
    token_rows(sim.get('preTokenBalances'),i,True,False);token_rows(sim.get('postTokenBalances'),i,True,True)
    states=account_states(sim.get('accounts'),i,simulation=True)
    return dict(state='simulation-passed-not-submitted',signature=v['signatures'][0],wireSha256=v['wireSha256'],
                messageSha256=v['wireMessageSha256'],slot=slot,feeLamports=sim['fee'],poolState=states)


def report(s,rpc,reason=None):
    r=dict(format='devnet-pool-report-1',state='not-started',wallet=s.wallet,reason=reason,
        submissionAttempts=0,sendRequestsThisRun=sum(x['method']=='sendTransaction' for x in rpc.calls),
        networkRequests=len(rpc.calls),requests=rpc.calls,stopRequested=stopped(s.home),controlledPoolVerified=False,**FLAGS)
    r['limitations']=['One application send per intact pool journal; copying or deleting local state defeats this protection.',
        'Devnet pool creation only. No swap, mainnet action or strategy approval.',
        'Pinned deployment is an observed identity, not verified source equivalence or protection against future upgrades.',
        'Creation fee and rent caps are pre-send checks, not on-chain ceilings; initialize has no fee-ceiling argument. Changes before execution can cause a charged-amount mismatch and quarantine.',
        'Finalized receipt and later accounts are separate RPC observations, not independently verified consensus.',
        'Shared fee receiver or pool changes can prevent strict reconciliation; never repeat execute to repair this.',
        'Same-user software signer is not an OS sandbox or hardware wallet; signed bytes remain private and usable while valid.']
    child=s.home/CHILD
    if exists(s.home,UNSIGNED_REPLACEMENT):
        r['unsignedReplacement']=loads(private_file(s.home/UNSIGNED_REPLACEMENT,4096))
        r['unsignedArchivePresent']=exists(s.home,UNSIGNED_ARCHIVE)
        if not os.path.lexists(child):r['state']='unsigned-replacement-incomplete'
    elif exists(s.home,UNSIGNED_ARCHIVE):r['state']='unsigned-replacement-incomplete'
    if not os.path.lexists(child):return r
    directory(child);r['state']='initialization-incomplete'
    r['journalFiles']={name:dict(present=exists(child,name),bytes=(child/name).lstat().st_size if exists(child,name) else None)
                       for name in JOURNAL_NAMES}
    r['journalReaderVersion']='pool-journal-size-1'
    if exists(child,'plan.json'):
        i=read(child,'plan.json');r.update(state='intent-recorded',intent={k:v for k,v in i.items() if k!='preAccounts'})
    if exists(child,'signing-attempt.json'):r['state']='signing-outcome-unknown'
    if exists(child,'signed.json'):
        i,wire,v=signed_plan(child,s.wallet);r.update(state='signed-not-submitted',signature=v['signatures'][0],wireSha256=v['wireSha256'])
    if exists(child,'simulation-review.json'):
        check(exists(child,'signed.json'),'pool-simulation-without-signature')
        r.update(state='simulation-passed-not-submitted',simulation=read(child,'simulation-review.json'))
    if exists(child,'send-boundary.json'):r.update(state='submission-unknown',submissionAttempts=1)
    history=observations(child)
    if history:r.update(state=history[-1]['state'],latestObservation=history[-1],controlledPoolVerified=history[-1]['state']=='finalized-success')
    return r


def prepare(s,child,c,rpc):
    slot,bh=context_value(rpc.request('getLatestBlockhash',[{'commitment':'finalized','minContextSlot':c['contextSlot']}]),c['contextSlot'])
    msg=message(c['pairAccounts'],bh['blockhash'])
    slot,fee=context_value(rpc.request('getFeeForMessage',[base64.b64encode(msg).decode(),{'commitment':'finalized','minContextSlot':slot}]),slot)
    check(0<=clock()-c['observedAtMs']<=10000,'pool-capture-stale')
    at=clock();i=dict(format='devnet-pool-intent-1',network='devnet',genesis=GENESIS['devnet'],pairAccounts=c['pairAccounts'],accounts=c['accounts'],
       depositAtomicPerMint=str(DEPOSIT),openTime=0,maximumFeeLamports=MAX_FEE,maximumCreationFeeLamports=MAX_CREATION_FEE,
       maximumSpendLamports=MAX_SPEND,computeUnits=COMPUTE_UNITS,rents=c['rents'],creationFeeLamports=c['creationFeeLamports'],
       quotedFeeLamports=fee,walletObservedLamports=c['walletLamports'],contextSlot=slot,blockhash=bh['blockhash'],
       lastValidBlockHeight=bh['lastValidBlockHeight'],recordedAtMs=at,expiresAtMs=at+30000,preAccounts=c['preAccounts'],
       messageSha256=hashlib.sha256(msg).hexdigest())
    intent_message(i,i['pairAccounts']);write_new(child/'plan.json',i)
    check(not stopped(s.home),'stop-requested');signer(s.home)
    i,wire,v=signed_plan(child,s.wallet);check(not stopped(s.home),'stop-requested')
    write_new(child/'simulation-request.json',dict(wireSha256=v['wireSha256'],atMs=clock()))
    item=rpc.request('simulateTransaction',[wire,dict(encoding='base64',commitment='finalized',sigVerify=True,
        replaceRecentBlockhash=False,minContextSlot=slot,accounts=dict(encoding='base64',addresses=[i['accounts'][n] for n in ROLES]))])
    write_new(child/'simulation-response.json',item);genesis(rpc)
    sim=simulation_review(i,wire,item);write_new(child/'simulation-review.json',sim)
    return i,wire,v,sim


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
                except (ValueError,KeyError,TypeError,IndexError) as e:
                    missing=type(e) is ValueError and str(e) in ('receipt-native-missing','receipt-token-missing','receipt-metadata-missing')
                    save_observation(child,'submission-unknown' if missing else 'quarantined',reason='finalized-receipt-incomplete' if missing else 'finalized-receipt-mismatch');return
                if checked['state']=='finalized-failure':save_observation(child,'finalized-failure',receipt=checked);return
                try:
                    slot,rows=context_value(rpc.request('getMultipleAccounts',[[i['accounts'][n] for n in ROLES],
                        {'encoding':'base64','commitment':'finalized','minContextSlot':st['slot']}]),st['slot']);genesis(rpc)
                    if type(rows) is not list or len(rows)!=20 or any(rows[ROLES.index(n)] is None for n in NEW_SIZES):raise ValueError('missing-pool-accounts')
                except (ValueError,KeyError,TypeError,IndexError):
                    save_observation(child,'finalized-success-accounts-unverified',receipt=checked,reason='account-snapshot-unavailable');return
                try:state=account_states(rows,i)
                except (ValueError,KeyError,TypeError,IndexError):
                    save_observation(child,'quarantined',receipt=checked,reason='pool-post-state-mismatch');return
                save_observation(child,'finalized-success',receipt=checked,poolState=state,accountEvidence=rows,
                                 accountSnapshotSlot=slot,accountStateCurrentOnLaterStatus=False);return
            n=height(rpc,plan);genesis(rpc)
            save_observation(child,'expired-outcome-unknown' if n>i['lastValidBlockHeight'] else 'submission-pending' if st else 'submission-unknown',
                             blockHeight=n,status=st['confirmationStatus'] if st else None)
        except (ValueError,KeyError,TypeError,IndexError):
            save_observation(child,'submission-unknown',reason='rpc-or-status-evidence-unavailable');return


def unsigned_size_plan(s,pair):
    """Only the original oversized, expired, never-signing preparation failure."""
    check(not exists(s.home,UNSIGNED_ARCHIVE) and not exists(s.home,UNSIGNED_REPLACEMENT),'unsigned-replacement-already-used')
    child=s.home/CHILD;directory(child)
    check({p.name for p in child.iterdir()}=={'plan.json','observation-000.json'},'unsigned-replacement-evidence-not-exclusive')
    raw=private_file(child/'plan.json',JOURNAL_BYTES)
    check(len(raw)>131072,'unsigned-replacement-not-size-failure')
    i=loads(raw);check(i.get('pairAccounts')==pair,'unsigned-replacement-pair-mismatch')
    intent_message(i,pair)
    check(clock()>=i['expiresAtMs'],'unsigned-replacement-intent-not-expired')
    evidence=private_file(child/'observation-000.json',4096);o=loads(evidence)
    check(set(o)=={'state','reason','recordedAtMs'} and o['state']=='preparation-incomplete'
          and o['reason']=='validation-or-transport-failure' and integer(o['recordedAtMs'])
          and o['recordedAtMs']>=i['recordedAtMs'],'unsigned-replacement-observation')
    return i,{name:hashlib.sha256(value).hexdigest() for name,value in
              [('plan.json',raw),('observation-000.json',evidence)]}


def archive_unsigned_size_plan(s,pair,old,hashes,expired_height):
    check(not stopped(s.home),'stop-requested')
    current,current_hashes=unsigned_size_plan(s,pair)
    check(current==old and current_hashes==hashes,'unsigned-replacement-journal-changed')
    check(integer(expired_height) and expired_height>old['lastValidBlockHeight'],'unsigned-replacement-blockhash-live')
    marker=dict(format='devnet-pool-unsigned-size-replacement-1',archive=UNSIGNED_ARCHIVE,
        oldMessageSha256=old['messageSha256'],oldLastValidBlockHeight=old['lastValidBlockHeight'],
        observedFinalizedHeight=expired_height,filesSha256=hashes,recordedAtMs=clock(),
        basis='intact-local-journal-no-signing-or-send-evidence',automaticRetry=False)
    # Durable boundary precedes the rename. A crash anywhere leaves execution
    # blocked; no automatic recovery ever signs, sends, deletes or resets state.
    write_new(s.home/UNSIGNED_REPLACEMENT,marker)
    os.rename(s.home/CHILD,s.home/UNSIGNED_ARCHIVE);sync_directory(s.home)


def execute(home,wallet,*,allow_replace_unsigned=False,opener=None,sleeper=time.sleep):
    rpc=PoolRpc(opener)
    with Session(home) as s:
        check(s.wallet==wallet,'explicit-wallet-mismatch')
        if not allow_replace_unsigned:
            if os.path.lexists(s.home/CHILD):return report(s,rpc,'existing-pool-journal-use-status-or-recover')
            if exists(s.home,UNSIGNED_REPLACEMENT) or exists(s.home,UNSIGNED_ARCHIVE):
                return report(s,rpc,'unsigned-replacement-interrupted-use-status')
        if stopped(s.home):return report(s,rpc,'stop-requested')
        child=None
        try:
            pair=pair_accounts(s)
            old,hashes=unsigned_size_plan(s,pair) if allow_replace_unsigned else (None,None)
            c=capture(rpc,pair)
            if not c['fundingSufficient']:
                return dict(report(s,rpc,'insufficient-devnet-funding'),state='funding-required',funding={k:c[k] for k in ('walletLamports','estimatedRequiredLamports','estimatedShortfallLamports')})
            check(not stopped(s.home),'stop-requested')
            if allow_replace_unsigned:
                expired_height=height(rpc,{'intent':old});genesis(rpc)
                archive_unsigned_size_plan(s,pair,old,hashes,expired_height)
            new_child=s.home/CHILD;new_child.mkdir(mode=0o700);sync_directory(s.home);child=new_child
            i,wire,v,sim=prepare(s,child,c,rpc)
            # Re-observe exact deployment and account state after simulation, before sending.
            genesis(rpc)
            slot,rows=context_value(rpc.request('getMultipleAccounts',[[i['accounts'][n] for n in ROLES]+[BASELINE['identity']['programDataAddress']],
                {'encoding':'base64','commitment':'finalized','minContextSlot':sim['slot']}]),sim['slot'])
            pin([rows[ROLES.index('program')],rows[-1]],slot)
            pre_state(rows[:-1],pair,i['rents'],i['creationFeeLamports'])
            check(rows[:-1]==i['preAccounts'],'pool-state-changed-before-send')
            check(height(rpc,{'intent':i})+5<=i['lastValidBlockHeight'],'blockhash-near-expiry')
            if signature_status(rpc,{'intent':i},v['signatures'][0]) is not None:
                save_observation(child,'quarantined',reason='signature-observed-before-send');return report(s,rpc)
            genesis(rpc);check(not stopped(s.home) and clock()<i['expiresAtMs'],'stopped-or-intent-expired')
            write_new(child/'send-boundary.json',dict(intentSha256=digest(i),wireSha256=v['wireSha256'],atMs=clock()))
            if stopped(s.home):return report(s,rpc,'stop-after-boundary-no-send')
            response=rpc.request('sendTransaction',[wire,dict(encoding='base64',skipPreflight=False,preflightCommitment='finalized',maxRetries=0,minContextSlot=slot)])
            write_new(child/'send-response.json',dict(state=response['state'],signatureMatched=response.get('result')==v['signatures'][0]))
            if response['state']=='received' and response.get('result')!=v['signatures'][0]:save_observation(child,'quarantined',reason='send-signature-mismatch')
            else:observe(s,child,rpc,sleeper=sleeper)
        except (ValueError,KeyError,TypeError,IndexError,OSError,subprocess.SubprocessError):
            if child is not None:save_observation(child,'submission-unknown' if exists(child,'send-boundary.json') else 'preparation-incomplete',reason='validation-or-transport-failure')
            return report(s,rpc,'validation-or-transport-failure')
        return report(s,rpc)


def recover(home,wallet,*,opener=None,sleeper=time.sleep):
    rpc=RecoveryRpc(opener)
    with Session(home) as s:
        check(s.wallet==wallet,'explicit-wallet-mismatch');r=report(s,rpc)
        if r['state'] in TERMINAL or not r['submissionAttempts']:return r
        child=s.home/CHILD;i,wire,v=signed_plan(child,s.wallet);boundary=read(child,'send-boundary.json')
        check(boundary.get('intentSha256')==digest(i) and boundary.get('wireSha256')==v['wireSha256'],'pool-boundary-binding')
        check(simulation_review(i,wire,read(child,'simulation-response.json'))==read(child,'simulation-review.json'),'pool-simulation-binding')
        observe(s,child,rpc,sleeper=sleeper);return report(s,rpc)


def status(home,wallet):
    with Session(home) as s:
        check(s.wallet==wallet,'explicit-wallet-mismatch');return report(s,RecoveryRpc())
