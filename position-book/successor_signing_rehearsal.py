"""Complete successor key rehearsal: temporary full source, real clocks, no network."""
from contextlib import contextmanager
from copy import deepcopy
import base64
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

import successor_signing_integration as m
from core import check
from contract import Rejected
from lifecycle_rehearsal import exit_inputs
from continuation_exit_checks import fixture_size,prepare_fixture,require_cold_reuse_scopes
from continuation_diagnostics import locations

VERSION='successor-signing-rehearsal-1'
FIXTURE_SETUP_VERSION='successor-fixture-setup-2'
DIAGNOSTIC_CODES=frozenset(('quote-read-stale-or-future','admission-raw-evidence',
    'admission-completion-clock','admission-read-deadline','reservation-read-deadline',
    'handoff-deadline','fixture-reuse-scope-leaked','temporary-scope','fixture-size',
    'rehearsal-request-count','rehearsal-independent-signature','rehearsal-original-deadline','rehearsal-parent-ack'))


def setup_history(fixture):
    """Bounded exact-content reuse for disposable history only; real clocks.

    This owner must end before instance setup and the measured successor path.
    No validation outcome, timing limit or signing rule is replaced.
    """
    require_cold_reuse_scopes()
    def construct():
        fixture.setUpClass()
        return {}
    try:return prepare_fixture(construct)
    finally:require_cold_reuse_scopes()

@contextmanager
def phase(report,name):
    row=dict(phase=name,elapsedMs=None,completed=False);report['phases'].append(row)
    start=time.monotonic()
    try:
        yield row;row['completed']=True
    except Exception as exc:
        report['failedPhase']=name;row['exceptionType']=type(exc).__name__ if type(exc).__name__ in ('ValueError','Rejected','AssertionError','OSError','TimeoutError','TimeoutExpired','CalledProcessError') else 'unclassified'
        row['diagnosticCode']=(exc.args[0] if type(exc) in (ValueError,Rejected) and len(exc.args)==1
            and type(exc.args[0]) is str and exc.args[0] in DIAGNOSTIC_CODES else 'unclassified')
        row['codeLocations']=locations(exc)
        raise
    finally:row['elapsedMs']=round((time.monotonic()-start)*1000,3)


def connected(f,report):
    import admission_exit as exit_contract
    import admission_exit_collection as original_collection
    import restricted_exit_signer as original_backend
    from admission_exit_capture_checks import Opener
    from test_expired_exit_evidence import Replies
    from preflight_checks import fake_key
    from paired_checks import shift
    clock=m.view.now
    with phase(report,'entry-receipt-accounting'):
        f.collect();accounting=f.settle()['accounting']
    baseline=deepcopy(f.e['costInputs']['baseline']);baseline.update(kind='observed-devnet-deployment',observedAtMs=0)
    with patch.object(exit_contract,'BASELINE',baseline):
        key=f.home/'signer.pk8';key.write_bytes(f.ephemeral_exit_key);key.chmod(0o600)
        with phase(report,'retired-predecessor-setup'):
            def build_old():
                first,e=exit_inputs(f.e,accounting,clock())
                prepared=original_collection.collect_and_prepare(f.home,f.wallet,f.pool,opener=Opener(first,e),clock=clock)
                check(prepared.get('createdThisRun') is True,'fixture-original-preparation')
                signed=original_backend.dispatch(f.home,f.wallet,f.pool,allow_private_key_signing=True,clock=clock)
                check(signed['state']=='exit-signed-recorded','fixture-original-signature')
                return prepared
            old=prepare_fixture(build_old);require_cold_reuse_scopes()
        with phase(report,'predecessor-expiry-wait'):
            time.sleep(max(0,(old['binding']['validUntilExclusiveMs']-clock())/1000)+0.01)
        with phase(report,'predecessor-retirement'):
            def get_context():
                with m.view.cycles.c.source_lock(f.home,f.wallet) as root,m.read_only_journals():
                    b=m.handoff.preparation.entry.submission._open(root,f.wallet,f.pool,clock)
                    try:return m.successor.expiry.context(root,b,f.wallet,f.pool,old['recordSha256'],clock)
                    finally:b.close()
            ctx=prepare_fixture(get_context)
            c=SimpleNamespace(now=clock())
            retired=prepare_fixture(m.successor.retirement.retire,f.home,f.wallet,f.pool,old['recordSha256'],allow_retire=True,
                opener=Replies(c,ctx),clock=clock)
            check(retired['state']=='exit-retired-held','fixture-retirement')
        before_source={str(p):p.read_bytes() for p in f.home.rglob('*') if p.is_file()}
        b=m.handoff.preparation.entry.submission._open(f.home,f.wallet,f.pool,clock)
        try:
            before_tables=table_rows(b)
            path=b.j.path
        finally:b.close()
        old_files={name:(path.parent/name).read_bytes() for name in ('exit-signer-attempt.json','exit-signer-ack.json')}
        providers=[]
        class Expiry:
            def open(self,request,timeout):
                if not providers:providers.append(Replies(SimpleNamespace(now=clock()),ctx))
                return providers[0].open(request,timeout)
        quotes=[]
        class Quote:
            def open(self,request,timeout):
                if not quotes:
                    # Real elapsed setup is included in the original collection deadline.
                    first,e=exit_inputs(f.e,accounting,clock());shift(first,0,100);shift(e,0,100)
                    q=Opener(first,e);q.rows[7]['value']['blockhash']=fake_key('successor-rehearsal-distinct-blockhash')
                    quotes.append(q)
                return quotes[0].open(request,timeout)
        with phase(report,'collection-persistence-independent-signing') as measured:
            require_cold_reuse_scopes();start=time.monotonic()
            result=m._collect_sign(f.home,f.wallet,f.pool,old['recordSha256'],retired['retirementSha256'],
                    allow_unsigned_successor=True,allow_private_key_signing=True,clock=clock,
                    _expiry_opener=Expiry(),_quote_opener=Quote())
            require_cold_reuse_scopes()
            report['integration']=result
            report['integrationElapsedMs']=round((time.monotonic()-start)*1000,3)
            report['headroomAtReturnMs']=(result['originalDeadlineMs']-clock()) if result['originalDeadlineMs'] else None
            check(result['collectionRequests']==28,'rehearsal-request-count')
            check(result['signerInvocationAttempts']==1 and result['signatureCreatedThisRun'] is True,'rehearsal-independent-signature')
            check(report['headroomAtReturnMs']>0,'rehearsal-original-deadline')
            check(result['state']=='successor-signed-within-deadline' and result['signerAcknowledgmentValidated'],'rehearsal-parent-ack')
            check((path.parent/m.backend.ACK).is_file(),'rehearsal-durable-ack')
        report['cases']['full-collector-persistence-and-independent-process-before-deadline']='passed'
        report['cases']['parent-acknowledgment-is-durable-before-completion']='passed'
        with phase(report,'keyless-ack-recovery'):
            key.unlink();(f.home/'STOP').touch(mode=0o600)
            with patch.object(m.backend,'_invoke',side_effect=AssertionError('unexpected signer')):
                recovered=m._recover(f.home,f.wallet,f.pool,result['successorSha256'],clock=clock)
            check(recovered['state']=='successor-signed-recorded' and not recovered['backendInvokedThisRun'],'rehearsal-keyless-recovery')
        report['cases']['keyless-recovery-after-stop']='passed'
        with phase(report,'repeated-recovery-and-original-holds'):
            frozen=path.read_bytes()
            with patch.object(m.backend,'_invoke',side_effect=AssertionError('unexpected signer')):
                again=m._recover(f.home,f.wallet,f.pool,result['successorSha256'],clock=clock)
            check(path.read_bytes()==frozen and again['headSha256']==recovered['headSha256'],'rehearsal-repeat-recovery')
            b=m.handoff.preparation.entry.submission._open(f.home,f.wallet,f.pool,clock)
            try:
                after=table_rows(b)
                check(all(after[k]==v for k,v in before_tables.items()),'rehearsal-old-evidence-changed')
                check(set(after)-set(before_tables)=={'admission_exit_successor','admission_successor_signing'},'rehearsal-unexpected-tables')
                from admission_recovery import retirement_projection
                report['heldAccounting']=prepare_fixture(retirement_projection,b,f.home,f.wallet,f.pool,clock)['scopedAccounting']
            finally:b.close()
            for name,raw in old_files.items():check((path.parent/name).read_bytes()==raw,'rehearsal-old-marker-changed')
            for name,raw in before_source.items():
                if Path(name)!=key:check(Path(name).read_bytes()==raw,'rehearsal-historical-source-changed')
        report['cases']['duplicate-recovery-does-not-write-or-resign']='passed'
        report['cases']['all-retired-records-markers-and-cumulative-holds-preserved']='passed'
        report['originalSourceUnchanged']=True


