"""Read validated saved evidence only; never collect, sign, replace or submit."""
from datetime import datetime,timezone
import time
import admission_exit_collection as collection
import admission_lifecycle as lifecycle
import fresh_signing
import exit_submission as transport
import restricted_exit_signer as backend
from contract import digest
from core import check
from journal import read_only_journals

VERSION='exit-history-timing-1'
view=lifecycle.view


def summarize(record):
    c=record['collection'];e=record['evidence'];p=c['provenance']
    built=c['packetBuild']['evidence']
    responses=([x[2] for x in collection.preflight_requests(c['initialCapture'],collection.exit.BASELINE)]+
        [built[n] for n in ('genesisBefore','blockhash','fee','genesisAfter')]+
        [x[2] for x in collection.preflight_requests(e['capture'],collection.exit.BASELINE)]+
        [dict(receivedAtMs=e['simulationReceivedAtMs']),dict(receivedAtMs=e['completedAtMs'])])
    trace=c['requestTrace'];check(len(trace)==len(responses)==20,'history-request-count')
    rows=[];previous=p['startedAtMs']
    for i,(request,response) in enumerate(zip(trace,responses),1):
        start=request['requestedAtMs'];end=response['receivedAtMs']
        check(previous<=start<=end<=p['completedAtMs'],'history-clock-order')
        rows.append(dict(index=i,method=request['method'],requestedAtMs=start,receivedAtMs=end,
            recordedRequestIntervalMs=end-start,gapBeforeRequestMs=start-previous))
        previous=end
    start=p['startedAtMs'];finish=p['completedAtMs'];recorded=record['recordedAtMs'];deadline=record['binding']['validUntilExclusiveMs']
    check(start<=finish<=recorded<deadline,'history-record-order')
    return dict(preparationSha256=digest(record),collectionStartedAtMs=start,
        collectionDeliveredAtMs=finish,recordTimestampAtMs=recorded,deadlineMs=deadline,
        collectionWindowMs=deadline-start,collectionElapsedMs=finish-start,
        summedRecordedRequestIntervalsMs=sum(x['recordedRequestIntervalMs'] for x in rows),
        summedInterRequestGapsMs=sum(x['gapBeforeRequestMs'] for x in rows),
        finalResponseToDeliveryMs=finish-previous,deliveryToRecordTimestampMs=recorded-finish,
        remainingAtDeliveryMs=deadline-finish,remainingAtRecordTimestampMs=deadline-recorded,
        commitCompletedAtMs=None,postCommitHeadroomMs=None,requests=rows,
        basis='Historical wall-clock intervals from validated saved evidence; request intervals include client work and are not pure provider latency. Record timestamp precedes validation/write/commit; commit time was not recorded.')


def signing_timeline(root,book,record,now):
    """Validated historical timestamps, never a replacement or send decision.

    Caller holds the source lock and shared admission read lock. Every marker
    and acknowledgment is reread. Missing durable timestamps stay unknown.
    """
    with transport.ExitSubmission(book).snapshot():
        state=transport.handoff.read(book,now)
        if state is None:
            return dict(version='saved-signing-timeline-1',state='signing-not-recorded',
                        signingRecorded=False,observedAtMs=now)
        check(state['request']['preparationSha256']==digest(record),'history-signing-generation')
        check(state['state']=='exit-signed-recorded' and state['signed'] is not None,
              'history-complete-signing-required')
        marker=backend._attempt_record_for_state(root,book,state)
        wire=backend._read_ack(root,book,state)
        check(wire==state['signed']['signedWireBase64'],'history-ack-conflict')
        rows=book.db.execute('SELECT seq,at_ms FROM admission_exit_signing ORDER BY seq LIMIT 4').fetchall()
        check(len(rows)==2 and [r['seq'] for r in rows]==[1,2],'history-signing-rows')
        boundary,recorded=rows[0]['at_ms'],rows[1]['at_ms']
        attempt=marker['atMs'];start=record['recordedAtMs'];deadline=record['binding']['validUntilExclusiveMs']
        check(start<=boundary<=attempt<=recorded<=now,'history-signing-order')
        # Do not collapse an existing transport attempt (possibly lost response)
        # into the locally-unsubmitted case. Validate its full transport state.
        status=transport.ExitSubmission(book).status()
        sent=status['applicationSendBoundaryRecorded']
        expired=now>=deadline
        label=('transport-recorded-inspect-recovery' if sent else
               'expired-signed-locally-unsubmitted-held' if expired else 'signed-locally-unsubmitted-held')
        return dict(version='saved-signing-timeline-1',state=label,signingRecorded=True,
            preparationSha256=digest(record),deadlineMs=deadline,observedAtMs=now,
            deadlineExpiredAtObservation=expired,
            boundaryRecordedAtMs=boundary,backendAttemptRecordedAtMs=attempt,
            acknowledgmentRecordedAtMs=recorded,
            recordTimestampToBoundaryMs=boundary-start,
            boundaryToBackendAttemptMs=attempt-boundary,
            backendAttemptToRecordedAcknowledgmentMs=recorded-attempt,
            remainingAtBoundaryTimestampMs=deadline-boundary,
            remainingAtBackendAttemptTimestampMs=deadline-attempt,
            remainingAtAcknowledgmentTimestampMs=deadline-recorded,
            acknowledgmentRecordedAfterDeadline=recorded>=deadline,
            applicationSendBoundaryRecorded=sent,transportState=status['state'],
            signatureCreationAtMs=None,ackFileWrittenAtMs=None,
            signingBoundaryCommitCompletedAtMs=None,acknowledgmentCommitCompletedAtMs=None,
            retryAllowed=False,replacementAuthorized=False,reservationsReleasedThisRun=False,
            basis='Stored wall-clock boundaries, not pure cryptographic or CPU durations. Backend attempt precedes marker fsync and signing; acknowledgment record includes backend return and Python validation. Commit times were not recorded. Absence of a local send boundary does not prove global non-broadcast or blockhash expiry.')


@view.cycles.binding.operation
@fresh_signing.timing.signature_replay
def inspect(home,wallet,pool):
    r=dict(format=VERSION,state='history-unavailable',timing=None,signingTimeline=None,diagnosticCode=None,
        databaseConnectionsReadOnly=True,networkRequests=0,privateKeyAccessed=False,
        signaturesCreated=0,transactionsSent=0,sourceStateChanged=False,
        replacementAuthorized=False,retryAllowed=False,executionApproved=False)
    started=time.monotonic()
    try:
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            book=lifecycle.entry.submission._open(root,wallet,pool,view.now)
            try:
                with lifecycle.admission_read_lock(book.j.path):
                    record=lifecycle.preparation.saved(book,view.now())
                    check(record is not None and record['format']==collection.exit.COLLECTED_FORMAT,'history-collected-required')
                    timing=summarize(record)
                    signing=signing_timeline(root,book,record,view.now())
                    check(0<=time.monotonic()-started<=lifecycle.MAX_READ_MS/1000,'history-read-budget')
                    r.update(state='saved-exit-timing-observed',timing=timing,signingTimeline=signing)
            finally:book.close()
    except view.ERRORS:r['diagnosticCode']='saved-exit-timing-unavailable'
    r['capturedAt']=datetime.now(timezone.utc).isoformat()
    return r
