"""Private local snapshot of historical source plus its admission sibling.

No active restore, repair, signer, sender, cloud transfer or allocation release.
Verification replays a stopped disposable copy without original source access.
"""
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import tempfile

import evidence_backup as backup
import entry_accounting as accounting
import restricted_signer
from pre_sign_admission import Admission, encoded
from contract import digest, fields, uint
from core import check, directory, private_file, write_new, sync_directory
from journal import read_only_journals
from wire import verify_wire

VERSION='admission-recovery-snapshot-1'
SOURCE='source'
SIBLING='source-entry-handoff-v1'
MANIFEST='manifest.json'
ADMISSION_CAPS={'entry.admission.sqlite':64*1024*1024,
                'signer-attempt.json':1024,'signer-ack.json':4096}
MAX_TOTAL=320*1024*1024+5120
NOW=accounting.submission.handoff.bridge.view.now
TABLES=('admission_submission','admission_submission_ack','admission_rpc_captures',
        'admission_receipt_events','admission_receipt_raw','admission_entry_accounting')


def admission_inventory(root):
    root=directory(root);files={};total=0
    with os.scandir(root) as entries:
        for item in entries:
            check(item.name in ADMISSION_CAPS,'unexpected-admission-file')
            path=Path(item.path);s=backup.metadata(path)
            check(s.st_size<=ADMISSION_CAPS[item.name],'admission-file-cap')
            raw=private_file(path,ADMISSION_CAPS[item.name])
            check(len(raw)==s.st_size,'admission-size-changed')
            files[item.name]=dict(bytes=len(raw),sha256=backup.sha(raw));total+=len(raw)
    check('entry.admission.sqlite' in files,'admission-ledger-required')
    check('signer-ack.json' not in files or 'signer-attempt.json' in files,'orphan-signer-ack')
    return dict(directories=[],files=dict(sorted(files.items())),bytes=total)


def copy_admission(source,target,inv):
    for name,expected in inv['files'].items():
        check(name in ADMISSION_CAPS,'unexpected-admission-file')
        raw=private_file(source/name,ADMISSION_CAPS[name])
        check(dict(bytes=len(raw),sha256=backup.sha(raw))==expected,'admission-changed-during-copy')
        backup.write_bytes(target/name,raw)


@contextmanager
def admission_read_lock(path):
    # Hold a shared SQLite lock while copying the DELETE-mode database. Existing
    # sidecars are refused by inventory/Journal; never repair or use immutable=1.
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2,isolation_level=None)
    try:
        db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA query_only=ON')
        check(db.execute('PRAGMA journal_mode').fetchone()[0]=='delete','unsupported-journal-mode')
        db.execute('BEGIN');db.execute('SELECT name FROM sqlite_master').fetchall()
        yield
    finally:db.close()