def table_rows(book):
    names=[r[0] for r in book.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {name:[tuple(r) for r in book.db.execute('SELECT * FROM '+name)] for name in names}


def run():
    import test_fresh_exit as fixture_module
    class Fixture(fixture_module.ActualBackendTests):pass
    report=dict(format=VERSION,state='review-required',cases={},casesPassed=0,phases=[],failedPhase=None,
        fixtureSetupVersion=FIXTURE_SETUP_VERSION,fixtureSetupReuse=None,
        mode='synthetic-offline',realNetworkRequests=0,transactionsSent=0,productionWalletAccessed=False,
        productionLedgerUpdated=False,scannerRuntimeChanged=False,disposableTestKeySigning=True,
        realClocks=True,programFixtureBytes=None,integration=None,originalSourceUnchanged=False,
        temporaryLedgersRemoved=False,executionApproved=False,liveSenderIntegrated=False,
        limitations=['Synthetic RPC replies; local timings exclude real network and finality delays.',
            'One 1 MiB connected fixture; no real-wallet execution, sender or receipt settlement.',
            'Original ten-second collection deadline and cumulative holds are unchanged.',
            'Completion recovery never creates another signature; component faults test lost child replies.'])
    with tempfile.TemporaryDirectory(prefix='radar-successor-rehearsal-') as owned,fixture_size(True):
        started=False;setup=False;f=None
        with patch.object(tempfile,'tempdir',owned),patch('socket.socket',side_effect=AssertionError('real network')):
            try:
                with phase(report,'fixture-class-setup'):
                    started=True;report['fixtureSetupReuse']=setup_history(Fixture)
                with phase(report,'fixture-instance-setup'):
                    f=Fixture();setup=True;f.setUp()
                    check(f.home.resolve().is_relative_to(Path(owned).resolve()),'temporary-scope')
                    report['programFixtureBytes']=len(base64.b64decode(f.e['costInputs']['capture']['evidence']['accounts']['result']['value'][-1]['data'][0]))
                    check(report['programFixtureBytes']==1024*1024,'fixture-size')
                connected(f,report);report['state']='offline-integration-passed'
            except Exception:report['state']='review-required'
            finally:
                try:
                    with phase(report,'fixture-cleanup'):
                        if setup:f.tearDown()
                        if started:Fixture.tearDownClass()
                except Exception:report['state']='review-required'
                finally:Fixture.ephemeral_exit_key=None
    report['temporaryLedgersRemoved']=not Path(owned).exists();report['casesPassed']=len(report['cases'])
    return report
