"""One-call signer-adapter dispatch and durable recovery, not a live key backend.

No default signer, sender, RPC transport, execution CLI, receipt application or
allocation release. Only an explicitly supplied in-process adapter can be called.
"""
from copy import deepcopy
import os
from pathlib import Path

import locked_admission as bridge
from pre_sign_admission import Admission, validate_policy, MAX_EVIDENCE_BYTES, encoded
from contract import digest, validate
from core import check, directory, sync_directory
from journal import read_only_journals

VERSION='durable-signer-handoff-1'
NAME='entry.admission.sqlite'


def storage(root, *, create=False):
    """One fixed sibling per canonical source directory, not caller-chosen files."""
    parent=root.parent/(root.name+'-entry-handoff-v1')
    if create and not os.path.lexists(parent):
        parent.mkdir(mode=0o700);sync_directory(root.parent)
    return directory(parent)/NAME


def public(book, calls=0):
    s=book.status()
    return dict(format=VERSION,state=s['state'],admission=s,
        accountingHandoffReady=bool(s['reservation'] and s['reservation'].get('accountingHandoffSha256'))
            and s['state'] in ('signed-recorded','stopped'),
        signerAdapterCallsThisRun=calls,networkRequestsByDispatcher=0,transactionsSentByDispatcher=0,
        liveKeyBackendConnected=False,liveSenderIntegrated=False,executionApproved=False,
        submissionObserved=False,receiptApplied=False,allocationTransferred=False,
        walletWideReservationsKnown=False,automaticResigningAllowed=False)


def request_for(book, now):
    state,_,_,_=book.read()
    check(state is not None and state['state']=='signing-unknown', 'handoff-boundary-required')
    request=deepcopy(state['signingRequest'])
    check(digest(request)==state['signingRequestSha256'], 'handoff-request-identity')
    check(state['signingBoundaryAtMs']<=now<state['validUntilExclusiveMs'], 'handoff-deadline')
    checked=validate(request['packet'],now_ms=now)
    check(checked['state']=='instruction-policy-match' and
          checked['wireMessageSha256']==state['messageSha256'], 'handoff-request-contract')
    return request


@bridge.view.cycles.binding.operation
def dispatch(home, wallet, pool, evidence, policy, *, signer_adapter, clock=bridge.view.now):
    """Trusted internal adapter seam. Nothing here is wired to production keys.

    The source lock covers both durable writes, the adapter call, acknowledgment
    verification and the same-ledger accounting outbox. Re-entry after a recorded
    boundary returns status, never another adapter call.
    """
    check(callable(signer_adapter),'explicit-signer-adapter-required')
    validate_policy(policy)
    check(len(encoded(evidence).encode())<=MAX_EVIDENCE_BYTES,'admission-evidence-cap')
    evidence=deepcopy(evidence);policy=deepcopy(policy)
    roles=policy['scope']['accounts']
    check(roles['wallet']==wallet and roles['pool']==pool,'handoff-source-scope')
    with bridge.view.cycles.c.source_lock(home,wallet) as root:
        return _dispatch_locked(root,wallet,pool,evidence,policy,signer_adapter=signer_adapter,clock=clock)


def _dispatch_locked(root,wallet,pool,evidence,policy,*,signer_adapter,clock):
    """Internal composition seam; caller owns source lock and validates policy/scope."""
    path=storage(root,create=True)
    book=Admission(path,policy,clock)
    try:
        if bridge.view.cycles.c.submit.swap.stop(root):
            book.stop();return public(book)
        existing=book.status()
        if existing['state'] not in ('empty','reserved'):return public(book)
        bridge._boundary_locked(root,wallet,pool,book,evidence,clock=clock,handoff=True)
        request=request_for(book,clock())
        if bridge.view.cycles.c.submit.swap.stop(root):
            book.stop();return public(book)
        # No automatic retry even if the callback raises, the process dies,
        # the response is lost, or validation/writing fails after this call.
        check(clock()<request['validUntilExclusiveMs'], 'handoff-deadline')
        with read_only_journals():
            signed=signer_adapter(deepcopy(request))
        book.record_signed(signed)
        if bridge.view.cycles.c.submit.swap.stop(root):book.stop()
        if book.status()['state'] in ('signed-recorded','stopped'):
            book.stage_accounting_handoff()
        return public(book,1)
    finally:book.close()

def recover(home, wallet, pool, *, signed_response=None, clock=bridge.view.now):
    """Observe/record an existing acknowledgment; there is no signer argument."""
    with bridge.view.cycles.c.source_lock(home,wallet) as root:
        book=Admission(storage(root),clock=clock)
        try:
            roles=book.policy['scope']['accounts']
            check(roles['wallet']==wallet and roles['pool']==pool,'handoff-source-scope')
            if bridge.view.cycles.c.submit.swap.stop(root):book.stop()
            if signed_response is not None:book.record_signed(signed_response)
            state=book.status()
            if state['state'] in ('signed-recorded','stopped') and state['reservation'].get('signedWireSha256'):
                book.stage_accounting_handoff()
            return public(book)
        finally:book.close()
