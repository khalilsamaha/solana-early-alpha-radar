"""Exact reverse-message fee observation and conditional cap arithmetic, no sender."""
import base64
from copy import deepcopy
import projected_exit
from contract import decode_wire, digest, U64
from core import check, context_value
from state import integer
from recorded_capture import Client, GENESIS

VERSION='projected-exit-fee-1'


def parameters(inputs, request, draft):
    reviewed=projected_exit.assess(inputs,request,draft)
    check(reviewed['state']=='projected-reverse-message-consistent','exit-fee-draft')
    _,msg,_,_,_=decode_wire(draft['unsignedTransactionBase64'])
    slot=inputs['simulation_item']['result']['context']['slot']
    return [base64.b64encode(msg).decode(),dict(commitment='finalized',minContextSlot=slot)]


class FeeRpc(Client):
    METHODS=('getFeeForMessage','getGenesisHash')
    REQUEST_CAP=2
    def __init__(self,opener):super().__init__('devnet',opener)


def collect(inputs, request, draft, *, transport, clock, deadline):
    from post_entry_simulation import FeeTransport
    check(type(transport) is FeeTransport,'exit-fee-transport')
    params=parameters(inputs,request,draft)
    start=clock();check(inputs['now_ms']<=start<deadline,'exit-fee-expired')
    transport.arm_fee(params)
    rpc=FeeRpc(transport)
    fee=rpc.request('getFeeForMessage',params)
    received=clock();check(start<=received<deadline,'exit-fee-expired')
    # Stop before another request for null/invalid/over-cap fees.
    slot,value=context_value(fee,params[1]['minContextSlot'])
    check(integer(value,1) and value<=int(draft['scope']['maxTotalFeeLamports']),'exit-fee-invalid')
    genesis=rpc.request('getGenesisHash',[])
    finished=clock();check(received<=finished<deadline,'exit-fee-expired')
    check(genesis.get('state')=='received' and genesis.get('result')==GENESIS['devnet'],'exit-fee-cluster')
    return dict(params=params,fee=fee,genesis=genesis,startedAtMs=start,receivedAtMs=received,finishedAtMs=finished)


def assess(inputs,request,draft,evidence):
    result=dict(format=VERSION,state='unavailable',reasons=[],calculation=None,evidence=None,
        exitFeeVerified=False,conditionalCapCoverage=False,liveCollectorVerified=False,
        signingApproved=False,executionApproved=False,actualEntryExecuted=False,
        exitSimulationVerified=False,roundTripFundingEstablished=False,walletWideReservationsKnown=False,
        failedAttemptBudgetLamports=None,netProfit=None,mainnetSupported=False,
        signaturesCreated=0,transactionsSent=0,
        limitations=[
            'Fee belongs to the exact reverse draft at the reported RPC context, not a future execution.',
            'Conditional two-leg caps assume unchanged balances and only the known controlled reservations.',
            'No failed-attempt budget, external wallet lock, durable reservation or complete round-trip funding.',
            'Simulated proceeds are not committed inventory; no exit simulation, signing, send or net-profit claim.'])
    try:result.update(_assess(inputs,request,draft,evidence))
    except (ValueError,KeyError,TypeError,IndexError,OverflowError):result['reasons']=['projected-exit-fee-rejected']
    return result


def _assess(inputs,request,draft,e):
    params=parameters(inputs,request,draft)
    check(type(e) is dict and set(e)=={'params','fee','genesis','startedAtMs','receivedAtMs','finishedAtMs'},'exit-fee-schema')
    check(e['params']==params,'exit-fee-request')
    times=[e[k] for k in ('startedAtMs','receivedAtMs','finishedAtMs')]
    check(all(integer(t) for t in times) and inputs['simulation_finished']<=times[0]<=times[1]<=times[2]<=inputs['now_ms'],'exit-fee-clock')
    slot,fee=context_value(e['fee'],params[1]['minContextSlot'])
    check(integer(fee,1) and fee<=U64,'exit-fee-value')
    check(e['genesis'].get('state')=='received' and e['genesis'].get('result')==GENESIS['devnet'],'exit-fee-cluster')
    parent=projected_exit.post_entry.assess(inputs,request)
    check(parent['state']=='simulated-post-entry-projection-consistent','exit-fee-parent')
    entry=parent['entryFeeEvidence']
    entry_cap=int(entry['networkFeeCapLamports']);exit_cap=int(draft['scope']['maxTotalFeeLamports'])
    native=int(entry['nativeSpendableLamports']);total=entry_cap+exit_cap
    check(fee<=exit_cap and total<=U64 and native>=total,'exit-fee-cap-coverage')
    observed=int(entry['observedNetworkFeeLamports'])+fee
    check(observed<=total,'exit-fee-total')
    msg=projected_exit.assess(inputs,request,draft)['binding']
    return dict(state='projected-exit-fee-consistent',exitFeeVerified=True,conditionalCapCoverage=True,
        calculation=dict(entryObservedFeeLamports=entry['observedNetworkFeeLamports'],
            exitObservedFeeLamports=str(fee),observedTwoLegFeesLamports=str(observed),
            entryCapLamports=str(entry_cap),exitCapLamports=str(exit_cap),
            conditionalTwoLegCapLamports=str(total),nativeSpendableLamports=str(native),
            nativeRemainingAfterBothCapsLamports=str(native-total),
            priorityIncludedLamports='0',separateTipLamports='0',newAccountRentDebitLamports='0',
            acquiredInputAtomic=msg['inputAtomic'],projectedOutputAtomic=msg['projectedOutputAtomic'],
            actualNativeDebitLamports='0'),
        evidence=dict(requestParametersSha256=digest(params),feeResponseSha256=digest(e['fee']),
            draftSha256=digest(draft),messageSha256=msg['messageSha256'],
            parentSimulationSha256=msg['parentSimulationSha256'],parentProjectionSha256=msg['parentProjectionSha256'],
            feeContextSlot=slot,simulationContextSlot=params[1]['minContextSlot'],
            startedAtMs=times[0],receivedAtMs=times[1],finishedAtMs=times[2],reviewedAtMs=inputs['now_ms']))
