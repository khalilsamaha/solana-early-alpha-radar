"""Internal fresh collection -> signing -> one devnet send; no live CLI.

The original evidence expiry and operation monotonic budget reach every sender
request. Recovery only observes the existing signature; it cannot resume entry.
"""
import fresh_signing as signing
import admission_submission as submission
from core import check, directory
from contract import uint
from journal import read_only_journals

VERSION='fresh-entry-sender-1'
IDENTITY=('validUntilExclusiveMs','messageSha256','signingRequestSha256',
          'signedWireSha256','accountingHandoffSha256','ledgerHeadSha256','cycleBindingSha256','policySha256')


@signing.view.cycles.binding.operation
def _run(home,wallet,pool,*,signer_adapter,submission_opener=None,
         clock=signing.view.now,monotonic=signing.timing.time.monotonic,**kwargs):
    """Trusted test seam; production entry point below binds the actual backend."""
    started=monotonic();wall=clock();r={};clients=[]
    progress=dict(stage='signing',senderRequestMethods=[],senderRequests=0,
        sendRequestsThisRun=0,applicationSendBoundaryRecorded=False,submission=None,
        originalDeadlineCheckedBeforeSend=False,submissionRecoveryRequired=False,
        receiptObserved=False,automaticRetryAllowed=False,automaticResigningAllowed=False)
    def sign(root,request):
        signing.guard(root,clock,monotonic,started,request['validUntilExclusiveMs'],wall,started)
        return signer_adapter(root,request)
    try:
        r=signing._run(home,wallet,pool,signer_adapter=sign,clock=clock,monotonic=monotonic,**kwargs)
        if not (r['state']=='signed-recorded' and r['signerAcknowledgmentValidated'] and
                r['completedWithinOriginalDeadline']):return r
        root=directory(home);deadline=r['originalDeadlineMs']
        expected=r['handoff']['admission']['reservation']
        check(expected['validUntilExclusiveMs']==deadline,'fresh-entry-identity')
        last_wall=r['completedAtMs'];last_tick=monotonic()
        # The signing sub-operation cannot give the sender a new 30-second budget.
        uint(last_wall,2**53-1,'fresh-entry-clock',minimum=wall)
        check(started<=last_tick<started+30,'fresh-entry-monotonic')
        def guard(stage,state):
            nonlocal last_wall,last_tick
            check(all(state[k]==expected[k] for k in IDENTITY),'fresh-entry-identity')
            if stage=='before-preflight':
                with read_only_journals():source=signing.view.read_locked(root,wallet,pool,clock)
                check(source['phase']=='closed' and source['wallet']==wallet and source['pool']==pool and
                      all(source[k]==expected[k] for k in ('ledgerHeadSha256','cycleBindingSha256')),
                      'fresh-entry-source-changed')
            last_wall,last_tick=signing.guard(root,clock,monotonic,started,deadline,last_wall,last_tick)
            if stage=='sendTransaction':progress['originalDeadlineCheckedBeforeSend']=True
        progress.update(stage='submission',applicationSendBoundaryRecorded=None,
                        submissionRecoveryRequired=True)
        with signing.timing.wire.signature_verification_scope() as metrics:
            try:
                outcome=submission.submit(root,wallet,pool,allow_devnet_submit=True,opener=submission_opener,
                    clock=clock,_guard=guard,_rpc_sink=clients.append)
            finally:r['submissionSignatureVerification']=metrics()
        progress.update(submission=outcome,applicationSendBoundaryRecorded=outcome['applicationSendBoundaryRecorded'])
        r.update(state=outcome['state'],recoveryRequired=True)
        # Acknowledgment is not finality; even a successful response needs receipt recovery.
        end=clock();tick=monotonic()
        r.update(completedAtMs=end,remainingMs=deadline-end,
                 completedWithinOriginalDeadline=last_wall<=end<deadline and last_tick<=tick<started+30)
        progress['stage']='complete'
    except signing.ERRORS as exc:
        r.update(state='fresh-entry-inspection-required',recoveryRequired=True,completedWithinOriginalDeadline=False,
                 diagnosticCode='fresh-entry-evidence-unavailable')
        if str(exc) in {'fresh-entry-identity','fresh-entry-source-changed','fresh-entry-clock','fresh-entry-monotonic',
                       'fresh-signing-expired','fresh-signing-clock','fresh-signing-monotonic',
                       'fresh-signing-stopped','submission-stopped','submission-not-fresh',
                       'submission-boundary-now-unknown','submission-wrong-cluster',
                       'submission-blockhash-unavailable','submission-fee-cap'}:
            r['diagnosticCode']=str(exc)
    finally:
        calls=[call for client in clients for call in client.calls]
        progress.update(senderRequests=len(calls),senderRequestMethods=[x['method'] for x in calls],
            sendRequestsThisRun=sum(x['method']=='sendTransaction' for x in calls))
        if 'signatureVerification' in r:r['signingSignatureVerification']=r.pop('signatureVerification')
        collection_count=r.get('networkRequests',0)
        methods=list(r.get('requestMethods',[]))+progress['senderRequestMethods']
        r.update(progress,format=VERSION,collectionRequests=collection_count,
            networkRequests=collection_count+len(calls),requestMethods=methods,
            totalRequestAttempts=collection_count+len(calls),
            recoveryRequired=r.get('recoveryRequired',False) or bool(r.get('signerInvocationAttempts')),
            # Invocation cannot establish delivery, including after a lost response.
            transactionsSent=None if progress['sendRequestsThisRun'] else 0,
            runtimeIntegrated=False,executionApproved=False,nextCycleAuthorized=False,
            limitations=[
                'Internal controlled-devnet path only; public CLI runs synthetic checks.',
                'At most 20 collection and five submission requests; no retry or automatic receipt polling.',
                'Original wall expiry and shared 30-second budget checked before each sender request, including send.',
                'An in-flight request may finish after expiry; its acknowledgment stays historical, not fresh.',
                'A send attempt or RPC acknowledgment does not prove delivery or finalized effects.',
                'Unknown signing or submission keeps reservations held; recovery never resumes entry.',
                'No live service wiring, mainnet, wallet-wide allocation, new cycle or profitability approval.'])
    return r


def prepare_sign_submit(home,wallet,pool,*,allow_private_key_signing=False,allow_devnet_submit=False,**kwargs):
    """Both explicit internal opt-ins checked before any collection or key access."""
    check(allow_private_key_signing is True,'explicit-private-key-opt-in-required')
    check(allow_devnet_submit is True,'explicit-devnet-submit-required')
    r=_run(home,wallet,pool,signer_adapter=signing.backend._invoke,**kwargs)
    if r.get('signerAcknowledgmentValidated') and r.get('signerInvocationAttempts')==1:r['privateKeyAccessed']=True
    return r


@signing.view.cycles.binding.operation
@signing.timing.signature_replay
def recover(home,wallet,pool,*,opener=None,clock=signing.view.now):
    """Observe existing transport only. No new signature or pending-entry send.

    An existing send boundary already implies a committed signer acknowledgment;
    receipt recovery must still work if that acknowledgment file was later lost.
    Incomplete signing without a send boundary uses fresh_signing.recover instead.
    """
    r=submission.recover(home,wallet,pool,opener=opener,clock=clock)
    return dict(r,format=VERSION+'-recovery',resumesEntry=False)
