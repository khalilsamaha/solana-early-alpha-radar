"""Bounded exact combined-message fee + unsigned simulation + final cluster read."""
import base64
from copy import deepcopy
import atomic_effects as effects
from core import check, context_value
from contract import TOKEN, U64, atomic, b58, decode_wire, digest, EvidenceError, fields
from state import integer
from program import MAX_BASE64
from recorded_capture import Client, GENESIS
from post_entry_simulation import AtomicTransport


def normalize_trace(groups,keys):
    """Simulation normally returns JSON Parsed CPI, not compiled instruction JSON.

    Normalize only standard SPL TransferChecked with one authority. No provider
    prose, float/UI quantities, unknown instruction or partial parse is admitted.
    """
    check(type(groups) is list and len(groups)==2,'atomic-inner-count')
    result=[];encodings=set()
    for group in groups:
        fields(group,{'index','instructions'},'atomic-inner-group')
        check(type(group['index']) is int and group['index'] in (2,3),'atomic-inner-index')
        rows=group['instructions'];check(type(rows) is list and len(rows)==2,'atomic-inner-rows')
        clean=[]
        for ix in rows:
            check(type(ix) is dict,'atomic-inner-row')
            if 'parsed' in ix:
                fields(ix,{'program','programId','parsed','stackHeight'},'atomic-parsed-fields')
                check(ix['program']=='spl-token' and ix['programId']==TOKEN and
                      type(ix['stackHeight']) is int and ix['stackHeight']==2,'atomic-parsed-program')
                parsed=ix['parsed'];fields(parsed,{'type','info'},'atomic-parsed-body')
                check(parsed['type']=='transferChecked','atomic-parsed-type')
                info=parsed['info'];fields(info,{'source','mint','destination','authority','tokenAmount'},'atomic-parsed-info')
                amount=info['tokenAmount'];check(type(amount) is dict and
                    {'amount','decimals'}<=set(amount)<={'amount','decimals','uiAmount','uiAmountString'},'atomic-parsed-amount')
                qty=atomic(amount['amount'],'atomic-parsed-quantity',positive=True)
                dec=amount['decimals'];check(type(dec) is int and 0<=dec<=255,'atomic-parsed-decimals')
                addresses=[info[k] for k in ('source','mint','destination','authority')]
                check(all(type(k) is str and k in keys for k in addresses),'atomic-parsed-accounts')
                clean.append(dict(programIdIndex=keys.index(TOKEN),accounts=[keys.index(k) for k in addresses],
                    stackHeight=2,data=b58(b'\x0c'+qty.to_bytes(8,'little')+bytes([dec]))))
                encodings.add('json-parsed')
            else:
                fields(ix,{'programIdIndex','accounts','data','stackHeight'},'atomic-compiled-fields')
                check(type(ix['programIdIndex']) is int and 0<=ix['programIdIndex']<len(keys) and
                      type(ix['stackHeight']) is int and ix['stackHeight']==2 and
                      type(ix['accounts']) is list and len(ix['accounts'])==4 and
                      all(type(i) is int and 0<=i<len(keys) for i in ix['accounts']) and
                      type(ix['data']) is str and len(ix['data'])<=16,'atomic-compiled-shape')
                clean.append(deepcopy(ix));encodings.add('compiled')
        result.append(dict(index=group['index'],instructions=clean))
    check(len(encodings)==1,'atomic-mixed-inner-encoding')
    return result,next(iter(encodings))


def sanitize(item,params):
    slot,v=context_value(item,0);check(type(v) is dict and 'err' in v,'atomic-response-shape')
    check(v['err'] is None,'atomic-program-failed')
    clean=dict(failed=False,replacementBlockhash=None if v.get('replacementBlockhash') is None else 'present')
    for name in ('fee','unitsConsumed'):
        check(integer(v.get(name)),'atomic-response-number');clean[name]=v[name]
    for name in ('preBalances','postBalances'):
        check(type(v.get(name)) is list and len(v[name])==14 and all(integer(n) for n in v[name]),'atomic-response-balances')
        clean[name]=deepcopy(v[name])
    rows=v.get('accounts');check(type(rows) is list and len(rows)==11,'atomic-response-accounts')
    clean['accounts']=[]
    for i,row in enumerate(rows):
        check(type(row) is dict and type(row.get('data')) is list and len(row['data'])==2 and
              row['data'][1]=='base64' and type(row['data'][0]) is str and
              len(row['data'][0])<=(MAX_BASE64 if i==7 else 6000),'atomic-response-account-size')
        clean['accounts'].append({k:deepcopy(row[k]) for k in ('owner','executable','lamports','data') if k in row})
    for name in ('preTokenBalances','postTokenBalances'):
        check(type(v.get(name)) is list and len(v[name])==4,'atomic-response-token-count')
        clean[name]=[]
        for row in v[name]:
            check(type(row) is dict and type(row.get('uiTokenAmount')) is dict,'atomic-response-token-row')
            clean[name].append(dict({k:row[k] for k in ('accountIndex','mint','owner','programId') if k in row},
                uiTokenAmount={k:row['uiTokenAmount'][k] for k in ('amount','decimals') if k in row['uiTokenAmount']}))
    keys=decode_wire(params[0])[4]['transaction']['message']['accountKeys']
    clean['innerInstructions'],clean['innerEncoding']=normalize_trace(v.get('innerInstructions'),keys)
    return dict(state='received',result=dict(context=dict(slot=slot),value=clean))


class AtomicRpc(Client):
    METHODS=('getFeeForMessage','simulateTransaction','getGenesisHash')
    REQUEST_CAP=3
    def __init__(self,opener):super().__init__('devnet',opener)
    def request(self,method,params):
        r=super().request(method,params)
        if method!='simulateTransaction' or r['state']!='received':return r
        try:return sanitize(r,params)
        except (ValueError,KeyError,TypeError,IndexError,OverflowError,EvidenceError):
            self.calls[-1]['state']='invalid-atomic-simulation-response'
            return dict(state='invalid-atomic-simulation-response')


def collect(inputs,review,draft,*,transport,clock,deadline):
    check(type(transport) is AtomicTransport,'atomic-transport')
    fp=effects.fee_parameters(review,draft)
    started=clock();check(inputs['now_ms']<=started<deadline,'atomic-expired')
    rpc=AtomicRpc(transport);transport.arm_atomic_fee(fp)
    fee=rpc.request('getFeeForMessage',fp);fee_received=clock()
    check(started<=fee_received<deadline,'atomic-expired')
    slot,value=context_value(fee,fp[1]['minContextSlot'])
    check(integer(value,1) and value<=int(inputs['packet']['policy']['maxTotalFeeLamports']),'atomic-fee-unavailable')
    sp=effects.simulation_parameters(inputs,draft,slot);transport.arm_atomic_simulation(sp)
    sim_started=clock();check(fee_received<=sim_started<deadline,'atomic-expired')
    simulation=rpc.request('simulateTransaction',sp);sim_received=clock()
    check(sim_started<=sim_received<deadline,'atomic-expired')
    check(simulation.get('state')=='received','atomic-simulation-response-unavailable')
    genesis=rpc.request('getGenesisHash',[]);finished=clock()
    check(sim_received<=finished<deadline,'atomic-expired')
    check(genesis.get('state')=='received' and genesis.get('result')==GENESIS['devnet'],'atomic-cluster')
    return dict(feeParams=fp,fee=fee,simulationParams=sp,simulation=simulation,genesis=genesis,
        startedAtMs=started,feeReceivedAtMs=fee_received,simulationStartedAtMs=sim_started,
        simulationReceivedAtMs=sim_received,finishedAtMs=finished)
