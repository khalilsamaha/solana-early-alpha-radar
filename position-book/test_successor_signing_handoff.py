"""Separate one-shot successor boundaries over real retired source replay."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import successor_signing_handoff as m
import test_retired_exit_successor as fixtures
import successor_signing_test_fixture as crypto_fixture
from test_signed_exit_timing import files
from exit_submission_checks import submit,FakeRpc


class SuccessorSigningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(fixtures,'signed_case',crypto_fixture.signed_case):
            fixtures.SuccessorTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixtures.SuccessorTests.tearDownClass.__func__(cls)
    def setUp(self):
        fixtures.SuccessorTests.setUp(self)
        r=fixtures.SuccessorTests.prepare(self)
        self.candidate=r['recordSha256'];self.before=files(self.c)
    def tearDown(self):fixtures.SuccessorTests.tearDown(self)
    def dispatch(self,adapter=None,expected=None):
        return m._dispatch(self.c.home,self.c.wallet,self.c.pool,expected or self.candidate,
            signer_adapter=adapter or self.lost,clock=lambda:self.c.now)
    def lost(self,request):raise TimeoutError('synthetic lost response')
    def status(self):return m._status(self.c.home,self.c.wallet,self.c.pool,self.candidate,clock=lambda:self.c.now)
    def recover(self,wire=None):return m._recover(self.c.home,self.c.wallet,self.c.pool,self.candidate,
        signed_response=wire,clock=lambda:self.c.now)
    def rows(self):return fixtures.SuccessorTests.rows(self)
    def boundary(self):
        with self.assertRaises(TimeoutError):self.dispatch()
    def rewrite(self,fn):
        b=self.c.book()
        try:
            rows=b.db.execute('SELECT * FROM admission_successor_signing ORDER BY seq').fetchall();previous=''
            for r in rows:
                v=json.loads(r['value']);fn(r['seq'],v)
                h=m.digest(dict(seq=r['seq'],atMs=r['at_ms'],value=v,previousHash=previous))
                b.db.execute('UPDATE admission_successor_signing SET value=?,previous_hash=?,hash=? WHERE seq=?',
                    (m.encoded(v),previous,h,r['seq']));previous=h
        finally:b.close()

    def test_durable_boundary_preserves_old_generation_and_never_retries(self):
        before=self.rows();calls=[]
        def adapter(request):
            calls.append(request)
            db=sqlite3.connect(self.c.path.as_uri()+'?mode=ro',uri=True)
            try:
                row=json.loads(db.execute('SELECT value FROM admission_successor_signing WHERE seq=1').fetchone()[0])
                self.assertEqual(row['request'],request)
            finally:db.close()
            with self.assertRaises(BlockingIOError):self.dispatch()
            raise TimeoutError('lost reply')
        with self.assertRaises(TimeoutError):self.dispatch(adapter)
        after=self.rows();self.assertEqual(set(after)-set(before),{m.TABLE})
        self.assertEqual(before,{k:after[k] for k in before})
        request=calls[0];self.assertEqual(request['attemptNumber'],2);self.assertEqual(request['attemptsConsumed'],1)
        self.assertEqual(request['additionalFeeReservationLamports'],'0')
        self.assertEqual(request['retiredFeeExposureHeldLamports'],'10000')
        frozen=files(self.c)
        r=self.dispatch(adapter);self.assertEqual(r['signerAdapterCallsThisRun'],0);self.assertEqual(len(calls),1)
        self.assertEqual(r['state'],'successor-signing-unknown');self.assertEqual(self.status()['headSha256'],r['headSha256'])
        self.assertEqual(self.recover()['headSha256'],r['headSha256']);self.assertEqual(files(self.c),frozen)
        for name,data in self.before.items():
            if Path(name)!=self.c.path:self.assertEqual(Path(name).read_bytes(),data)
        self.assertNotIn('packet',json.dumps(r));self.assertNotIn('signedTransaction',json.dumps(r))

    def test_exact_successor_signature_and_duplicate_recovery_preserve_holds(self):
        before=self.rows();r=self.dispatch(self.c.sign_successor)
        self.assertEqual(r['state'],'successor-signed-recorded');self.assertTrue(r['acknowledgmentRecorded'])
        self.assertEqual(r['signerAdapterCallsThisRun'],1)
        after=self.rows();self.assertEqual(before,{k:after[k] for k in before})
        b=self.c.book()
        try:
            state=m.read(b,m.successor.row(b),self.c.now);wire=state['signed']['signedWireBase64']
            self.assertNotEqual(wire,self.c.exit_wire)
        finally:b.close()
        frozen=files(self.c)
        self.assertEqual(self.recover(wire)['headSha256'],r['headSha256'])
        self.assertEqual(self.dispatch()['signerAdapterCallsThisRun'],0);self.assertEqual(files(self.c),frozen)
        self.assertNotIn(wire,json.dumps(r));self.assertFalse(r['validForSubmission'])

    def test_lost_signature_recovered_after_stop_and_expiry_without_resigning(self):
        replies=[]
        def adapter(request):
            replies.append(self.c.sign_successor(request));raise TimeoutError('lost real signed reply')
        with self.assertRaises(TimeoutError):self.dispatch(adapter)
        self.c.now+=30000;(self.c.home/'STOP').touch(mode=0o600)
        r=self.recover(replies[0]);self.assertEqual(r['state'],'successor-signed-recorded')
        self.assertTrue(r['evidenceExpired']);self.assertTrue(r['stopRequested'])
        self.assertEqual(r['signerAdapterCallsThisRun'],0);self.assertFalse(r['reservationsReleasedThisRun'])
        self.assertEqual(self.dispatch(adapter)['signerAdapterCallsThisRun'],0);self.assertEqual(len(replies),1)

    def test_late_adapter_reply_is_recorded_but_conflicting_reply_quarantines(self):
        def adapter(request):
            wire=self.c.sign_successor(request);self.c.now+=10000
            (self.c.home/'STOP').touch(mode=0o600);return wire
        r=self.dispatch(adapter);self.assertEqual(r['state'],'successor-signed-recorded')
        self.assertTrue(r['evidenceExpired']);self.assertTrue(r['stopRequested'])
        r=self.recover(self.c.exit_wire);self.assertEqual(r['state'],'successor-signing-quarantined')
        self.assertTrue(r['acknowledgmentRecorded']);self.assertFalse(r['validForSubmission'])

    def test_ack_write_and_final_output_loss_never_repeat_signing(self):
        for mode in ('ack-write','output'):
            with self.subTest(mode=mode):
                for path,raw in self.before.items():Path(path).write_bytes(raw)
                responses=[];append=m.append;public=m.public
                def adapter(request):
                    responses.append(self.c.sign_successor(request));return responses[-1]
                def failing_append(book,value,state,now):
                    append(book,value,state,now)
                    if state is not None and mode=='ack-write':raise OSError('lost acknowledgment write')
                def failing_public(*a,**kw):
                    if mode=='output':raise OSError('lost completion output')
                    return public(*a,**kw)
                with patch.object(m,'append',side_effect=failing_append),patch.object(m,'public',side_effect=failing_public):
                    with self.assertRaises(OSError):self.dispatch(adapter)
                state=self.status()['state']
                self.assertEqual(state,'successor-signing-unknown' if mode=='ack-write' else 'successor-signed-recorded')
                self.assertEqual(self.dispatch(adapter)['signerAdapterCallsThisRun'],0);self.assertEqual(len(responses),1)
                self.assertEqual(self.recover(responses[0])['state'],'successor-signed-recorded')

    def test_wrong_candidate_expiry_and_stop_prevent_boundary(self):
        with self.assertRaises(ValueError):self.dispatch(expected='0'*64)
        self.c.now+=10000
        with self.assertRaisesRegex(ValueError,'expired'):self.dispatch()
        self.c.now=self.stamp
        (self.c.home/'STOP').touch(mode=0o600)
        with self.assertRaisesRegex(ValueError,'stopped'):self.dispatch()
        (self.c.home/'STOP').unlink();self.assertEqual(files(self.c),self.before)

    def test_old_wire_is_quarantined_and_cannot_become_successor_ack(self):
        r=self.dispatch(lambda _:self.c.exit_wire)
        self.assertEqual(r['state'],'successor-signing-quarantined');self.assertFalse(r['acknowledgmentRecorded'])
        before=files(self.c);self.assertEqual(self.recover(self.c.exit_wire)['state'],r['state'])
        self.assertEqual(self.dispatch()['signerAdapterCallsThisRun'],0);self.assertEqual(files(self.c),before)
        r=m.successor.history.lifecycle.inspect(self.c.home,self.c.wallet,self.c.pool,clock=lambda:self.c.now)
        self.assertFalse(r['coherent']);self.assertEqual(r['phase'],'quarantined')

    def test_rehashed_request_cannot_change_generation_or_holds(self):
        for field,value in (('attemptsConsumed',0),('retirementSha256','0'*64),('feeCapLamports','10001'),
                            ('quantityAtomic','1'),('contextSha256','0'*64)):
            with self.subTest(field=field):
                for path,raw in self.before.items():Path(path).write_bytes(raw)
                self.boundary()
                def corrupt(seq,v):
                    if seq==1:v['request'][field]=value;v['requestSha256']=m.digest(v['request'])
                self.rewrite(corrupt)
                with self.assertRaisesRegex(ValueError,'request-binding'):self.status()

    def test_writer_exclusion_and_invalid_reply_durable_quarantine(self):
        def adapter(request):
            db=sqlite3.connect(self.c.path,timeout=0,isolation_level=None)
            try:
                with self.assertRaises(sqlite3.OperationalError):db.execute('BEGIN IMMEDIATE')
            finally:db.close()
            request['quantityAtomic']='1'
            return 'invalid'
        self.assertEqual(self.dispatch(adapter)['state'],'successor-signing-quarantined')

    def test_precommit_failure_rolls_back_and_postcommit_expiry_stays_unknown(self):
        original=m.append
        def fail(*args):original(*args);raise OSError('synthetic write failure')
        with patch.object(m,'append',side_effect=fail):
            with self.assertRaises(OSError):self.dispatch()
        self.assertEqual(files(self.c),self.before)
        original_load=m.load
        def expire(*args):
            r=original_load(*args)
            if r[-1] is not None:self.c.now+=10000
            return r
        calls=[]
        with patch.object(m,'load',side_effect=expire):
            with self.assertRaises(ValueError):self.dispatch(lambda request:calls.append(request))
        self.assertEqual(calls,[]);self.assertTrue(self.status()['boundaryRecorded'])
        self.assertEqual(self.dispatch()['signerAdapterCallsThisRun'],0)

    def test_recovery_without_boundary_and_verifier_outage_keep_evidence(self):
        with self.assertRaisesRegex(ValueError,'boundary-required'):self.recover('invalid')
        self.assertEqual(files(self.c),self.before)
        self.boundary();before=files(self.c)
        with patch.object(m.original,'signed_check',side_effect=ValueError('node-runtime-unavailable')):
            with self.assertRaisesRegex(ValueError,'node-runtime-unavailable'):self.recover('opaque')
        self.assertEqual(files(self.c),before);self.assertEqual(self.status()['state'],'successor-signing-unknown')

    def test_original_sender_stays_denied_and_snapshot_replays_new_head(self):
        self.boundary();before=files(self.c);rpc=FakeRpc(self.c)
        with self.assertRaisesRegex(ValueError,'retired-or-marker-invalid'):submit(self.c,rpc)
        self.assertEqual(rpc.requests,[])
        with m.read_only_journals():
            b=self.c.book()
            try:
                from admission_recovery import retirement_projection
                r=retirement_projection(b,self.c.home,self.c.wallet,self.c.pool,lambda:self.c.now)
            finally:b.close()
        self.assertEqual(r['successorSigningState'],'successor-signing-unknown')
        self.assertEqual(r['successorSigningHeadSha256'],self.status()['headSha256'])
        self.assertEqual(files(self.c),before)

    def test_rehashed_signed_wire_cannot_bypass_signature_verification(self):
        import base64,hashlib
        self.dispatch(self.c.sign_successor)
        def corrupt(seq,v):
            if seq==2:
                raw=bytearray(base64.b64decode(v['signedWireBase64']));raw[1]^=1
                v['signedWireBase64']=base64.b64encode(raw).decode();v['wireSha256']=hashlib.sha256(raw).hexdigest()
        self.rewrite(corrupt);before=files(self.c)
        with self.assertRaises(ValueError):self.status()
        with self.assertRaises(ValueError):self.dispatch()
        self.assertEqual(files(self.c),before)

    def test_stop_after_committed_boundary_and_backend_tampering_prevent_adapter(self):
        original_load=m.load;calls=[]
        def stop(*args):
            r=original_load(*args)
            if r[-1] is not None:(self.c.home/'STOP').touch(mode=0o600)
            return r
        with patch.object(m,'load',side_effect=stop):
            with self.assertRaisesRegex(ValueError,'stopped'):self.dispatch(lambda r:calls.append(r))
        self.assertEqual(calls,[]);self.assertTrue(self.status()['boundaryRecorded'])
        self.assertEqual(self.dispatch()['signerAdapterCallsThisRun'],0)
        (self.c.home/'STOP').unlink()
        for path,raw in self.before.items():Path(path).write_bytes(raw)
        (self.c.path.parent/m.successor.history.backend.ACK).write_text('{}')
        with self.assertRaises(ValueError):self.dispatch(lambda r:calls.append(r))
        self.assertEqual(calls,[])

    def test_orphan_and_oversized_and_clock_regressed_records_refuse(self):
        self.boundary();before=files(self.c)
        with patch.object(m,'MAX_ROW',1):
            with self.assertRaises(ValueError):self.status()
        self.c.now-=1
        with self.assertRaises(ValueError):self.status()
        self.c.now+=1
        db=sqlite3.connect(self.c.path)
        try:db.execute('DROP TABLE admission_exit_successor');db.commit()
        finally:db.close()
        r=m.successor.history.lifecycle.inspect(self.c.home,self.c.wallet,self.c.pool,clock=lambda:self.c.now)
        self.assertFalse(r['coherent'])


if __name__=='__main__':unittest.main()
