"""Internal fresh successor collection/persistence/key handoff; no sender or live CLI.

One call creates one candidate at most. An existing candidate is never refreshed
or automatically signed, even if its creation response was lost.
"""
import os
import subprocess
from pathlib import Path
import time

import retired_successor_collection as collection
import restricted_successor_signer as backend
import encoding_replay
import admission_history_replay
import canonical_replay
import serialization_replay
from core import check
from journal import read_only_journals

VERSION='successor-signing-integration-1'
handoff=backend.handoff
successor=handoff.successor
view=handoff.view
CODES=set(collection.CODES)|{'successor-key-opt-in-required','successor-prepare-opt-in-required',
    'successor-key-slot-occupied','successor-integration-clock','successor-integration-budget',
    'successor-signing-expired','successor-signing-expired-or-stopped',
    'successor-expired-before-commit','restricted-successor-signer-refused',
    'successor-integration-expired','successor-integration-ack-required',
    'successor-backend-request-mismatch','successor-backend-candidate-mismatch',
    'successor-backend-boundary-mismatch'}


@serialization_replay.operation
@canonical_replay.operation
@view.cycles.binding.operation
@successor.history.fresh_signing.timing.signature_replay
@encoding_replay.operation
@admission_history_replay.operation
def _run(home,wallet,pool,expected,expected_retirement,*,
                  allow_unsigned_successor=False,allow_private_key_signing=False,
                  clock=view.now,monotonic=time.monotonic,_expiry_opener=None,_quote_opener=None):
    check(allow_unsigned_successor is True,'successor-prepare-opt-in-required')
    check(allow_private_key_signing is True,'successor-key-opt-in-required')
    successor.replan.identity(expected);successor.replan.identity(expected_retirement)
    started=monotonic();last_tick=started;last_wall=clock();root=Path(home).absolute();producer=None
    r=dict(format=VERSION,state='successor-signing-review-required',stage='local-replay',diagnosticCode=None,
        preparationCreatedThisRun=False,successorSha256=None,originalDeadlineMs=None,
        signerInvocationAttempts=0,signerAcknowledgmentValidated=False,
        completedWithinOriginalDeadline=False,completedAtMs=None,deadlineHeadroomMs=None,
        privateKeyAccessedThisRun=False,signatureCreatedThisRun=False,
        requestMethods=[],collectionRequests=0,timing={},transactionsSent=0,
        oldAttemptStillRetired=True,retiredFeeExposureHeld=True,additionalFeeReservationLamports='0',
        reservationsReleasedThisRun=False,automaticResigningAllowed=False,automaticRefreshAllowed=False,
        scannerRuntimeChanged=False,executionApproved=False,validForSubmission=False)
    def guard():
        nonlocal last_wall,last_tick
        wall=clock();tick=monotonic()
        check(wall>=last_wall and tick>=last_tick,'successor-integration-clock')
        check(0<=tick-started<=120,'successor-integration-budget')
        if r['originalDeadlineMs'] is not None:check(wall<r['originalDeadlineMs'],'successor-integration-expired')
        check(not view.cycles.c.submit.swap.stop(root),'successor-stopped')
        last_wall=wall;last_tick=tick
        return wall
    def produce(ctx):
        nonlocal producer
        guard()
        with read_only_journals():
            b=handoff.preparation.entry.submission._open(root,wallet,pool,clock)
            try:
                producer=collection.Collector(root,b,wallet,pool,collection.retirement.row(b),clock,monotonic,
                    expiry_opener=_expiry_opener,quote_opener=_quote_opener,operation_started=started)
                r['stage']='collection';item=producer(ctx)
                r['originalDeadlineMs']=item['collection']['provenance']['validUntilExclusiveMs']
                guard();r['stage']='persistence';return item
            finally:b.close()
    def sign(request):
        guard();r['signerInvocationAttempts']+=1;r['stage']='independent-key-process'
        # On failure after invocation, key/signature effects cannot be inferred.
        r['privateKeyAccessedThisRun']=None;r['signatureCreatedThisRun']=None
        start=monotonic()
        try:
            wire=backend._invoke(root,wallet,pool,r['successorSha256'],request,clock)
            r['privateKeyAccessedThisRun']=True;r['signatureCreatedThisRun']=True
            return wire
        finally:r['timing']['independentBackendMs']=round((monotonic()-start)*1000,3)
    try:
        # Refuse orphan/new-generation files before performing fresh RPC reads.
        with view.cycles.c.source_lock(root,wallet) as locked,read_only_journals():
            b=handoff.preparation.entry.submission._open(locked,wallet,pool,clock)
            try:
                existing=successor.row(b)
                if existing is None:
                    check(not any(os.path.lexists(b.j.path.parent/name) for name in (backend.ATTEMPT,backend.ACK)),
                          'successor-key-slot-occupied')
            finally:b.close()
        guard();start=monotonic()
        try:
            prepared=successor._prepare_from_producer(root,wallet,pool,expected,expected_retirement,produce,
                allow_unsigned_successor=True,clock=clock,monotonic=monotonic)
        finally:r['timing']['collectionPersistenceMs']=round((monotonic()-start)*1000,3)
        r['preparationCreatedThisRun']=prepared['createdThisRun'];r['successorSha256']=prepared['recordSha256']
        r['originalDeadlineMs']=prepared['binding']['validUntilExclusiveMs']
        if not prepared['createdThisRun']:
            r.update(state='existing-successor-held',stage='existing-candidate');return r
        guard();r['stage']='signing-handoff';start=monotonic()
        try:
            signed=handoff._dispatch(root,wallet,pool,r['successorSha256'],signer_adapter=sign,clock=clock)
        finally:r['timing']['signingHandoffMs']=round((monotonic()-start)*1000,3)
        r['signerAcknowledgmentValidated']=signed['acknowledgmentRecorded']
        check(signed['state']=='successor-signed-recorded' and signed['signerAdapterCallsThisRun']==1,
              'successor-integration-ack-required')
        r['stage']='completion-check';end=guard()
        r.update(state='successor-signed-within-deadline',stage='complete',completedWithinOriginalDeadline=True,
                 completedAtMs=end,deadlineHeadroomMs=r['originalDeadlineMs']-end)
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError,view.sqlite3.Error) as exc:
        r['diagnosticCode']=str(exc) if type(exc) is ValueError and str(exc) in CODES else 'successor-integration-unavailable'
    finally:
        if producer:
            data=producer.telemetry();r.update(collectionRequests=data['networkRequests'],requestMethods=data['requestMethods'])
            r['timing'].update(data['timing'])
        r['timing']['totalElapsedMs']=round((monotonic()-started)*1000,3)
    return r


