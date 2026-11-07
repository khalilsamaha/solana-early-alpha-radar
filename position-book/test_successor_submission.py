"""Real retired-source replay with disposable signatures and synthetic transport."""
from copy import deepcopy
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import successor_submission as m
import test_restricted_successor_signer as fixtures
from test_signed_exit_timing import files


class Replies:
    def __init__(self,test,*,lost=False,reply=None,missing=False,failed=False,wrong_wire=False,confirmed=False,genesis=None,fee=5000,valid=True,callback=None):
        self.t=test;self.calls=[];self.lost=lost;self.reply=reply;self.missing=missing;self.failed=failed
        self.wrong_wire=wrong_wire;self.confirmed=confirmed;self.genesis=genesis or m.transport.GENESIS['devnet']
        self.fee=fee;self.valid=valid;self.callback=callback
    def open(self,request,timeout=None):
        q=json.loads(request.data);self.calls.append(q);method=q['method'];params=q['params'];t=self.t
        t.assertEqual(request.full_url,m.transport.ENDPOINT)
        if self.callback:self.callback(method)
        slot=t.signed['minimumContextSlot'];sig=t.signed['signed']['signature'];wire=t.signed['signed']['signedWireBase64']
        error={'InstructionError':[2,'Custom']} if self.failed else None
        if method=='getGenesisHash':value=self.genesis
        elif method=='isBlockhashValid':
            t.assertEqual(params,[t.signed['request']['packet']['policy']['blockhash'],dict(commitment='confirmed',minContextSlot=slot)])
            value=dict(context=dict(slot=slot),value=self.valid)
        elif method=='getFeeForMessage':
            t.assertEqual(params,[m.base64.b64encode(m.original.decode_wire(wire)[1]).decode(),dict(commitment='confirmed',minContextSlot=slot)])
            value=dict(context=dict(slot=slot),value=self.fee)
        elif method=='sendTransaction':
            t.assertEqual(params,[wire,dict(encoding='base64',skipPreflight=False,preflightCommitment='confirmed',maxRetries=0,minContextSlot=slot)])
            db=sqlite3.connect(t.c.path.as_uri()+'?mode=ro',uri=True)
            try:t.assertEqual(db.execute('SELECT COUNT(*) FROM admission_successor_transport').fetchone()[0],1)
            finally:db.close()
            if self.lost:raise TimeoutError('synthetic lost send reply')
            value=self.reply or sig
        elif method=='getSignatureStatuses':
            t.assertEqual(params,[[sig],dict(searchTransactionHistory=True)])
            value=dict(context=dict(slot=slot+1),value=[dict(slot=slot+1,err=error,confirmations=1 if self.confirmed else None,confirmationStatus='confirmed' if self.confirmed else 'finalized')])
        elif method=='getTransaction':
            t.assertEqual(params,[sig,dict(encoding='base64',commitment='finalized',maxSupportedTransactionVersion=0)])
            value=None if self.missing else dict(slot=slot+1,transaction=[t.c.exit_wire if self.wrong_wire else wire,'base64'],meta=dict(err=error),version='legacy')
        else:raise AssertionError(method)
        return io.BytesIO(json.dumps(dict(jsonrpc='2.0',id=q['id'],result=value)).encode())


class SuccessorSubmissionTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.SuccessorBackendTests.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.SuccessorBackendTests.tearDownClass.__func__)
    tearDown=fixtures.SuccessorBackendTests.tearDown
    dispatch=fixtures.SuccessorBackendTests.dispatch
    lost=fixtures.SuccessorBackendTests.lost
    boundary=fixtures.SuccessorBackendTests.boundary
    markers=fixtures.SuccessorBackendTests.markers
    rows=fixtures.SuccessorBackendTests.rows
    def setUp(self):
        fixtures.SuccessorBackendTests.setUp(self)
        self.boundary();self.markers()
        m.backend._recover(self.c.home,self.c.wallet,self.c.pool,self.candidate,clock=lambda:self.c.now)
        b=self.c.book()
        try:
            record,ctx,_,signed=m.handoff.load(self.c.home,b,self.c.wallet,self.c.pool,self.candidate,lambda:self.c.now)
            self.signed=m.signing_state(record,signed)
            self.held=deepcopy(ctx['identity']['scopedAccounting'])
        finally:b.close()
        self.original_rows=self.rows();self.original_files=files(self.c)
    def submit(self,rpc=None):
        return m._submit(self.c.home,self.c.wallet,self.c.pool,self.candidate,allow_devnet_submit=True,opener=rpc or Replies(self),clock=lambda:self.c.now)
    def recover(self,rpc=None):return m._recover(self.c.home,self.c.wallet,self.c.pool,self.candidate,opener=rpc or Replies(self),clock=lambda:self.c.now)
    def status(self):return m._status(self.c.home,self.c.wallet,self.c.pool,self.candidate,clock=lambda:self.c.now)
    def preserved(self):
        after=self.rows();self.assertEqual(self.original_rows,{k:after[k] for k in self.original_rows})
        for name,data in self.original_files.items():
            if name!=str(self.c.path):self.assertEqual(files(self.c)[name],data)
    def rewrite(self,fn):
        b=self.c.book()
        try:
            rows=b.db.execute('SELECT * FROM admission_successor_transport ORDER BY seq').fetchall();previous=''
            for row in rows:
                v=json.loads(row['value']);fn(row['seq'],v)
                h=m.digest(dict(seq=row['seq'],atMs=row['at_ms'],value=v,previousHash=previous))
                b.db.execute('UPDATE admission_successor_transport SET value=?,previous_hash=?,hash=? WHERE seq=?',(m.encoded(v),previous,h,row['seq']));previous=h
        finally:b.close()

    def test_one_exact_send_commits_before_transport_and_duplicate_does_not_send(self):
        rpc=Replies(self);r=self.submit(rpc)
        self.assertEqual(r['state'],'rpc-acknowledged');self.assertEqual(r['sendRequestsThisRun'],1);self.assertEqual(len(rpc.calls),5)
        before=files(self.c);second=Replies(self);self.assertEqual(self.submit(second)['sendRequestsThisRun'],0)
        self.assertFalse(second.calls);self.assertEqual(files(self.c),before);self.preserved()
        self.assertNotIn(self.signed['signed']['signedWireBase64'],json.dumps(r))
        self.assertFalse(r['receiptEffectsReconciled']);self.assertFalse(r['reservationsReleased'])

    def test_lost_reply_recovers_exact_signature_after_stop_expiry_without_key_or_send(self):
        self.assertEqual(self.submit(Replies(self,lost=True))['state'],'successor-submission-unknown')
        self.c.now+=30000;(self.c.home/'STOP').touch(mode=0o600)
        with patch.object(m.backend,'_invoke',side_effect=AssertionError('key access')):
            rpc=Replies(self);r=self.recover(rpc);self.assertEqual(r['state'],'successor-finalized-evidence');self.assertEqual(len(rpc.calls),4)
            before=files(self.c);rpc=Replies(self);self.assertEqual(self.recover(rpc)['state'],r['state']);self.assertFalse(rpc.calls)
            self.assertEqual(files(self.c),before);self.assertEqual(self.submit()['sendRequestsThisRun'],0)
        self.preserved()

    def test_preflight_refusals_preserve_no_boundary(self):
        for kwargs in (dict(genesis='mainnet'),dict(valid=False),dict(fee=10001)):
            with self.subTest(kwargs=kwargs):
                rpc=Replies(self,**kwargs)
                with self.assertRaises(ValueError):self.submit(rpc)
                self.assertFalse(any(x['method']=='sendTransaction' for x in rpc.calls));self.assertEqual(self.status()['state'],'not-attempted')
        self.assertEqual(files(self.c),self.original_files)

    def test_missing_optin_and_default_transport_fail_before_source_access(self):
        with patch.object(m.handoff.view.cycles.c,'source_lock',side_effect=AssertionError('source')):
            with self.assertRaisesRegex(ValueError,'explicit-successor-submit-required'):m._submit('/missing','x','y','z')
            with self.assertRaisesRegex(ValueError,'successor-injected-transport-required'):m._submit('/missing','x','y','z',allow_devnet_submit=True)
            class FalseAdapter:
                def __bool__(self):return False
                def open(self,*args,**kwargs):raise AssertionError('network')
            with self.assertRaisesRegex(ValueError,'successor-injected-transport-required'):
                m._submit('/missing','x','y','z',allow_devnet_submit=True,opener=FalseAdapter())
            with self.assertRaisesRegex(ValueError,'successor-injected-transport-required'):
                m._recover('/missing','x','y','z',opener=FalseAdapter())

    def test_stop_and_expiry_before_or_during_preflight_refuse(self):
        original=self.c.now
        for kind in ('stop','expiry'):
            with self.subTest(kind=kind):
                def stop(method):
                    if method=='getFeeForMessage':
                        if kind=='stop':(self.c.home/'STOP').touch(mode=0o600)
                        else:self.c.now+=30000
                rpc=Replies(self,callback=stop)
                with self.assertRaises(ValueError):self.submit(rpc)
                self.assertFalse(any(x['method']=='sendTransaction' for x in rpc.calls));self.assertEqual(self.status()['state'],'not-attempted')
                before=Replies(self)
                with self.assertRaises(ValueError):self.submit(before)
                self.assertFalse(before.calls);self.c.now=original;(self.c.home/'STOP').unlink(missing_ok=True)

    def test_source_mutation_during_preflight_blocks_send(self):
        path=self.c.path.parent/'exit-signer-ack.json';raw=path.read_bytes()
        def changed(method):
            if method=='getFeeForMessage':path.write_text('{}')
        rpc=Replies(self,callback=changed)
        try:
            with self.assertRaises(ValueError):self.submit(rpc)
            self.assertFalse(any(x['method']=='sendTransaction' for x in rpc.calls))
        finally:path.write_bytes(raw)
        self.assertEqual(self.status()['state'],'not-attempted')

    def test_postcommit_crash_consumes_send_boundary_without_retry(self):
        request=m.transport.SendRpc.request
        def crash(client,method,params):
            if method=='sendTransaction':raise OSError('after durable commit')
            return request(client,method,params)
        with patch.object(m.transport.SendRpc,'request',crash),self.assertRaises(OSError):self.submit()
        self.assertEqual(self.status()['state'],'successor-submission-unknown')
        rpc=Replies(self);self.assertEqual(self.submit(rpc)['sendRequestsThisRun'],0);self.assertFalse(rpc.calls)
        self.assertEqual(self.recover()['state'],'successor-finalized-evidence');self.preserved()

    def test_postcommit_expiry_and_storage_rollback(self):
        append=m.append
        def fail(*args):append(*args);raise OSError('precommit write failure')
        with patch.object(m,'append',fail),self.assertRaises(OSError):self.submit()
        self.assertEqual(files(self.c),self.original_files)
        request=m.transport.SendRpc.request
        def expire(client,method,params):
            if method=='sendTransaction':self.c.now+=30000
            return request(client,method,params)
        rpc=Replies(self)
        with patch.object(m.transport.SendRpc,'request',expire),self.assertRaises(ValueError):self.submit(rpc)
        self.assertFalse(any(x['method']=='sendTransaction' for x in rpc.calls))
        self.assertEqual(self.status()['state'],'successor-submission-unknown');self.assertEqual(self.submit()['sendRequestsThisRun'],0)

    def test_wrong_send_ack_quarantines_and_blocks_recovery_rpc(self):
        self.assertEqual(self.submit(Replies(self,reply=self.c.wallet))['state'],'quarantined')
        rpc=Replies(self);self.assertEqual(self.recover(rpc)['state'],'quarantined');self.assertFalse(rpc.calls);self.preserved()

    def test_failed_and_wrong_wire_finality_never_release(self):
        self.submit();r=self.recover(Replies(self,failed=True));self.assertEqual(r['state'],'successor-failed-evidence')
        self.assertFalse(r['reservationsReleased']);self.preserved()
        # Restore this disposable per-test source to exercise a different outcome.
        for name,data in self.original_files.items():Path(name).write_bytes(data)
        self.submit();r=self.recover(Replies(self,wrong_wire=True));self.assertEqual(r['state'],'quarantined');self.preserved()

    def test_pending_confirmed_and_capture_cap_do_not_invent_success(self):
        rpc=Replies(self);before=files(self.c);self.assertEqual(self.recover(rpc)['state'],'not-attempted');self.assertFalse(rpc.calls);self.assertEqual(before,files(self.c))
        self.submit()
        for i in range(m.MAX_CAPTURES):
            r=self.recover(Replies(self,missing=i%2==0,confirmed=i%2==1));self.assertNotEqual(r['state'],'successor-finalized-evidence')
        rpc=Replies(self)
        with self.assertRaisesRegex(ValueError,'successor-transport-capture-cap'):self.recover(rpc)
        self.assertFalse(rpc.calls);self.preserved()

    def test_rehashed_boundary_substitution_refuses_and_lifecycle_tracks_history(self):
        self.submit();self.recover()
        b=self.c.book()
        try:
            projection=m.handoff.successor.history.lifecycle.projection(b,self.c.home,self.c.wallet,self.c.pool,lambda:self.c.now)
            self.assertEqual(projection[3]['exitSuccessorTransport'],'successor-finalized-evidence')
            self.assertFalse(projection[2]['scopedClosureRecorded']);self.assertEqual(projection[2],self.held)
            from admission_recovery import retirement_projection
            p=retirement_projection(b,self.c.home,self.c.wallet,self.c.pool,lambda:self.c.now)
            self.assertEqual(p['successorTransportState'],'successor-finalized-evidence')
        finally:b.close()
        self.rewrite(lambda seq,v:v.update(successorSha256='0'*64) if seq==1 else None)
        with self.assertRaisesRegex(ValueError,'successor-transport-boundary-binding'):self.status()

    def test_writer_exclusion_and_orphan_transport(self):
        append=m.append
        def locked(*args):
            db=sqlite3.connect(self.c.path,timeout=0)
            try:
                with self.assertRaises(sqlite3.OperationalError):db.execute('BEGIN IMMEDIATE')
            finally:db.close()
            return append(*args)
        with patch.object(m,'append',locked):self.submit()
        b=self.c.book()
        try:b.db.execute('DROP TABLE admission_successor_signing')
        finally:b.close()
        with self.assertRaises(ValueError):self.status()
        self.assertFalse(m.handoff.successor.history.lifecycle.inspect(self.c.home,self.c.wallet,self.c.pool,clock=lambda:self.c.now)['coherent'])

    def test_acknowledgment_write_loss_recovers_without_resending(self):
        append=m.append;rpc=Replies(self)
        def fail(book,value,state,now):
            append(book,value,state,now)
            if value['kind']=='ack':raise OSError('ack persistence lost')
        with patch.object(m,'append',fail),self.assertRaises(OSError):self.submit(rpc)
        self.assertEqual(sum(q['method']=='sendTransaction' for q in rpc.calls),1)
        self.assertEqual(self.status()['state'],'successor-submission-unknown')
        self.assertEqual(self.submit()['sendRequestsThisRun'],0)
        self.assertEqual(self.recover()['state'],'successor-finalized-evidence');self.preserved()

    def test_context_regression_and_clock_rollback_refuse_before_send(self):
        rpc=Replies(self);open_reply=rpc.open
        def stale(request,timeout=None):
            reply=json.load(open_reply(request,timeout))
            if json.loads(request.data)['method']=='isBlockhashValid':reply['result']['context']['slot']=0
            return io.BytesIO(json.dumps(reply).encode())
        with patch.object(rpc,'open',stale),self.assertRaises(ValueError):self.submit(rpc)
        self.assertEqual(self.status()['state'],'not-attempted')
        stamp=self.c.now
        def backwards(method):
            if method=='getGenesisHash':self.c.now-=1
        rpc=Replies(self,callback=backwards)
        with self.assertRaises(ValueError):self.submit(rpc)
        self.c.now=stamp
        self.assertFalse(any(q['method']=='sendTransaction' for q in rpc.calls))
        self.assertEqual(files(self.c),self.original_files)

    def test_empty_or_corrupt_chain_fails_closed_without_network(self):
        b=self.c.book()
        try:b.db.execute('CREATE TABLE admission_successor_transport (seq INTEGER PRIMARY KEY,at_ms INTEGER,value TEXT,previous_hash TEXT,hash TEXT)')
        finally:b.close()
        rpc=Replies(self)
        with self.assertRaisesRegex(ValueError,'successor-transport-event-cap'):self.submit(rpc)
        self.assertFalse(rpc.calls)
        b=self.c.book()
        try:b.db.execute('DROP TABLE admission_successor_transport')
        finally:b.close()
        self.submit();b=self.c.book()
        try:b.db.execute('UPDATE admission_successor_transport SET hash=? WHERE seq=1',('0'*64,))
        finally:b.close()
        with self.assertRaisesRegex(ValueError,'successor-transport-integrity'):self.status()

    def test_conflicting_terminal_claims_quarantine_without_releasing_holds(self):
        self.submit();self.recover();b=self.c.book()
        try:
            record,_,_,signed,state=m.load(self.c.home,b,self.c.wallet,self.c.pool,self.candidate,lambda:self.c.now)
            capture=deepcopy(state['captures'][0])
            capture['rpcEvidence']['transaction']['result']['meta']['err']={'InstructionError':[2,'Custom']}
            capture['rpcEvidence']['signatureStatus']['result']['value'][0]['err']={'InstructionError':[2,'Custom']}
            with b.j.transaction():m.append(b,capture,state,self.c.now)
        finally:b.close()
        self.assertEqual(self.status()['state'],'quarantined');self.preserved()


if __name__=='__main__':unittest.main()
