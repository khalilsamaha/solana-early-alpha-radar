"""Disposable journals and synthetic RPC for the bounded third-generation contract."""
from copy import deepcopy
from pathlib import Path
import json
import subprocess
from unittest.mock import patch
import unsigned_exit_continuation as m
from preserved_exit_checks import case
from unsigned_exit_replacement_checks import rows
from core import check


def collect(c):
    return m.collect_and_prepare(c.home,c.wallet,c.pool,expected_original_sha256=c.expected,
        expected_current_sha256=c.current,allow_unsigned_continuation=True,
        opener=c.rpc,clock=c.clock,monotonic=lambda:0)


def private_capture(c):
    import admission_exit_capture
    items=[]
    r=admission_exit_capture.collect(c.home,c.wallet,c.pool,opener=c.rpc,clock=c.clock,
        monotonic=lambda:0,_continuation_expected=(c.expected,c.current),_evidence_sink=items.append)
    check(r['state']=='exit-evidence-collected-research-only','fixture-capture')
    proof=items[0];evidence=proof.pop('evidence');return evidence,proof


def prepare(c,e,p):
    return m.prepare(c.home,c.wallet,c.pool,e,p,expected_original_sha256=c.expected,
        expected_current_sha256=c.current,allow_unsigned_continuation=True,clock=c.clock)


def refused(fn):
    try:fn()
    except (ValueError,KeyError,TypeError,OSError):return
    raise AssertionError('unexpected acceptance')


