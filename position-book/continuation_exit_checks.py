"""Offline continuation-to-transport exercise with disposable keys and synthetic RPC."""
from copy import deepcopy
from contextlib import contextmanager
from functools import wraps
import base64
from pathlib import Path
import tempfile
import json
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import patch
import fresh_exit as m
from core import check
from contract import digest
from lifecycle_rehearsal import exit_inputs,leg
from unsigned_exit_replacement_checks import rows
from preserved_exit_checks import case
from continuation_diagnostics import phase,observation

VERSION='continuation-exit-integration-1'


@m.fresh_signing.timing.signature_replay
@m.encoding_replay.operation
@m.admission_history_replay.operation
@m.serialization_replay.operation
@m.canonical_replay.operation
def prepare_fixture(fn,*args,**kwargs):
    """Optimize only disposable predecessor construction; keep every real clock.

    These are fresh independent scopes for each prerequisite. They end before
    the measured continuation; ordinary production preparation is not changed.
    """
    return fn(*args,**kwargs)


def require_cold_reuse_scopes():
    scopes=(m.canonical_replay._SCOPE,m.serialization_replay._SCOPE,m.encoding_replay._SCOPE,
            m.admission_history_replay._SCOPE,m.fresh_signing.timing.wire._SIGNATURE_SCOPE)
    check(all(scope.get() is None for scope in scopes),'fixture-reuse-scope-leaked')


def fault_checks():
    cases={}
    for kind in ('stop','wrong-original','wrong-current','marker','write-failure','budget','lost-signer','deadline','stop-after-write','persisted-expiry'):
        with case() as c:
            signs=[];mono=[0];write=m.continuation.write_record
            def adapter(root,request):
                signs.append(request)
                raise TimeoutError('private synthetic signer response')
            if kind=='stop':(c.home/'STOP').touch(mode=0o600)
            if kind=='wrong-original':c.expected='0'*64
            if kind=='wrong-current':c.current='0'*64
            if kind=='marker':(c.path.parent/m.backend.ATTEMPT).touch(mode=0o600)
            def hook(book,envelope):
                write(book,envelope)
                if kind=='write-failure':raise OSError('private synthetic storage')
                if kind=='budget':mono[0]=30
                if kind=='stop-after-write':(c.home/'STOP').touch(mode=0o600)
            def collector_hook(n,q,o):
                if kind=='deadline' and n==20:c.timer.at+=10000
            c.rpc.hook=collector_hook
            before={t:rows(c,t) for t in ('admission_exit_preparation','admission_exit_replacement','admission_entry_accounting')}
            prepare=m.continuation.collect_and_prepare
            def delayed(*args,**kwargs):
                result=prepare(*args,**kwargs)
                if kind=='persisted-expiry' and result.get('createdThisRun'):c.timer.at+=10000
                return result
            with patch.object(m.continuation,'write_record',hook),patch.object(m.continuation,'collect_and_prepare',delayed):
                with patch.object(m.backend,'_invoke',adapter):
                    r=m.continue_sign_submit(c.home,c.wallet,c.pool,
                        expected_original_sha256=c.expected,expected_current_sha256=c.current,
                        allow_unsigned_continuation=True,allow_private_key_signing=True,allow_devnet_submit=True,
                        collection_opener=c.rpc,clock=c.clock,monotonic=lambda:mono[0])
            check(r['sendRequestsThisRun']==0 and r['senderRequests']==0,'fault-send')
            check(len(signs)==(1 if kind=='lost-signer' else 0),'fault-sign')
            check(r['collectionRequests']==(0 if kind in ('stop','wrong-original','wrong-current','marker') else 20),'fault-count')
            check(all(rows(c,t)==v for t,v in before.items()),'fault-predecessors')
            if kind in ('budget','lost-signer','persisted-expiry'):
                persisted=rows(c,'admission_exit_continuation')
                with patch.object(m.backend,'_invoke',adapter):
                    again=m.continue_sign_submit(c.home,c.wallet,c.pool,
                        expected_original_sha256=c.expected,expected_current_sha256=c.current,
                        allow_unsigned_continuation=True,allow_private_key_signing=True,allow_devnet_submit=True,
                        clock=c.clock,monotonic=lambda:0)
                check(again['networkRequests']==0 and len(signs)==(kind=='lost-signer') and
                      rows(c,'admission_exit_continuation')==persisted,'fault-repeat')
            if kind=='lost-signer':
                check(r['privateKeyAccessed'] is None and r['signaturesCreated'] is None,'fault-unknown')
            cases[kind+'-preserves-one-attempt-boundaries']='passed'
    with patch.object(m.view.cycles.c,'source_lock',side_effect=AssertionError('scope accessed')):
        for name in ('allow_unsigned_continuation','allow_private_key_signing','allow_devnet_submit'):
            for value in (False,1,'yes'):
                opts=dict(allow_unsigned_continuation=True,allow_private_key_signing=True,allow_devnet_submit=True)
                opts[name]=value
                try:m.continue_sign_submit('/missing','w','p',expected_original_sha256='a'*64,expected_current_sha256='b'*64,**opts)
                except ValueError:pass
                else:raise AssertionError('opt-in accepted')
        try:m.prepare_sign_submit('/missing','w','p',allow_private_key_signing=True,
            allow_devnet_submit=True,_continuation_expected=('a'*64,'b'*64))
        except ValueError:pass
        else:raise AssertionError('ordinary wrapper accepted continuation')
    cases['three-exact-opt-ins-and-no-ordinary-wrapper-bypass']='passed'
    return cases


