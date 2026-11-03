"""One read-only live entry/admission timing rehearsal. No durable admission or sender."""
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import math
import os
import time

import fresh_quote
import wire
import pre_sign_admission as admission
import locked_admission as bridge
from contract import atomic,digest,uint
from core import check
from journal import read_only_journals

VERSION='admission-timing-1'
OPTIMIZATION='exact-signature-replay-1'
view=bridge.view
ALLOWED_METHODS=fresh_quote.METHODS|{'simulateTransaction'}
DIAGNOSTICS={'timing-existing-admission','timing-policy-limits','timing-collector-unavailable',
    'timing-raw-handoff','timing-source-clock','timing-original-deadline','timing-clock-regression',
    'timing-monotonic-budget','timing-stop','timing-request-evidence','admission-source-changed',
    'admission-source-scope','admission-native-budget','admission-total-budget',
    'admission-raw-evidence','admission-pinned-baseline','admission-price','admission-pool-changed'}


def base():
    return dict(format=VERSION,state='unavailable',stage='policy',diagnosticCode=None,
        network='devnet',networkRequests=0,requestMethods=[],timings=[],
        collectionState=None,collectionStage=None,collectionDiagnosticCode=None,
        originalDeadlineMs=None,completedAtMs=None,lastMeasuredAtMs=None,remainingMs=None,quoteAgeMs=None,
        rawAdmissionValidationPassed=False,sourceIdentity=None,assessment=None,
        signaturesCreated=0,transactionsSent=0,privateKeyAccessed=False,
        sourceStateChanged=False,databaseConnectionsReadOnly=True,
        admissionLedgerCreated=False,productionReservationsCreated=False,
        signingApproved=False,executionApproved=False,nextCycleAuthorized=False,
        walletWideReservationsKnown=False,roundTripFundingEstablished=False,runtimeIntegrated=False,
        limitations=['One unsigned entry observation followed by raw admission validation; no durable reservation.',
            'Original evidence expiry is never refreshed; failures are retained and not retried.',
            'Measured headroom excludes disk commit, private signing, submission and future exit work.',
            'The original closed cycles remain unchanged; no new allocation or current wallet-wide solvency is established.',
            'Devnet timing is not mainnet execution or profitability evidence.'])


def vacant(root):
    # Even an empty/partial prior handoff requires separate recovery; do not read,
    # reset, overwrite or present it as a newly available admission slot.
    check(not os.path.lexists(root.parent/(root.name+'-entry-handoff-v1')),'timing-existing-admission')


@contextmanager
def phase(result,name,clock,monotonic):
    result['stage']=name;wall=clock();start=monotonic()
    uint(wall,2**53-1,'timing-clock-regression',minimum=result['lastMeasuredAtMs'] or 1)
    try:yield
    finally:
        end=clock();elapsed=(monotonic()-start)*1000
        result['timings'].append(dict(stage=name,startedAtMs=wall,finishedAtMs=end,
            elapsedMs=round(elapsed,3) if math.isfinite(elapsed) and elapsed>=0 else None))
        uint(end,2**53-1,'timing-clock-regression',minimum=wall)
        result['lastMeasuredAtMs']=end
        check(math.isfinite(elapsed) and elapsed>=0,'timing-monotonic-budget')


