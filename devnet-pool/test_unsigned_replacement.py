"""Synthetic refused-entry recovery preserves history and never replaces signed attempts."""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import unsigned_replacement as u
import test_cycle_execution as original
from test_cycle_execution import c,s,binding,Transport,BASE


class UnsignedReplacementCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original.CycleExecutionCase.setUpClass.__func__(cls)
        baseline=dict(copy.deepcopy(BASE),network='devnet',kind='observed-devnet-deployment',observedAtMs=0)
        with patch('preflight.BASELINE',baseline),patch('preflight_capture.BASELINE',baseline),patch.object(s.swap,'invoke_signer',side_effect=ValueError('refused')):
            r=s.execute(cls.template,cls.wallet,cls.pool,cycle=True,opener=Transport(cls.template,cls.wallet),sleeper=lambda _:None)
            assert r['failure']['phase']=='signing',r
        policy=json.loads((cls.template/binding.CYCLE/s.CHILD/'plan.json').read_text())['packet']['policy']
        time.sleep(max(0,(policy['expiresAtMs']+30)/1000-time.time()))
    tearDownClass=classmethod(original.CycleExecutionCase.tearDownClass.__func__)
    setUp=original.CycleExecutionCase.setUp
    tearDown=original.CycleExecutionCase.tearDown

    def fingerprints(self):
        r=u.audit.inspect(self.home,self.wallet,self.pool)
        return r['preparationSha256'],r['evidenceSha256']
    def prepare(self,expected=None):return u.prepare(self.home,self.wallet,self.pool,*(expected or self.fingerprints()))
    def entry(self,t=None):
        t=t or Transport(self.home,self.wallet);change=t.change
        def fresh(q,v):
            if q['method']=='getLatestBlockhash':v['value']['blockhash']=original.fake_key('replacement-fresh-entry')
            return change(q,v) if change else v
        t.change=fresh
        return s.execute(self.home,self.wallet,self.pool,cycle=True,replace_unsigned=True,opener=t,sleeper=lambda _:None)
    def all_files(self):return {str(p.relative_to(self.home)):p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
    def guard(self):
        with s.spend_guard.Guard(self.home/binding.CYCLE) as g:return g.summary()

    def test_prepare_without_key_preserves_archive_and_allocation_and_repeats(self):
        expected=self.fingerprints();cycle=self.home/binding.CYCLE
        before={p.name:p.read_bytes() for p in (cycle/s.CHILD).iterdir()}
        (self.home/'signer.pk8').unlink();r=self.prepare(expected)
        self.assertEqual(r['state'],'unsigned-replacement-prepared');self.assertFalse(r['privateKeyAccessed'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in (cycle/u.ARCHIVE).iterdir()})
        self.assertFalse((cycle/s.CHILD).exists());self.assertEqual(self.guard()['reservedFeeLamports'],'20000')
        self.assertEqual(self.guard()['eventCount'],2);all_before=self.all_files()
        self.assertFalse(self.prepare(expected)['preparationChanged']);self.assertEqual(all_before,self.all_files())

    def test_complete_entry_reverse_and_recovery_preserve_original_contract(self):
        self.prepare();cycle=self.home/binding.CYCLE;before={p.name:p.read_bytes() for p in (cycle/u.ARCHIVE).iterdir()}
        r=self.entry();self.assertEqual(r['state'],'finalized-success',r)
        self.assertEqual(r['sendRequestsThisRun'],1);self.assertEqual(self.guard()['cumulativeConfirmedFeeLamports'],'15000')
        self.assertNotEqual(self.guard()['unsignedReplacement']['originalPlanSha256'],self.guard()['unsignedReplacement']['newPlanSha256'])
        t=Transport(self.home,self.wallet);again=s.recover(self.home,self.wallet,cycle=True,opener=t)
        self.assertEqual(again['signature'],r['signature']);self.assertEqual(t.calls,[])
        x=s.execute_reverse(self.home,self.wallet,self.pool,cycle=True,opener=Transport(self.home,self.wallet,reverse=True),sleeper=lambda _:None)
        self.assertEqual(x['state'],'finalized-success',x);self.assertEqual(self.guard()['state'],'closed')
        self.assertEqual(self.guard()['cumulativeConfirmedFeeLamports'],'20000')
        self.assertEqual(before,{p.name:p.read_bytes() for p in (cycle/u.ARCHIVE).iterdir()})

    def test_ordinary_entry_cannot_consume_replacement(self):
        self.prepare();t=Transport(self.home,self.wallet)
        with self.assertRaisesRegex(ValueError,'explicit-unsigned-replacement-required'):s.execute(self.home,self.wallet,self.pool,cycle=True,opener=t)
        self.assertEqual(t.calls,[]);self.assertFalse((self.home/binding.CYCLE/s.CHILD).exists())

    def test_reusing_archived_blockhash_refuses_before_signing(self):
        self.prepare();t=Transport(self.home,self.wallet)
        with patch.object(s.swap,'invoke_signer',side_effect=AssertionError('must not sign')):
            r=s.execute(self.home,self.wallet,self.pool,cycle=True,replace_unsigned=True,opener=t,sleeper=lambda _:None)
        self.assertEqual(r['state'],'preparation-incomplete');self.assertEqual(r['sendRequestsThisRun'],0)
        self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000')
        self.assertFalse(r['spendingGuard']['replacementReservationTransferred'])

    def test_packet_build_failure_keeps_reservation_visible(self):
        self.prepare()
        with patch.object(s,'build',side_effect=ValueError('synthetic transport refusal')):r=self.entry()
        self.assertEqual(r['spendingGuard']['heldEntryPrincipalAtomic'],'1000')
        self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000')
        self.assertEqual(r['spendingGuard']['cumulativeConfirmedFeeLamports'],'10000')
        self.assertEqual(r['sendRequestsThisRun'],0)

    def test_repeated_entry_and_prepare_never_create_second_attempt(self):
        expected=self.fingerprints();self.prepare(expected);first=self.entry();before=self.all_files()
        t=Transport(self.home,self.wallet);again=self.entry(t)
        self.assertEqual(again['signature'],first['signature']);self.assertEqual(t.calls,[])
        self.prepare(expected);self.assertEqual(before,self.all_files())

    def test_any_signing_or_submission_marker_rejects_before_intent(self):
        expected=self.fingerprints();cycle=self.home/binding.CYCLE
        for name in ('signing-attempt.json','signed.json','submission-boundary.json'):
            path=cycle/s.CHILD/name;path.symlink_to('nonexistent')
            try:
                with self.assertRaises(ValueError):self.prepare(expected)
                self.assertFalse((cycle/u.INTENT).exists())
            finally:path.unlink()

    def test_unexpired_unsigned_plan_cannot_be_replaced(self):
        expected=self.fingerprints();plan=json.loads((self.home/binding.CYCLE/s.CHILD/'plan.json').read_text())
        with patch.object(u.time,'time_ns',return_value=(plan['packet']['policy']['issuedAtMs']+1)*1000000):
            with self.assertRaisesRegex(ValueError,'replacement-old-plan-not-expired'):self.prepare(expected)
        self.assertFalse((self.home/binding.CYCLE/u.INTENT).exists())

    def test_expected_hashes_must_match_reviewed_evidence(self):
        prep,evidence=self.fingerprints()
        for pair in ((prep,'0'*64),('0'*64,evidence)):
            with self.assertRaises(ValueError):self.prepare(pair)
        self.assertFalse((self.home/binding.CYCLE/u.INTENT).exists())

    def test_crash_after_intent_resumes_without_dropping_reservation(self):
        expected=self.fingerprints();write=u.write_new
        def crash(path,value):
            write(path,value)
            if path.name==u.INTENT:raise KeyboardInterrupt()
        with patch.object(u,'write_new',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):self.prepare(expected)
        self.assertEqual(self.guard()['reservedFeeLamports'],'20000')
        self.prepare(expected);self.assertEqual(self.guard()['eventCount'],2)

    def test_crash_after_rename_resumes_from_preserved_archive(self):
        expected=self.fingerprints();rename=u.os.rename
        def crash(*a):rename(*a);raise KeyboardInterrupt()
        with patch.object(u.os,'rename',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):self.prepare(expected)
        self.assertFalse((self.home/binding.CYCLE/s.CHILD).exists());self.assertEqual(self.guard()['reservedFeeLamports'],'20000')
        self.prepare(expected);self.assertEqual(self.guard()['eventCount'],2)

    def test_crash_after_authorization_resumes_without_duplicate_event(self):
        expected=self.fingerprints();authorize=s.spend_guard.Guard.authorize_unsigned_replacement
        def crash(g,m):authorize(g,m);raise KeyboardInterrupt()
        with patch.object(s.spend_guard.Guard,'authorize_unsigned_replacement',crash):
            with self.assertRaises(KeyboardInterrupt):self.prepare(expected)
        self.assertEqual(self.guard()['eventCount'],2);self.prepare(expected);self.assertEqual(self.guard()['eventCount'],2)

    def test_actual_process_death_after_ready_seal_keeps_prepared_state(self):
        expected=self.fingerprints()
        code='''
import sys,os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
import unsigned_replacement as u
write=u.write_new
def crash(p,v):
 write(p,v)
 if p.name==u.SEAL:os._exit(73)
with patch.object(u,'write_new',side_effect=crash):u.prepare(Path(sys.argv[2]),*sys.argv[3:])
'''
        r=subprocess.run([sys.executable,'-c',code,str(Path(__file__).parent),str(self.home),self.wallet,self.pool,*expected],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,73,r.stderr)
        self.assertFalse(self.prepare(expected)['preparationChanged']);self.assertEqual(self.guard()['reservedFeeLamports'],'20000')

    def test_unknown_replacement_keeps_budget_and_recovery_never_resends(self):
        self.prepare();t=Transport(self.home,self.wallet,pending=True);r=self.entry(t)
        self.assertEqual(r['sendRequestsThisRun'],1);self.assertEqual(self.guard()['reservedFeeLamports'],'20000')
        t.pending=False;t.calls.clear();r=s.recover(self.home,self.wallet,cycle=True,opener=t,sleeper=lambda _:None)
        self.assertEqual(r['state'],'finalized-success');self.assertFalse(any(q['method']=='sendTransaction' for q in t.calls))

    def test_changed_current_balance_refuses_before_new_signing(self):
        self.prepare();t=Transport(self.home,self.wallet);t.rows[self.wallet]['lamports']+=1
        with patch.object(s.swap,'invoke_signer',side_effect=AssertionError('must not sign')):r=self.entry(t)
        self.assertEqual(r['sendRequestsThisRun'],0);self.assertEqual(self.guard()['reservedFeeLamports'],'20000')
        self.assertIsNone(self.guard()['unsignedReplacement']['newPlanSha256'])

    def test_signer_independently_refuses_changed_archive(self):
        self.prepare();signer=s.swap.invoke_signer
        def sign(*a,**kw):
            path=self.home/binding.CYCLE/u.ARCHIVE/'failure.json';before=path.read_bytes();path.write_bytes(before+b' ')
            try:
                with self.assertRaisesRegex(ValueError,'restricted-signer-refused'):signer(*a,**kw)
            finally:path.write_bytes(before)
            raise ValueError('test-refusal')
        with patch.object(s.swap,'invoke_signer',side_effect=sign):r=self.entry()
        self.assertEqual(r['sendRequestsThisRun'],0);self.assertFalse((self.home/binding.CYCLE/s.CHILD/'signing-attempt.json').exists())

    def test_signer_independently_refuses_changed_ready_seal(self):
        self.prepare();signer=s.swap.invoke_signer
        def sign(*a,**kw):
            path=self.home/binding.CYCLE/u.SEAL;before=path.read_bytes();path.write_text('{}')
            try:
                with self.assertRaisesRegex(ValueError,'restricted-signer-refused'):signer(*a,**kw)
            finally:path.write_bytes(before)
            raise ValueError('test-refusal')
        with patch.object(s.swap,'invoke_signer',side_effect=sign):r=self.entry()
        self.assertEqual(r['sendRequestsThisRun'],0)

    def test_stop_blocks_preparation_and_fresh_entry(self):
        expected=self.fingerprints();stop=self.home/'STOP';stop.touch(mode=0o600)
        with self.assertRaisesRegex(ValueError,'stop-requested'):self.prepare(expected)
        stop.unlink();self.prepare(expected);stop.touch(mode=0o600)
        with self.assertRaisesRegex(ValueError,'stop-requested'):self.entry()
        self.assertEqual(self.guard()['reservedFeeLamports'],'20000')

    def test_second_refusal_cannot_get_another_replacement(self):
        expected=self.fingerprints();self.prepare(expected)
        with patch.object(s.swap,'invoke_signer',side_effect=ValueError('refused')):r=self.entry()
        self.assertEqual(r['state'],'preparation-incomplete');before=self.all_files()
        self.prepare(expected);t=Transport(self.home,self.wallet);self.entry(t)
        self.assertEqual(t.calls,[]);self.assertEqual(before,self.all_files());self.assertEqual(self.guard()['reservedFeeLamports'],'20000')

    def test_standalone_cli_status_and_explicit_action_flags(self):
        expected=self.fingerprints();out=Path(self.tmp.name)/'replacement.json.gz';cli=Path(__file__).with_name('cycle_replacement_cli.py')
        args=[sys.executable,'-E','-s',str(cli),'--directory',str(self.home),'--wallet',self.wallet,'--pool',self.pool,'--output',str(out)]
        r=subprocess.run(args+['--action','prepare','--expected-preparation',expected[0],'--expected-evidence',expected[1]],capture_output=True,text=True,timeout=20)
        self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())
        r=subprocess.run(args+['--action','prepare','--allow-unsigned-plan-replacement','--expected-preparation',expected[0],'--expected-evidence',expected[1]],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        out.unlink();(self.home/'signer.pk8').unlink();before=self.all_files()
        r=subprocess.run(args+['--action','status'],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(before,self.all_files())
        with gzip.open(out,'rt') as f:self.assertEqual(json.load(f)['entry']['state'],'not-started')
