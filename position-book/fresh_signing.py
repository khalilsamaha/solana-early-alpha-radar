"""Internal fresh devnet collection-to-signer integration; no live CLI or sender.

The isolated unsigned rehearsal is never an input. Each attempt owns a fresh
collector result and a vacant fixed operational handoff slot. Unknown signing
outcomes stay held for acknowledgment recovery, never recollected or resigned.
"""
from copy import deepcopy
import subprocess
import entry_profile as profile

import admission_timing as timing
import signer_handoff as handoff
import restricted_signer as backend
from contract import uint, atomic
from core import check
from journal import read_only_journals

VERSION='fresh-signing-handoff-1'
view=timing.view
ERRORS=view.ERRORS+(subprocess.SubprocessError,)


def base():
    r=timing.base()
    r.update(format=VERSION,signerInvocationAttempts=0,signerAcknowledgmentValidated=False,
        handoff=None,automaticRetryAllowed=False,automaticResigningAllowed=False,
        originalDeadlineCheckedAtInvocation=False,completedWithinOriginalDeadline=False,
        collectionFreshnessDoesNotAuthorizeSubmission=True,
        recoveryRequired=False)
    r['limitations']=[
        'Internal controlled-devnet integration only; no live CLI, service wiring or sender.',
        'One original evidence deadline covers collection, admission and signer invocation.',
        'A signer timeout can hide a signature; preserve its attempt and acknowledgment for recovery.',
        'Signing after a durable boundary does not establish submission or wallet-wide solvency.',
        'The cooperating source lock does not prevent unrelated external wallet activity.',
        'No mainnet readiness, fill or profitability claim.']
    return r


def guard(root,clock,monotonic,started,deadline,minimum_wall,minimum_tick):
    now=clock();tick=monotonic()
    uint(now,2**53-1,'fresh-signing-clock',minimum=minimum_wall)
    check(minimum_tick<=tick<started+30,'fresh-signing-monotonic')
    check(now<deadline,'fresh-signing-expired')
    check(not view.cycles.c.submit.swap.stop(root),'fresh-signing-stopped')
    return now,tick