def connected(fixture,report):
    from admission_exit_capture_checks import Opener
    from exit_submission_checks import FakeRpc
    from preflight_checks import fake_key
    f=fixture;clock=m.view.now
    with phase(report,'entry-collection'):f.collect()
    with phase(report,'entry-settlement') as diagnostic:
        settled=f.settle();diagnostic['observation']=observation(settled)
        accounting=settled['accounting']
    baseline=deepcopy(f.e['costInputs']['baseline']);baseline.update(kind='observed-devnet-deployment',observedAtMs=0)
    with patch.object(m.collection.exit,'BASELINE',baseline):
        with phase(report,'original-preparation') as diagnostic:
            first,e=exit_inputs(f.e,accounting,clock())
            old=prepare_fixture(m.collection.collect_and_prepare,f.home,f.wallet,f.pool,opener=Opener(first,e),clock=clock)
            diagnostic['observation']=observation(old)
            diagnostic['fixtureCanonicalDigestReplay']=m.canonical_replay.summary(old.get('canonicalDigestReplay'))
            require_cold_reuse_scopes()
            check(old.get('createdThisRun') is True,'original-not-prepared')
        # Let actual wall time expire the synthetic original. Never move the real
        # signer's clock or widen the ten-second collection window to make a pass.
        with phase(report,'original-expiry-wait') as diagnostic:
            time.sleep(max(0,(old['binding']['validUntilExclusiveMs']-clock())/1000)+0.01)
        with phase(report,'replacement-preparation') as diagnostic:
            first,e=exit_inputs(f.e,accounting,clock());prior_rpc=Opener(first,e)
            prior_rpc.rows[7]['value']['blockhash']=fake_key('continuation-previous-blockhash')
            previous=prepare_fixture(m.replacement.collect_and_replace,f.home,f.wallet,f.pool,
                expected_preparation_sha256=old['recordSha256'],allow_unsigned_replacement=True,
                opener=prior_rpc,clock=clock)
            diagnostic['observation']=observation(previous)
            diagnostic['fixtureCanonicalDigestReplay']=m.canonical_replay.summary(previous.get('canonicalDigestReplay'))
            require_cold_reuse_scopes()
            check(previous.get('createdThisRun') is True,'previous-not-prepared')
        with phase(report,'replacement-expiry-wait') as diagnostic:
            time.sleep(max(0,(previous['binding']['validUntilExclusiveMs']-clock())/1000)+0.01)
        with phase(report,'predecessor-snapshot') as diagnostic:
            f.stamp=clock()
            b=m.submission.transport._open(f.home,f.wallet,f.pool,clock)
            try:
                original=list(b.db.execute('SELECT * FROM admission_exit_preparation'))
                previous_rows=list(b.db.execute('SELECT * FROM admission_exit_replacement'))
                entry=list(b.db.execute('SELECT * FROM admission_entry_accounting'))
            finally:b.close()
            source={p.name:p.read_bytes() for p in f.home.iterdir() if p.is_file()}
        with phase(report,'continuation-fixture-inputs') as diagnostic:
            first,e=exit_inputs(f.e,accounting,clock());rpc=Opener(first,e)
            rpc.rows[7]['value']['blockhash']=fake_key('continuation-connected-blockhash')
            key=f.home/'signer.pk8';key.write_bytes(f.ephemeral_exit_key);key.chmod(0o600)
        transports=[]
        class Lazy:
            def open(self,request,timeout=None):
                if not transports:
                    book=m.submission.transport._open(f.home,f.wallet,f.pool,clock)
                    try:
                        state=m.submission.ExitSubmission(book).signing()
                        current=m.collection.exit.saved(book,clock())
                        check(state['request']['preparationSha256']==digest(current) and
                              state['request']['preparationSha256'] not in (old['recordSha256'],previous['recordSha256']),'continuation-signing-identity')
                        c=SimpleNamespace(exit_state=state,exit_wire=state['signed']['signedWireBase64'],path=book.j.path,signed={})
                    finally:book.close()
                    transports.append(FakeRpc(c,lost=True))
                return transports[0].open(request,timeout)
        with phase(report,'continuation-sign-send') as diagnostic:
            require_cold_reuse_scopes()
            report['fixtureSetup']=dict(version='offline-predecessor-reuse-1',
                realClocksUnchanged=True,scopesClearedBeforeContinuation=True,
                changesProductionWrappers=False)
            def timed(name,fn):
                @wraps(fn)
                def call(*args,**kwargs):
                    with phase(report,name) as measured:
                        value=fn(*args,**kwargs)
                        measured['observation']=observation(value)
                        return value
                return call
            start=time.monotonic()
            report['continuationStarted']=True
            # Measurement wrappers only: use the original functions, arguments,
            # clocks and deadlines. These hooks exist in this offline fixture,
            # never in the operational CLI or the independent signer.
            with patch.object(m.continuation,'collect_and_prepare',timed('continuation-collection-persistence',m.continuation.collect_and_prepare)),\
                 patch.object(m.handoff,'dispatch',timed('continuation-signing-handoff',m.handoff.dispatch)),\
                 patch.object(m.submission,'submit',timed('continuation-submission',m.submission.submit)):
                r=m.continue_sign_submit(f.home,f.wallet,f.pool,expected_original_sha256=old['recordSha256'],
                    expected_current_sha256=previous['recordSha256'],allow_unsigned_continuation=True,allow_private_key_signing=True,allow_devnet_submit=True,
                    collection_opener=rpc,submission_opener=Lazy(),clock=clock)
            require_cold_reuse_scopes()
            report['integrationElapsedMs']=round((time.monotonic()-start)*1000,3)
            report['deadlineHeadroomMs']=r.get('originalDeadlineMs',0)-r.get('completedAtMs',0) if r.get('completedAtMs') else None
            report['encodingReplay']=r.get('encodingReplay')
            report['admissionHistoryReplay']=r.get('admissionHistoryReplay')
            report['canonicalDigestReplay']=m.canonical_replay.summary(r.get('canonicalDigestReplay'))
            report['canonicalTextReplay']=m.serialization_replay.summary(r.get('canonicalTextReplay'))
            report['integrationStage']=r['stage'];report['integrationDiagnostic']=r['diagnosticCode']
            report['collectionRequests']=r['collectionRequests'];report['senderRequests']=r['senderRequests']
            diagnostic['observation']=observation(r)
            report['exit']=leg(r)
        with phase(report,'preserved-records') as diagnostic:
            check(r['privateKeyAccessed'] is True and r['originalDeadlineCheckedBeforeSend'],'continuation-signing-evidence')
            check(r['canonicalDigestReplay']['enabled'] is True and
                  r['canonicalDigestReplay']['hits']>0 and
                  r['canonicalDigestReplay']['reusesValidationOrAuthorization'] is False,
                  'canonical-digest-reuse-missing')
            report['cases']['actual-isolated-signer-and-one-lost-response-send']='passed'
            check(r['preparation']['originalPreparationSha256']==old['recordSha256'] and
                  r['preparation']['previousPreparationSha256']==previous['recordSha256'],'continuation-lineage')
            b=m.submission.transport._open(f.home,f.wallet,f.pool,clock)
            try:
                check(list(b.db.execute('SELECT * FROM admission_exit_preparation'))==original and
                      list(b.db.execute('SELECT * FROM admission_entry_accounting'))==entry and
                      list(b.db.execute('SELECT * FROM admission_exit_replacement'))==previous_rows,'predecessor-records-mutated')
                data=dict(policy=json.loads(b.db.execute('SELECT value FROM admission_policy').fetchone()[0]),
                    admissionRows=[dict(x) for x in b.db.execute('SELECT * FROM admission_events ORDER BY seq')],
                    signingRows=[dict(b.db.execute('SELECT * FROM admission_exit_signing ORDER BY seq LIMIT 1').fetchone())],
                    preparationRow=dict(original[0]),accountingRow=dict(entry[0]),
                    replacementRow=dict(b.db.execute('SELECT * FROM admission_exit_replacement').fetchone()),
                    continuationRow=dict(b.db.execute('SELECT * FROM admission_exit_continuation').fetchone()))
                boundary=json.loads(data['signingRows'][0]['value'])
                contract_input=dict(data=data,metadata=json.loads((f.home/'wallet.json').read_text()),
                    pair=json.loads((f.home/'controlled-pool-v1'/'plan.json').read_text())['pairAccounts'],
                    requestedHash=boundary['requestSha256'],now=data['signingRows'][0]['at_ms'])
            finally:b.close()
            key.unlink()
            contract=subprocess.run(['node',str(Path(__file__).with_name('continuation_exit_contract_checks.mjs'))],
                input=json.dumps(contract_input),capture_output=True,text=True,timeout=10,check=True)
            result=json.loads(contract.stdout);check(result['casesPassed']==14,'independent-contract-cases')
            report['independentContractCases']=result['cases']
            report['cases']['independent-signer-rejects-rehashed-lineage-and-ownership-changes']='passed'
            check({p.name:p.read_bytes() for p in f.home.iterdir() if p.is_file()}==source,'source-mutated')
            report['cases']['both-predecessors-source-and-entry-accounting-preserved']='passed'
        with phase(report,'repeat-refusal-recovery') as diagnostic:
            with patch.object(m.backend,'_invoke',side_effect=AssertionError('second signer')):
                again=m.continue_sign_submit(f.home,f.wallet,f.pool,expected_original_sha256=old['recordSha256'],
                    expected_current_sha256=previous['recordSha256'],allow_unsigned_continuation=True,allow_private_key_signing=True,allow_devnet_submit=True,clock=clock)
                check(again['networkRequests']==again['signerInvocationAttempts']==0,'repeat-attempt')
                (f.home/'STOP').touch(mode=0o600)
                recovery=m.recover(f.home,f.wallet,f.pool,opener=transports[0],clock=lambda:clock()+30000)
            check(recovery['state']=='exit-finalized-evidence' and recovery['sendRequestsThisRun']==0 and
                  not recovery['reservationReleased'] and not recovery['resumesExit'],'recovery-not-observation')
            check(sum(x['method']=='sendTransaction' for x in transports[0].requests)==1,'repeat-send')
        with phase(report,'repeated-recovery') as diagnostic:
            b=m.submission.transport._open(f.home,f.wallet,f.pool,clock)
            try:path=b.j.path
            finally:b.close()
            recovered_bytes=path.read_bytes()
            with patch.object(m.backend,'_invoke',side_effect=AssertionError('recovery signer')):
                repeated=m.recover(f.home,f.wallet,f.pool,opener=transports[0],clock=lambda:clock()+30000)
            check(repeated['state']==recovery['state'] and repeated['sendRequestsThisRun']==0 and
                  path.read_bytes()==recovered_bytes,'repeated-recovery-mutated')
            check(sum(x['method']=='sendTransaction' for x in transports[0].requests)==1,'repeated-recovery-send')
            report['cases']['repeat-refused-before-collection-keyless-stopped-recovery-never-resends']='passed'
            report['cases']['repeated-recovery-keeps-durable-evidence-byte-identical']='passed'
            report['recovery']=dict(state=recovery['state'],sendRequests=0,reservationReleased=False)


