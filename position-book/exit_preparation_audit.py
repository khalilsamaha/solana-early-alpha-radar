"""Read-only inspection of preserved exit preparation; never replacement authority."""
import os
import time
import admission_lifecycle as lifecycle
import fresh_signing
import restricted_exit_signer as backend
from contract import digest, uint
from core import check
from journal import read_only_journals

VERSION='exit-preparation-audit-1'
view=lifecycle.view


def base():
    return dict(format=VERSION,state='exit-preparation-audit-unavailable',coherent=False,
        phase=None,preparation=None,signing=None,backendMarkers=None,scopedAccounting=None,
        recordIdentity=None,stopRequested=None,capturedAtMs=None,elapsedMs=None,
        networkRequests=0,privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,
        databaseConnectionsReadOnly=True,sourceStateChanged=False,
        reservationsReleasedThisRun=False,replacementAuthorized=False,retryAllowed=False,
        executionApproved=False,nextCycleAuthorized=False,fundsAvailableForNewEntry=False,
        blockingReasons=[],limitations=[
            'Historical local evidence only; no live balances, blockhash or transaction status requested.',
            'Absent signing records and markers do not authorize replacing or retrying a preparation.',
            'Existing preparations, deadlines, STOP state and all reservations are preserved.',
            'Marker presence includes symlinks; marker contents and private keys are not opened.'])


@view.cycles.binding.operation
@fresh_signing.timing.signature_replay
def inspect(home,wallet,pool,*,clock=view.now,monotonic=time.monotonic):
    result=base();started=monotonic();wall=clock()
    try:
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            book=lifecycle.entry.submission._open(root,wallet,pool,clock)
            try:
                with lifecycle.admission_read_lock(book.j.path):
                    phase,_,amounts,_,ids,state=lifecycle.projection(book,root,wallet,pool,clock)
                    check(phase!='quarantined','exit-audit-quarantined')
                    prepared=lifecycle.preparation.saved(book,clock())
                    signed=lifecycle.signing.read(book,clock())
                    markers={key:os.path.lexists(book.j.path.parent/name) for key,name in
                        (('attemptPresent',backend.ATTEMPT),('acknowledgmentPresent',backend.ACK))}
                    stamp=clock();elapsed=(monotonic()-started)*1000
                    uint(stamp,2**53-1,'exit-audit-clock',minimum=wall)
                    check(0<=elapsed<=lifecycle.MAX_READ_MS,'exit-audit-read-deadline')
                    stop=view.cycles.c.submit.swap.stop(root) or state['state']=='stopped'
                    summary=None
                    if prepared is not None:
                        b=prepared['binding'];deadline=b['validUntilExclusiveMs']
                        summary=dict(recordSha256=digest(prepared),recordedAtMs=prepared['recordedAtMs'],
                            validUntilExclusiveMs=deadline,expired=stamp>=deadline,
                            remainingMs=max(0,deadline-stamp),expiredByMs=max(0,stamp-deadline),
                            quantityAtomic=b['quantityAtomic'],protectedInventoryAtomic=b['protectedInventoryAtomic'],
                            entryAccountingSha256=b['entryAccountingSha256'],messageSha256=b['messageSha256'])
                    label='exit-preparation-absent'
                    reasons=['replacement-not-implemented']
                    if signed is not None:
                        label='exit-signing-or-transport-recorded';reasons.append('signing-recorded')
                    elif any(markers.values()):
                        label='exit-artifact-inspection-required';reasons.append('backend-marker-present')
                    elif summary is not None:
                        label='expired-unsigned-exit-preserved' if summary['expired'] else 'unsigned-exit-preparation-preserved'
                    if stop:reasons.append('stop-present')
                    result.update(state=label,coherent=True,phase=phase,preparation=summary,
                        signing=dict(recorded=signed is not None,state=None if signed is None else signed['state']),
                        backendMarkers=markers,scopedAccounting=amounts,recordIdentity=ids,
                        stopRequested=stop,capturedAtMs=stamp,elapsedMs=round(elapsed,3),blockingReasons=reasons)
            finally:book.close()
    except view.ERRORS:
        result=base();result['blockingReasons']=['exit-preparation-evidence-unavailable']
    return result