@view.cycles.binding.operation
@timing.signature_replay
def _run(home,wallet,pool,*,signer_adapter,maximum_exit_attempts,
         maximum_exit_fee_lamports,maximum_total_fee_lamports,
         opener=None,clock=view.now,monotonic=timing.time.monotonic):
    """Trusted internal adapter seam. The CLI does not expose it or raw inputs."""
    r=base();private=[];started=monotonic();wall=clock();slot_started=False
    try:
        check(callable(signer_adapter),'fresh-signing-adapter-required')
        uint(wall,2**53-1,'fresh-signing-clock',minimum=1)
        uint(maximum_exit_attempts,3,'fresh-signing-policy',minimum=1)
        fee=atomic(maximum_exit_fee_lamports,'fresh-signing-policy',positive=True)
        total=atomic(maximum_total_fee_lamports,'fresh-signing-policy',positive=True)
        check(fee<=10000 and total<=40000 and fee*maximum_exit_attempts<total,'fresh-signing-policy')
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            timing.vacant(root)
            check(not view.cycles.c.submit.swap.stop(root),'fresh-signing-stopped')
        with timing.phase(r,'fresh-entry-collection',clock,monotonic), profile.measure('entry-collection'):
            obs=timing.fresh_quote.observe(home,wallet,pool,opener=opener,clock=clock,monotonic=monotonic,
                simulate=True,assess_costs=True,refreshed_deployment=True,_evidence_sink=private.append)
            count=obs['networkRequests'];methods=obs['requestMethods']
            uint(count,20,'fresh-signing-request-evidence')
            check(type(methods) is list and len(methods)==count and all(x in timing.ALLOWED_METHODS for x in methods),
                  'fresh-signing-request-evidence')
            r.update(networkRequests=count,requestMethods=list(methods),collectionState=obs['state'],
                collectionStage=obs['stage'],collectionDiagnosticCode=obs.get('diagnosticCode'))
            check(obs['state']=='controlled-cost-observation-consistent' and len(private)==1,'fresh-signing-collection')
        evidence=private.pop()
        deadlines=[obs['costReadiness']['validUntilExclusiveMs'],obs['preflight']['validUntilExclusiveMs'],
                   obs['binding']['binding']['validUntilExclusiveMs']]
        for d in deadlines:uint(d,2**53-1,'fresh-signing-deadline',minimum=1)
        deadline=min(deadlines);r['originalDeadlineMs']=deadline
        # The durable request and independent child signer must enforce this same
        # original deadline, not only an outer Python callback check.
        check(deadline==deadlines[0],'fresh-signing-deadline-mismatch')
        profile.pin_deadline(deadline)
        policy=dict(format=timing.admission.VERSION+'-policy',scope=deepcopy(evidence['scope']),
            maximumExitAttempts=maximum_exit_attempts,maximumExitFeeLamports=maximum_exit_fee_lamports,
            maximumTotalFeeLamports=maximum_total_fee_lamports)
        handoff.validate_policy(policy)
        roles=policy['scope']['accounts']
        check(roles['wallet']==wallet and roles['pool']==pool,'handoff-source-scope')
        before,tick=guard(root,clock,monotonic,started,deadline,max(wall,r['lastMeasuredAtMs'],evidence['completedAtMs']),started)
        def invoke(request):
            check(r['signerInvocationAttempts']==0,'fresh-signing-duplicate')
            check(request['validUntilExclusiveMs']==deadline,'fresh-signing-deadline-mismatch')
            guard(root,clock,monotonic,started,deadline,before,tick)
            r.update(originalDeadlineCheckedAtInvocation=True,signerInvocationAttempts=1,
                signaturesCreated=None,privateKeyAccessed=None,recoveryRequired=True)
            # The durable signing boundary is already committed. No retry on
            # interruption, exceptions or an acknowledgment that arrives late.
            return signer_adapter(root,deepcopy(request))
        # dispatch owns the cooperating source lock through final rereads, all
        # durable boundaries, the independent backend and signed acknowledgment.
        # Recheck vacancy while holding that very lock to reject a competitor.
        with view.cycles.c.source_lock(home,wallet) as locked:
            timing.vacant(locked)
            guard(locked,clock,monotonic,started,deadline,before,tick)
            slot_started=True
            r.update(admissionLedgerCreated=None,databaseConnectionsReadOnly=False)
            with timing.phase(r,'admission-and-signing',clock,monotonic):
                result=handoff._dispatch_locked(locked,wallet,pool,evidence,policy,signer_adapter=invoke,clock=clock)
        r.update(handoff=result,state=result['state'],admissionLedgerCreated=True,
                 databaseConnectionsReadOnly=False)
        valid=result['accountingHandoffReady'] and result['state'] in ('signed-recorded','stopped')
        end=clock();elapsed=monotonic()-started
        uint(end,2**53-1,'fresh-signing-clock',minimum=r['lastMeasuredAtMs'])
        r.update(signerAcknowledgmentValidated=valid,
            signaturesCreated=(1 if valid else None) if r['signerInvocationAttempts'] else 0,
            privateKeyAccessed=None if r['signerInvocationAttempts'] else False,
            rawAdmissionValidationPassed=valid,recoveryRequired=not valid,
            completedAtMs=end,remainingMs=deadline-end,
            quoteAgeMs=end-evidence['costInputs']['price']['quote']['requestedAtMs'],
            completedWithinOriginalDeadline=end<deadline and 0<=elapsed<30,stage='complete')
    except ERRORS as exc:
        r.update(state='fresh-signing-inspection-required' if slot_started else 'unavailable',
            recoveryRequired=slot_started,diagnosticCode='fresh-signing-evidence-unavailable')
        allowed={'timing-existing-admission','fresh-signing-expired','fresh-signing-clock',
                 'fresh-signing-monotonic','fresh-signing-stopped','fresh-signing-deadline-mismatch'}
        if str(exc) in allowed:r['diagnosticCode']=str(exc)
        if str(exc)=='timing-existing-admission':r['recoveryRequired']=True
    finally:private.clear()
    return r


def prepare_and_sign(home,wallet,pool,*,allow_private_key_signing=False,**kwargs):
    """Internal opt-in only. No caller-supplied evidence, adapter or report input."""
    check(allow_private_key_signing is True,'explicit-private-key-opt-in-required')
    r=_run(home,wallet,pool,signer_adapter=backend._invoke,**kwargs)
    # Invocation does not prove a key was read or signature produced on failure.
    if r['signerAcknowledgmentValidated'] and r['signerInvocationAttempts']==1:r['privateKeyAccessed']=True
    return r


def recover(home,wallet,pool,*,clock=view.now):
    """Recover the existing private ack only; never collect, sign or send again."""
    return backend.recover(home,wallet,pool,clock=clock)