def run():
    cases={}
    with case() as c:
        preserved={t:rows(c,t) for t in ('admission_exit_preparation','admission_exit_replacement','admission_entry_accounting','admission_events')}
        source={p.name:p.read_bytes() for p in c.home.iterdir()}
        r=collect(c);check(r.get('createdThisRun') and r['continuationCount']==1,'continuation-create')
        check(len(c.rpc.calls)==20 and r['collectionRequestsThisRun']==20,'request-bound')
        check(all(rows(c,t)==v for t,v in preserved.items()),'history-mutated')
        check(source=={p.name:p.read_bytes() for p in c.home.iterdir()},'source-mutated')
        cases['one-twenty-request-continuation-preserves-both-generations-and-accounting']='passed'
        check(r['binding']['quantityAtomic']=='98' and r['binding']['protectedInventoryAtomic']=='902' and
              r['binding']['feeCommitmentRemainingLamports']=='20999','owner-holds')
        check(not any(r[k] for k in ('reservationReleased','allocationTransferred','privateKeyAccessed','signaturesCreated','transactionsSent','executionApproved','validForSubmission')),'public-capability')
        check('unsignedTransactionBase64' not in json.dumps(r),'wire-exposed')
        cases['quantity-protected-inventory-cumulative-holds-and-public-boundaries-preserved']='passed'
        import admission_lifecycle
        from exit_signing_handoff import request_for
        b=c.book()
        try:
            current=m.preparation.saved(b,c.clock())
            check(m.digest(current)==r['recordSha256'],'current-identity')
            check(request_for(current)['validUntilExclusiveMs']==r['binding']['validUntilExclusiveMs'],'request-deadline')
        finally:b.close()
        pristine=c.path.read_bytes()
        for kind in ('original-hash','replacement-hash','continuation-hash','rehashed-lineage','orphan','extra-row','early-signing'):
                b=c.book()
                try:
                    if kind.endswith('-hash'):
                        t={'original-hash':'admission_exit_preparation','replacement-hash':'admission_exit_replacement','continuation-hash':m.TABLE}[kind]
                        b.db.execute('UPDATE '+t+' SET hash=?',('0'*64,))
                    if kind=='rehashed-lineage':
                        v=json.loads(b.db.execute('SELECT value FROM '+m.TABLE).fetchone()[0]);v['previousPreparationSha256']='f'*64
                        b.db.execute('UPDATE '+m.TABLE+' SET value=?,hash=?',(m.preparation.encoded(v),m.digest(v)))
                    if kind=='orphan':b.db.execute('DROP TABLE admission_exit_replacement')
                    if kind=='extra-row':
                        b.db.execute('ALTER TABLE '+m.TABLE+' RENAME TO bad_old')
                        b.db.execute('CREATE TABLE '+m.TABLE+' AS SELECT * FROM bad_old')
                        b.db.execute('INSERT INTO '+m.TABLE+' SELECT * FROM bad_old')
                    if kind=='early-signing':
                        b.db.execute('CREATE TABLE admission_exit_signing (seq INTEGER,at_ms INTEGER)')
                        b.db.execute('INSERT INTO admission_exit_signing VALUES(1,1)')
                    refused(lambda:m.preparation.saved(b,c.clock()))
                finally:
                    b.close()
                    # Disposable fixture only; never an operator recovery path.
                    c.path.write_bytes(pristine)
                cases[kind+'-never-falls-back']='passed'
        phase=admission_lifecycle.inspect(c.home,c.wallet,c.pool,clock=c.clock,monotonic=lambda:0)
        check(phase['coherent'] and phase['phase']=='exit-prepared','lifecycle-continuation')
        cases['reader-lifecycle-and-signing-request-use-exact-third-generation']='passed'
        before=c.path.read_bytes();c.timer.at+=30000
        again=collect(c)
        check(again['networkRequests']==0 and again['diagnosticCode']=='continuation-limit-reached' and c.path.read_bytes()==before,'repeat')
        check(c.run()['diagnosticCode']=='replacement-limit-reached','replacement-reset')
        check(c.observe()['state']=='preserved-exit-observation-unavailable','old-observer-bypass')
        check(c.path.read_bytes()==before,'expired-rewritten')
        cases['expired-third-generation-cannot-reopen-continuation-or-replacement']='passed'
    for kind in ('stop','wrong-original','wrong-current','marker','signing','unknown-schema','not-expired'):
        with case() as c:
            if kind=='stop':(c.home/'STOP').touch(mode=0o600)
            if kind=='wrong-original':c.expected='a'*64
            if kind=='wrong-current':c.current='b'*64
            if kind=='marker':(c.path.parent/m.replacement.MARKERS[0]).symlink_to('missing')
            if kind in ('signing','unknown-schema'):
                b=c.book()
                try:b.db.execute('CREATE TABLE '+('admission_exit_signing' if kind=='signing' else 'admission_unknown')+' (seq INTEGER)')
                finally:b.close()
            if kind=='not-expired':
                b=c.book()
                try:c.timer.at=m.preparation.saved(b,c.clock())['binding']['validUntilExclusiveMs']-100
                finally:b.close()
            before=c.path.read_bytes();r=collect(c)
            check(r['state']=='unavailable' and r['networkRequests']==0 and c.path.read_bytes()==before,'precondition:'+kind)
            cases[kind+'-refused-before-rpc']='passed'
    for kind in ('write-failure','stop','marker','expiry','ledger-cap'):
        with case() as c:
            e,p=private_capture(c);before=c.path.read_bytes();write=m.write_record
            def fault(book,envelope):
                write(book,envelope)
                if kind=='write-failure':raise OSError('synthetic write')
                if kind=='stop':(c.home/'STOP').touch(mode=0o600)
                if kind=='marker':(c.path.parent/m.replacement.MARKERS[1]).touch(mode=0o600)
                if kind=='expiry':c.timer.at+=10000
                if kind=='ledger-cap':book.db.execute('CREATE TABLE cap_fixture (value BLOB)');book.db.execute('INSERT INTO cap_fixture VALUES(zeroblob(67108864))')
            with patch.object(m,'write_record',side_effect=fault):refused(lambda:prepare(c,e,p))
            check(c.path.read_bytes()==before,'rollback:'+kind)
            cases[kind+'-rolls-back-entire-append']='passed'
    with case() as c:
        e,p=private_capture(c);before=c.path.read_bytes()
        p['provenance']['validUntilExclusiveMs']+=10000
        refused(lambda:prepare(c,e,p));check(c.path.read_bytes()==before,'deadline-extended')
        cases['provenance-deadline-extension-refused']='passed'
    with patch.object(m.view.cycles.c,'source_lock',side_effect=AssertionError('source')):
        for value in (False,1,'yes'):
            refused(lambda:m.collect_and_prepare('/missing','w','p',expected_original_sha256='a'*64,expected_current_sha256='b'*64,allow_unsigned_continuation=value))
        for pair in (('a'*64,'a'*64),(None,'b'*64),('a'*64,'X'*64)):
            refused(lambda:m.collect_and_prepare('/missing','w','p',expected_original_sha256=pair[0],expected_current_sha256=pair[1],allow_unsigned_continuation=True))
    cases['exact-opt-in-and-distinct-identities-required-before-access']='passed'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',casesPassed=len(cases),cases=cases,
        realNetworkRequests=0,productionWalletAccessed=False,privateKeyAccessed=False,signaturesCreated=0,
        transactionsSent=0,productionLedgerUpdated=False,runtimeIntegrated=False,executionApproved=False,
        automaticContinuationAllowed=False,originalAndReplacementPreserved=True)


