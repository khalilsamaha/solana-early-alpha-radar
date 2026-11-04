"""Disposable real journals, actual collectors and synthetic RPC; no user scope."""
from contextlib import contextmanager
from copy import deepcopy
import json
from unittest.mock import patch
import unsigned_exit_replacement as m
import admission_exit_collection_checks as old
import admission_exit_capture_checks as fixture
from paired_checks import shift
from preflight_checks import fake_key
import admission_lifecycle
import exit_signing_handoff


@contextmanager
def case():
    with old.case() as c:
        old.collect(c);old.apply(c);e,p,baseline=old.collected(c)
        original=old.prepare(c,e,p,baseline)
        first,second,_=fixture.setup(c)
        # A genuinely later set of synthetic replies is passed through the actual
        # collector. Hashes/provenance are recomputed there, never patched later.
        shift(first,30000,10);shift(second,30000,10)
        first['evidence']['blockTime']['result']+=30
        second['capture']['evidence']['blockTime']['result']+=30
        c.timer=fixture.Clock();c.timer.at+=30000
        c.rpc=fixture.Opener(first,second)
        c.rpc.rows[7]['value']['blockhash']=fake_key('replacement-collected-exit')
        c.expected=original['recordSha256'];c.original=original
        def clock():c.now=c.timer();return c.now
        c.clock=clock
        c.run=lambda:m.collect_and_replace(c.home,c.wallet,c.pool,
            expected_preparation_sha256=c.expected,allow_unsigned_replacement=True,
            opener=c.rpc,clock=c.clock,monotonic=lambda:0)
        c.items=[]
        def capture():
            import admission_exit_capture
            r=admission_exit_capture.collect(c.home,c.wallet,c.pool,opener=c.rpc,clock=c.clock,
                monotonic=lambda:0,_evidence_sink=c.items.append,_replacement_expected=c.expected)
            assert r['state']=='exit-evidence-collected-research-only',r
            envelope=deepcopy(c.items[0]);evidence=envelope.pop('evidence')
            return evidence,envelope
        c.capture=capture
        c.replace=lambda e,p:m.replace(c.home,c.wallet,c.pool,e,p,
            expected_preparation_sha256=c.expected,allow_unsigned_replacement=True,clock=c.clock)
        with patch.object(m.preparation,'BASELINE',baseline),patch.object(m.view,'read_locked',return_value=c.e['costInputs']['reservations']),patch('socket.socket',side_effect=AssertionError('real network')):
            yield c


def rows(c,table):
    b=c.book()
    try:return [tuple(r) for r in b.db.execute('SELECT * FROM '+table).fetchall()]
    finally:b.close()


