"""Raw combined-simulation effects and oracle reference replay. No transport or sender."""
from copy import deepcopy
import atomic_rehearsal as contract
from contract import (TOKEN, SYSTEM, PROGRAM, U64, EvidenceError, atomic, b58,
                      decode_wire, digest, fields)
from core import check, context_value
from state import account, anchor, decode_pool, configuration, integer, token, u64
from recorded_capture import GENESIS

import base64

VERSION='atomic-simulation-effects-1'
CLOCK='SysvarC1ock11111111111111111111111111111111'
SYSVAR='Sysvar1111111111111111111111111111111111111'
NAMES=('source','destination','inputVault','outputVault')
DIAGNOSTICS=frozenset('''atomic-fee-binding atomic-fee-unavailable atomic-simulation-binding
atomic-evidence-clocks atomic-cluster atomic-simulation-failed atomic-simulated-fee atomic-compute
atomic-native-evidence atomic-native-effects atomic-prestate-drift atomic-returned-accounts
atomic-wallet-balance atomic-deployment-config-drift atomic-token-metadata atomic-token-index
atomic-token-set atomic-token-layout atomic-token-rent atomic-trace-account-mismatch
atomic-token-metadata-mismatch atomic-bank-clock atomic-pool-rent atomic-pool-counter-overflow
atomic-epoch-regression atomic-pool-transition atomic-oracle-layout atomic-oracle-index
atomic-oracle-input atomic-oracle-clock-regression atomic-oracle-multiply-overflow
atomic-oracle-identity atomic-oracle-transition atomic-native-cap atomic-inner-encoding
atomic-trace-groups atomic-trace-order atomic-trace-count atomic-trace-program
atomic-trace-roles atomic-trace-depth atomic-trace-amount atomic-trace-balance
atomic-acquired-residual'''.split())


def fee_parameters(review,draft):
    review.binding(draft)
    msg=decode_wire(draft['unsignedTransactionBase64'])[1]
    return [base64.b64encode(msg).decode(),dict(commitment='finalized',
        minContextSlot=review.parent()['evidence']['simulationContextSlot'])]


def simulation_parameters(inputs,draft,fee_slot):
    a=inputs['packet']['policy']['accounts'];c=inputs['capture']
    addresses=[a[k] for k in ('wallet',)+NAMES]+[a['config'],PROGRAM,c['accountKeys'][-1],a['pool'],a['observation'],CLOCK]
    return [draft['unsignedTransactionBase64'],dict(encoding='base64',commitment='finalized',
        sigVerify=False,replaceRecentBlockhash=False,innerInstructions=True,minContextSlot=fee_slot,
        accounts=dict(encoding='base64',addresses=addresses))]