def inspect_locked(home,wallet,pool,clock):
    """Semantic replay under caller's source lock and read-only journal scope."""
    backup.historical_ok(backup.r.inspect_locked(home,wallet,pool))
    sibling=accounting.submission.handoff.storage(home).parent
    book=accounting.submission._open(home,wallet,pool,clock)
    try:
        state,count,head,at=book.read()
        check(state is not None and state.get('reservedAtMs') is not None,'funded-admission-required')
        check(clock()>=at,'snapshot-clock-regressed')
        # The source's closed spending history must be the one used at admission.
        with backup.r.cycles.c.submit.spend_guard.Guard(home/backup.r.cycles.binding.CYCLE) as guard:
            _,_,source_head,_=guard.read()
            check(state['ledgerHeadSha256']==source_head and
                  state['cycleBindingSha256']==digest(guard.cycle),'admission-history-mismatch')
        attempt=(sibling/'signer-attempt.json').exists();ack=(sibling/'signer-ack.json').exists()
        if attempt:
            v=json.loads(private_file(sibling/'signer-attempt.json',1024))
            fields(v,{'format','requestSha256','admissionHeadSha256','atMs'},'snapshot-attempt-shape')
            boundary=book.db.execute('SELECT hash,at_ms FROM admission_events WHERE seq=3').fetchone()
            check(boundary is not None and state.get('signingBoundaryAtMs') is not None and
                  v['format']=='admission-signer-attempt-1' and v['requestSha256']==state.get('signingRequestSha256') and
                  v['admissionHeadSha256']==boundary['hash'],'snapshot-attempt-binding')
            uint(v['atMs'],min(clock(),state['validUntilExclusiveMs']-1),'snapshot-attempt-clock',minimum=boundary['at_ms'])
        if state.get('signingRequest') is not None:
            check(digest(state['signingRequest'])==state.get('signingRequestSha256'),'snapshot-request-binding')
        signed=state.get('signedWireBase64')
        if signed is not None:
            verified=verify_wire(signed)
            check(verified['requiredSignatures']==1 and verified['wallet']==wallet and
                  verified['wireMessageSha256']==state['messageSha256'] and
                  verified['wireSha256']==state['signedWireSha256'] and
                  verified['signatures'][0]==state['signature'],'snapshot-signed-wire-binding')
        if ack:
            wire=restricted_signer.acknowledgment(home,book);verified=verify_wire(wire)
            check(verified['requiredSignatures']==1 and verified['wallet']==wallet and
                  verified['wireMessageSha256']==state['messageSha256'] and
                  (signed is None or signed==wire),'snapshot-ack-binding')
        transport=None;settled=None;accounting_hash=None
        if state.get('accountingHandoff') is not None and state['state'] in ('signed-recorded','stopped'):
            t=accounting.submission.Submission(book).status()
            transport={k:t[k] for k in ('state','applicationSendBoundaryRecorded','receiptCaptureCount','genesisBoundReceiptCollected')}
            evidence=accounting.review(book);saved=accounting.saved(book.db,clock())
            result=accounting.public(evidence,saved)
            settled={k:result[k] for k in ('state','accountingRecorded','accountingUsable')}
            accounting_hash=result['recordSha256']
        else:
            # Preserve incomplete signing without inventing a receipt or repairing
            # the acknowledgment. Later-stage tables cannot be silently omitted.
            for name in TABLES:
                check(book.db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(name,)).fetchone() is None,
                      'later-evidence-without-handoff')
        result=dict(admissionState=state['state'],admissionEvents=count,admissionHeadSha256=head,
            policySha256=digest(book.policy),sourceHeadSha256=source_head,
            reservedPrincipalAtomic=state['reservedPrincipalAtomic'],reservedFeeLamports=state['reservedFeeLamports'],
            signerAttemptPresent=attempt,signerAcknowledgmentPresent=ack,
            transport=transport,settlement=settled,accountingRecordSha256=accounting_hash)
        # Optional new evidence is semantically replayed, not merely copied.
        # Omitting this field when absent preserves existing snapshot manifests.
        if book.db.execute("SELECT 1 FROM sqlite_master WHERE name='admission_exit_preparation'").fetchone():
            import admission_exit
            prepared=admission_exit.saved(book,clock())
            result['exitPreparationSha256']=digest(prepared)
        return result
    finally:book.close()


def inventories(source,sibling,*,original=False):
    a=backup.inventory(source,source=original);b=admission_inventory(sibling)
    check(a['bytes']+b['bytes']<=MAX_TOTAL,'combined-snapshot-byte-cap')
    return {SOURCE:a,SIBLING:b}


def replay(snapshot,invs,wallet,pool,clock):
    with tempfile.TemporaryDirectory(prefix='.admission-restore-check-',dir=snapshot) as temp:
        root=Path(temp);source=root/SOURCE;source.mkdir(mode=0o700)
        sibling=root/SIBLING;sibling.mkdir(mode=0o700)
        backup.copy_inventory(snapshot/SOURCE,source,invs[SOURCE])
        copy_admission(snapshot/SIBLING,sibling,invs[SIBLING])
        check(inventories(source,sibling)==invs,'restore-bytes-mismatch')
        checked=backup.sqlite_integrity(source,invs[SOURCE])+backup.sqlite_integrity(sibling,invs[SIBLING])
        if not (source/'STOP').exists():backup.write_bytes(source/'STOP',b'isolated restore verification only\n')
        before=inventories(source,sibling)
        with backup.r.cycles.c.source_lock(source,wallet),read_only_journals():
            result=inspect_locked(source,wallet,pool,clock)
            check(backup.r.cycles.c.submit.swap.stop(source),'restore-must-remain-stopped')
        check(inventories(source,sibling)==before,'restore-mutated-evidence')
    return checked,result


