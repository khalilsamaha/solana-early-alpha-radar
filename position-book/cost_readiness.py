"""Recompute single-leg cost evidence; no exported summary is execution authority."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import preflight
import quote_binding
import unsigned_simulation
from core import check
from contract import digest

# The economic calculator and instruction validator both use contract.py.
# Load the pure economic module by its fixed path without changing sys.path or
# replacing the already loaded instruction validator.
_spec = importlib.util.spec_from_file_location('radar_execution_cost_contract',
    Path(__file__).resolve().parents[1] / 'execution-cost' / 'contract.py')
cost = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cost)
VERSION = 'controlled-single-leg-cost-readiness-1'


def assess(packet, capture, price, simulation_item, reservations, *, baseline,
           simulation_started, simulation_received, simulation_finished, now_ms):
    """Internal raw-evidence seam. Caller must hold lock and replay local journals.

No report-input CLI exists. All account/message/fee/effect reviews are recomputed;
local reservation provenance comes from the locked observer, not this pure function.
"""
    result = dict(format=VERSION, state='unavailable', reasons=[], calculation=None,
                  network='devnet', executionApproved=False, signingApproved=False,
                  nextCycleAuthorized=False, mainnetSupported=False,
                  measuredNetProfit=False, actualExecutionObserved=False,
                  walletWideReservationsKnown=False, sourceEquivalenceVerified=False,
                  economics=dict(state='unavailable', calculation=None,
                      reasons=['controlled-devnet-assets-not-usdc-economics',
                               'validated-exit-leg-absent','native-valuation-not-provided']),
                  networkRequests=0, signaturesCreated=0, transactionsSent=0)
    try:
        result.update(_assess(packet,capture,price,simulation_item,reservations,
            baseline=baseline,simulation_started=simulation_started,
            simulation_received=simulation_received,simulation_finished=simulation_finished,now_ms=now_ms))
    except (ValueError, TypeError, KeyError, IndexError, OverflowError):
        # No raw provider text or arbitrary local error gets into a public report.
        result['reasons']=['single-leg-cost-evidence-rejected']
    return result


def _assess(packet,capture,price,item,r,*,baseline,simulation_started,
            simulation_received,simulation_finished,now_ms):
    for value in (simulation_started,simulation_received,simulation_finished,now_ms):
        cost.integer(value,cost.MAX_CLOCK,'cost-clock')
    check(capture['packet']==packet,'cost-packet-binding')
    checked=preflight._review(capture,deepcopy(baseline),now_ms)
    check(checked['state']=='preflight-evidence-consistent','cost-preflight')
    raw,_=preflight.split_capture(capture)
    q=price['quote']
    cost.integer(r['readStartedAtMs'],cost.MAX_CLOCK,'reservation-clock')
    cost.integer(r['observedAtMs'],cost.MAX_CLOCK,'reservation-clock')
    check(capture['finishedAtMs']<=simulation_started<=simulation_received<=simulation_finished
          <=r['readStartedAtMs']<=r['observedAtMs']<=now_ms,'cost-observation-order')
    check(r['phase']=='closed' and r['wallet']==q['wallet'] and r['pool']==q['pool'],
          'cost-reservation-scope')
    for name in ('ledgerHeadSha256','cycleBindingSha256'):
        v=r[name]
        check(type(v) is str and len(v)==64 and all(c in '0123456789abcdef' for c in v),'cost-ledger-identity')
    token=[v for v in r['tokenAccounts'] if v['account']==q['source'] and v['mint']==q['inputMint']]
    check(len(token)==1,'cost-token-reservation')
    projected=dict(wallet=q['wallet'],source=q['source'],inputMint=q['inputMint'],
        otherTokenAtomic=token[0]['heldAtomic'],otherNativeLamports=r['nativeHeldLamports'],asOfMs=r['observedAtMs'])
    binding=quote_binding._review(dict(format=quote_binding.VERSION,quote=q,capture=raw,
        reservations=projected,maxSlippageBps=100),now_ms=now_ms,current_local_reservations=True)
    check(binding['state']=='declared-quote-state-consistent','cost-binding')
    effects=unsigned_simulation.review(packet,capture,price,item,now_ms=now_ms)
    b=binding['binding']
    check(effects['messageSha256']==b['messageSha256']==checked['wireMessageSha256'] and
          effects['preflightCaptureSha256']==checked['captureSha256'] and
          effects['quoteSha256']==b['quoteSha256'],'cost-evidence-binding')
    deadline=min(checked['validUntilExclusiveMs'],b['validUntilExclusiveMs'])
    check(now_ms<deadline,'cost-expired')
    cap=cost.atomic(b['totalFeeCapLamports'],'cost-cap',positive=True)
    observed=cost.atomic(b['rpcMessageFeeLamports'],'cost-message-fee',positive=True)
    simulated=cost.atomic(effects['feeLamports'],'cost-simulated-fee',positive=True)
    priority=cost.atomic(b['priorityIncludedLamports'],'cost-priority')
    native=cost.atomic(b['nativeSpendableLamports'],'cost-native')
    tokens=cost.atomic(b['tokenSpendableAtomic'],'cost-token')
    amount=cost.atomic(q['inAmount'],'cost-input',positive=True)
    check(priority<=observed==simulated<=cap<=native and amount<=tokens,'cost-funding')
    check(b['accountCreationInstructions']==0 and b['newAccountRentDebitLamports']=='0','cost-account-funding')
    # Only CU-limit, CU-price and exact swap instructions are accepted by the
    # validator. Simulation permits only the exact native network fee debit.
    return dict(state='single-leg-cost-evidence-consistent',reasons=[],evaluatedAtMs=now_ms,
        validUntilExclusiveMs=deadline,
        evidence=dict(messageSha256=b['messageSha256'],quoteSha256=b['quoteSha256'],
            preflightCaptureSha256=checked['captureSha256'],simulationEvidenceSha256=effects['evidenceSha256'],
            baselineSha256=checked['baselineSha256'],reservationSha256=digest(projected),
            ledgerHeadSha256=r['ledgerHeadSha256'],cycleBindingSha256=r['cycleBindingSha256'],
            quoteContextSlot=q['contextSlot'],accountContextSlot=checked['snapshotSlot'],
            simulationContextSlot=effects['simulationSlot']),
        calculation=dict(inputAtomic=q['inAmount'],quotedOutputAtomic=q['outAmount'],
            simulatedOutputAtomic=effects['simulatedOutputAtomic'],minimumOutputAtomic=q['minimumOutAmount'],
            inputMint=q['inputMint'],outputMint=q['outputMint'],
            observedNetworkFeeLamports=str(observed),simulatedNetworkFeeLamports=str(simulated),
            networkFeeCapLamports=str(cap),priorityIncludedLamports=str(priority),
            separateTipLamports='0',newAccountRentDebitLamports='0',
            nativeSpendableLamports=str(native),requiredNativeForThisLegLamports=str(cap),
            nativeRemainingAfterCapLamports=str(native-cap),feeCapHeadroomLamports=str(cap-observed),
            tokenSpendableAtomic=str(tokens),tokenRemainingAfterInputAtomic=str(tokens-amount),
            simulatedNativeDebitLamports=str(simulated),actualNativeDebitLamports='0',
            exitFeeBudgetLamports=None,failedAttemptBudgetLamports=None),
        limitations=[
            'One controlled direct devnet swap only; no economic comparison between different token units.',
            'Network cap includes priority; embedded swap fees are reflected in output, not added again.',
            'Zero separate tip and new rent apply only to this exact validated and simulated message.',
            'Exit and failed-attempt budgets are unknown; no round-trip reserve or profitability pass.',
            'Local reservations were supplied by the locked reader; external wallet activity is not locked.',
            'No signing, sending, new durable spending reservation or reuse as an execution permit.'])
