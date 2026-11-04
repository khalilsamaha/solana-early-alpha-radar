"""Real disposable ledgers and synthetic fixed-order RPC; never user keys or sockets."""
from contextlib import contextmanager
from unittest.mock import patch
import json
import preserved_exit_observation as m
import unsigned_exit_replacement_checks as previous
import admission_exit_capture_checks as fixture
from paired_checks import shift
from preflight_checks import fake_key


@contextmanager
def case():
    with previous.case() as c:
        replacement=c.run()
        assert replacement.get('createdThisRun'),replacement
        c.current=replacement['recordSha256']
        first,second,_=fixture.setup(c)
        shift(first,60000,20);shift(second,60000,20)
        first['evidence']['blockTime']['result']+=60
        second['capture']['evidence']['blockTime']['result']+=60
        c.timer.at+=30000
        c.rpc=fixture.Opener(first,second)
        c.rpc.rows[7]['value']['blockhash']=fake_key('preserved-observation-only')
        c.observe=lambda **kw:m.observe(c.home,c.wallet,c.pool,
            expected_original_sha256=c.expected,expected_current_sha256=c.current,
            allow_devnet_observation=True,opener=c.rpc,clock=c.clock,monotonic=lambda:0,**kw)
        yield c


def run():
    cases={}
    with case() as c:
        before=c.path.read_bytes();sources={p.name:p.read_bytes() for p in c.home.iterdir()}
        r=c.observe()
        assert r['state']=='preserved-exit-observation-complete',r
        assert len(c.rpc.calls)==20 and r['networkRequests']==20
        assert r['observationTiming']['headroomAfterValidationMs']>0
        assert r['binding']['validUntilExclusiveMs']==r['observationTiming']['originalDeadlineMs']
        assert r['binding']['quantityAtomic']=='98' and r['binding']['protectedInventoryAtomic']=='902'
        assert r['binding']['feeCommitmentRemainingLamports']=='20999'
        assert before==c.path.read_bytes() and sources=={p.name:p.read_bytes() for p in c.home.iterdir()}
        assert r['encodingReplay']['hits']>0 and r['encodingReplay']['entries']<=512
        assert not any(r[k] for k in ('preparationPersisted','replacementAppended','signaturesCreated',
            'transactionsSent','privateKeyAccessed','reservationReleased','validForSubmission'))
        assert not any(x in json.dumps(r) for x in ('unsignedTransactionBase64','secretKey'))
        cases['fresh-twenty-request-observation-keeps-journals-and-holds']='passed'
        cases['public-report-excludes-wire-and-execution-capability']='passed'
        cases['encoding-scope-bounded-and-observation-headroom-labelled']='passed'
        # Writers must still reject a second replacement even after this successful observation.
        repeat=c.run()
        assert repeat['diagnosticCode']=='replacement-limit-reached' and repeat['networkRequests']==0
        assert before==c.path.read_bytes()
        cases['successful-observation-does-not-reopen-replacement-slot']='passed'
    with case() as c:
        import sqlite3
        blocked=[]
        def competing_write(n,body,rpc):
            if n!=10:return
            db=sqlite3.connect(c.path,timeout=0,isolation_level=None)
            try:
                try:db.execute('UPDATE admission_exit_replacement SET hash=hash')
                except sqlite3.OperationalError as exc:
                    assert 'locked' in str(exc)
                    blocked.append(True)
                else:raise AssertionError('writer crossed shared snapshot')
            finally:db.close()
        c.rpc.hook=competing_write;before=c.path.read_bytes();r=c.observe()
        assert r['state']=='preserved-exit-observation-complete' and blocked==[True],r
        assert before==c.path.read_bytes()
        cases['read-only-admission-snapshot-blocks-concurrent-commit']='passed'
    for kind in ('wrong-original','wrong-current','missing-replacement','not-expired','stop',
                 'backend-symlink','signing-table','unknown-schema','rehashed-lineage'):
        with case() as c:
            if kind=='wrong-original':c.expected='0'*64
            if kind=='wrong-current':c.current='1'*64
            if kind=='not-expired':c.timer.at-=30000
            if kind=='stop':(c.home/'STOP').touch(mode=0o600)
            if kind=='backend-symlink':(c.path.parent/m.replacement.MARKERS[0]).symlink_to('absent')
            if kind in ('missing-replacement','signing-table','unknown-schema','rehashed-lineage'):
                b=c.book()
                try:
                    if kind=='missing-replacement':b.db.execute('DROP TABLE admission_exit_replacement')
                    elif kind=='signing-table':b.db.execute('CREATE TABLE admission_exit_signing (seq INTEGER)')
                    elif kind=='unknown-schema':b.db.execute('CREATE TABLE admission_unknown (seq INTEGER)')
                    else:
                        row=json.loads(b.db.execute('SELECT value FROM admission_exit_replacement').fetchone()[0])
                        row['originalPreparationSha256']='f'*64
                        b.db.execute('UPDATE admission_exit_replacement SET value=?,hash=?',
                            (m.replacement.preparation.encoded(row),m.digest(row)))
                finally:b.close()
            before=c.path.read_bytes();r=c.observe()
            assert r['state']=='preserved-exit-observation-unavailable' and r['networkRequests']==0,(kind,r)
            assert not c.rpc.calls and before==c.path.read_bytes()
            cases[kind+'-refused-before-rpc']='passed'
    for kind in ('stop-during','expiry','clock-regression','timeout','cluster','simulation','marker-during',
                 'provenance-change','validation-expiry'):
        with case() as c:
            def hook(n,body,rpc):
                if n==10:
                    if kind=='stop-during':(c.home/'STOP').touch(mode=0o600)
                    if kind=='expiry':c.timer.at+=10000
                    if kind=='clock-regression':c.timer.at-=10000
                    if kind=='timeout':rpc.rows[0]=TimeoutError('PRIVATE_ERROR')
                    if kind=='marker-during':(c.path.parent/m.replacement.MARKERS[0]).touch(mode=0o600)
                if n==20 and kind=='cluster':rpc.rows[0]='bad-cluster'
                if n==19 and kind=='simulation':rpc.rows[0]['value']['err']={'PRIVATE_ERROR':'unknown'}
            c.rpc.hook=hook
            original=m.validate
            def validate(*args):
                if kind=='validation-expiry':c.timer.at+=10000
                if kind=='provenance-change':args[4]['requestTrace'][0]['parametersSha256']='0'*64
                return original(*args)
            before=c.path.read_bytes()
            with patch.object(m,'validate',side_effect=validate):r=c.observe()
            assert r['state']=='preserved-exit-observation-unavailable',(kind,r)
            assert len(c.rpc.calls)<=20 and r['binding'] is None and r['provenance'] is None
            assert before==c.path.read_bytes() and 'PRIVATE_ERROR' not in json.dumps(r)
            cases[kind+'-fails-closed-without-write']='passed'
    with patch.object(m.view.cycles.c,'source_lock',side_effect=AssertionError('source touched')):
        for flag in (False,1,'yes'):
            try:m.observe('/missing','w','p',expected_original_sha256='0'*64,
                expected_current_sha256='1'*64,allow_devnet_observation=flag)
            except ValueError:pass
            else:raise AssertionError('opt-in accepted')
        for pair in (('0'*64,'0'*64),('bad','1'*64)):
            try:m.observe('/missing','w','p',expected_original_sha256=pair[0],
                expected_current_sha256=pair[1],allow_devnet_observation=True)
            except ValueError:pass
            else:raise AssertionError('identity accepted')
    cases['exact-opt-in-and-distinct-identities-before-access']='passed'
    return dict(format=m.VERSION+'-check',state='offline-checks-passed',casesPassed=len(cases),cases=cases,
        realNetworkRequests=0,privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,
        productionLedgerUpdated=False,executionApproved=False)