def public(invs,projection,databases,raw,created):
    return dict(format=VERSION,state='isolated-admission-restore-verified',capturedAt=backup.stamp(),
        snapshotCreatedAt=created,manifestSha256=backup.sha(raw),
        files=sum(len(x['files']) for x in invs.values()),bytes=sum(x['bytes'] for x in invs.values()),
        sqliteDatabasesChecked=databases,closedCyclesVerified=2,
        admissionState=projection['admissionState'],signerAttemptPreserved=projection['signerAttemptPresent'],
        signerAcknowledgmentPreserved=projection['signerAcknowledgmentPresent'],
        transport=projection['transport'],settlement=projection['settlement'],
        byteHashesVerified=True,sourceBindingReplayed=True,temporaryRestoreRemoved=True,restoredCopyStopped=True,
        signingKeyIncluded=False,privateKeyAccessed=False,sourceStateChanged=False,
        networkRequests=0,signaturesCreated=0,transactionsSent=0,cloudRequests=0,
        reservationReleased=False,allocationTransferred=False,executionApproved=False,nextCycleAuthorized=False,
        runtimeIntegrated=False,mainnetEnabled=False,
        limitations=[
            'Local private snapshot; no off-machine transfer or signing-key recovery.',
            'Contains signed evidence: do not upload the snapshot, manifest or source directory.',
            'Checksums detect corruption, not malicious replacement of all evidence and manifest.',
            'Historical replay does not establish current balances or that this is the latest snapshot.',
            'Unknown or quarantined states are preserved, not cleared; successful restore verification is not trading readiness.',
            'No active restore destination, repair, re-sign, resend, allocation release or study evaluation.'])


@backup.r.cycles.binding.operation
def capture(home,wallet,pool,destination,*,clock=NOW):
    home=directory(home);sibling=accounting.submission.handoff.storage(home).parent
    destination=Path(destination).absolute();parent=directory(destination.parent)
    for source in (home,sibling):
        check(not destination.is_relative_to(source) and not source.is_relative_to(destination),'snapshot-source-overlap')
    check(not os.path.lexists(destination),'snapshot-already-exists')
    with backup.r.cycles.c.source_lock(home,wallet),read_only_journals():
        invs=inventories(home,sibling,original=True)
        with admission_read_lock(sibling/'entry.admission.sqlite'):
            projection=inspect_locked(home,wallet,pool,clock)
            destination.mkdir(mode=0o700);sync_directory(parent)
            for name in (SOURCE,SIBLING):(destination/name).mkdir(mode=0o700)
            backup.copy_inventory(home,destination/SOURCE,invs[SOURCE])
            copy_admission(sibling,destination/SIBLING,invs[SIBLING])
            check(inventories(home,sibling,original=True)==invs,'sources-changed-during-capture')
        databases,restored=replay(destination,invs,wallet,pool,clock)
        check(restored==projection,'restored-admission-mismatch')
        check(inventories(destination/SOURCE,destination/SIBLING)==invs,'snapshot-changed-during-replay')
        manifest=dict(format=VERSION,createdAt=backup.stamp(),wallet=wallet,pool=pool,inventories=invs,
                      projection=projection,excludedSigningKeys=sorted(backup.EXCLUDED_KEYS))
        write_new(destination/MANIFEST,manifest);sync_directory(destination)
    raw=private_file(destination/MANIFEST,262144)
    return public(invs,projection,databases,raw,manifest['createdAt'])


@backup.r.cycles.binding.operation
def verify(snapshot,wallet,pool,*,clock=NOW):
    snapshot=directory(snapshot)
    check(set(p.name for p in snapshot.iterdir())=={SOURCE,SIBLING,MANIFEST},'incomplete-or-unexpected-snapshot')
    raw=private_file(snapshot/MANIFEST,262144);v=json.loads(raw)
    fields(v,{'format','createdAt','wallet','pool','inventories','projection','excludedSigningKeys'},'snapshot-manifest-shape')
    check(v['format']==VERSION and v['wallet']==wallet and v['pool']==pool and
          v['excludedSigningKeys']==sorted(backup.EXCLUDED_KEYS),'snapshot-manifest-scope')
    check(type(v['createdAt']) is str and backup.re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00',v['createdAt']) is not None,'snapshot-timestamp')
    datetime.fromisoformat(v['createdAt'])
    invs=inventories(snapshot/SOURCE,snapshot/SIBLING)
    check(invs==v['inventories'],'snapshot-integrity-mismatch')
    databases,projection=replay(snapshot,invs,wallet,pool,clock)
    check(projection==v['projection'],'snapshot-projection-mismatch')
    check(inventories(snapshot/SOURCE,snapshot/SIBLING)==invs and private_file(snapshot/MANIFEST,262144)==raw,'snapshot-changed-during-replay')
    return public(invs,projection,databases,raw,v['createdAt'])
