"""Two independent raw-validated legs and an explicit fee-cap scenario.

This is observation plumbing, not a post-entry state transition or sender.
The internal raw handoff is never accepted from a public report or CLI input.
"""
from copy import deepcopy
import time
import fresh_quote
import cost_readiness
from core import check
from contract import digest, uint
from fresh_packet import scope_check
from swap_rehearsal import scope_for
from cpmm_quote import derive

VERSION = 'independent-paired-cost-observation-1'
ERRORS = {'pair-leg-evidence','pair-scope','pair-price','pair-order','pair-window',
          'pair-baseline','pair-quantity','pair-economic-inputs','pair-reservations','pair-slot-order'}


def policy(failed_exit_attempts):
    uint(failed_exit_attempts,2,'failed-exit-attempts')
    return dict(format='independent-leg-fee-scenario-1',additionalFailedEntryAttempts=0,
                additionalFailedExitAttempts=failed_exit_attempts,maximumObservationWindowMs=60000,
                createsReservations=False,authorizesRetries=False)


def assess(entry, reverse, *, baseline, failed_exit_attempts):
    """Recompute raw costs at each leg's own completion time, never refresh old clocks."""
    scenario=policy(failed_exit_attempts)
    out=dict(format=VERSION,state='unavailable',reasons=[],scenario=scenario,calculation=None,
        executionApproved=False,signingApproved=False,roundTripFundingEstablished=False,
        postEntryPoolObserved=False,actualExecutionObserved=False,currentFundingVerified=False,
        netProfit=None,sourceEquivalenceVerified=False,mainnetSupported=False,
        reservationCreated=False,authorizesRetries=False,
        limitations=[
            'Two independent current-state simulations; exit uses existing inventory, not entry proceeds.',
            'Each leg retains its own ten-second deadline; combining observations does not refresh it.',
            'Fee scenario uses the lower of two historical native-spendable observations, not atomic current funding.',
            'Additional failed-exit allowance is a scenario only; no retry or spending reservation is created.',
            'No observed post-entry pool transition, complete execution-cost budget, native valuation or profit.'])
    try:out.update(_assess(entry,reverse,baseline,scenario))
    except (ValueError,KeyError,TypeError,IndexError,OverflowError) as exc:
        out['reasons']=[str(exc) if str(exc) in ERRORS else 'pair-evidence-invalid']
    return out


def _leg(e,baseline):
    args=deepcopy(e['costInputs']);stamp=e['completedAtMs']
    uint(stamp,2**53-1,'pair-order')
    check(args['baseline']==baseline,'pair-baseline')
    args.update(baseline=deepcopy(baseline),now_ms=stamp)
    cost=cost_readiness.assess(**args)
    check(cost['state']=='single-leg-cost-evidence-consistent','pair-leg-evidence')
    scope_check(e['scope']);scope_check(e['entryScope'])
    check(scope_for(args['packet']['policy'])==e['scope'],'pair-scope')
    computed=derive(e['initialPool'],e['scope'],slippage_bps=100,now_ms=stamp)
    check(computed==args['price'],'pair-price')
    return cost,args['price'],args['reservations']


