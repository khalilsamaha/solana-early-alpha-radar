"""Disposable synthetic provider and connected real-clock successor execution gate."""
import base64
import io
import json
from pathlib import Path
import sqlite3
import time
from unittest.mock import patch

import successor_execution as m
import successor_signing_rehearsal as fixture
from core import check

VERSION='successor-execution-rehearsal-1'


class Provider:
    """Synthetic one-send loss plus exact-signature finalized RPC claims."""
    def __init__(self,path,*,lost=True,hook=None):
        self.path=path;self.lost=lost;self.hook=hook;self.calls=[];self.wire=None;self.signature=None;self.slot=None
    def open(self,request,timeout=None):
        q=json.loads(request.data);method=q['method'];p=q['params'];self.calls.append(method)
        check(request.full_url==m.submission.transport.ENDPOINT,'rehearsal-endpoint')
        if self.hook:self.hook(method)
        if method=='getGenesisHash':value=m.submission.transport.GENESIS['devnet']
        elif method=='isBlockhashValid':
            self.blockhash=p[0];self.slot=p[1]['minContextSlot'];value=dict(context=dict(slot=self.slot),value=True)
        elif method=='getFeeForMessage':
            self.message=p[0];check(p[1]['minContextSlot']==self.slot,'rehearsal-context')
            value=dict(context=dict(slot=self.slot),value=5000)
        elif method=='sendTransaction':
            check(self.calls.count(method)==1,'rehearsal-duplicate-send')
            check(p[1]==dict(encoding='base64',skipPreflight=False,preflightCommitment='confirmed',maxRetries=0,minContextSlot=self.slot),'rehearsal-send-options')
            parts=m.submission.original.decode_wire(p[0]);self.wire=p[0]
            self.signature=parts[4]['transaction']['signatures'][0];self.version=parts[4]['version']
            check(base64.b64encode(parts[1]).decode()==self.message and
                  parts[4]['transaction']['message']['recentBlockhash']==self.blockhash,'rehearsal-exact-wire')
            db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)
            try:
                rows=db.execute('SELECT value FROM admission_successor_transport ORDER BY seq').fetchall()
                check(len(rows)==1 and json.loads(rows[0][0])['signature']==self.signature,'rehearsal-durable-boundary')
            finally:db.close()
            if self.lost:raise TimeoutError('synthetic lost send reply')
            value=self.signature
        elif method=='getSignatureStatuses':
            check(p==[[self.signature],dict(searchTransactionHistory=True)],'rehearsal-recovery-signature')
            value=dict(context=dict(slot=self.slot+1),value=[dict(slot=self.slot+1,err=None,confirmationStatus='finalized',confirmations=None)])
        elif method=='getTransaction':
            check(p==[self.signature,dict(encoding='base64',commitment='finalized',maxSupportedTransactionVersion=0)],'rehearsal-recovery-signature')
            value=dict(slot=self.slot+1,transaction=[self.wire,'base64'],version=self.version,meta=dict(err=None))
        else:raise AssertionError('unexpected synthetic method')
        return io.BytesIO(json.dumps(dict(jsonrpc='2.0',id=q['id'],result=value)).encode())


