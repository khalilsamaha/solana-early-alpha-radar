"""One explicit replacement of expired unsigned collected evidence; original retained.

Internal coordinator only. No report import, signing, submission or deadline extension.
"""
from copy import deepcopy
import json
import os
import time
import admission_exit as preparation
from contract import digest, fields
from core import check
from journal import read_only_journals

VERSION='unsigned-exit-replacement-1'
TABLE='admission_exit_replacement'
MAX_RECORD=preparation.MAX_RECORD+2048
view=preparation.view
BLOCKED_TABLES={'admission_exit_signing','admission_exit_submission','admission_exit_submission_ack',
    'admission_exit_rpc_captures','admission_exit_accounting','admission_exit_closure'}
MARKERS=('exit-signer-attempt.json','exit-signer-ack.json')


def exists(book):
    return book.db.execute('SELECT type FROM sqlite_master WHERE name=?',(TABLE,)).fetchone()


def replay(book,original,now):
    """Reader never falls back to the original when replacement evidence is invalid."""
    found=exists(book)
    if not found:return original
    check(original is not None and original['format']==preparation.COLLECTED_FORMAT,'replacement-original-required')
    check(found[0]=='table','replacement-table')
    rows=book.db.execute('SELECT id,CASE WHEN length(value)<=? THEN value ELSE NULL END value,hash FROM admission_exit_replacement LIMIT 2',(MAX_RECORD,)).fetchall()
    check(len(rows)==1 and rows[0]['id']==1 and type(rows[0]['value']) is str,'replacement-record')
    envelope=json.loads(rows[0]['value']);fields(envelope,{'format','originalPreparationSha256','replacement'},'replacement-schema')
    check(preparation.encoded(envelope)==rows[0]['value'] and digest(envelope)==rows[0]['hash'] and
          envelope['format']==VERSION+'-record' and envelope['originalPreparationSha256']==digest(original),
          'replacement-integrity')
    current=envelope['replacement']
    check(len(preparation.encoded(current).encode())<=preparation.MAX_RECORD,'replacement-evidence-cap')
    preparation.validate_record(book,current,now)
    relationship(original,current)
    # A later signer must reference this current preparation and cannot precede
    # its persistence. Full signing replay remains the existing reader's job.
    if book.db.execute("SELECT 1 FROM sqlite_master WHERE name='admission_exit_signing'").fetchone():
        row=book.db.execute('SELECT at_ms FROM admission_exit_signing ORDER BY seq LIMIT 1').fetchone()
        check(row is not None and row[0]>=current['recordedAtMs'],'replacement-after-signing')
    return current


def relationship(original,current):
    check(current['format']==preparation.COLLECTED_FORMAT,'replacement-collected-required')
    old=original['binding'];new=current['binding']
    start=current['collection']['provenance']['startedAtMs']
    check(start>=old['validUntilExclusiveMs'] and current['recordedAtMs']>=start and
          current['recordedAtMs']<new['validUntilExclusiveMs'],'replacement-observation-order')
    for key in ('entryAccountingSha256','entryReceiptIdentity','quantityAtomic',
                'feeCommitmentRemainingLamports','attemptNumber','attemptsConsumed'):
        check(new[key]==old[key],'replacement-ownership-changed')
    check(int(new['feeCapLamports'])<=int(old['feeCapLamports']) and
          int(new['protectedInventoryAtomic'])>=int(old['protectedInventoryAtomic']),
          'replacement-protection-changed')
    check(current['evidence']['packet']['policy']['blockhash']!=original['evidence']['packet']['policy']['blockhash'],
          'replacement-blockhash-reused')
    check(current['evidence']['price']['quote']['contextSlot']>=original['evidence']['price']['quote']['contextSlot'],
          'replacement-slot-regressed')


def eligible(book,root,expected,now):
    """Caller holds source lock; recheck before requests, persistence and commit."""
    check(type(expected) is str and len(expected)==64 and all(c in '0123456789abcdef' for c in expected),'replacement-expected-identity')
    check(not view.cycles.c.submit.swap.stop(root) and book.read()[0]['state']=='signed-recorded','replacement-stopped')
    check(exists(book) is None,'replacement-limit-reached')
    tables=book.db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'admission_%' LIMIT 65").fetchall()
    from admission_lifecycle import KNOWN
    check(len(tables)<=64 and all(row[0] in KNOWN for row in tables),'replacement-unknown-schema')
    check(not any(row[0] in BLOCKED_TABLES for row in tables),'replacement-signing-or-later-evidence')
    check(not any(os.path.lexists(book.j.path.parent/name) for name in MARKERS),'replacement-backend-marker')
    old=preparation.original_saved(book,now)
    check(old is not None and old['format']==preparation.COLLECTED_FORMAT and digest(old)==expected,'replacement-original-mismatch')
    check(now>=old['binding']['validUntilExclusiveMs'],'replacement-original-not-expired')
    preparation.owner(book,now)
    return old