def _collect_sign(home,wallet,pool,expected,expected_retirement,*,
                  allow_unsigned_successor=False,allow_private_key_signing=False,
                  clock=view.now,monotonic=time.monotonic,_expiry_opener=None,_quote_opener=None):
    """Include owner-scope cleanup in the reported original deadline."""
    start=monotonic()
    r=_run(home,wallet,pool,expected,expected_retirement,
        allow_unsigned_successor=allow_unsigned_successor,allow_private_key_signing=allow_private_key_signing,
        clock=clock,monotonic=monotonic,_expiry_opener=_expiry_opener,_quote_opener=_quote_opener)
    wall=clock();tick=monotonic()
    r['timing']['totalElapsedMs']=round((tick-start)*1000,3)
    r['returnedAtMs']=wall
    r['headroomAtReturnMs']=None if r.get('originalDeadlineMs') is None else r['originalDeadlineMs']-wall
    if r['completedWithinOriginalDeadline']:
        old=r['completedAtMs'];r['completedAtMs']=wall;r['deadlineHeadroomMs']=r['originalDeadlineMs']-wall
        if not (old<=wall<r['originalDeadlineMs'] and 0<=tick-start<=120):
            r.update(state='successor-signing-review-required',stage='return-boundary',
                diagnosticCode='successor-integration-expired',completedWithinOriginalDeadline=False)
    return r


@serialization_replay.operation
@canonical_replay.operation
@encoding_replay.operation
@admission_history_replay.operation
def _recover(home,wallet,pool,expected,*,clock=view.now):
    """One exact-content replay owner; backend still opens no key or network."""
    return backend._recover(home,wallet,pool,expected,clock=clock)