@contextmanager
def fixture_size(large):
    """Only disposable generated fixtures, never a baseline or live RPC override."""
    if type(large) is not bool:raise ValueError('fixture-mode')
    if not large:
        yield
        return
    import pool_fixtures
    row=deepcopy(pool_fixtures.DEPLOY_ROW)
    raw=base64.b64decode(row['data'][0])
    check(len(raw)<=1024*1024,'synthetic-program-size')
    row['data'][0]=base64.b64encode(raw+bytes(1024*1024-len(raw))).decode()
    baseline=deepcopy(pool_fixtures.BASE)
    baseline['identity'].update({k:v for k,v in pool_fixtures.deployment(row,100).items()
                                if k in pool_fixtures.IDENTITY_FIELDS})
    # The connected fixture replays generated historical files. Its constructors
    # import these dictionary objects directly, so preserve their shared identity
    # while changing only disposable fixture inputs, then restore both exactly.
    with patch.dict(pool_fixtures.DEPLOY_ROW,row,clear=True),patch.dict(pool_fixtures.BASE,baseline,clear=True):
        yield


def run(*,large_fixture=False):
    if type(large_fixture) is not bool:raise ValueError('fixture-mode')
    # Keep the fault matrix small; expand the full connected signer/transport
    # fixture only, including its historical source and both predecessors.
    faults=fault_checks()
    with fixture_size(large_fixture):
        return _run(large_fixture=large_fixture,faults=faults)


