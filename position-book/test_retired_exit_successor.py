"""Unsigned successor storage against real semantic replay and synthetic RPC."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import retired_exit_successor as m
import admission_exit_capture_checks as capture_fixture
from exit_submission_checks import signed_case,submit,FakeRpc
from test_expired_exit_evidence import fixture,Replies,evidence as expiry_evidence
from test_signed_exit_timing import files
from paired_checks import shift,NOW
from preflight_checks import fake_key


def new_envelope(c,ctx):
    """Temporarily prepare an independent first-exit collector in disposable data.

    All retired source bytes are restored before the successor API is exercised.
    No production source or reusable wallet is involved.
    """
    saved=files(c);stamp=c.now
    try:
        db=sqlite3.connect(c.path)
        try:
            for name in m.history.lifecycle.EXIT_TABLES:
                db.execute('DROP TABLE IF EXISTS '+name)
            db.commit()
        finally:db.close()
        for name in (m.history.backend.ATTEMPT,m.history.backend.ACK):(c.path.parent/name).unlink(missing_ok=True)
        first,e,b=capture_fixture.setup(c)
        delta=stamp+1000-(NOW+30200)
        for v in (first,e):shift(v,delta,100)
        first['evidence']['blockTime']['result']=(stamp+1000)//1000
        e['capture']['evidence']['blockTime']['result']=(stamp+1000)//1000
        clock=capture_fixture.Clock();clock.at=stamp+1000
        rpc=capture_fixture.Opener(first,e)
        rpc.rows[7]['value']['blockhash']=fake_key('distinct-retired-successor')
        items=[]
        with patch.object(m.preparation,'BASELINE',b):
            result=capture_fixture.m.collect(c.home,c.wallet,c.pool,opener=rpc,clock=clock,
                monotonic=lambda:0,_evidence_sink=items.append)
        if result['state']!='exit-evidence-collected-research-only':raise AssertionError(result)
        item=items[0];ev=item.pop('evidence')
        proof=dict(contextSha256=m.digest(ctx),startedAtMs=stamp,observedAtMs=stamp,
                   rpcEvidence=expiry_evidence(c,ctx))
        c.now=clock()+1
        return dict(expiryProof=proof,evidence=ev,collection=item)
    finally:
        for name,data in saved.items():Path(name).write_bytes(data);Path(name).chmod(0o600)


class SuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager=signed_case();cls.c=cls.manager.__enter__();cls.c.now+=30000
        cls.ctx=fixture(cls.c)
        for key in ('signatureVerification','timingOptimization'):cls.ctx.pop(key,None)
        cls.expected=cls.c.exit_state['request']['preparationSha256']
        r=m.retirement.retire(cls.c.home,cls.c.wallet,cls.c.pool,cls.expected,
            allow_retire=True,opener=Replies(cls.c,cls.ctx),clock=lambda:cls.c.now,monotonic=lambda:0)
        if r['state']!='exit-retired-held':raise AssertionError(r)
        cls.retired=r['retirementSha256'];cls.envelope=new_envelope(cls.c,cls.ctx)
        cls.saved=files(cls.c);cls.stamp=cls.c.now
    @classmethod
    def tearDownClass(cls):cls.manager.__exit__(None,None,None)
    def setUp(self):
        self.c.now=self.stamp
        for name,data in self.saved.items():Path(name).write_bytes(data);Path(name).chmod(0o600)
    def tearDown(self):
        (self.c.home/'STOP').unlink(missing_ok=True)
        for name,data in self.saved.items():Path(name).write_bytes(data);Path(name).chmod(0o600)
    def prepare(self,item=None,producer=None,expected=None):
        return m._prepare_from_producer(self.c.home,self.c.wallet,self.c.pool,self.expected,
            expected or self.retired,producer or (lambda ctx:deepcopy(item or self.envelope)),
            allow_unsigned_successor=True,clock=lambda:self.c.now,monotonic=lambda:0)
    def rows(self):
        db=sqlite3.connect(self.c.path)
        try:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            return {t:db.execute('SELECT * FROM '+t).fetchall() for t in tables}
        finally:db.close()

    def test_separate_unsigned_record_preserves_history_and_charges_retired_slot(self):
        before=self.rows();r=self.prepare()
        self.assertTrue(r['createdThisRun']);self.assertEqual(r['state'],'unsigned-successor-prepared-held')
        self.assertEqual(r['binding']['attemptNumber'],2);self.assertEqual(r['binding']['attemptsConsumed'],1)
        self.assertEqual(r['binding']['retiredFeeExposureHeldLamports'],'10000')
        self.assertGreaterEqual(int(r['binding']['otherHeldFeeLamports']),10000)
        after=self.rows();self.assertEqual(set(after)-set(before),{m.TABLE})
        self.assertEqual(before,{k:after[k] for k in before})
        for name,data in self.saved.items():
            if Path(name)!=self.c.path:self.assertEqual(Path(name).read_bytes(),data)
        book=self.c.book()
        try:self.assertEqual(m.digest(m.preparation.saved(book,self.c.now)),self.expected)
        finally:book.close()
        for k in ('replacementAuthorized','signingApproved','executionApproved','reservationsReleasedThisRun',
                  'privateKeyAccessed','signaturesCreated','transactionsSent','liveCollectorConnected'):
            self.assertFalse(r[k])
        self.assertNotIn('unsignedTransactionBase64',json.dumps(r))

    def test_duplicate_and_expired_replay_never_call_producer_or_refresh(self):
        first=self.prepare();before=files(self.c);self.c.now+=30000
        def forbidden(ctx):raise AssertionError('second producer')
        r=self.prepare(producer=forbidden)
        self.assertEqual(r['recordSha256'],first['recordSha256']);self.assertFalse(r['createdThisRun'])
        self.assertEqual(r['state'],'unsigned-successor-expired-held');self.assertEqual(files(self.c),before)

    def test_lifecycle_snapshot_and_sender_preserve_retired_denial(self):
        r=self.prepare();before=files(self.c)
        status=m.history.lifecycle.inspect(self.c.home,self.c.wallet,self.c.pool,clock=lambda:self.c.now)
        self.assertTrue(status['coherent'],status);self.assertEqual(status['phase'],'exit-retired-held')
        self.assertEqual(status['recordIdentity']['exitSuccessorSha256'],r['recordSha256'])
        self.assertEqual(status['scopedAccounting'],self.ctx['identity']['scopedAccounting'])
        import admission_recovery
        with m.read_only_journals():
            b=self.c.book()
            try:projection=admission_recovery.retirement_projection(b,self.c.home,self.c.wallet,self.c.pool,lambda:self.c.now)
            finally:b.close()
        self.assertEqual(projection['unsignedSuccessorSha256'],r['recordSha256'])
        rpc=FakeRpc(self.c)
        with self.assertRaisesRegex(ValueError,'retired-or-marker-invalid'):submit(self.c,rpc)
        self.assertEqual(rpc.requests,[]);self.assertEqual(files(self.c),before)

    def test_wrong_retirement_stop_and_external_backend_changes_refuse(self):
        with self.assertRaises(ValueError):self.prepare(expected='0'*64)
        (self.c.home/'STOP').touch(mode=0o600)
        with self.assertRaisesRegex(ValueError,'stopped'):self.prepare()
        (self.c.home/'STOP').unlink()
        before=self.c.path.read_bytes()
        def corrupt(ctx):
            (self.c.path.parent/m.history.backend.ACK).write_text('{}')
            return deepcopy(self.envelope)
        with self.assertRaises(ValueError):self.prepare(producer=corrupt)
        self.assertEqual(self.c.path.read_bytes(),before)

    def test_returned_transaction_changed_accounts_and_stale_proof_refuse(self):
        mutations=[lambda v:v['expiryProof']['rpcEvidence']['transaction'].update(result=dict(
            slot=self.ctx['identity']['minimumContextSlot']+11,transaction=[self.ctx['signedWire'],'base64'])),
            lambda v:v['expiryProof']['rpcEvidence']['accounts']['result']['value'][0].update(lamports=1),
            lambda v:v['expiryProof'].update(contextSha256='0'*64),
            lambda v:v['expiryProof']['rpcEvidence']['blockTime'].update(result=self.c.now//1000-31)]
        for mutate in mutations:
            v=deepcopy(self.envelope);mutate(v)
            with self.assertRaises(ValueError):self.prepare(item=v)
            self.assertEqual(files(self.c),self.saved)

    def test_rehashed_provenance_and_changed_fee_quantity_or_message_refuse(self):
        import admission_exit_collection_checks as checks
        for mode in ('trace','quantity','fee','wire'):
            with self.subTest(mode=mode):
                v=deepcopy(self.envelope)
                if mode=='trace':v['collection']['requestTrace'][18]['parametersSha256']='0'*64
                if mode=='quantity':v['evidence']['packet']['policy']['amountIn']='99'
                if mode=='fee':v['evidence']['packet']['policy']['maxTotalFeeLamports']='10001'
                if mode=='wire':v['evidence']['packet']['unsignedTransactionBase64']='invalid'
                checks.rehash(v['collection'],v['evidence'])
                with self.assertRaises(ValueError):self.prepare(item=v)
                self.assertEqual(files(self.c),self.saved)

    def test_failed_write_stop_and_deadline_roll_back_whole_record(self):
        original=m.write_record
        for mode in ('write','stop','deadline','cap'):
            with self.subTest(mode=mode):
                def fault(book,record):
                    original(book,record)
                    if mode=='write':raise OSError('synthetic write failure')
                    if mode=='stop':(self.c.home/'STOP').touch(mode=0o600)
                    if mode=='deadline':self.c.now+=10000
                with patch.object(m,'write_record',side_effect=fault),patch.object(m,'MAX_RECORD',1 if mode=='cap' else m.MAX_RECORD):
                    with self.assertRaises((ValueError,OSError)):self.prepare()
                self.assertEqual(self.c.path.read_bytes(),self.saved[str(self.c.path)])
                (self.c.home/'STOP').unlink(missing_ok=True);self.c.now=self.stamp

    def test_lost_completion_is_recovered_by_existing_record_without_repeating(self):
        original=m.public
        def lost(record,now,created=False):
            if created:raise OSError('synthetic output failure after commit')
            return original(record,now,created)
        with patch.object(m,'public',side_effect=lost):
            with self.assertRaises(OSError):self.prepare()
        r=self.prepare(producer=lambda ctx:(_ for _ in ()).throw(AssertionError('repeat')))
        self.assertFalse(r['createdThisRun']);self.assertEqual(r['state'],'unsigned-successor-prepared-held')

    def test_rehashed_candidate_cannot_bypass_semantic_replay(self):
        self.prepare();db=sqlite3.connect(self.c.path)
        try:
            value=json.loads(db.execute('SELECT value FROM admission_exit_successor').fetchone()[0])
            value['candidate']['binding']['attemptsConsumed']=0
            db.execute('UPDATE admission_exit_successor SET value=?,hash=?',(m.preparation.encoded(value),m.digest(value)));db.commit()
        finally:db.close()
        before=files(self.c)
        r=m.history.lifecycle.inspect(self.c.home,self.c.wallet,self.c.pool,clock=lambda:self.c.now)
        self.assertFalse(r['coherent']);self.assertEqual(files(self.c),before)
        with self.assertRaises(ValueError):self.prepare()

    def test_producer_runs_under_writer_reservation_after_source_replay(self):
        called=[]
        def producer(ctx):
            self.assertEqual(ctx,self.ctx)
            db=sqlite3.connect(self.c.path,timeout=0,isolation_level=None)
            try:
                with self.assertRaises(sqlite3.OperationalError):db.execute('BEGIN IMMEDIATE')
            finally:db.close()
            called.append(True);return deepcopy(self.envelope)
        self.prepare(producer=producer);self.assertEqual(called,[True])


    def test_orphan_record_and_oversized_record_fail_closed(self):
        self.prepare();db=sqlite3.connect(self.c.path)
        try:db.execute('DROP TABLE admission_exit_retirement');db.commit()
        finally:db.close()
        before=files(self.c)
        result=m.history.lifecycle.inspect(self.c.home,self.c.wallet,self.c.pool,clock=lambda:self.c.now)
        self.assertFalse(result['coherent']);self.assertEqual(files(self.c),before)
        for name,data in self.saved.items():Path(name).write_bytes(data);Path(name).chmod(0o600)
        self.prepare();book=self.c.book()
        try:
            with patch.object(m,'MAX_RECORD',1):
                with self.assertRaisesRegex(ValueError,'successor-row'):m.row(book)
        finally:book.close()

    def test_reused_blockhash_and_changed_parent_fee_binding_refuse(self):
        # Keep full collection validation; simulate a historically used candidate
        # blockhash and a changed parent fee binding.
        candidate_hash=self.envelope['evidence']['packet']['policy']['blockhash']
        with patch.object(m,'previous_blockhashes',return_value={candidate_hash}):
            with self.assertRaisesRegex(ValueError,'successor-reused-blockhash'):self.prepare()
        original=m.preparation.saved
        def higher_old_exposure(*a,**kw):
            value=deepcopy(original(*a,**kw));value['binding']['feeCapLamports']='20000';return value
        # A changed old record must already fail its exact source binding.
        with patch.object(m.preparation,'saved',side_effect=higher_old_exposure):
            with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(files(self.c),self.saved)


if __name__=='__main__':unittest.main()
