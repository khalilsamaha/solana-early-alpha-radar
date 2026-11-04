"""One explicit continuation after an expired unsigned replacement; offline interface only.

All three generations remain immutable. This module prepares evidence, never signs,
sends, resets replacement capacity, changes ownership or releases reservations.
"""
from copy import deepcopy
import json
import os
import time
import unsigned_exit_replacement as replacement
import preserved_exit_observation as preserved
from contract import digest, fields
from core import check
from journal import read_only_journals
import fresh_signing
import encoding_replay
import admission_history_replay

VERSION='unsigned-exit-continuation-1'
TABLE='admission_exit_continuation'
preparation=replacement.preparation
view=preparation.view
MAX_RECORD=preparation.MAX_RECORD+4096


def exists(book):
    return book.db.execute('SELECT type FROM sqlite_master WHERE name=?',(TABLE,)).fetchone()


def eligible(book,root,pair,now):
    preserved.identities(pair)
    check(exists(book) is None,'continuation-limit-reached')
    return preserved.guard(book,root,pair,now)


def relationship(original,previous,current):
    # Unique new blockhash across BOTH expired generations, unchanged cumulative
    # owner/quantity/fee holds, and no weaker protection than either generation.
    replacement.relationship(original,current)
    replacement.relationship(previous,current)


def replay(book,original,previous,now):
    found=exists(book)
    if not found:return previous
    check(found[0]=='table' and original is not None and previous is not None and
          replacement.exists(book) is not None,'continuation-history-required')
    rows=book.db.execute('SELECT id,CASE WHEN length(value)<=? THEN value ELSE NULL END value,hash FROM admission_exit_continuation LIMIT 2',(MAX_RECORD,)).fetchall()
    check(len(rows)==1 and rows[0]['id']==1 and type(rows[0]['value']) is str,'continuation-record')
    envelope=json.loads(rows[0]['value'])
    fields(envelope,{'format','originalPreparationSha256','previousPreparationSha256','continuation'},'continuation-schema')
    check(preparation.encoded(envelope)==rows[0]['value'] and digest(envelope)==rows[0]['hash'] and
          envelope['format']==VERSION+'-record' and envelope['originalPreparationSha256']==digest(original) and
          envelope['previousPreparationSha256']==digest(previous),'continuation-integrity')
    current=envelope['continuation']
    check(len(preparation.encoded(current).encode())<=preparation.MAX_RECORD,'continuation-evidence-cap')
    preparation.validate_record(book,current,now)
    relationship(original,previous,current)
    if book.db.execute("SELECT 1 FROM sqlite_master WHERE name='admission_exit_signing'").fetchone():
        row=book.db.execute('SELECT at_ms FROM admission_exit_signing ORDER BY seq LIMIT 1').fetchone()
        check(row is not None and row[0]>=current['recordedAtMs'],'continuation-after-signing')
    return current


def write_record(book,envelope):
    book.db.execute('CREATE TABLE admission_exit_continuation (id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL,hash TEXT NOT NULL)')
    book.db.execute('INSERT INTO admission_exit_continuation VALUES(1,?,?)',(preparation.encoded(envelope),digest(envelope)))


@view.cycles.binding.operation
def prepare(home,wallet,pool,evidence,collection,*,expected_original_sha256,expected_current_sha256,
            allow_unsigned_continuation=False,clock=view.now):
    check(allow_unsigned_continuation is True,'explicit-unsigned-continuation-required')
    pair=(expected_original_sha256,expected_current_sha256);preserved.identities(pair)
    from admission_exit_collection import MAX_COLLECTION,review
    check(len(preparation.encoded(evidence).encode())<=preparation.MAX_RECORD and
          len(preparation.encoded(collection).encode())<=MAX_COLLECTION,'continuation-input-cap')
    evidence=deepcopy(evidence);collection=deepcopy(collection)
    with view.cycles.c.source_lock(home,wallet) as root:
        book=preparation.entry.submission._open(root,wallet,pool,clock)
        try:
            with book.j.transaction():
                with read_only_journals():
                    reader=preparation.entry.submission._open(root,wallet,pool,clock)
                    try:
                        previous=eligible(reader,root,pair,clock())
                        original=preparation.original_saved(reader,clock())
                        from admission_lifecycle import projection
                        phase,_,_,_,_,_=projection(reader,root,wallet,pool,clock)
                        check(phase=='exit-prepared','continuation-lifecycle-conflict')
                        now=clock();binding=preparation.review(reader,evidence,now)
                        binding=review(reader,evidence,collection,now,binding)
                        check(digest(reader.read()[0])==collection['provenance']['identity']['admissionStateSha256'],
                              'continuation-admission-changed')
                        current=dict(format=preparation.COLLECTED_FORMAT,recordedAtMs=now,
                                     evidence=evidence,collection=collection,binding=binding)
                        relationship(original,previous,current)
                        eligible(reader,root,pair,clock())
                    finally:reader.close()
                envelope=dict(format=VERSION+'-record',originalPreparationSha256=pair[0],
                              previousPreparationSha256=pair[1],continuation=current)
                check(len(preparation.encoded(envelope).encode())<=MAX_RECORD,'continuation-record-cap')
                end=clock();check(now<=end<binding['validUntilExclusiveMs'],'continuation-expired-before-write')
                write_record(book,envelope)
                check(book.db.execute('PRAGMA page_count').fetchone()[0]*book.db.execute('PRAGMA page_size').fetchone()[0]<=64*1024*1024,'continuation-ledger-size-cap')
                end=clock();check(now<=end<binding['validUntilExclusiveMs'],'continuation-expired-before-commit')
                check(not view.cycles.c.submit.swap.stop(root) and book.read()[0]['state']=='signed-recorded','continuation-stopped')
                check(not any(os.path.lexists(book.j.path.parent/name) for name in replacement.MARKERS),'continuation-backend-marker')
                return dict(preparation.public(current,end,created=True),format=VERSION,
                    originalPreparationSha256=pair[0],previousPreparationSha256=pair[1],
                    continuationCount=1,originalPreserved=True,replacementPreserved=True,
                    existingReplacementLimitUnchanged=True,automaticContinuationAllowed=False)
        finally:book.close()


@view.cycles.binding.operation
@fresh_signing.timing.signature_replay
@encoding_replay.operation
@admission_history_replay.operation
def collect_and_prepare(home,wallet,pool,*,expected_original_sha256,expected_current_sha256,
                        allow_unsigned_continuation=False,opener=None,clock=view.now,monotonic=time.monotonic):
    check(allow_unsigned_continuation is True,'explicit-unsigned-continuation-required')
    pair=(expected_original_sha256,expected_current_sha256);preserved.identities(pair)
    from admission_exit_capture import collect
    items=[]
    result=collect(home,wallet,pool,opener=opener,clock=clock,monotonic=monotonic,
                   _continuation_expected=pair,_evidence_sink=items.append)
    if result['state']!='exit-evidence-collected-research-only':return result
    check(len(items)==1,'continuation-collection-handoff')
    envelope=items[0];evidence=envelope.pop('evidence')
    prepared=prepare(home,wallet,pool,evidence,envelope,expected_original_sha256=pair[0],
        expected_current_sha256=pair[1],allow_unsigned_continuation=True,clock=clock)
    return dict(prepared,collectionRequestsThisRun=result['networkRequests'])
