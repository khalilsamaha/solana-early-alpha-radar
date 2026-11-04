"""Standalone offline instrumentation; no production hooks or operational inputs."""
from contextlib import contextmanager,ExitStack
from functools import wraps
import sys
import threading
from unittest.mock import patch
import exit_profile as profile
import fresh_exit as m
import admission_exit_capture as capture_module
import admission_exit_collection as collection
import admission_lifecycle as lifecycle
import journal
from core import check

VERSION='exit-profile-rehearsal-1'
_lock=threading.Lock()


def timed(original,stage):
    @wraps(original)
    def wrapped(*args,**kwargs):
        with profile.measure(stage):return original(*args,**kwargs)
    return wrapped


def transaction(original):
    @contextmanager
    def wrapped(self,*args,**kwargs):
        if profile._current.get() is None or getattr(self,'read_only',False):
            with original(self,*args,**kwargs) as value:yield value
            return
        cm=original(self,*args,**kwargs)
        with profile.measure('transaction-enter'):value=cm.__enter__()
        try:yield value
        except BaseException:
            with profile.measure('transaction-rollback'):suppressed=cm.__exit__(*sys.exc_info())
            if not suppressed:raise
        else:
            with profile.measure('transaction-commit'):cm.__exit__(None,None,None)
    return wrapped


@contextmanager
def instrument():
    # Only used by this standalone, single-threaded offline harness. Patches are
    # restored on every exit and never installed by importing the module.
    if not _lock.acquire(blocking=False):raise ValueError('offline-instrumentation-busy')
    try:
        targets=[(capture_module,'collect','collection'),(capture_module.Transport,'open','rpc-open'),
            (m.view,'read_locked','source-replay'),(m.submission.transport,'_open','journal-open'),
            (m.replacement,'eligible','eligibility-replay'),(lifecycle,'projection','lifecycle-replay'),
            (collection.exit,'review','evidence-review'),(collection,'review','provenance-review'),
            (m.replacement,'replace','replacement-persist'),(m.replacement,'write_record','replacement-write'),
            (m.handoff,'dispatch','signing-handoff'),(m.backend,'_invoke','signer-backend'),
            (m.submission,'submit','transport-submit'),(m.fresh_signing,'guard','freshness-guard')]
        with ExitStack() as stack:
            for obj,key,stage in targets:stack.enter_context(patch.object(obj,key,timed(getattr(obj,key),stage)))
            stack.enter_context(patch.object(journal.Journal,'transaction',transaction(journal.Journal.transaction)))
            yield
    finally:_lock.release()


def expiry_reproduction():
    from unsigned_exit_replacement_checks import case,rows
    with case() as c:
        p=profile.Profile(clock=lambda:c.timer.at)
        original=m.replacement.collect_and_replace;before=rows(c,'admission_exit_preparation')
        def expire(*args,**kwargs):
            result=original(*args,**kwargs)
            check(result.get('createdThisRun') is True,'expiry-fixture-not-persisted')
            # Explicit synthetic delay AFTER actual persistence. It proves the
            # original guard still refuses, not how long the user's commit took.
            c.timer.at=result['binding']['validUntilExclusiveMs']
            return result
        with instrument(),profile.capture(p),patch.object(m.replacement,'collect_and_replace',expire),\
                patch.object(m.backend,'_invoke',side_effect=AssertionError('signer forbidden')):
            with profile.measure('replacement-attempt'):
                result=m.replace_sign_submit(c.home,c.wallet,c.pool,expected_preparation_sha256=c.expected,
                    allow_unsigned_replacement=True,allow_private_key_signing=True,allow_devnet_submit=True,
                    collection_opener=c.rpc,clock=c.clock,monotonic=lambda:0)
            p.pin(result['originalDeadlineMs'])
        check(result['diagnosticCode']=='fresh-signing-expired' and result['collectionRequests']==20 and
              result['signerInvocationAttempts']==result['sendRequestsThisRun']==0,'expiry-fixture-effects')
        check(rows(c,'admission_exit_preparation')==before and len(rows(c,'admission_exit_replacement'))==1,
              'expiry-fixture-preservation')
        again=m.replace_sign_submit(c.home,c.wallet,c.pool,expected_preparation_sha256=c.expected,
            allow_unsigned_replacement=True,allow_private_key_signing=True,allow_devnet_submit=True,clock=c.clock)
        check(again['networkRequests']==again['signerInvocationAttempts']==0,'expiry-fixture-repeat')
        return dict(state='persisted-expiry-reproduced',syntheticDelayInjected=True,
            signerInvocationAttempts=0,sendRequests=0,replacementPreserved=True,repeatRequests=0,
            profile=p.report())


def run():
    import replacement_exit_checks as connected
    reports=[];original=m.replace_sign_submit
    def observed(*args,**kwargs):
        flags=('allow_unsigned_replacement','allow_private_key_signing','allow_devnet_submit')
        if not all(kwargs.get(k) is True for k in flags):return original(*args,**kwargs)
        p=profile.Profile()
        try:
            with profile.capture(p),profile.measure('replacement-attempt'):
                result=original(*args,**kwargs)
                if result.get('originalDeadlineMs') is not None:p.pin(result['originalDeadlineMs'])
                return result
        finally:reports.append(p.report())
    report=dict(format=VERSION,state='review-required',profiles=reports,connected=None,expiry=None,
        realNetworkRequests=0,productionWalletAccessed=False,transactionsSent=0,
        disposableTestKeySigning=True,runtimeIntegrated=False,executionApproved=False,
        automaticRetryAllowed=False,measuredProviderLatency=False,
        limitations=['Offline synthetic replies and disposable keys; no user wallet or source directory accepted.',
            'Instrumentation adds overhead. Durations are one local sample, not a live latency guarantee.',
            'Inclusive spans overlap. Do not sum nested durations or treat RPC-open as full response time.',
            'Transaction spans cover writable journals; read-only transaction overhead stays inside parent phases.',
            'Historical inspection separately exposes recorded client/request intervals; commit completion was not recorded.',
            'An offline pass never grants another replacement, signing, send or mainnet action.'])
    try:
        with instrument(),patch.object(m,'replace_sign_submit',observed):result=connected.run()
        report['connected']=result
        check(result['state']=='offline-integration-passed' and len(reports)==2,'profile-connected-incomplete')
        required=profile.STAGES-{'transaction-rollback'}
        check(reports[0]['valid'] and required<={x['stage'] for x in reports[0]['spans']},'profile-stages-missing')
        check(all(x['completed'] for x in reports[0]['spans']),'profile-stage-incomplete')
        # No new real request is added; the existing lost-response and keyless
        # recovery assertions in connected.run() remain authoritative.
        report['expiry']=expiry_reproduction()
        check(report['expiry']['profile']['valid'],'profile-expiry-invalid')
        report.update(state='offline-exit-profile-passed',connectedChecksPassed=result['casesPassed'])
    except Exception:report['diagnosticCode']='exit-profile-incomplete'
    return report
