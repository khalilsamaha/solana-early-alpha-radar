"""Bounded first-exit observation for an existing admission; read-only journals.

The private in-process handoff is evidence, never a signing capability. Atomic
persistence and restricted exit signing remain separate integration gates.
"""
from copy import deepcopy
from contextlib import ExitStack
import json
import time

import exit_collection_diagnostics as diagnostics
import admission_exit as exit
import fresh_quote
import preflight_capture
from fresh_packet import build, scope_check
from contract import digest
from core import check
from journal import read_only_journals

VERSION='admission-exit-capture-1'
view=exit.view
METHODS=(['getGenesisHash','getMultipleAccounts','getMultipleAccounts','getMultipleAccounts',
          'getBlockTime','getGenesisHash']+
         ['getGenesisHash','getLatestBlockhash','getFeeForMessage','getGenesisHash']+
         ['getGenesisHash','getMultipleAccounts','getMultipleAccounts','getMultipleAccounts',
          'getBlockTime','isBlockhashValid','getFeeForMessage','getGenesisHash',
          'simulateTransaction','getGenesisHash'])


class Transport(exit.unsigned_simulation.Transport):
    """Existing byte/time caps plus exact method order, STOP and wall-clock deadline."""
    def __init__(self,root,clock,opener,monotonic,start):
        super().__init__(opener,monotonic)
        self.root=root;self.clock=clock;self.start=start;self.last=start
        self.deadline=start+10000;self.request_hashes=[]

    def open(self,request,timeout):
        check(not view.cycles.c.submit.swap.stop(self.root),'exit-capture-stopped')
        stamp=self.clock()
        check(self.last<=stamp<self.deadline,'exit-capture-expired')
        self.last=stamp
        body=json.loads(request.data);index=len(self.calls)
        check(index<len(METHODS) and body['method']==METHODS[index],'exit-capture-request-order')
        row=dict(method=body['method'],parametersSha256=digest(body['params']),requestedAtMs=stamp)
        response=super().open(request,min(timeout,(self.deadline-stamp)/1000))
        self.request_hashes.append(row)
        return response


def identity(book,root,wallet,pool,clock):
    state=book.read()[0]
    check(state['state']=='signed-recorded','exit-capture-admission-stopped')
    record,reservation=exit.owner(book,clock())
    source=view.read_locked(root,wallet,pool,clock)
    check(source['wallet']==wallet and source['pool']==pool and source['phase']=='closed' and
          source['nativeHeldLamports']=='0' and all(x['heldAtomic']=='0' for x in source['tokenAccounts']) and
          source['ledgerHeadSha256']==reservation['ledgerHeadSha256'] and
          source['cycleBindingSha256']==reservation['cycleBindingSha256'],'exit-capture-source-changed')
    return dict(entryAccountingSha256=digest(record),admissionStateSha256=digest(state),
        policySha256=digest(book.policy),reservationSha256=digest(reservation),
        ledgerHeadSha256=source['ledgerHeadSha256'],cycleBindingSha256=source['cycleBindingSha256']),record,reservation


def reverse_scope(book,record,reservation):
    scope=deepcopy(book.policy['scope'])
    for left,right in (('source','destination'),('inputMint','outputMint'),('inputVault','outputVault')):
        scope['accounts'][left],scope['accounts'][right]=scope['accounts'][right],scope['accounts'][left]
    scope['amountIn']=record['accounting']['ownedAcquiredAtomic']
    scope['maxTotalFeeLamports']=reservation['exitFeeCapLamports']
    scope_check(scope)
    return scope