def write_record(book,envelope):
    book.db.execute('CREATE TABLE admission_exit_replacement (id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL,hash TEXT NOT NULL)')
    book.db.execute('INSERT INTO admission_exit_replacement VALUES(1,?,?)',(preparation.encoded(envelope),digest(envelope)))


@view.cycles.binding.operation
def replace(home,wallet,pool,evidence,collection,*,expected_preparation_sha256,
            allow_unsigned_replacement=False,clock=view.now):
    """Atomically append one collected replacement; no changes to original tables."""
    check(allow_unsigned_replacement is True,'explicit-unsigned-replacement-required')
    from admission_exit_collection import MAX_COLLECTION,review
    check(len(preparation.encoded(evidence).encode())<=preparation.MAX_RECORD and
          len(preparation.encoded(collection).encode())<=MAX_COLLECTION,'replacement-input-cap')
    evidence=deepcopy(evidence);collection=deepcopy(collection)
    with view.cycles.c.source_lock(home,wallet) as root:
        book=preparation.entry.submission._open(root,wallet,pool,clock)
        try:
            with book.j.transaction():
                with read_only_journals():
                    reader=preparation.entry.submission._open(root,wallet,pool,clock)
                    try:
                        old=eligible(reader,root,expected_preparation_sha256,clock())
                        from admission_lifecycle import projection
                        phase,_,_,_,_,_=projection(reader,root,wallet,pool,clock)
                        check(phase=='exit-prepared','replacement-lifecycle-conflict')
                        now=clock();binding=preparation.review(reader,evidence,now)
                        binding=review(reader,evidence,collection,now,binding)
                        check(digest(reader.read()[0])==collection['provenance']['identity']['admissionStateSha256'],
                              'replacement-admission-changed')
                        current=dict(format=preparation.COLLECTED_FORMAT,recordedAtMs=now,
                            evidence=evidence,collection=collection,binding=binding)
                        relationship(old,current)
                        eligible(reader,root,expected_preparation_sha256,clock())
                    finally:reader.close()
                envelope=dict(format=VERSION+'-record',originalPreparationSha256=digest(old),replacement=current)
                check(len(preparation.encoded(envelope).encode())<=MAX_RECORD,'replacement-record-cap')
                end=clock();check(now<=end<binding['validUntilExclusiveMs'],'replacement-expired-before-write')
                write_record(book,envelope)
                check(book.db.execute('PRAGMA page_count').fetchone()[0]*book.db.execute('PRAGMA page_size').fetchone()[0]<=64*1024*1024,'replacement-ledger-size-cap')
                end=clock();check(now<=end<binding['validUntilExclusiveMs'],'replacement-expired-before-commit')
                check(not view.cycles.c.submit.swap.stop(root),'replacement-stopped')
                check(not any(os.path.lexists(book.j.path.parent/name) for name in MARKERS),'replacement-backend-marker')
                return dict(preparation.public(current,end,created=True),format=VERSION,
                    originalPreparationSha256=digest(old),replacementCount=1,originalPreserved=True,
                    automaticReplacementAllowed=False)
        finally:book.close()


@view.cycles.binding.operation
def collect_and_replace(home,wallet,pool,*,expected_preparation_sha256,
                        allow_unsigned_replacement=False,opener=None,clock=view.now,
                        monotonic=time.monotonic,_observation_sink=None):
    check(_observation_sink is None or callable(_observation_sink),
          'exit-collection-observation-sink')
    check(allow_unsigned_replacement is True,'explicit-unsigned-replacement-required')
    check(type(expected_preparation_sha256) is str and len(expected_preparation_sha256)==64 and
          all(c in '0123456789abcdef' for c in expected_preparation_sha256),'replacement-expected-identity')
    from admission_exit_capture import collect
    items=[]
    observed=collect(home,wallet,pool,opener=opener,clock=clock,monotonic=monotonic,
        _evidence_sink=items.append,_replacement_expected=expected_preparation_sha256)
    if _observation_sink is not None:_observation_sink(deepcopy(observed))
    if observed['state']!='exit-evidence-collected-research-only':return observed
    check(len(items)==1,'replacement-collection-handoff')
    envelope=items[0];evidence=envelope.pop('evidence')
    result=replace(home,wallet,pool,evidence,envelope,
        expected_preparation_sha256=expected_preparation_sha256,allow_unsigned_replacement=True,clock=clock)
    return dict(result,collectionRequestsThisRun=observed['networkRequests'])
