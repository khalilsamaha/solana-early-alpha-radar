"""One-shot devnet swap signing/simulation. No send method or position ledger mutation."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'swap-preflight'))
from preflight import audit, digest, validate, GENESIS
from preflight_capture import collect
from state import account, token, TOKEN, SYSTEM, NATIVE, integer
from contract import POLICY_FIELDS, decode_wire
sys.path.insert(0,str(ROOT/'devnet-rehearsal'))
from core import Session, directory, private_file, write_new, sync_directory, loads, check, Rpc, context_value, Client
from wire import verify_wire

CHILD='swap-simulation-v1'
FLAGS=dict(network='devnet',transactionsSent=0,executionApproved=False,productionLedgerUpdated=False,
           positionBookConnected=False,privateKeyExported=False,resubmitAllowed=False)
SCOPE_FIELDS=POLICY_FIELDS-{'issuedAtMs','expiresAtMs','blockhash','format'}


def scope_for(policy):
    return dict(format='devnet-swap-scope-1',**{k:copy.deepcopy(policy[k]) for k in SCOPE_FIELDS})


def policy_check(scope,packet,wallet,at):
    check(type(scope) is dict and set(scope)==SCOPE_FIELDS|{'format'},'scope-schema')
    check(scope==scope_for(packet['policy']),'independent-scope-mismatch')
    v=validate(packet,now_ms=at)
    check(v['state']=='instruction-policy-match','current-contract-required')
    check(v['messageVersion']=='legacy','legacy-only-rehearsal')
    check(v['accounts']['wallet']==wallet,'explicit-wallet-mismatch')
    check(int(scope['amountIn'])<=1000 and int(scope['maxTotalFeeLamports'])<=10000
          and scope['maxComputeUnits']<=300000 and int(scope['maxMicroLamportsPerCU'])<=10000
          and int(scope['maxPriorityFeeLamports'])<=3000,'rehearsal-hard-cap')
    return v


def stop(home):return os.path.lexists(Path(home)/'STOP')


def invoke_signer(home, *, execution=False):
    node=shutil.which('node');check(node is not None,'node-unavailable')
    p=subprocess.run([str(Path(node).resolve()),str(Path(__file__).with_name('swap_signer.mjs'))],
       input=json.dumps(dict(directory=str(home), **({'purpose':'controlled-pool-swap-execution-1'} if execution else {}))),text=True,capture_output=True,timeout=10,env={'PATH':os.defpath})
    check(p.returncode==0 and p.stdout=='{"signed":true}','restricted-signer-refused')


class SimulationRpc(Rpc):
    METHODS=('simulateTransaction','getGenesisHash')
    REQUEST_CAP=2

    def request(self,method,params):
        r=Client.request(self,method,params)
        if r['state']!='received' or method!='simulateTransaction':return r
        try:
            v=r['result']['value'];slot=r['result']['context']['slot']
            check(type(v) is dict and 'err' in v and integer(slot),'simulation-shape')
            clean={'failed':v['err'] is not None}
            for k in ('fee','unitsConsumed'):
                if k in v:check(integer(v[k]),'simulation-number');clean[k]=v[k]
            clean['replacementBlockhash']=None if v.get('replacementBlockhash') is None else 'present'
            for k in ('preBalances','postBalances'):
                if k in v:
                    check(type(v[k]) is list and len(v[k])<=14 and all(integer(x) for x in v[k]),'simulation-array')
                    clean[k]=v[k]
            if 'accounts' in v:
                check(type(v['accounts']) is list and len(v['accounts'])==5,'simulation-accounts')
                clean['accounts']=[]
                for a in v['accounts']:
                    check(type(a) is dict and type(a.get('data')) is list and len(a['data'])==2
                          and type(a['data'][0]) is str and len(a['data'][0])<=220,'simulation-account-data')
                    clean['accounts'].append({k:a[k] for k in ('owner','executable','lamports','data') if k in a})
            for name in ('preTokenBalances','postTokenBalances'):
                if name in v:
                    check(type(v[name]) is list and len(v[name])<=4,'simulation-token-array')
                    clean[name]=[]
                    for t in v[name]:
                        check(type(t) is dict and type(t.get('uiTokenAmount')) is dict,'simulation-token-shape')
                        row={k:t[k] for k in ('accountIndex','mint','owner','programId') if k in t}
                        row['uiTokenAmount']={k:t['uiTokenAmount'][k] for k in ('amount','decimals') if k in t['uiTokenAmount']}
                        clean[name].append(row)
            r['result']={'context':{'slot':slot},'value':clean}
        except (ValueError,TypeError,KeyError,IndexError):
            r={'state':'invalid-simulation-response'};self.calls[-1]['state']=r['state']
        return r


def signed_binding(packet,wire):
    v=verify_wire(wire)
    check(decode_wire(wire)[1]==decode_wire(packet['unsignedTransactionBase64'])[1], 'signed-message-mismatch')
    check(v['requiredSignatures']==1 and v['wallet']==packet['policy']['accounts']['wallet'],'signed-wallet-mismatch')
    return v


def simulation_review(packet,capture,wire,item):
    """Require exact wallet deltas and SPL vault conservation, not just err=null."""
    signed=signed_binding(packet,wire)
    slot,value=context_value(item,capture['evidence']['accounts']['result']['context']['slot'])
    check(value.get('failed') is False,'simulation-failed')
    check(value.get('replacementBlockhash') is None,'simulation-blockhash-replaced')
    p=packet['policy'];a=p['accounts'];fee=int(packet['feeAssertion']['lamports'])
    contract=validate(packet,now_ms=capture['finishedAtMs'])
    check(contract['state']=='instruction-policy-match','simulation-contract')
    check(integer(value.get('fee'),1) and value['fee']==fee<=int(p['maxTotalFeeLamports']),'simulation-fee')
    check(integer(value.get('unitsConsumed')) and value['unitsConsumed']<=contract['computeUnits'],'simulation-compute')
    keys=decode_wire(wire)[4]['transaction']['message']['accountKeys']
    before,after=value.get('preBalances'),value.get('postBalances')
    check(type(before) is list and type(after) is list and len(before)==len(after)==len(keys)
          and all(integer(v) for v in before+after),'simulation-native-balances')
    expected=before.copy();expected[0]-=fee
    check(after==expected and expected[0]>=0,'simulation-native-deltas')
    raw=capture['evidence']['accounts']['result']['value'];bykey=dict(zip(capture['accountKeys'],raw))
    check(before[0]==bykey[a['wallet']]['lamports'],'simulation-wallet-prebalance-changed')
    rows=value.get('accounts')
    check(type(rows) is list and len(rows)==5,'simulation-account-count')
    account(rows[0],SYSTEM,0)
    check(rows[0]['lamports']==after[0],'simulation-wallet-account')
    names=('source','destination','inputVault','outputVault')
    pre_tokens=value.get('preTokenBalances');post_tokens=value.get('postTokenBalances')
    check(type(pre_tokens) is list and type(post_tokens) is list and len(pre_tokens)==len(post_tokens)==4,
          'simulation-token-balances')
    def indexed(items):
        out={}
        for r in items:
            check(type(r) is dict and integer(r.get('accountIndex')) and r['accountIndex']<len(keys),'simulation-token-index')
            k=keys[r['accountIndex']];check(k not in out,'duplicate-simulation-token')
            out[k]=r
        check(set(out)=={a[n] for n in names},'simulation-token-set')
        return out
    pre,post=indexed(pre_tokens),indexed(post_tokens)
    deltas=[]
    for i,name in enumerate(names):
        k=a[name];mint=a['inputMint' if i in (0,2) else 'outputMint'];owner=a['wallet' if i<2 else 'authority']
        t=token(rows[i+1],mint,owner)
        orig=token(bykey[k],mint,owner)
        check(rows[i+1]['lamports']==bykey[k]['lamports']==before[keys.index(k)],'simulation-token-rent')
        prior_raw=account(bykey[k],TOKEN,165);post_raw=account(rows[i+1],TOKEN,165)
        check(prior_raw[:64]+prior_raw[72:]==post_raw[:64]+post_raw[72:],'simulation-token-authority-or-layout')
        amounts=[]
        for group in (pre,post):
            r=group[k];u=r.get('uiTokenAmount')
            check(r.get('mint')==mint and r.get('owner')==owner and r.get('programId')==TOKEN
                  and type(u) is dict and type(u.get('decimals')) is int,'simulation-token-identity')
            # Orientation-independent mint lookup.
            decimals=base64.b64decode(bykey[mint]['data'][0])[44]
            check(u['decimals']==decimals,'simulation-token-decimals')
            from contract import atomic
            amounts.append(atomic(u.get('amount'),'simulation-token-amount'))
        check(amounts[1]==int(t['amount']),'simulation-post-account-amount')
        if i<2:check(amounts[0]==int(orig['amount']),'simulation-wallet-token-prebalance-changed')
        deltas.append(amounts[1]-amounts[0])
    check(deltas[0]==-int(p['amountIn']) and deltas[1]>=int(p['minimumAmountOut'])
          and deltas[2]==-deltas[0] and deltas[3]==-deltas[1],'simulation-token-deltas')
    return dict(state='signed-simulation-consistent',simulationSlot=slot,signature=signed['signatures'][0],
                wireSha256=signed['wireSha256'],messageSha256=signed['wireMessageSha256'],feeLamports=str(fee),
                inputAtomic=p['amountIn'],simulatedOutputAtomic=str(deltas[1]),unitsConsumed=value['unitsConsumed'],
                actualExecutionObserved=False,**FLAGS)


def report(home,rpc=None,reason=None):
    child=Path(home)/CHILD
    result=dict(format='devnet-swap-rehearsal-1',state='not-started',reason=reason,**FLAGS,
                networkRequests=len(rpc.calls) if rpc else 0,requests=rpc.calls if rpc else [],
                signaturesCreatedThisRun=0,signedBytesExported=False,signingAttemptRecorded=False,signatureOutcomeUnknown=False)
    if not child.exists():return result
    directory(child)
    if (child/'plan.json').exists():
        plan=loads(private_file(child/'plan.json',32768));result.update(state='plan-recorded',scope=plan['scope'])
    if (child/'signing-attempt.json').exists():result.update(state='signing-outcome-unknown',signingAttemptRecorded=True,signatureOutcomeUnknown=True)
    if (child/'signed.json').exists():
        signed=loads(private_file(child/'signed.json',8192));v=signed_binding(plan['packet'],signed['wire'])
        result.update(state='signed-not-simulated',signature=v['signatures'][0],wireSha256=v['wireSha256'],signatureOutcomeUnknown=False)
    if (child/'simulation-request.json').exists():result['state']='simulation-outcome-unknown'
    if (child/'simulation-review.json').exists():
        result['simulation']=loads(private_file(child/'simulation-review.json',32768))
        result['state']=result['simulation']['state']
    if (child/'failure.json').exists():result.update(state='preparation-incomplete',reason='recorded-preparation-failure')
    return result


def _prepare(home,wallet,scope,packet,*,opener=None,collector=collect,reviewer=audit,clock=None,signer=invoke_signer):
    """Dependency injection for synthetic tests; CLI supplies no collector/baseline overrides."""
    clock=clock or (lambda:time.time_ns()//1000000)
    scope,packet=copy.deepcopy(scope),copy.deepcopy(packet)
    rpc=SimulationRpc(opener)
    with Session(home) as s:
        check(s.wallet==wallet,'explicit-wallet-mismatch')
        child=s.home/CHILD
        if os.path.lexists(child):return report(s.home,reason='existing-plan-use-status-no-retry')
        v=policy_check(scope,packet,wallet,clock());check(not stop(s.home),'stop-requested')
        child.mkdir(mode=0o700);sync_directory(s.home)
        write_new(child/'plan.json',dict(format='swap-signing-plan-1',scope=scope,packet=packet,recordedAtMs=clock()))
        capture=None
        try:
            capture=collector(packet=packet,opener=opener)
            check(capture.get('packet')==packet,'preflight-packet-changed')
            write_new(child/'preflight.json',capture)
            reviewed=reviewer(capture,now_ms=clock())
            check(reviewed['state']=='preflight-evidence-consistent','fresh-preflight-required')
            policy_check(scope,packet,wallet,clock());check(not stop(s.home),'stop-requested')
            write_new(child/'signing-request.json',dict(format='restricted-swap-request-1',
                planSha256=digest(loads(private_file(child/'plan.json',32768))),preflightSha256=digest(capture),
                expiresAtMs=reviewed['validUntilExclusiveMs'],computeUnits=v['computeUnits'],
                microLamportsPerCU=v['microLamportsPerCU'],messageBase64=base64.b64encode(decode_wire(packet['unsignedTransactionBase64'])[1]).decode()))
            signer(s.home)
            signed=loads(private_file(child/'signed.json',8192));signed_binding(packet,signed['wire'])
            check(reviewer(capture,now_ms=clock())['state']=='preflight-evidence-consistent','preflight-expired-after-signing')
            check(not stop(s.home),'stop-requested')
            a=packet['policy']['accounts'];addresses=[a[n] for n in ('wallet','source','destination','inputVault','outputVault')]
            params=[signed['wire'],dict(encoding='base64',commitment='finalized',sigVerify=True,replaceRecentBlockhash=False,
                    minContextSlot=reviewed['snapshotSlot'],accounts=dict(encoding='base64',addresses=addresses))]
            write_new(child/'simulation-request.json',dict(messageSha256=v['wireMessageSha256'],addresses=addresses))
            item=rpc.request('simulateTransaction',params)
            # Core Rpc strips provider logs/errors. Preserve token evidence through our strict projection below.
            write_new(child/'simulation-response.json',item)
            identity=rpc.request('getGenesisHash',[])
            check(identity.get('state')=='received' and identity.get('result')==GENESIS['devnet'],'simulation-cluster')
            sim=simulation_review(packet,capture,signed['wire'],item)
            write_new(child/'simulation-review.json',sim)
        except (ValueError,KeyError,TypeError,IndexError,OSError,subprocess.SubprocessError):
            write_new(child/'failure.json',{'reason':'preparation-validation-failed','atMs':clock()})
        result=report(s.home,rpc)
        # A lost signer acknowledgement may follow a durable signed.json write.
        # report() has already verified that file; do not report zero in that case.
        result['signaturesCreatedThisRun']=None if result['signatureOutcomeUnknown'] else int((child/'signed.json').exists())
        result['preflightRequests']=capture.get('requests',[]) if capture else []
        result['networkRequests']+=len(result['preflightRequests'])
        return result


def prepare(home,wallet,scope,packet,*,opener=None):
    return _prepare(home,wallet,scope,packet,opener=opener)
