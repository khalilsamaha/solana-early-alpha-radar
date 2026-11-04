"""Fresh collected exit -> independent signer -> one devnet transport attempt.

Internal opt-in only. No live CLI, retry, refresh, receipt accounting or release.
"""
import time
import admission_exit_collection as collection
import exit_submission as submission
import fresh_signing
import unsigned_exit_replacement as replacement
from contract import digest
from core import check
from journal import read_only_journals
import encoding_replay
import admission_history_replay

VERSION='fresh-exit-transport-1'
handoff=submission.handoff
backend=submission.backend
view=handoff.view


@view.cycles.binding.operation
@fresh_signing.timing.signature_replay
@encoding_replay.operation
@admission_history_replay.operation
def _run(home,wallet,pool,*,signer_adapter,collection_opener=None,submission_opener=None,
         clock=view.now,monotonic=time.monotonic,_replacement_expected=None):
    """Injected adapter is a trusted test seam; public wrapper fixes the backend."""
    observations=[];clients=[];started=monotonic();wall=clock()
    last_wall=wall;last_tick=started;deadline=None;expected=None
    r=dict(format=VERSION,state='fresh-exit-inspection-required',stage='collection',
        diagnosticCode=None,preparation=None,signing=None,submission=None,
        signerInvocationAttempts=0,privateKeyAccessed=False,signaturesCreated=0,
        signerAcknowledgmentValidated=False,applicationSendBoundaryRecorded=False,
        originalDeadlineMs=None,completedWithinOriginalDeadline=False,
        originalDeadlineCheckedBeforeSend=False,recoveryRequired=False,
        automaticRetryAllowed=False,automaticResigningAllowed=False,
        reservationReleased=False,allocationTransferred=False,nextCycleAuthorized=False,
        runtimeIntegrated=False,executionApproved=False,receiptEffectsReconciled=False)
    def guard(root):
        nonlocal last_wall,last_tick
        last_wall,last_tick=fresh_signing.guard(root,clock,monotonic,started,deadline,last_wall,last_tick)
    try:
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            book=submission.transport._open(root,wallet,pool,clock)
            try:
                if _replacement_expected is None:
                    check(collection.exit.saved(book,clock()) is None and handoff.read(book,clock()) is None,
                          'fresh-exit-slot-occupied')
                else:
                    replacement.eligible(book,root,_replacement_expected,clock())
                check(not handoff.stopped(root,book),'fresh-signing-stopped')
                # Orphan backend markers require inspection, never another key invocation.
                check(not any((book.j.path.parent/n).exists() or (book.j.path.parent/n).is_symlink()
                      for n in (backend.ATTEMPT,backend.ACK)),'fresh-exit-slot-occupied')
            finally:book.close()
        options=dict(opener=collection_opener,clock=clock,monotonic=monotonic,
                     _observation_sink=observations.append)
        if _replacement_expected is None:
            prepared=collection.collect_and_prepare(root,wallet,pool,**options)
        else:
            prepared=replacement.collect_and_replace(root,wallet,pool,
                expected_preparation_sha256=_replacement_expected,allow_unsigned_replacement=True,**options)
            check(prepared.get('originalPreparationSha256')==_replacement_expected and
                  prepared.get('replacementCount')==1 and prepared.get('originalPreserved') is True,
                  'fresh-exit-replacement-identity')
        r['preparation']=prepared
        check(prepared.get('createdThisRun') is True and prepared.get('collectionRecorded') is True,
              'fresh-exit-not-created')
        deadline=prepared['binding']['validUntilExclusiveMs'];r['originalDeadlineMs']=deadline
        guard(root)
        def sign(request):
            nonlocal expected
            check(request['preparationSha256']==prepared['recordSha256'] and
                  request['validUntilExclusiveMs']==deadline,'fresh-exit-identity')
            expected=digest(request);guard(root)
            r.update(stage='signing',signerInvocationAttempts=1,privateKeyAccessed=None,
                     signaturesCreated=None,recoveryRequired=True)
            return signer_adapter(root,request)
        r['stage']='signing-validation'
        result=handoff.dispatch(root,wallet,pool,signer_adapter=sign,clock=clock)
        r['signing']=result
        check(r['signerInvocationAttempts']==1 and result['state']=='exit-signed-recorded' and
              result['acknowledgmentRecorded'],'fresh-exit-signing-unavailable')
        r.update(signerAcknowledgmentValidated=True,signaturesCreated=1)
        guard(root)
        def sender_guard(stage,state):
            check(digest(state['request'])==expected and state['request']['validUntilExclusiveMs']==deadline,
                  'fresh-exit-identity')
            guard(root)
            if stage=='sendTransaction':r['originalDeadlineCheckedBeforeSend']=True
        r.update(stage='submission',applicationSendBoundaryRecorded=None)
        outcome=submission.submit(root,wallet,pool,allow_devnet_submit=True,opener=submission_opener,
            clock=clock,_guard=sender_guard,_rpc_sink=clients.append)
        r.update(submission=outcome,state=outcome['state'],stage='complete',
                 applicationSendBoundaryRecorded=outcome['applicationSendBoundaryRecorded'])
        end=clock();tick=monotonic()
        r.update(completedAtMs=end,completedWithinOriginalDeadline=
            last_wall<=end<deadline and last_tick<=tick<started+30)
    except fresh_signing.ERRORS as exc:
        r['diagnosticCode']=str(exc) if str(exc) in {
            'fresh-exit-slot-occupied','fresh-exit-not-created','fresh-exit-identity','fresh-exit-signing-unavailable',
            'fresh-signing-stopped','fresh-signing-expired','fresh-signing-clock','fresh-signing-monotonic',
            'exit-wrong-cluster','exit-blockhash-unavailable','exit-fee-cap','exit-boundary-now-unknown',
            'exit-signing-expired','exit-signing-boundary-expired-or-stopped','exit-signing-stopped',
            'fresh-exit-replacement-identity','replacement-limit-reached',
            'replacement-expected-identity','replacement-original-not-expired',
            'replacement-stopped','replacement-backend-marker',
            'replacement-expired-before-write','replacement-expired-before-commit'
        } else 'fresh-exit-evidence-unavailable'
        r['recoveryRequired']=True
    finally:
        calls=[x for client in clients for x in client.calls]
        count=sum(x.get('networkRequests',0) for x in observations)
        sends=sum(x['method']=='sendTransaction' for x in calls)
        r.update(collectionRequests=count,senderRequests=len(calls),networkRequests=count+len(calls),
            senderRequestMethods=[x['method'] for x in calls],sendRequestsThisRun=sends,
            transactionsSent=None if sends else 0,
            limitations=[
                'Internal controlled devnet integration; CLI is synthetic only.',
                'At most twenty collection and five transport requests; no retries or receipt polling.',
                'Original expiry and shared thirty-second budget reach the signer and every sender request.',
                'Late acknowledgments remain historical; unknown attempts keep reservations held.',
                'Recovery observes the existing signature only; no new exit preparation or signing.',
                'RPC acknowledgment is not a fill, reconciled receipt, released allocation or mainnet approval.'])
    return r