def run():
    cases={}
    with case() as c:
        original=rows(c,'admission_exit_preparation');entry=rows(c,'admission_entry_accounting')
        source={p.name:p.read_bytes() for p in c.home.iterdir()}
        r=c.run();assert r['createdThisRun'] and r['replacementCount']==1,r
        assert len(c.rpc.calls)==20 and r['collectionRequestsThisRun']==20
        cases['twenty-request-collection-appends-one-replacement']='passed'
        assert rows(c,'admission_exit_preparation')==original and rows(c,'admission_entry_accounting')==entry
        assert source=={p.name:p.read_bytes() for p in c.home.iterdir()}
        cases['original-record-entry-accounting-and-source-preserved']='passed'
        assert r['binding']['quantityAtomic']=='98' and r['binding']['feeCommitmentRemainingLamports']=='20999'
        assert r['binding']['protectedInventoryAtomic']=='902' and not r['reservationReleased']
        cases['owned-quantity-protected-inventory-and-fee-holds-preserved']='passed'
        b=c.book()
        try:
            current=m.preparation.saved(b,c.now)
            assert m.digest(m.preparation.original_saved(b,c.now))==c.expected
            request=exit_signing_handoff.request_for(current)
            assert request['preparationSha256']==r['recordSha256'] and request['validUntilExclusiveMs']==r['binding']['validUntilExclusiveMs']
            assert current['collection']['provenance']['startedAtMs']>=c.original['binding']['validUntilExclusiveMs']
        finally:b.close()
        cases['current-reader-and-signer-request-bind-new-evidence-not-old-deadline']='passed'
        before=c.path.read_bytes();c.timer.at+=30000
        r2=c.run();assert r2['networkRequests']==0 and r2['diagnosticCode']=='replacement-limit-reached',r2
        assert len(c.rpc.calls)==20 and before==c.path.read_bytes()
        cases['second-replacement-refused-without-requests-or-mutation']='passed'
        r3=admission_lifecycle.inspect(c.home,c.wallet,c.pool,clock=c.clock,monotonic=lambda:0)
        assert r3['coherent'] and r3['phase']=='exit-prepared',r3
        cases['expired-replacement-remains-readable-with-held-position']='passed'
        b=c.book()
        try:
            envelope=json.loads(b.db.execute('SELECT value FROM admission_exit_replacement').fetchone()[0])
            envelope['originalPreparationSha256']='0'*64
            b.db.execute('UPDATE admission_exit_replacement SET value=?,hash=?',(m.preparation.encoded(envelope),m.digest(envelope)))
        finally:b.close()
        r4=admission_lifecycle.inspect(c.home,c.wallet,c.pool,clock=c.clock,monotonic=lambda:0)
        assert not r4['coherent'] and r4['scopedAccounting'] is None
        cases['rehashed-lineage-conflict-never-falls-back-to-original']='passed'
    for kind in ('stop','marker','signing','wrong-identity','not-expired'):
        with case() as c:
            if kind=='stop':(c.home/'STOP').touch(mode=0o600)
            if kind=='marker':(c.path.parent/m.MARKERS[0]).symlink_to(c.path.parent/'missing')
            if kind=='signing':
                b=c.book()
                try:b.db.execute('CREATE TABLE admission_exit_signing (seq INTEGER)')
                finally:b.close()
            if kind=='wrong-identity':c.expected='0'*64
            if kind=='not-expired':c.timer.at=c.original['binding']['validUntilExclusiveMs']-1000
            before=c.path.read_bytes();r=c.run()
            assert r['state']=='unavailable' and not c.rpc.calls and before==c.path.read_bytes(),r
        cases[kind+'-refused-before-rpc']='passed'
    for kind in ('write-failure','stop-before-commit','expiry-before-commit','marker-before-commit'):
        with case() as c:
            e,p=c.capture();before=c.path.read_bytes();write=m.write_record
            def fault(book,envelope):
                write(book,envelope)
                if kind=='write-failure':raise OSError('synthetic storage failure')
                if kind=='stop-before-commit':(c.home/'STOP').touch(mode=0o600)
                if kind=='expiry-before-commit':c.timer.at+=30000
                if kind=='marker-before-commit':(c.path.parent/m.MARKERS[1]).touch(mode=0o600)
            with patch.object(m,'write_record',side_effect=fault):old.refuses(lambda:c.replace(e,p))
            assert before==c.path.read_bytes()
        cases[kind+'-rolls-back-whole-append']='passed'
    with patch.object(m.view.cycles.c,'source_lock',side_effect=AssertionError('source')):
        for flag in (False,1,'yes'):
            old.refuses(lambda:m.replace('/missing','w','p',{}, {},expected_preparation_sha256='0'*64,allow_unsigned_replacement=flag))
            old.refuses(lambda:m.collect_and_replace('/missing','w','p',expected_preparation_sha256='0'*64,allow_unsigned_replacement=flag))
    cases['exact-replacement-opt-in-required-before-access']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',casesPassed=len(cases),cases=cases,
        mode='synthetic-offline',realNetworkRequests=0,privateKeyAccessed=False,signaturesCreated=0,
        transactionsSent=0,productionLedgerUpdated=False,originalPreparationPreserved=True,
        automaticReplacementAllowed=False,executionApproved=False,runtimeIntegrated=False)
