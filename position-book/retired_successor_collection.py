"""Bounded raw successor collection; operator entry point is read-only observation.

The collector is also exercised with the atomic contract offline. No live durable
preparation, signer, sender or report-import path is exposed by this module.
"""
from copy import deepcopy
import time
import urllib.error

import retired_exit_successor as successor
import admission_exit_capture as capture
from contract import digest
from core import check
from journal import read_only_journals

VERSION='retired-successor-collection-1'
view=successor.view
expiry=successor.expiry
retirement=successor.retirement
history=successor.history
CODES=set(capture.diagnostics.CODES)|{'successor-retirement-mismatch','successor-already-present',
    'successor-stopped','successor-total-budget','successor-signing-conflict','successor-backend-conflict',
    'successor-expiry-conflict','successor-expiry-age','successor-chain-regressed',
    'successor-reused-blockhash','successor-unresolved-fee-exposure','successor-account-slot-regressed',
    'successor-scoped-account-changed','successor-budget-blocked','successor-expiry-context',
    'successor-expired-before-return','retirement-evidence-conflict','chain-read-budget','expiry-account-time'}


def diagnostic(exc):
    if isinstance(exc,urllib.error.HTTPError):return 'provider-http-error'
    if isinstance(exc,TimeoutError):return 'provider-timeout'
    return str(exc) if str(exc) in CODES else 'successor-evidence-unavailable'


class ExpiryReads(expiry.chain.BoundedReads):
    def __init__(self,opener,monotonic,guard,budget):
        super().__init__([],opener,monotonic,budget=budget);self.guard=guard
    def open(self,request,timeout):
        self.guard();return super().open(request,timeout)


class QuoteTransport(capture.Transport):
    def __init__(self,root,clock,opener,monotonic,start,guard):
        super().__init__(root,clock,opener,monotonic,start);self.guard=guard
    def open(self,request,timeout):
        remaining=self.guard()
        check(remaining>0,'successor-total-budget')
        return super().open(request,min(timeout,remaining))


class Collector:
    """In-process producer; caller owns the root lock and pinned admission source."""
    def __init__(self,root,book,wallet,pool,retired,clock,monotonic,*,expiry_opener=None,quote_opener=None,operation_started=None):
        self.root=root;self.book=book;self.wallet=wallet;self.pool=pool;self.retired=retired
        self.clock=clock;self.monotonic=monotonic;self.expiry_opener=expiry_opener;self.quote_opener=quote_opener
        self.started=monotonic() if operation_started is None else operation_started
        self.reads=None;self.quote=None;self.stage='local-scope';self.timings={};self.stopped=False
    def mark(self,stage):self.stage=stage
    def guard(self):
        elapsed=self.monotonic()-self.started
        check(0<=elapsed<=120,'successor-total-budget')
        self.stopped=view.cycles.c.submit.swap.stop(self.root)
        check(not self.stopped,'successor-stopped')
        check(digest(retirement.row(self.book))==digest(self.retired),'successor-retirement-mismatch')
        check(not successor.present(self.book),'successor-already-present')
        return 120-elapsed
    def __call__(self,ctx):
        self.guard()
        before,record,reservation=capture.identity(self.book,self.root,self.wallet,self.pool,self.clock)
        scope=capture.reverse_scope(self.book,record,reservation)
        self.mark('expiry-observation');begin=self.clock()
        self.reads=ExpiryReads(self.expiry_opener,self.monotonic,self.guard,min(30,self.guard()))
        proof=expiry.collect_context(ctx,self.reads,self.clock)
        check(0<=self.monotonic()-self.reads.started<=self.reads.budget,'chain-read-budget')
        successor.fresh_review(ctx,self.retired,proof,self.clock());self.guard()
        self.timings['expiryElapsedMs']=self.clock()-begin
        start=self.clock();self.quote=QuoteTransport(self.root,self.clock,self.quote_opener,self.monotonic,start,self.guard)
        try:
            envelope,_,p=capture.collect_locked(self.book,self.root,self.wallet,self.pool,before,scope,
                self.quote,self.clock,self.monotonic,self.mark,self.guard)
            evidence=envelope.pop('evidence')
            self.timings.update(collectionElapsedMs=p['completedAtMs']-start,
                originalDeadlineMs=p['validUntilExclusiveMs'],collectedAtMs=p['completedAtMs'])
            self.mark('successor-validation')
            return dict(expiryProof=proof,evidence=evidence,collection=envelope)
        finally:self.quote.close()
    def telemetry(self):
        calls=(self.reads.calls if self.reads else [])+(self.quote.calls if self.quote else [])
        return dict(networkRequests=len(calls),requestMethods=list(calls),timing=deepcopy(self.timings),
            rpcSession=self.quote.session.summary() if self.quote and self.quote.session else None)