def prepare_sign_submit(home,wallet,pool,*,allow_private_key_signing=False,allow_devnet_submit=False,**kwargs):
    check(allow_private_key_signing is True,'explicit-exit-private-key-opt-in-required')
    check(allow_devnet_submit is True,'explicit-devnet-submit-required')
    check('_replacement_expected' not in kwargs,'explicit-unsigned-replacement-required')
    r=_run(home,wallet,pool,signer_adapter=backend._invoke,**kwargs)
    if r['signerAcknowledgmentValidated']:r['privateKeyAccessed']=True
    return r


def replace_sign_submit(home,wallet,pool,*,expected_preparation_sha256,
                        allow_unsigned_replacement=False,allow_private_key_signing=False,
                        allow_devnet_submit=False,**kwargs):
    """Explicit one replacement, one signer and one send. Internal, no live CLI."""
    check(allow_unsigned_replacement is True,'explicit-unsigned-replacement-required')
    check(allow_private_key_signing is True,'explicit-exit-private-key-opt-in-required')
    check(allow_devnet_submit is True,'explicit-devnet-submit-required')
    check(type(expected_preparation_sha256) is str and len(expected_preparation_sha256)==64 and
          all(c in '0123456789abcdef' for c in expected_preparation_sha256),'replacement-expected-identity')
    r=_run(home,wallet,pool,signer_adapter=backend._invoke,
        _replacement_expected=expected_preparation_sha256,**kwargs)
    r.update(format='replacement-exit-transport-1',automaticReplacementAllowed=False)
    if r['signerAcknowledgmentValidated']:r['privateKeyAccessed']=True
    return r


@view.cycles.binding.operation
@fresh_signing.timing.signature_replay
def recover(home,wallet,pool,*,opener=None,clock=view.now):
    """Existing transport recovery only. Lost signing uses backend.recover separately."""
    return dict(submission.recover(home,wallet,pool,opener=opener,clock=clock),
                format=VERSION+'-recovery',resumesExit=False)
