"""One isolated unsigned admission commit rehearsal; no sender-compatible storage."""
from copy import deepcopy
import os
import subprocess

import admission_timing as timing
from pre_sign_admission import Admission, review, VERSION as ADMISSION_VERSION, MAX_EVIDENCE_BYTES
from core import check, directory, sync_directory
from contract import digest, fields, uint
from journal import encoded, read_only_journals

VERSION='durable-admission-rehearsal-1'
SUFFIX='-unsigned-admission-rehearsal-v1'
NAME='rehearsal.admission.sqlite'
LIMIT=MAX_EVIDENCE_BYTES+65536
view=timing.view
ERRORS=view.ERRORS+(subprocess.SubprocessError,)


def storage(root):return root.parent/(root.name+SUFFIX)


def base():
    r=timing.base()
    r.update(format=VERSION,storageMode='isolated-unsigned-rehearsal',
        rehearsalJournalCreated=False,reservationRecorded=None,commitCompleted=False,
        commitOnTimeObserved=False,commitTimingKnown=False,reservation=None,
        currentSourceVerified=False,sourceDatabaseConnectionsReadOnly=True,
        databaseConnectionsReadOnly=False,admissionLedgerCreated=False,
        operationalAdmissionCreated=False,signerCompatibleStorage=False,
        rawEvidenceExported=False,automaticRetryAllowed=False)
    r['limitations']=[
        'Isolated rehearsal commitments only; not operational wallet reservations or signing authority.',
        'No signing request, signing boundary, private key access or submission.',
        'Source is reread under its cooperating lock; external wallet activity is not locked.',
        'Pre-commit expiry rolls back the reservation; late or ambiguous commit retains storage for read-only inspection.',
        'Recovery does not establish an on-time disk commit or current wallet balances.',
        'No mainnet execution or profitability evidence.']
    return r


def vacant(root):
    timing.vacant(root)
    check(not os.path.lexists(storage(root)), 'rehearsal-slot-occupied')


def guard(root, clock, monotonic, start, deadline, minimum, minimum_tick=None):
    now=clock();tick=monotonic()
    uint(now,2**53-1,'rehearsal-clock',minimum=minimum)
    check((start if minimum_tick is None else minimum_tick)<=tick<start+30,'rehearsal-monotonic-expired')
    check(now<deadline,'rehearsal-expired')
    check(not view.cycles.c.submit.swap.stop(root),'rehearsal-stopped')
    timing.vacant(root)
    return now,tick


def insert_capture(book, record):
    raw=encoded(record);check(len(raw.encode())<=LIMIT,'rehearsal-capture-cap')
    book.db.execute('CREATE TABLE rehearsal_capture (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL, hash TEXT NOT NULL)')
    book.db.execute('INSERT INTO rehearsal_capture VALUES (1,?,?)',(raw,digest(record)))
    check(book.db.execute('PRAGMA page_count').fetchone()[0]*book.db.execute('PRAGMA page_size').fetchone()[0]<=64*1024*1024,'rehearsal-ledger-cap')