def independent_contract():
    """Use address-consistent disposable source history; no exit key/backend call."""
    import tempfile
    import test_fresh_exit as fixture_module
    from lifecycle_rehearsal import exit_inputs
    from admission_exit_capture_checks import Clock,Opener
    from preflight_checks import fake_key
    from exit_signing_handoff import request_for
    import admission_exit_collection
    class Fixture(fixture_module.ActualBackendTests):pass
    with tempfile.TemporaryDirectory(prefix='radar-continuation-contract-') as owned:
        with patch.object(tempfile,'tempdir',owned),patch('socket.socket',side_effect=AssertionError('real network')):
            f=None;started=False;setup=False
            try:
                started=True;Fixture.setUpClass();f=Fixture();setup=True;f.setUp()
                check(f.home.resolve().is_relative_to(Path(owned).resolve()),'temporary-fixture')
                f.collect();accounting=f.settle()['accounting']
                clock=Clock();clock.at=m.view.now()
                baseline=deepcopy(f.e['costInputs']['baseline']);baseline.update(kind='observed-devnet-deployment',observedAtMs=0)
                with patch.object(m.preparation,'BASELINE',baseline):
                    def rpc(label):
                        first,e=exit_inputs(f.e,accounting,clock())
                        result=Opener(first,e);result.rows[7]['value']['blockhash']=fake_key(label);return result
                    original=admission_exit_collection.collect_and_prepare(f.home,f.wallet,f.pool,opener=rpc('continuation-original'),clock=clock,monotonic=lambda:0)
                    check(original.get('createdThisRun'),'original-fixture')
                    clock.at+=30000
                    previous=m.replacement.collect_and_replace(f.home,f.wallet,f.pool,
                        expected_preparation_sha256=original['recordSha256'],allow_unsigned_replacement=True,
                        opener=rpc('continuation-previous'),clock=clock,monotonic=lambda:0)
                    check(previous.get('createdThisRun'),'previous-fixture')
                    clock.at+=30000
                    current=m.collect_and_prepare(f.home,f.wallet,f.pool,
                        expected_original_sha256=original['recordSha256'],expected_current_sha256=previous['recordSha256'],
                        allow_unsigned_continuation=True,opener=rpc('continuation-current'),clock=clock,monotonic=lambda:0)
                    check(current.get('createdThisRun'),'continuation-fixture')
                    b=m.preparation.entry.submission._open(f.home,f.wallet,f.pool,clock)
                    try:
                        record=m.preparation.saved(b,clock());request=request_for(record)
                        _,_,head,_=b.read();stamp=clock()
                        boundary=dict(state='exit-signing-unknown',request=request,requestSha256=m.digest(request),admissionHeadSha256=head)
                        signing=dict(seq=1,at_ms=stamp,value=m.preparation.encoded(boundary),previous_hash='',
                            hash=m.digest(dict(seq=1,atMs=stamp,value=boundary,previousHash='')))
                        data=dict(policy=b.policy,admissionRows=[dict(r) for r in b.db.execute('SELECT * FROM admission_events ORDER BY seq')],signingRows=[signing])
                        for key,table in (('preparationRow','admission_exit_preparation'),('replacementRow','admission_exit_replacement'),('continuationRow',m.TABLE),('accountingRow','admission_entry_accounting')):
                            data[key]=dict(b.db.execute('SELECT * FROM '+table).fetchone())
                        payload=dict(data=data,metadata=json.loads((f.home/'wallet.json').read_text()),
                            pair=json.loads((f.home/'controlled-pool-v1'/'plan.json').read_text())['pairAccounts'],requestedHash=m.digest(request),now=stamp)
                    finally:b.close()
                    result=subprocess.run(['node',str(Path(__file__).with_name('continuation_exit_contract_checks.mjs'))],
                        input=json.dumps(payload),capture_output=True,text=True,timeout=20,check=True)
                    checks=json.loads(result.stdout)
                    check(checks['casesPassed']==14,'independent-contract-count')
                    return checks
            finally:
                if setup:f.tearDown()
                if started:Fixture.tearDownClass()
                Fixture.ephemeral_exit_key=None