def signature_replay(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        reuse = kwargs.pop('_reuse_signature_scope', False)
        # Default callers retain an independent cache, including recovery.
        scope = (wire.signature_verification_scope(reuse_current=True) if reuse is True
                 else wire.signature_verification_scope())
        check(type(reuse) is bool, 'signature-scope-mode')
        with scope as statistics:
            result = fn(*args, **kwargs)
            result['signatureVerification'] = statistics()
            result['timingOptimization'] = OPTIMIZATION
            return result
    return wrapped


@view.cycles.binding.operation
@signature_replay
def observe(home,wallet,pool,*,maximum_exit_attempts,maximum_exit_fee_lamports,
            maximum_total_fee_lamports,opener=None,clock=view.now,monotonic=time.monotonic):
    r=base();started=monotonic();wall=clock();private=[]
    try:
        uint(wall,2**53-1,'timing-clock-regression',minimum=1)
        uint(maximum_exit_attempts,3,'timing-policy-limits',minimum=1)
        exit_fee=atomic(maximum_exit_fee_lamports,'timing-policy-limits',positive=True)
        total=atomic(maximum_total_fee_lamports,'timing-policy-limits',positive=True)
        check(exit_fee<=10000 and total<=40000 and exit_fee*maximum_exit_attempts<total,'timing-policy-limits')
        with phase(r,'local-slot-check',clock,monotonic):
            with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
                vacant(root);check(not view.cycles.c.submit.swap.stop(root),'timing-stop')
        with phase(r,'fresh-entry-collection',clock,monotonic):
            observed=fresh_quote.observe(home,wallet,pool,opener=opener,clock=clock,monotonic=monotonic,
                simulate=True,assess_costs=True,refreshed_deployment=True,_evidence_sink=private.append)
            count=observed['networkRequests'];methods=observed['requestMethods']
            uint(count,20,'timing-request-evidence')
            check(type(methods) is list and len(methods)==count and all(v in ALLOWED_METHODS for v in methods),'timing-request-evidence')
            r.update(networkRequests=count,requestMethods=list(methods),collectionState=observed['state'],
                collectionStage=observed['stage'],collectionDiagnosticCode=observed.get('diagnosticCode'))
            check(observed['state']=='controlled-cost-observation-consistent','timing-collector-unavailable')
            check(len(private)==1,'timing-raw-handoff')
        e=private.pop();q=e['costInputs']['price']['quote']
        deadlines=[observed['costReadiness']['validUntilExclusiveMs'],
            observed['preflight']['validUntilExclusiveMs'],observed['binding']['binding']['validUntilExclusiveMs']]
        for value in deadlines:uint(value,2**53-1,'timing-original-deadline',minimum=1)
        deadline=min(deadlines)
        r['originalDeadlineMs']=deadline
        policy=dict(format=admission.VERSION+'-policy',scope=deepcopy(e['scope']),
            maximumExitAttempts=maximum_exit_attempts,maximumExitFeeLamports=maximum_exit_fee_lamports,
            maximumTotalFeeLamports=maximum_total_fee_lamports)
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            vacant(root);check(not view.cycles.c.submit.swap.stop(root),'timing-stop')
            with phase(r,'locked-source-before',clock,monotonic):
                before=view.read_locked(root,wallet,pool,clock)
                bridge.same(before,e['costInputs']['reservations'],wallet,pool)
                check(e['completedAtMs']<=before['readStartedAtMs']<=before['observedAtMs']<=clock(),'timing-source-clock')
            with phase(r,'raw-admission-validation',clock,monotonic):
                check(clock()<deadline,'timing-original-deadline')
                checked=admission.review(e,policy,clock())
                check(checked['validUntilExclusiveMs']==deadlines[0],'timing-original-deadline')
                check(clock()<deadline,'timing-original-deadline')
            with phase(r,'locked-source-after',clock,monotonic):
                after=view.read_locked(root,wallet,pool,clock);bridge.same(after,before,wallet,pool)
                check(before['observedAtMs']<=after['readStartedAtMs']<=after['observedAtMs']<=clock(),'timing-source-clock')
                vacant(root);check(not view.cycles.c.submit.swap.stop(root),'timing-stop')
            finished=clock();elapsed=monotonic()-started
            r.update(completedAtMs=finished,remainingMs=deadline-finished,quoteAgeMs=finished-q['requestedAtMs'])
            uint(finished,2**53-1,'timing-clock-regression',minimum=max(wall,r['lastMeasuredAtMs'] or wall))
            check(math.isfinite(elapsed) and 0<=elapsed<30,'timing-monotonic-budget')
            check(after['observedAtMs']<=finished<deadline,'timing-original-deadline')
            r.update(state='entry-admission-timing-consistent',stage='complete',rawAdmissionValidationPassed=True,
                sourceIdentity=dict(ledgerHeadSha256=after['ledgerHeadSha256'],cycleBindingSha256=after['cycleBindingSha256']),
                assessment=dict(evidenceSha256=checked['evidenceSha256'],policySha256=digest(policy),
                    messageSha256=checked['messageSha256'],principalAtomic=checked['reservedPrincipalAtomic'],
                    projectedFeeCommitmentLamports=checked['reservedFeeLamports'],maximumExitAttempts=maximum_exit_attempts,
                    basis='validated-projection-no-reservation-created'))
    except view.ERRORS as exc:
        r['diagnosticCode']=str(exc) if str(exc) in DIAGNOSTICS else 'timing-evidence-unavailable'
    finally:
        if r['remainingMs'] is None and r['originalDeadlineMs'] is not None and r['lastMeasuredAtMs'] is not None:
            r['remainingMs']=r['originalDeadlineMs']-r['lastMeasuredAtMs']
        private.clear()
    return r
