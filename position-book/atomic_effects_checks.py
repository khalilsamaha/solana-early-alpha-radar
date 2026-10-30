"""Synthetic raw combined responses and adversarial portable checks; no RPC."""
import base64
from copy import deepcopy
import atomic_effects as m
import atomic_rehearsal as contract
from atomic_rehearsal_checks import fixture as parent_fixture
from atomic_simulation import sanitize
from contract import TOKEN, PROGRAM, b58, decode, decode_wire
from state import account, decode_pool, configuration, u64
from cpmm_quote import calculate
from post_entry_checks import mutate_row, NOW
from recorded_capture import GENESIS


def response(capture,wire,slot=103,fee=6000,parsed=True):
    """Fixture bank applies two constant-product swaps and records raw transfers."""
    a=capture['packet']['policy']['accounts'];by=dict(zip(capture['accountKeys'],capture['evidence']['accounts']['result']['value']))
    msg=decode_wire(wire)[4]['transaction']['message'];keys=msg['accountKeys']
    pool=decode_pool(by[a['pool']]);rates=configuration(by[a['config']]);side=0 if a['inputMint']==pool['mint0'] else 1
    amounts={k:u64(account(by[k],TOKEN,165),64) for k in (a[n] for n in m.NAMES)}
    original=amounts.copy();pool_row=deepcopy(by[a['pool']]);groups=[];timestamp=capture['evidence']['blockTime']['result'];epoch=41
    obs=account(by[a['observation']],PROGRAM,4075)
    for index,direction in ((2,side),(3,1-side)):
        data=decode(msg['instructions'][index]['data']);qty=int.from_bytes(data[8:16],'little')
        src,dst,iv,ov,im,om=(a[k] for k in (('source','destination','inputVault','outputVault','inputMint','outputMint') if index==2 else
            ('destination','source','outputVault','inputVault','outputMint','inputMint')))
        current_pool=decode_pool(pool_row)
        reserve=[amounts[pool['vault'+str(i)]]-current_pool['accruedFees'+str(i)] for i in range(2)]
        math=calculate(qty,reserve[direction],reserve[1-direction],rates['trade'],0,False)
        output=int(math['outputAtomic']);trade=int(math['tradeFeeAtomic'])
        obs=m.oracle_update(obs,timestamp,*reserve)
        for offset,share in ((341+8*direction,rates['protocolShare']),(357+8*direction,rates['fundShare'])):
            raw=account(pool_row,PROGRAM,637);mutate_row(pool_row,offset,(u64(raw,offset)+trade*share//1000000).to_bytes(8,'little'))
        instructions=[]
        for source,mint,dest,authority,amount in ((src,im,iv,a['wallet'],qty),(ov,om,dst,a['authority'],output)):
            decimals=account(by[mint],TOKEN,82)[44]
            amounts[source]-=amount;amounts[dest]+=amount
            if parsed:
                instructions.append(dict(program='spl-token',programId=TOKEN,stackHeight=2,
                    parsed=dict(type='transferChecked',info=dict(source=source,mint=mint,destination=dest,authority=authority,
                        tokenAmount=dict(amount=str(amount),decimals=decimals,uiAmount=123.456,uiAmountString='ignored')))))
            else:instructions.append(dict(programIdIndex=keys.index(TOKEN),accounts=[keys.index(k) for k in (source,mint,dest,authority)],
                stackHeight=2,data=b58(b'\x0c'+amount.to_bytes(8,'little')+bytes([decimals]))))
        groups.append(dict(index=index,instructions=instructions))
    mutate_row(pool_row,381,epoch.to_bytes(8,'little'))
    before=[by[k]['lamports'] if k in by else 1 for k in keys];after=before.copy();after[0]-=fee
    rows=[deepcopy(by[a[n]]) for n in ('wallet',)+m.NAMES];rows[0]['lamports']=after[0]
    pre=[];post=[]
    for i,n in enumerate(m.NAMES):
        k=a[n];mint=a['inputMint' if i in (0,2) else 'outputMint'];owner=a['wallet' if i<2 else 'authority']
        mutate_row(rows[i+1],64,amounts[k].to_bytes(8,'little'))
        for group,amount in ((pre,original[k]),(post,amounts[k])):
            group.append(dict(accountIndex=keys.index(k),mint=mint,owner=owner,programId=TOKEN,
                uiTokenAmount=dict(amount=str(amount),decimals=account(by[mint],TOKEN,82)[44])))
    rows += [deepcopy(by[k]) for k in (a['config'],PROGRAM,capture['accountKeys'][-1])]
    obs_row=deepcopy(by[a['observation']]);obs_row['data'][0]=base64.b64encode(obs).decode()
    clock=slot.to_bytes(8,'little')+bytes(8)+epoch.to_bytes(8,'little')+bytes(8)+timestamp.to_bytes(8,'little',signed=True)
    rows += [pool_row,obs_row,dict(owner=m.SYSVAR,executable=False,lamports=1,data=[base64.b64encode(clock).decode(),'base64'])]
    return dict(context=dict(slot=slot),value=dict(err=None,fee=fee,unitsConsumed=180000,
        preBalances=before,postBalances=after,preTokenBalances=pre,postTokenBalances=post,accounts=rows,innerInstructions=groups))


def fixture(reverse=False,parsed=True):
    args,request,draft,_=parent_fixture(reverse)
    args['now_ms']=NOW+400;args['reservations'].update(readStartedAtMs=NOW+350,observedAtMs=NOW+360)
    review=contract._Review(args,request)
    fp=m.fee_parameters(review,draft);slot=fp[1]['minContextSlot'];sp=m.simulation_parameters(args,draft,slot)
    raw=response(args['capture'],draft['unsignedTransactionBase64'],slot=slot+1,parsed=parsed)
    e=dict(feeParams=fp,fee=dict(state='received',result=dict(context=dict(slot=slot),value=6000)),
        simulationParams=sp,simulation=sanitize(dict(state='received',result=raw),sp),
        genesis=dict(state='received',result=GENESIS['devnet']),startedAtMs=NOW+210,feeReceivedAtMs=NOW+220,
        simulationStartedAtMs=NOW+230,simulationReceivedAtMs=NOW+300,finishedAtMs=NOW+320)
    return args,request,draft,e


def run():
    cases={}
    for reverse in (False,True):
        for parsed in (False,True):
            args,p,d,e=fixture(reverse,parsed);r=m.assess(args,p,d,e)
            if r['state']!='atomic-simulation-effects-consistent':raise ValueError('atomic-fixture-rejected')
            if r['fee']['observedCombinedLamports']!='6000' or r['trace']['residualAcquiredAtomic']!='0':raise ValueError('atomic-fixture-fee-trace')
            cases[('reverse' if reverse else 'forward')+'-'+('parsed' if parsed else 'compiled')]='passed'
    changes={
        'borrowed-entry-fee':lambda a,e:e['fee']['result'].update(value=5000),
        'wrong-exact-fee-message':lambda a,e:e['feeParams'].__setitem__(0,'different'),
        'wrong-exact-simulation-wire':lambda a,e:e['simulationParams'].__setitem__(0,'different'),
        'native-extra-debit':lambda a,e:e['simulation']['result']['value']['postBalances'].__setitem__(0,1),
        'wrong-token-balance':lambda a,e:mutate_row(e['simulation']['result']['value']['accounts'][1],64,(42).to_bytes(8,'little')),
        'missing-trace':lambda a,e:e['simulation']['result']['value']['innerInstructions'].pop(),
        'wrong-pool-counter':lambda a,e:mutate_row(e['simulation']['result']['value']['accounts'][8],349,(999).to_bytes(8,'little')),
        'pool-padding-changed':lambda a,e:mutate_row(e['simulation']['result']['value']['accounts'][8],636,b'\x01'),
        'oracle-padding-changed':lambda a,e:mutate_row(e['simulation']['result']['value']['accounts'][9],4074,b'\x01'),
        'wrong-clock-slot':lambda a,e:mutate_row(e['simulation']['result']['value']['accounts'][10],0,(999).to_bytes(8,'little')),
        'wrong-clock-epoch':lambda a,e:mutate_row(e['simulation']['result']['value']['accounts'][10],16,(999).to_bytes(8,'little')),
        'deployment-drift':lambda a,e:e['simulation']['result']['value']['accounts'][7].update(lamports=1),
        'over-compute-cap':lambda a,e:e['simulation']['result']['value'].update(unitsConsumed=300001),
        'unknown-native-reservations':lambda a,e:a['reservations'].update(nativeHeldLamports=None),
        'expired-parent':lambda a,e:a.update(now_ms=NOW+20000),
        'local-read-before-simulation':lambda a,e:a['reservations'].update(readStartedAtMs=NOW+100),
        'cluster-change':lambda a,e:e['genesis'].update(result=GENESIS['mainnet-beta']),
    }
    for name,change in changes.items():
        a,p,d,e=fixture();change(a,e);r=m.assess(a,p,d,e)
        if r['state']!='unavailable' or r['binding'] is not None:raise ValueError('atomic-rejection-'+name)
        cases[name]='rejected'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        executionApproved=False,simulationVerified=False,productionStateChanged=False)