def _commit(root,wallet,pool,evidence,policy,deadline,*,clock,monotonic,start,result):
    """Caller owns source lock; only this fixed isolated sibling can be written."""
    with read_only_journals():
        with timing.phase(result,'locked-source-before',clock,monotonic):
            before=view.read_locked(root,wallet,pool,clock)
            timing.bridge.same(before,evidence['costInputs']['reservations'],wallet,pool)
            check(evidence['completedAtMs']<=before['readStartedAtMs']<=before['observedAtMs']<=clock(),'rehearsal-source-clock')
    vacant(root)
    _,first_tick=guard(root,clock,monotonic,start,deadline,before['observedAtMs'])
    path=storage(root);path.mkdir(mode=0o700)
    result.update(rehearsalJournalCreated=True,reservationRecorded=None)
    sync_directory(root.parent)
    book=Admission(directory(path)/NAME,policy,clock)
    try:
        result['admissionLedgerCreated']=True
        with timing.phase(result,'durable-reservation',clock,monotonic):
            with book.j.transaction():
                check(book.read()[1]==0,'rehearsal-not-empty')
                _,second_tick=guard(root,clock,monotonic,start,deadline,before['observedAtMs'],first_tick)
                reserved=book._change_in_transaction(book._reservation_action(evidence))
                check(reserved['state']=='reserved','rehearsal-not-reserved')
                with read_only_journals():
                    after=view.read_locked(root,wallet,pool,clock)
                    timing.bridge.same(after,before,wallet,pool)
                state,_,_,stamp=book.read()
                check(before['observedAtMs']<=state['reservedAtMs']<=stamp<=after['readStartedAtMs']<=after['observedAtMs']<=clock(),'rehearsal-source-clock')
                record=dict(format=VERSION,evidence=deepcopy(evidence),firstSource=before,finalSource=after,
                            effectiveDeadlineMs=deadline)
                insert_capture(book,record)
                precommit,tick=guard(root,clock,monotonic,start,deadline,after['observedAtMs'],second_tick)
            # A late COMMIT cannot be rolled back after it returns. Retain its
            # reservation and explicitly refuse to label it an on-time result.
            result['commitCompleted']=True
            completed=clock();end=monotonic()
            uint(completed,2**53-1,'rehearsal-clock',minimum=precommit)
            ontime=completed<deadline and tick<=end<start+30
            stopped=view.cycles.c.submit.swap.stop(root)
            result.update(state='unsigned-rehearsal-recorded' if ontime and not stopped else 'unsigned-rehearsal-recorded-unusable',
                reservationRecorded=True,commitTimingKnown=True,commitOnTimeObserved=ontime,
                reservation=reserved,completedAtMs=completed,remainingMs=deadline-completed,
                quoteAgeMs=completed-evidence['costInputs']['price']['quote']['requestedAtMs'],
                currentSourceVerified=True,rawAdmissionValidationPassed=True,stage='complete')
    finally:book.close()


@view.cycles.binding.operation
@timing.signature_replay
def prepare(home,wallet,pool,*,allow_local_rehearsal=False,maximum_exit_attempts,
            maximum_exit_fee_lamports,maximum_total_fee_lamports,opener=None,clock=view.now,monotonic=timing.time.monotonic):
    r=base();private=[];start=monotonic()
    try:
        check(allow_local_rehearsal is True,'explicit-local-rehearsal-required')
        uint(maximum_exit_attempts,3,'rehearsal-policy',minimum=1)
        fee=timing.atomic(maximum_exit_fee_lamports,'rehearsal-policy',positive=True)
        total=timing.atomic(maximum_total_fee_lamports,'rehearsal-policy',positive=True)
        check(fee<=10000 and total<=40000 and fee*maximum_exit_attempts<total,'rehearsal-policy')
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            vacant(root);check(not view.cycles.c.submit.swap.stop(root),'rehearsal-stopped')
        with timing.phase(r,'fresh-entry-collection',clock,monotonic):
            obs=timing.fresh_quote.observe(home,wallet,pool,opener=opener,clock=clock,monotonic=monotonic,
                simulate=True,assess_costs=True,refreshed_deployment=True,_evidence_sink=private.append)
            r.update(networkRequests=obs['networkRequests'],requestMethods=obs['requestMethods'],
                collectionState=obs['state'],collectionStage=obs['stage'],collectionDiagnosticCode=obs.get('diagnosticCode'))
            check(obs['state']=='controlled-cost-observation-consistent' and len(private)==1,'rehearsal-collection-unavailable')
        evidence=private.pop()
        deadlines=[obs['costReadiness']['validUntilExclusiveMs'],obs['preflight']['validUntilExclusiveMs'],
                   obs['binding']['binding']['validUntilExclusiveMs']]
        for value in deadlines:uint(value,2**53-1,'rehearsal-deadline',minimum=1)
        deadline=min(deadlines);r['originalDeadlineMs']=deadline
        policy=dict(format=ADMISSION_VERSION+'-policy',scope=deepcopy(evidence['scope']),
            maximumExitAttempts=maximum_exit_attempts,maximumExitFeeLamports=maximum_exit_fee_lamports,
            maximumTotalFeeLamports=maximum_total_fee_lamports)
        with view.cycles.c.source_lock(home,wallet) as root:
            _commit(root,wallet,pool,evidence,policy,deadline,clock=clock,monotonic=monotonic,start=start,result=r)
    except ERRORS as exc:
        r.update(state='rehearsal-inspection-required' if r['rehearsalJournalCreated'] else 'unavailable',
            diagnosticCode='rehearsal-evidence-unavailable')
        if str(exc) in ('rehearsal-slot-occupied','timing-existing-admission','rehearsal-expired','rehearsal-stopped',
                        'rehearsal-clock','rehearsal-monotonic-expired','explicit-local-rehearsal-required'):
            r['diagnosticCode']=str(exc)
    finally:private.clear()
    return r