@view.cycles.binding.operation
def collect(home,wallet,pool,*,opener=None,clock=view.now,monotonic=time.monotonic,_evidence_sink=None,
            _replacement_expected=None,_preserved_expected=None,_continuation_expected=None):
    check(_evidence_sink is None or callable(_evidence_sink),'exit-capture-sink')
    if _continuation_expected is not None:
        from unsigned_exit_continuation import eligible as continuation_guard
        from preserved_exit_observation import identities
        identities(_continuation_expected)
        check(_replacement_expected is None and _preserved_expected is None and callable(_evidence_sink),'exit-capture-mode-conflict')
    if _preserved_expected is not None:
        from preserved_exit_observation import identities,guard,validate
        identities(_preserved_expected)
        check(_replacement_expected is None and _evidence_sink is None,'exit-capture-mode-conflict')
    result=dict(format=VERSION,state='unavailable',stage='admission',network='devnet',
        networkRequests=0,requestMethods=[],binding=None,provenance=None,diagnosticCode=None,
        databaseConnectionsReadOnly=True,preparationPersisted=False,sourceStateChanged=False,
        allocationTransferred=False,reservationReleased=False,exitAttemptsConsumed=0,
        signingApproved=False,executionApproved=False,validForSubmission=False,
        signaturesCreated=0,transactionsSent=0,privateKeyAccessed=False,
        runtimeIntegrated=False,nextCycleAuthorized=False,mainnetSupported=False,
        limitations=['Fresh RPC observations are not fills or a signing/submission permit.',
          'Twenty fixed devnet requests maximum, no retries; original ten-second freshness is not extended.',
          'Private evidence handoff only; atomic persistence and signing integration remain pending.',
          'Source lock covers cooperating local tools, not unrelated wallet activity.'])
    transport=None; phase_timing=diagnostics.Timing()
    def stage(name):
        phase_timing.mark(name); result['stage']=name
    try:
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals(),ExitStack() as locks:
            check(not view.cycles.c.submit.swap.stop(root),'exit-capture-stopped')
            book=exit.entry.submission._open(root,wallet,pool,clock)
            try:
                if _preserved_expected is not None or _continuation_expected is not None:
                    # Pin the existing DELETE-mode admission snapshot throughout
                    # the diagnostic. Closing rolls back this read-only transaction.
                    from admission_recovery import admission_read_lock
                    locks.enter_context(admission_read_lock(book.j.path))
                before,record,reservation=identity(book,root,wallet,pool,clock)
                # Replacement is a distinct internal path: one exact expired
                # unsigned preparation, with no signing/transport evidence.
                def preparation_guard():
                    if _continuation_expected is not None:
                        continuation_guard(book,root,_continuation_expected,clock())
                    elif _preserved_expected is not None:
                        guard(book,root,_preserved_expected,clock())
                    elif _replacement_expected is None:
                        check(exit.saved(book,clock()) is None,'exit-capture-already-prepared')
                    else:
                        from unsigned_exit_replacement import eligible
                        eligible(book,root,_replacement_expected,clock())
                preparation_guard()
                scope=reverse_scope(book,record,reservation)
                baseline=deepcopy(exit.BASELINE)
                start=clock();transport=Transport(root,clock,opener,monotonic,start)
                reviewer=lambda capture,now_ms:exit.preflight._review(capture,baseline,now_ms)
                stage('pool')
                first=preflight_capture._collect(pool=pool,opener=transport,now=clock,
                    monotonic=monotonic,baseline=baseline)
                check(reviewer(first,clock())['state']=='pinned-pool-snapshot','exit-capture-initial-pool')
                raw,_=exit.preflight.split_capture(first)
                price=exit.derive(raw,scope,slippage_bps=100,now_ms=clock())
                fresh=deepcopy(scope);fresh['minimumAmountOut']=price['quote']['minimumOutAmount']
                stage('packet')
                built=build(fresh,opener=transport,now=clock)
                stage('accounts')
                second=preflight_capture._collect(packet=built['packet'],opener=transport,now=clock,
                    monotonic=monotonic,baseline=baseline)
                price,checked,_=fresh_quote.combine(first,built,second,scope,stamp=clock(),review=reviewer)
                stage('simulation')
                items=[];genesis_items=[]
                sim=exit.unsigned_simulation.collect(built['packet'],second,price,transport=transport,
                    clock=clock,deadline=min(transport.deadline,checked['validUntilExclusiveMs']),
                    _evidence_sink=items.append,_genesis_sink=genesis_items.append)
                check(sim['state']=='unsigned-effects-match-quote' and len(items)==len(genesis_items)==1,'exit-capture-simulation')
                stage('final-binding')
                after,_,_=identity(book,root,wallet,pool,clock)
                check(before==after,'exit-capture-admission-changed')
                preparation_guard()
                evidence=dict(initialPool=raw,packet=built['packet'],capture=second,price=price,
                    simulationItem=items[0],simulationStartedAtMs=sim['requestedAtMs'],
                    simulationReceivedAtMs=sim['receivedAtMs'],completedAtMs=sim['finishedAtMs'])
                binding=exit.review(book,evidence,clock())
                finish=clock()
                check(transport.last<=finish<min(transport.deadline,binding['validUntilExclusiveMs']),
                      'exit-capture-expired')
                check(0<=monotonic()-transport.started<30,'exit-capture-time-budget')
                check(not view.cycles.c.submit.swap.stop(root),'exit-capture-stopped')
                check(transport.calls==METHODS and len(transport.request_hashes)==20,'exit-capture-incomplete')
                provenance=dict(format=VERSION+'-provenance',identity=before,startedAtMs=start,completedAtMs=finish,
                    evidenceSha256=digest(evidence),initialCaptureSha256=digest(first),packetBuildSha256=digest(built),
                    requestTraceSha256=digest(transport.request_hashes),finalGenesisSha256=digest(genesis_items[0]),networkRequests=20,
                    simulationParametersSha256=digest(transport.expected),
                    validUntilExclusiveMs=min(transport.deadline,binding['validUntilExclusiveMs']),durable=False)
                envelope=deepcopy(dict(evidence=evidence,initialCapture=first,packetBuild=built,
                    requestTrace=transport.request_hashes,finalGenesis=genesis_items[0],provenance=provenance)) if _evidence_sink is not None or _preserved_expected is not None else None
                # Hashing and private-envelope construction also consume freshness.
                delivered=clock()
                check(finish<=delivered<provenance['validUntilExclusiveMs'],'exit-capture-expired')
                check(0<=monotonic()-transport.started<30,'exit-capture-time-budget')
                check(not view.cycles.c.submit.swap.stop(root),'exit-capture-stopped')
                provenance['completedAtMs']=delivered
                if envelope is not None:
                    envelope['provenance']['completedAtMs']=delivered
                    if _preserved_expected is not None:
                        deadline=provenance['validUntilExclusiveMs']
                        timing=dict(collectionStartedAtMs=start,collectedAtMs=delivered,
                            originalDeadlineMs=deadline,collectionElapsedMs=delivered-start,
                            headroomAtCollectionMs=deadline-delivered,validatedAtMs=None,
                            validationElapsedMs=None,headroomAfterValidationMs=None)
                        result['observationTiming']=timing
                        stage('preserved-validation')
                        proof={k:v for k,v in envelope.items() if k!='evidence'}
                        end=validate(book,root,_preserved_expected,evidence,proof,binding,
                                     clock,monotonic,transport.started)
                        binding=dict(binding,validUntilExclusiveMs=deadline)
                        timing.update(validatedAtMs=end,validationElapsedMs=end-delivered,
                                      headroomAfterValidationMs=deadline-end)
                    else:
                        _evidence_sink(envelope)
                stage('complete')
                result.update(state='exit-evidence-collected-research-only',stage='complete',
                    binding=binding,provenance=provenance)
            finally:book.close()
    except (ValueError,KeyError,TypeError,IndexError,OSError,view.sqlite3.Error) as exc:
        if _preserved_expected is not None or _continuation_expected is not None:
            result.update(state='unavailable',binding=None,provenance=None)
        result['diagnosticCode']=str(exc) if str(exc) in diagnostics.CODES else 'exit-evidence-unavailable'
    finally:
        result['collectionTiming']=phase_timing.finish()
        if transport is not None:
            result.update(networkRequests=len(transport.calls),requestMethods=list(transport.calls))
    return result