def oracle_update(raw, timestamp, reserve0, reserve1):
    """Pinned source reference, not a claim of deployed-source equivalence.

    Layout and update from raydium-cp-swap f4b9b263, states/oracle.rs. Two
    instructions in one bank use the same Clock; the second usually adds zero.
    """
    check(len(raw)==4075 and raw[8] in (0,1),'atomic-oracle-layout')
    index=int.from_bytes(raw[9:11],'little');check(index<100,'atomic-oracle-index')
    check(integer(timestamp) and reserve0>0 and reserve1>0,'atomic-oracle-input')
    out=bytearray(raw);offset=43+index*40
    if not raw[8]:
        out[8]=1;out[offset:offset+8]=timestamp.to_bytes(8,'little')
        out[offset+8:offset+40]=bytes(32);out[4043:4051]=timestamp.to_bytes(8,'little')
        return bytes(out)
    prior=u64(raw,offset);updated=u64(raw,4043) or prior
    check(prior<=timestamp and updated<=timestamp,'atomic-oracle-clock-regression')
    out[4043:4051]=updated.to_bytes(8,'little')
    delta=timestamp-updated;elapsed=timestamp-prior
    if delta==0 or elapsed==0:return bytes(out)
    target=offset if elapsed<15 else 43+((index+1)%100)*40
    if elapsed>=15:
        out[9:11]=((index+1)%100).to_bytes(2,'little')
        out[target:target+8]=timestamp.to_bytes(8,'little')
    for n,price in enumerate(((reserve1<<32)//reserve0,(reserve0<<32)//reserve1)):
        increment=price*delta;check(increment<2**128,'atomic-oracle-multiply-overflow')
        total=(int.from_bytes(raw[offset+8+n*16:offset+24+n*16],'little')+increment)%(2**128)
        out[target+8+n*16:target+24+n*16]=total.to_bytes(16,'little')
    out[4043:4051]=timestamp.to_bytes(8,'little')
    return bytes(out)


def _review(inputs,request,draft,e):
    parent=contract._Review(inputs,request);binding=parent.binding(draft);post=parent.parent()
    fields(e,{'feeParams','fee','simulationParams','simulation','genesis','startedAtMs',
              'feeReceivedAtMs','simulationStartedAtMs','simulationReceivedAtMs','finishedAtMs'},'atomic-evidence-fields')
    check(digest(e['feeParams'])==digest(fee_parameters(parent,draft)),'atomic-fee-binding')
    fee_slot,fee=context_value(e['fee'],post['evidence']['simulationContextSlot'])
    cap=int(inputs['packet']['policy']['maxTotalFeeLamports'])
    check(integer(fee,1) and fee<=cap,'atomic-fee-unavailable')
    check(digest(e['simulationParams'])==digest(simulation_parameters(inputs,draft,fee_slot)),'atomic-simulation-binding')
    clocks=[e[k] for k in ('startedAtMs','feeReceivedAtMs','simulationStartedAtMs','simulationReceivedAtMs','finishedAtMs')]
    check(all(integer(t) for t in clocks) and inputs['simulation_finished']<=clocks[0] and
          clocks==sorted(clocks) and clocks[-1]<=inputs['reservations']['readStartedAtMs']<=
          inputs['reservations']['observedAtMs']<=inputs['now_ms'],'atomic-evidence-clocks')
    check(e['genesis'].get('state')=='received' and e['genesis'].get('result')==GENESIS['devnet'],'atomic-cluster')
    slot,v=context_value(e['simulation'],fee_slot)
    check(v.get('failed') is False and v.get('replacementBlockhash') is None,'atomic-simulation-failed')
    check(integer(v.get('fee'),1) and v['fee']==fee,'atomic-simulated-fee')
    check(integer(v.get('unitsConsumed'),1) and v['unitsConsumed']<=binding['computeUnitsShared'],'atomic-compute')
    trace=parent.trace(draft,v.get('innerInstructions'));trace.pop('binding')
    binding['feeBasis']='exact-combined-message-rpc-and-simulation'
    check(v.get('innerEncoding') in ('json-parsed','compiled'),'atomic-inner-encoding')
    c=inputs['capture'];a=inputs['packet']['policy']['accounts']
    bykey=dict(zip(c['accountKeys'],c['evidence']['accounts']['result']['value']))
    keys=decode_wire(draft['unsignedTransactionBase64'])[4]['transaction']['message']['accountKeys']
    before,after=v.get('preBalances'),v.get('postBalances')
    check(type(before) is list and type(after) is list and len(before)==len(after)==len(keys) and
          all(integer(x) for x in before+after),'atomic-native-evidence')
    expected=before.copy();expected[0]-=fee
    check(expected[0]>=0 and after==expected,'atomic-native-effects')
    check(all(before[i]==bykey[k]['lamports'] for i,k in enumerate(keys) if k in bykey),'atomic-prestate-drift')
    rows=v.get('accounts');check(type(rows) is list and len(rows)==11,'atomic-returned-accounts')
    account(rows[0],SYSTEM,0);check(rows[0]['lamports']==after[0],'atomic-wallet-balance')
    for i,k in enumerate((a['config'],PROGRAM,c['accountKeys'][-1]),5):
        check(rows[i]==bykey[k],'atomic-deployment-config-drift')
    def indexed(name):
        source=v.get(name);check(type(source) is list and len(source)==4,'atomic-token-metadata')
        result={}
        for row in source:
            ix=row.get('accountIndex');check(integer(ix) and ix<len(keys) and keys[ix] not in result,'atomic-token-index')
            result[keys[ix]]=row
        check(set(result)=={a[n] for n in NAMES},'atomic-token-set')
        return result
    pre_tokens,post_tokens=indexed('preTokenBalances'),indexed('postTokenBalances')
    for i,n in enumerate(NAMES):
        k=a[n];mint=a['inputMint' if i in (0,2) else 'outputMint'];owner=a['wallet' if i<2 else 'authority']
        original=token(bykey[k],mint,owner);returned=token(rows[i+1],mint,owner)
        old=account(bykey[k],TOKEN,165);new=account(rows[i+1],TOKEN,165)
        check(old[:64]+old[72:]==new[:64]+new[72:],'atomic-token-layout')
        check(rows[i+1]['lamports']==before[keys.index(k)]==after[keys.index(k)],'atomic-token-rent')
        decimals=account(bykey[mint],TOKEN,82)[44]
        b=trace['balances'][n]
        check(original['amount']==b['beforeAtomic'] and returned['amount']==b['afterExitAtomic'],'atomic-trace-account-mismatch')
        for group,amount in ((pre_tokens,original['amount']),(post_tokens,returned['amount'])):
            r=group[k];u=r.get('uiTokenAmount',{})
            check(r.get('mint')==mint and r.get('owner')==owner and r.get('programId')==TOKEN and
                  type(u.get('decimals')) is int and u['decimals']==decimals and
                  atomic(u.get('amount'),'atomic-token-amount')==int(amount),'atomic-token-metadata-mismatch')
    clock_raw=account(rows[10],SYSVAR,40)
    bank_slot=u64(clock_raw,0);epoch=u64(clock_raw,16);timestamp=int.from_bytes(clock_raw[32:40],'little',signed=True)
    check(bank_slot==slot and timestamp>=c['evidence']['blockTime']['result'],'atomic-bank-clock')
    pool_pre=account(bykey[a['pool']],PROGRAM,637);pool_post=account(rows[8],PROGRAM,637)
    pool=decode_pool(bykey[a['pool']]);rates=configuration(bykey[a['config']])
    check(rows[8]['lamports']==bykey[a['pool']]['lamports'],'atomic-pool-rent')
    side=0 if a['inputMint']==pool['mint0'] else 1;expected_pool=bytearray(pool_pre)
    for direction,trade in ((side,int(inputs['price']['arithmetic']['tradeFeeAtomic'])),
                            (1-side,int(post['projection']['arithmetic']['tradeFeeAtomic']))):
        for offset,share in ((341+8*direction,rates['protocolShare']),(357+8*direction,rates['fundShare'])):
            total=u64(expected_pool,offset)+trade*share//1000000
            check(total<=U64,'atomic-pool-counter-overflow');expected_pool[offset:offset+8]=total.to_bytes(8,'little')
    check(epoch>=u64(pool_pre,381),'atomic-epoch-regression')
    expected_pool[381:389]=epoch.to_bytes(8,'little')
    check(bytes(expected_pool)==pool_post,'atomic-pool-transition')
    old_obs=account(bykey[a['observation']],PROGRAM,4075);new_obs=account(rows[9],PROGRAM,4075)
    anchor(old_obs,'ObservationState');anchor(new_obs,'ObservationState')
    check(b58(old_obs[11:43])==a['pool'] and rows[9]['lamports']==bykey[a['observation']]['lamports'],'atomic-oracle-identity')
    vault_amounts={a[n]:int(trace['balances'][n]['beforeAtomic']) for n in ('inputVault','outputVault')}
    reserves=[vault_amounts[pool['vault'+str(i)]]-pool['accruedFees'+str(i)] for i in range(2)]
    expected_obs=oracle_update(old_obs,timestamp,*reserves)
    expected_obs=oracle_update(expected_obs,timestamp,*map(int,post['projection']['reservesToken0Token1Atomic']))
    check(expected_obs==new_obs,'atomic-oracle-transition')
    native=int(post['entryFeeEvidence']['nativeSpendableLamports']);check(native>=cap,'atomic-native-cap')
    return dict(state='atomic-simulation-effects-consistent',binding=binding,trace=trace,
        simulationSlot=slot,bankTimestamp=timestamp,bankEpoch=epoch,oracleReferenceEffectsMatched=True,
        finalTokenAccountsMatched=True,finalPoolEffectsMatched=True,returnedDeploymentMatched=True,
        fee=dict(observedCombinedLamports=str(fee),simulatedCombinedLamports=str(v['fee']),
                 combinedCapLamports=str(cap),nativeRemainingAfterCapLamports=str(native-cap),
                 transactionCount=1,actualNativeDebitLamports='0'),
        evidence=dict(simulationSha256=digest(e['simulation']),feeSha256=digest(e['fee']),
            simulationParametersSha256=digest(e['simulationParams']),feeParametersSha256=digest(e['feeParams']),
            prePoolSha256=digest(bykey[a['pool']]),postPoolSha256=digest(rows[8]),
            preOracleSha256=digest(bykey[a['observation']]),postOracleSha256=digest(rows[9]),
            clockSha256=digest(rows[10]),ledgerHeadSha256=inputs['reservations']['ledgerHeadSha256'],
            cycleBindingSha256=inputs['reservations']['cycleBindingSha256']),
        unitsConsumed=v['unitsConsumed'],innerInstructionEncoding=v['innerEncoding'])


def assess(inputs,request,draft,evidence):
    result=dict(format=VERSION,state='unavailable',reasons=[],binding=None,trace=None,fee=None,
        liveCollectorVerified=False,simulationVerified=False,executionApproved=False,
        twoTransactionExecutionVerified=False,sourceEquivalenceVerified=False,
        signingApproved=False,validForSubmission=False,mainnetSupported=False,actualEntryExecuted=False,
        roundTripFundingEstablished=False,netProfit=None,transactionsSent=0,signaturesCreated=0)
    try:result.update(_review(deepcopy(inputs),request,draft,evidence))
    except (ValueError,KeyError,TypeError,IndexError,OverflowError,EvidenceError) as exc:
        result['reasons']=['atomic-effects-rejected']
        result['diagnosticCode']=str(exc) if str(exc) in DIAGNOSTICS else 'unclassified-atomic-evidence'
    return result