@view.cycles.binding.operation
def status(home,wallet,pool,*,clock=view.now):
    r=base();r.update(databaseConnectionsReadOnly=True,stage='read-only-recovery')
    try:
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            path=storage(root)
            if not os.path.lexists(path):r.update(state='rehearsal-not-found',reservationRecorded=False);return r
            book=Admission(directory(path)/NAME,clock=clock)
            try:
                roles=book.policy['scope']['accounts'];check(roles['wallet']==wallet and roles['pool']==pool,'rehearsal-scope')
                state,count,_,stamp=book.read()
                exists=book.db.execute("SELECT type FROM sqlite_master WHERE name='rehearsal_capture'").fetchone()
                if state is None and exists is None:
                    r.update(state='preparation-incomplete',reservationRecorded=False);return r
                check(count==1 and state['state']=='reserved' and state['signingBoundaryAtMs'] is None,'rehearsal-unsigned-required')
                rows=book.db.execute('SELECT id,CASE WHEN length(CAST(value AS BLOB))<=? THEN value ELSE NULL END value,hash FROM rehearsal_capture LIMIT 2',(LIMIT,)).fetchall()
                check(len(rows)==1 and rows[0]['id']==1 and type(rows[0]['value']) is str,'rehearsal-capture')
                record=timing.admission.json.loads(rows[0]['value'])
                fields(record,{'format','evidence','firstSource','finalSource','effectiveDeadlineMs'},'rehearsal-record')
                check(record['format']==VERSION and encoded(record)==rows[0]['value'] and digest(record)==rows[0]['hash'],'rehearsal-integrity')
                checked=review(record['evidence'],book.policy,state['reservedAtMs'])
                check(all(state[k]==v for k,v in checked.items()),'rehearsal-reservation-conflict')
                a,b=record['firstSource'],record['finalSource'];timing.bridge.same(a,record['evidence']['costInputs']['reservations'],wallet,pool)
                timing.bridge.same(b,a,wallet,pool)
                deadline=record['effectiveDeadlineMs'];uint(deadline,checked['validUntilExclusiveMs'],'rehearsal-deadline',minimum=1)
                check(record['evidence']['completedAtMs']<=a['readStartedAtMs']<=a['observedAtMs']<=state['reservedAtMs']
                    <=stamp<=b['readStartedAtMs']<=b['observedAtMs']<deadline,'rehearsal-source-clock')
                now=clock();uint(now,2**53-1,'rehearsal-clock',minimum=b['observedAtMs'])
                stopped=view.cycles.c.submit.swap.stop(root)
                r.update(state='unsigned-rehearsal-stopped' if stopped else 'unsigned-rehearsal-expired' if now>=deadline else 'unsigned-rehearsal-recorded',
                    reservationRecorded=True,reservation=book.status(),originalDeadlineMs=deadline,
                    completedAtMs=now,remainingMs=deadline-now,rawAdmissionValidationPassed=True)
            finally:book.close()
    except ERRORS:r.update(state='rehearsal-inspection-required',diagnosticCode='rehearsal-evidence-unavailable',reservation=None)
    return r