def _run(*,large_fixture=False,faults):
    import test_fresh_exit as fixture_module
    class Fixture(fixture_module.ActualBackendTests):pass
    report=dict(format=VERSION,state='review-required',cases=faults,casesPassed=0,
        requestedProgramFixtureBytes=1024*1024 if large_fixture else None,programFixtureBytes=None,
        mode='synthetic-offline',realNetworkRequests=0,productionWalletAccessed=False,
        disposableTestKeySigning=True,transactionsSent=0,productionLedgerUpdated=False,
        runtimeIntegrated=False,executionApproved=False,automaticRetryAllowed=False,
        integrationElapsedMs=None,integrationStage=None,integrationDiagnostic=None,
        continuationStarted=False,
        limitations=['Synthetic RPC and disposable keys only; no real network latency or user position test.',
                    'The original ten-second freshness and thirty-second shared budget are unchanged.',
                    'A returned quote or finalized synthetic receipt is not evidence of profitability.'])
    with tempfile.TemporaryDirectory(prefix='radar-continuation-integration-') as owned:
        with patch.object(tempfile,'tempdir',owned),patch('socket.socket',side_effect=AssertionError('real network')):
            instance=None;started=False;setup=False
            try:
                with phase(report,'fixture-class-setup'):
                    started=True;Fixture.setUpClass()
                with phase(report,'fixture-instance-setup'):
                    instance=Fixture();setup=True;instance.setUp()
                    check(instance.home.resolve().is_relative_to(Path(owned).resolve()),'temporary-scope')
                    data=instance.e['costInputs']['capture']['evidence']['accounts']['result']['value'][-1]['data'][0]
                    report['programFixtureBytes']=len(base64.b64decode(data,validate=True))
                    check(not large_fixture or report['programFixtureBytes']==1024*1024,'synthetic-program-size')
                with phase(report,'connected-rehearsal'):connected(instance,report)
                report['state']='offline-integration-passed'
            except Exception:
                report['diagnosticCode']='connected-rehearsal-incomplete'
            finally:
                try:
                    with phase(report,'fixture-cleanup'):
                        if setup:instance.tearDown()
                        if started:Fixture.tearDownClass()
                except Exception:
                    report['state']='review-required';report['diagnosticCode']='fixture-cleanup-incomplete'
                finally:Fixture.ephemeral_exit_key=None
    report['temporaryLedgersRemoved']=not Path(owned).exists()
    report['casesPassed']=len(report['cases'])
    return report