def _assess(entry,reverse,baseline,scenario):
    ec,ep,er=_leg(entry,baseline);xc,xp,xr=_leg(reverse,baseline)
    eq,xq=ep['quote'],xp['quote']
    # Reference scope comes from the same fixed closed local cycles in each call.
    check(entry['entryScope']==reverse['entryScope'],'pair-scope')
    reference=derive(reverse['initialPool'],reverse['entryScope'],slippage_bps=100,
                     now_ms=reverse['completedAtMs'])
    check(ep['economicInputs']==reference['economicInputs'],'pair-economic-inputs')
    expected=deepcopy(entry['scope']['accounts'])
    for left,right in (('source','destination'),('inputMint','outputMint'),('inputVault','outputVault')):
        expected[left],expected[right]=expected[right],expected[left]
    check(reverse['scope']['accounts']==expected,'pair-scope')
    check(eq['outAmount']==reference['quote']['outAmount']==xq['inAmount'],'pair-quantity')
    check(eq['receivedAtMs']<=entry['completedAtMs']<=xq['requestedAtMs']
          <=xq['receivedAtMs']<=reverse['completedAtMs'],'pair-order')
    check(0<=reverse['completedAtMs']-eq['requestedAtMs']<=scenario['maximumObservationWindowMs'],'pair-window')
    check(ec['evidence']['simulationContextSlot']<=xq['contextSlot'],'pair-slot-order')
    for name in ('wallet','pool','phase','nativeHeldLamports','tokenAccounts','ledgerHeadSha256','cycleBindingSha256'):
        check(er[name]==xr[name],'pair-reservations')
    e,x=ec['calculation'],xc['calculation']
    entry_cap=int(e['networkFeeCapLamports']);exit_cap=int(x['networkFeeCapLamports'])
    failed_cap=scenario['additionalFailedExitAttempts']*exit_cap
    budget=entry_cap+exit_cap+failed_cap
    available=min(int(e['nativeSpendableLamports']),int(x['nativeSpendableLamports']))
    return dict(state='independent-leg-costs-consistent',
        entryCostEvidence=ec,reverseCostEvidence=xc,
        identities=dict(entryMessageSha256=ec['evidence']['messageSha256'],
            reverseMessageSha256=xc['evidence']['messageSha256'],
            entryQuoteSha256=digest(eq),reverseQuoteSha256=digest(xq),
            entryEconomicInputsSha256=ep['economicInputsSha256'],
            ledgerHeadSha256=er['ledgerHeadSha256'],cycleBindingSha256=er['cycleBindingSha256']),
        observationClocks=dict(entryCompletedAtMs=entry['completedAtMs'],
            entryValidUntilExclusiveMs=ec['validUntilExclusiveMs'],reverseCompletedAtMs=reverse['completedAtMs'],
            reverseValidUntilExclusiveMs=xc['validUntilExclusiveMs'],
            entryExpiredAtPairCompletion=reverse['completedAtMs']>=ec['validUntilExclusiveMs'],
            state='historical-independent-observations'),
        calculation=dict(entryInputAtomic=eq['inAmount'],entrySimulatedOutputAtomic=e['simulatedOutputAtomic'],
            reverseInputAtomic=xq['inAmount'],reverseSimulatedOutputAtomic=x['simulatedOutputAtomic'],
            entryObservedFeeLamports=e['observedNetworkFeeLamports'],reverseObservedFeeLamports=x['observedNetworkFeeLamports'],
            observedIndependentFeeSumLamports=str(int(e['observedNetworkFeeLamports'])+int(x['observedNetworkFeeLamports'])),
            entryFeeCapLamports=str(entry_cap),reverseFeeCapLamports=str(exit_cap),
            additionalFailedExitFeeAllowanceLamports=str(failed_cap),modelledFeeCapBudgetLamports=str(budget),
            lowerObservedNativeSpendableLamports=str(available),modelledFeeCapBudgetCovered=available>=budget,
            shortfallForModelledFeeCapsLamports=str(max(0,budget-available)),
            actualNativeDebitLamports='0',completeExecutionCostBudget=False,netProfit=None))


def observe(home,wallet,pool,*,failed_exit_attempts,refreshed_deployment=False,
            opener=None,clock=fresh_quote.view.now,monotonic=time.monotonic):
    scenario=policy(failed_exit_attempts)  # Reject invalid counts before local or RPC access.
    check(type(refreshed_deployment) is bool,'pair-baseline')
    baseline=deepcopy(fresh_quote.preflight.BASELINE)
    if refreshed_deployment:
        from simulation_baseline import BASELINE
        baseline=deepcopy(BASELINE)
    result=dict(format=VERSION,state='unavailable',stage='entry',reasons=[],scenario=scenario,
        legs={},pairedAssessment=None,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        privateKeyAccessed=False,sourceStateChanged=False,executionApproved=False,
        frozenStudyChanged=False,mainnetSupported=False)
    raw=[];started=monotonic()
    try:
        for name in ('entry','reverse'):
            result['stage']=name
            check(0<=monotonic()-started<60,'pair-window')
            evidence=[]
            leg=fresh_quote.observe(home,wallet,pool,simulate=True,assess_costs=True,
                reverse_reference=name=='reverse',refreshed_deployment=refreshed_deployment,
                opener=opener,clock=clock,monotonic=monotonic,_evidence_sink=evidence.append)
            result['legs'][name]=leg;result['networkRequests']+=leg['networkRequests']
            expected=('controlled-cost-observation-consistent' if name=='entry' else
                      'controlled-reverse-cost-observation-consistent')
            check(leg['state']==expected and len(evidence)==1,'pair-leg-evidence')
            raw.append(evidence[0])
        result['stage']='paired-assessment'
        assessed=assess(*raw,baseline=baseline,failed_exit_attempts=failed_exit_attempts)
        result['pairedAssessment']=assessed
        check(assessed['state']=='independent-leg-costs-consistent','pair-leg-evidence')
        finished=clock();uint(finished,2**53-1,'pair-order')
        check(raw[1]['completedAtMs']<=finished,'pair-order')
        check(finished-raw[0]['costInputs']['price']['quote']['requestedAtMs']<=60000
              and 0<=monotonic()-started<60,'pair-window')
        result.update(state='independent-paired-cost-observation-consistent',stage='complete',
            reviewedAtMs=finished,entryQuoteExpiredAtReport=finished>=assessed['entryCostEvidence']['validUntilExclusiveMs'])
    except (ValueError,KeyError,TypeError,IndexError,OverflowError) as exc:
        result['reasons']=[str(exc) if str(exc) in ERRORS else 'pair-evidence-invalid']
    finally:raw.clear()
    return result