@view.cycles.binding.operation
@history.fresh_signing.timing.signature_replay
def observe(home,wallet,pool,expected,expected_retirement,*,clock=view.now,monotonic=time.monotonic,
            _expiry_opener=None,_quote_opener=None):
    r=dict(format=VERSION,state='successor-observation-unavailable-held',stage='local-replay',
        diagnosticCode=None,network='devnet',networkRequests=0,requestMethods=[],timing={},rpcSession=None,
        preparationSha256=None,retirementSha256=None,binding=None,
        sourceStateChanged=False,databaseConnectionsReadOnly=True,successorPersisted=False,
        oldAttemptStillRetired=True,reservationsReleasedThisRun=False,commitAndSigningHeadroomMeasured=False,
        privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,
        signingApproved=False,executionApproved=False,validForSubmission=False,replacementAuthorized=False,mainnetSupported=False,
        limitations=['One fixed devnet endpoint; provider absence is not proof of non-execution.',
            'Read-only observation is not a saved successor or transferable signing authority.',
            'Eight expiry/account reads followed by at most twenty quote/simulation requests; no retries.',
            'Original quote freshness and all existing holds remain enforced.'])
    producer=None;started=monotonic();local_start=clock()
    try:
        successor.replan.identity(expected);successor.replan.identity(expected_retirement)
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            book=successor.preparation.entry.submission._open(root,wallet,pool,clock)
            try:
                with history.lifecycle.admission_read_lock(book.j.path):
                    ctx=expiry.context(root,book,wallet,pool,expected,clock)
                    retired=retirement.row(book)
                    check(retired is not None and digest(retired)==expected_retirement,'successor-retirement-mismatch')
                    retirement.validate(retired,ctx,clock())
                    check(not successor.present(book),'successor-already-present')
                    check(successor.replan.budget(book.policy,ctx['identity']['scopedAccounting'])['blockers']==[],
                        'successor-budget-blocked')
                    with history.transport.ExitSubmission(book).snapshot():
                        signed=history.transport.ExitSubmission(book).signing()
                        check(digest(signed)==ctx['identity']['signingStateSha256'],'successor-signing-conflict')
                    check(0<=monotonic()-started<120,'successor-total-budget')
                    r['timing']['localReplayMs']=clock()-local_start
                    producer=Collector(root,book,wallet,pool,retired,clock,monotonic,
                        expiry_opener=_expiry_opener,quote_opener=_quote_opener,operation_started=started)
                    item=producer(ctx)
                    history.backend._attempt_record_for_state(root,book,signed)
                    check(history.backend._read_ack(root,book,signed)==ctx['signedWire'],'successor-backend-conflict')
                    binding=successor.binding(book,ctx,retired,item['expiryProof'],item['evidence'],item['collection'],clock())
                    end=clock();deadline=binding['validUntilExclusiveMs']
                    check(item['collection']['provenance']['completedAtMs']<=end<deadline,'successor-expired-before-return')
                    successor.fresh_review(ctx,retired,item['expiryProof'],end);producer.guard()
                    final=clock()
                    check(end<=final<deadline,'successor-expired-before-return')
                    check(final-item['expiryProof']['observedAtMs']<=30000,'successor-expiry-age')
                    end=final
                    check(0<=monotonic()-started<=120,'successor-total-budget')
                    producer.timings.update(validatedAtMs=end,validationElapsedMs=end-item['collection']['provenance']['completedAtMs'],
                        headroomAfterValidationMs=deadline-end)
                    r.update(state='successor-observation-consistent-held',stage='complete',binding=binding,
                        preparationSha256=expected,retirementSha256=expected_retirement)
            finally:book.close()
        completed=clock()
        check(end<=completed<deadline,'successor-expired-before-return')
        check(completed-item['expiryProof']['observedAtMs']<=30000,'successor-expiry-age')
        check(0<=monotonic()-started<=120,'successor-total-budget')
        producer.timings.update(completedAtMs=completed,headroomAtReturnMs=deadline-completed)
    except (ValueError,KeyError,TypeError,IndexError,OSError,view.sqlite3.Error) as exc:
        r.update(state='successor-observation-unavailable-held',binding=None)
        r['diagnosticCode']='successor-stopped' if producer and producer.stopped else diagnostic(exc)
        if producer:r['stage']=producer.stage
    finally:
        if producer:
            info=producer.telemetry();info['timing']={**r['timing'],**info['timing']};r.update(info)
        r['timing']['totalElapsedMs']=round((monotonic()-started)*1000,3)
    return r