def connected(c):
    report=c.report;f=c.f;rpc=Provider(c.path)
    args=dict(allow_unsigned_successor=True,allow_private_key_signing=True,allow_devnet_submit=True,
              expiry_opener=c.expiry,quote_opener=c.quote,submission_opener=rpc,clock=c.clock)
    with fixture.phase(report,'collection-signing-preflight-single-send'):
        fixture.require_cold_reuse_scopes();start=time.monotonic()
        result=m._collect_sign_submit(f.home,f.wallet,f.pool,c.expected,c.retirement,**args)
        fixture.require_cold_reuse_scopes()
        report['integration']=result;report['integrationElapsedMs']=round((time.monotonic()-start)*1000,3)
        report['headroomAtReturnMs']=None if result['originalDeadlineMs'] is None else result['originalDeadlineMs']-c.clock()
        report['syntheticSendRequests']=rpc.calls.count('sendTransaction')
        check(result['state']=='successor-submission-unknown','rehearsal-send-state')
        check(result['completedWithinOriginalDeadline'] and report['headroomAtReturnMs']>0,'rehearsal-original-deadline')
        check(result['collectionRequests']==28 and result['senderRequests']==5 and result['sendRequestsThisRun']==1,'rehearsal-request-count')
        check(result['originalDeadlineCheckedBeforeSend'] and result['applicationSendBoundaryRecorded'],'rehearsal-durable-boundary')
        check(result['signing']['signatureCreatedThisRun'] is True and result['signing']['signerInvocationAttempts']==1,'rehearsal-independent-signature')
    report['cases'].update({'complete-collection-independent-signing-and-send-before-original-deadline':'passed',
        'one-durable-send-with-lost-response-keeps-uncertainty':'passed'})
    with fixture.phase(report,'repeated-composition-no-send-or-resign'):
        frozen=c.path.read_bytes();n=len(rpc.calls)
        with patch.object(m.signing.backend,'_invoke',side_effect=AssertionError('second signature')):
            again=m._collect_sign_submit(f.home,f.wallet,f.pool,c.expected,c.retirement,**args)
        check(again['state']=='existing-successor-held' and again['sendRequestsThisRun']==0 and
              again['collectionRequests']==0 and len(rpc.calls)==n and c.path.read_bytes()==frozen,'rehearsal-repeat-composition')
    report['cases']['repeated-composition-preserves-records-without-new-requests']='passed'
    with fixture.phase(report,'keyless-signature-observation-after-stop'):
        c.key.unlink();(f.home/'STOP').touch(mode=0o600)
        n=len(rpc.calls)
        with patch.object(m.signing.backend,'_invoke',side_effect=AssertionError('unexpected signer')):
            recovered=m._recover(f.home,f.wallet,f.pool,result['successorSha256'],opener=rpc,clock=c.clock)
        check(recovered['state']=='successor-finalized-evidence' and len(rpc.calls)-n==4 and
              recovered['sendRequestsThisRun']==0,'rehearsal-recovery-state')
        report['recovery']=recovered
    report['cases']['lost-send-response-recovered-by-original-signature-without-key']='passed'
    with fixture.phase(report,'terminal-recovery-and-preserved-holds'):
        frozen=c.path.read_bytes();n=len(rpc.calls)
        again=m._recover(f.home,f.wallet,f.pool,result['successorSha256'],opener=rpc,clock=c.clock)
        check(again['transportHeadSha256']==recovered['transportHeadSha256'] and len(rpc.calls)==n and c.path.read_bytes()==frozen,
              'rehearsal-repeat-recovery')
        b=m.submission.transport._open(f.home,f.wallet,f.pool,c.clock)
        try:
            after=fixture.table_rows(b)
            check(all(after[k]==v for k,v in c.before_tables.items()),'rehearsal-old-evidence-changed')
            check(set(after)-set(c.before_tables)=={'admission_exit_successor','admission_successor_signing','admission_successor_transport'},'rehearsal-unexpected-tables')
            from admission_recovery import retirement_projection
            projection=fixture.prepare_fixture(retirement_projection,b,f.home,f.wallet,f.pool,c.clock)
            report['heldAccounting']=projection['scopedAccounting']
            check(projection['successorTransportState']=='successor-finalized-evidence' and
                  not report['heldAccounting']['scopedClosureRecorded'],'rehearsal-held-accounting')
        finally:b.close()
        for name,raw in c.old_files.items():check((c.path.parent/name).read_bytes()==raw,'rehearsal-old-marker-changed')
        for name,raw in c.before_source.items():
            if Path(name)!=c.key:check(Path(name).read_bytes()==raw,'rehearsal-historical-source-changed')
    report['cases'].update({'terminal-recovery-no-network-or-write':'passed',
        'retired-source-and-cumulative-holds-preserved':'passed',
        'finalized-claim-does-not-release-funds-or-close-position':'passed'})
    report['originalSourceUnchanged']=True


def run():
    r=fixture.run(_exercise=connected)
    r.update(format=VERSION,liveSenderIntegrated=False,executionApproved=False,
        preservationChecksCompleted=r.get('originalSourceUnchanged') is True,
        limitations=['Synthetic RPC replies and disposable keys only; no operational wallet or real network.',
            'Real-clock 1 MiB collection/sign/send path; original freshness limit and cumulative holds unchanged.',
            'One simulated lost send response; recovery observes the exact signature and does not resend.',
            'Finalized RPC claims are not reconciled token/fee balances or scoped closure.'])
    return r
