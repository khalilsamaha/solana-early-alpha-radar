"""Internal bounded collection/sign/send composition; no public execution CLI.

One owner retains exact-content computational reuse only. Every component still
replays evidence across writes/provider calls and enforces the original expiry.
"""
from pathlib import Path
import time

import successor_signing_integration as signing
import successor_submission as submission
from core import check

VERSION='successor-execution-1'
CODES=signing.CODES|{'successor-execution-clock','successor-execution-budget',
    'successor-execution-expired','successor-execution-stopped','successor-execution-identity',
    'successor-execution-send-required','successor-transport-clock-budget','successor-signing-expired-or-stopped',
    'successor-transport-wrong-cluster','successor-transport-blockhash','exit-fee-cap','rpc-evidence-unavailable',
    'rpc-slot-invalid','successor-transport-source-changed'}


@signing.serialization_replay.operation
@signing.canonical_replay.operation
@signing.view.cycles.binding.operation
@signing.successor.history.fresh_signing.timing.signature_replay
@signing.encoding_replay.operation
@signing.admission_history_replay.operation
def _run(home,wallet,pool,expected,retirement,*,clock,monotonic,expiry_opener,quote_opener,submission_opener):
    start=monotonic();last_tick=start;last_wall=clock();root=Path(home).absolute();clients=[]
    r=dict(format=VERSION,computationScopeVersion='successor-computation-owner-1',state='successor-execution-review-required',stage='collection-signing',diagnosticCode=None,
        signing=None,submission=None,successorSha256=None,originalDeadlineMs=None,
        applicationSendBoundaryRecorded=False,sendRequestsThisRun=0,senderRequests=0,collectionRequests=0,
        requestMethods=[],completedWithinOriginalDeadline=False,originalDeadlineCheckedBeforeSend=False,
        completedAtMs=None,timing={},recoveryRequired=False,automaticRetryAllowed=False,automaticResigningAllowed=False,
        reservationsReleased=False,receiptEffectsReconciled=False,executionApproved=False,runtimeIntegrated=False)
    def guard():
        nonlocal last_tick,last_wall
        tick=monotonic();wall=clock()
        check(tick>=last_tick and wall>=last_wall,'successor-execution-clock')
        check(0<=tick-start<120,'successor-execution-budget')
        if r['originalDeadlineMs'] is not None:check(wall<r['originalDeadlineMs'],'successor-execution-expired')
        check(not signing.view.cycles.c.submit.swap.stop(root),'successor-execution-stopped')
        last_tick=tick;last_wall=wall;return wall
    try:
        guard();begin=monotonic()
        r['signing']=signing._collect_sign(root,wallet,pool,expected,retirement,
            allow_unsigned_successor=True,allow_private_key_signing=True,clock=clock,monotonic=monotonic,
            _expiry_opener=expiry_opener,_quote_opener=quote_opener,_reuse_computation_scope=True)
        r['timing']['collectionSigningMs']=round((monotonic()-begin)*1000,3)
        s=r['signing'];r['successorSha256']=s['successorSha256'];r['originalDeadlineMs']=s['originalDeadlineMs']
        r['recoveryRequired']=s['preparationCreatedThisRun'] or s['successorSha256'] is not None
        if s['state']=='existing-successor-held':
            r.update(state='existing-successor-held',stage='existing-candidate');return r
        if not (s['state']=='successor-signed-within-deadline' and s['completedWithinOriginalDeadline'] and s['signerAcknowledgmentValidated']):
            r['diagnosticCode']=s['diagnosticCode'];return r
        guard();r['stage']='submission';r['applicationSendBoundaryRecorded']=None
        def sender_guard(stage,state):
            check(state['request']['successorSha256']==r['successorSha256'] and
                state['request']['validUntilExclusiveMs']==r['originalDeadlineMs'],'successor-execution-identity')
            guard();r['stage']='submission:'+str(stage)
            if stage=='sendTransaction':r['originalDeadlineCheckedBeforeSend']=True
        begin=monotonic()
        try:
            r['submission']=submission._submit(root,wallet,pool,r['successorSha256'],allow_devnet_submit=True,
                opener=submission_opener,clock=clock,monotonic=monotonic,_guard=sender_guard,_rpc_sink=clients.append,_reuse_signature_scope=True)
        finally:r['timing']['submissionMs']=round((monotonic()-begin)*1000,3)
        outcome=r['submission'];r['applicationSendBoundaryRecorded']=outcome['applicationSendBoundaryRecorded']
        check(outcome['sendRequestsThisRun']==1 and outcome['state'] in ('rpc-acknowledged','successor-submission-unknown'),
              'successor-execution-send-required')
        r['stage']='completion-check';end=guard()
        r.update(state=outcome['state'],stage='complete',completedAtMs=end,completedWithinOriginalDeadline=True)
    except (ValueError,KeyError,TypeError,OSError,signing.subprocess.SubprocessError,signing.view.sqlite3.Error) as exc:
        r['recoveryRequired']=True
        r['diagnosticCode']=str(exc) if type(exc) is ValueError and str(exc) in CODES else 'successor-execution-unavailable'
    finally:
        calls=[c for rpc in clients for c in rpc.calls];s=r['signing'] or {}
        r['collectionRequests']=s.get('collectionRequests',0);r['senderRequests']=len(calls)
        r['sendRequestsThisRun']=sum(c['method']=='sendTransaction' for c in calls)
        r['requestMethods']=s.get('requestMethods',[])+[c['method'] for c in calls]
        r['networkRequestsThisRun']=r['collectionRequests']+len(calls)
        r['transactionsSent']=None if r['sendRequestsThisRun'] else 0
        r['timing']['totalElapsedMs']=round((monotonic()-start)*1000,3)
    return r


def _collect_sign_submit(home,wallet,pool,expected,retirement,*,allow_unsigned_successor=False,
                        allow_private_key_signing=False,allow_devnet_submit=False,
                        expiry_opener=None,quote_opener=None,submission_opener=None,
                        clock=signing.view.now,monotonic=time.monotonic):
    check(all(x is True for x in (allow_unsigned_successor,allow_private_key_signing,allow_devnet_submit)),
          'successor-execution-three-opt-ins-required')
    check(all(x is not None and callable(getattr(x,'open',None)) and bool(x) for x in
              (expiry_opener,quote_opener,submission_opener)),'successor-execution-injected-providers-required')
    start=monotonic()
    r=_run(home,wallet,pool,expected,retirement,clock=clock,monotonic=monotonic,
        expiry_opener=expiry_opener,quote_opener=quote_opener,submission_opener=submission_opener)
    now=clock();tick=monotonic()
    r['timing']['totalElapsedMs']=round((tick-start)*1000,3)
    r['returnedAtMs']=now;r['headroomAtReturnMs']=None if r['originalDeadlineMs'] is None else r['originalDeadlineMs']-now
    if r['completedWithinOriginalDeadline'] and not (r['completedAtMs']<=now<r['originalDeadlineMs'] and 0<=tick-start<120):
        r.update(state='successor-execution-review-required',stage='return-boundary',
            completedWithinOriginalDeadline=False,diagnosticCode='successor-execution-expired')
    return r


@signing.serialization_replay.operation
@signing.canonical_replay.operation
@signing.encoding_replay.operation
@signing.admission_history_replay.operation
def _recover(home,wallet,pool,expected,*,opener,clock=signing.view.now):
    return submission._recover(home,wallet,pool,expected,opener=opener,clock=clock)
