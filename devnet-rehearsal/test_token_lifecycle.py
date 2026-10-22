import base64
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from core import initialize,Session,signer as original_signer,raw58
from token_contract import message,bound,receipt,MAX_FEE,MAX_RENT,AMOUNT
from token_lifecycle import (execute,recover,status,TokenSession,TokenRecoveryRpc,signer,CHILD)
from submission import stop
from token_lifecycle_fixtures import FakeTokenRpc
from token_lifecycle_checks import run

ROOT=Path(__file__).resolve().parent


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name)/'wallet'
        self.wallet=initialize(self.home)['wallet']
    def tearDown(self):self.temp.cleanup()
    def execute(self,mode='ok'):
        self.fake=FakeTokenRpc(self.home,mode)
        return execute(self.home,self.wallet,opener=self.fake,sleeper=lambda _:None)
    def plan(self):return self.fake.plan()
    def test_offline_ten_cases(self):
        with patch('socket.socket',side_effect=AssertionError('no network')):
            self.assertEqual(run()['casesPassed'],10)
    def test_success_exact_contract_and_one_send(self):
        r=self.execute();self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['submissionAttempts'],1)
        self.assertEqual(r['sendRequestsThisRun'],1);self.assertLessEqual(r['networkRequests'],30)
        self.assertEqual(r['result']['feeLamports'],15000);self.assertTrue(r['result']['lifecycleCompleted'])
        self.assertFalse(r['result']['intermediateTokenBalancesObserved'])
        p=self.plan();v=bound(p,self.wallet,r['source'],r['destination']);self.assertEqual(v['requiredSignatures'],3)
        from core import decode_wire
        tx=decode_wire(p['signed_wire'])[4];ops=tx['transaction']['message']['instructions']
        self.assertEqual(len(ops),7);self.assertEqual(len(base64.b64decode(p['signed_wire'])),643)
        self.assertEqual(r['intent']['amountLamports'],1000)
        with sqlite3.connect(self.home/'rehearsal.sqlite') as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM plans').fetchone()[0],0)
        self.assertNotIn('signed_wire',json.dumps(r));self.assertNotIn('private-provider-error',json.dumps(r))
    def test_intent_committed_before_signer(self):
        real=signer;seen=[]
        def watch(home,action,**fields):
            if action=='sign':
                with sqlite3.connect(home/CHILD/'lifecycle.sqlite') as db:
                    row=db.execute('SELECT state,signed_wire,boundary FROM run').fetchone()
                self.assertEqual(row,('intent-recorded',None,0));seen.append(True)
            return real(home,action,**fields)
        with patch('token_lifecycle.signer',side_effect=watch):self.execute()
        self.assertEqual(seen,[True])
    def test_original_prepared_self_transfer_is_preserved(self):
        from core import prepare
        from rehearsal_fixtures import FakeRpc
        prior=prepare(self.home,opener=FakeRpc(home=self.home))
        self.assertEqual(prior['state'],'simulation-passed-not-submitted')
        with sqlite3.connect(self.home/'rehearsal.sqlite') as db:
            before=db.execute('SELECT * FROM plans ORDER BY id').fetchall()
        self.assertEqual(self.execute()['state'],'finalized-success')
        with sqlite3.connect(self.home/'rehearsal.sqlite') as db:
            self.assertEqual(db.execute('SELECT * FROM plans ORDER BY id').fetchall(),before)
    def test_existing_execution_and_terminal_recovery_zero_requests(self):
        first=self.execute();again=self.execute()
        r=recover(self.home,self.wallet,opener=FakeTokenRpc(self.home),sleeper=lambda _:None)
        self.assertEqual(again['networkRequests'],0);self.assertEqual(r['networkRequests'],0)
        self.assertEqual(first['result'],r['result'])
    def test_failed_transaction_fee_only(self):
        r=self.execute('failed');self.assertEqual(r['state'],'finalized-failure')
        self.assertFalse(r['result']['lifecycleCompleted']);self.assertEqual(r['result']['walletAfterLamports'],'9985000')
    def test_timeout_is_observed_not_resent(self):
        r=self.execute('timeout');self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['sendRequestsThisRun'],1)
    def test_unknown_and_expiry_never_enable_resend(self):
        r=self.execute('absent');self.assertEqual(r['state'],'submission-unknown')
        r=recover(self.home,self.wallet,opener=FakeTokenRpc(self.home,'expired'),sleeper=lambda _:None)
        self.assertEqual(r['state'],'expired-outcome-unknown');self.assertEqual(r['sendRequestsThisRun'],0)
        self.assertEqual(self.execute()['networkRequests'],0)
    def test_wrong_ack_is_sticky(self):
        r=self.execute('wrong-signature');self.assertEqual(r['state'],'quarantined')
        r=recover(self.home,self.wallet,opener=FakeTokenRpc(self.home),sleeper=lambda _:None)
        self.assertEqual(r['state'],'quarantined');self.assertEqual(r['networkRequests'],0)
    def test_bad_receipts_quarantined(self):
        for mode in ('bad-balance','temporary-balance','bad-fee','bad-wire','bad-slot','bad-token'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                home=Path(d)/'wallet';wallet=initialize(home)['wallet']
                r=execute(home,wallet,opener=FakeTokenRpc(home,mode),sleeper=lambda _:None)
                self.assertEqual(r['state'],'quarantined',r)
    def test_missing_receipt_and_balance_stay_unknown(self):
        for mode in ('missing-receipt','missing-balances'):
            with tempfile.TemporaryDirectory() as d:
                home=Path(d)/'wallet';wallet=initialize(home)['wallet']
                r=execute(home,wallet,opener=FakeTokenRpc(home,mode),sleeper=lambda _:None)
                self.assertEqual(r['state'],'submission-unknown')
    def test_preparation_failures_have_no_send(self):
        for mode in ('wrong-cluster','low-balance','existing-account','rent-cap','fee-cap',
                     'sim-failed','sim-balance','sim-missing','sim-account','near-expiry','already-seen'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                home=Path(d)/'wallet';wallet=initialize(home)['wallet'];fake=FakeTokenRpc(home,mode)
                r=execute(home,wallet,opener=fake,sleeper=lambda _:None)
                self.assertEqual(r['submissionAttempts'],0);self.assertEqual(r['sendRequestsThisRun'],0)
                self.assertNotIn(r['state'],('finalized-success','finalized-failure'))
    def test_stop_before_any_network(self):
        stop(self.home);r=self.execute();self.assertEqual(r['networkRequests'],0);self.assertEqual(r['reason'],'stop-requested')
    def test_stop_after_boundary_prevents_transport_but_preserves_uncertainty(self):
        original=TokenSession.boundary
        def after(s):original(s);stop(s.home)
        with patch.object(TokenSession,'boundary',after):r=self.execute()
        self.assertEqual(r['submissionAttempts'],1);self.assertEqual(r['sendRequestsThisRun'],0)
        self.assertEqual(r['state'],'submission-unknown');self.assertEqual(self.execute()['networkRequests'],0)
    def test_recovery_allowlist_cannot_send_sign_or_get_blockhash(self):
        rpc=TokenRecoveryRpc(FakeTokenRpc(self.home))
        for method in ('sendTransaction','simulateTransaction','getLatestBlockhash','getMultipleAccounts','requestAirdrop'):
            with self.assertRaises(ValueError):rpc.request(method,[])
        self.assertEqual(rpc.calls,[])
    def test_exclusive_parent_session_lock(self):
        with Session(self.home):
            with self.assertRaises(BlockingIOError):self.execute()
    def test_wrong_wallet_rejected_before_token_setup(self):
        with self.assertRaises(ValueError):execute(self.home,'11111111111111111111111111111111',opener=FakeTokenRpc(self.home))
        self.assertFalse((self.home/CHILD).exists())
    def test_partial_setup_is_not_overwritten(self):
        (self.home/CHILD).mkdir(mode=0o700)
        with self.assertRaises(FileNotFoundError):self.execute()
        self.assertEqual(list((self.home/CHILD).iterdir()),[])
    def test_existing_key_permissions_hardlinks_and_symlinks_refused(self):
        with TokenSession(self.home,self.wallet,create=True):pass
        key=self.home/CHILD/'source.pk8';key.chmod(0o644)
        with self.assertRaises(ValueError):status(self.home,self.wallet)
        key.chmod(0o600);other=self.home/CHILD/'copy.pk8';os.link(key,other)
        with self.assertRaises(ValueError):status(self.home,self.wallet)
        other.unlink();key.rename(other);key.symlink_to(other)
        with self.assertRaises(ValueError):status(self.home,self.wallet)
    def test_signer_refuses_policy_mutation_and_old_signer_stays_narrow(self):
        r=self.execute();i=r['intent'];msg=message(self.wallet,r['source'],r['destination'],i['blockhash'],i['rentPerAccountLamports'])
        fields={'rent':i['rentPerAccountLamports'],'blockhashBase64':base64.b64encode(raw58(i['blockhash'])).decode()}
        for index in (0,4,36,68,100,132,len(msg)-2):
            altered=bytearray(msg);altered[index]^=1
            with self.assertRaises(ValueError):signer(self.home,'sign',messageBase64=base64.b64encode(altered).decode(),**fields)
        with self.assertRaises(ValueError):original_signer(self.home,'sign',messageBase64=base64.b64encode(msg).decode())
        for rent in (0,MAX_RENT+1,True):
            with self.assertRaises(ValueError):signer(self.home,'sign',messageBase64=base64.b64encode(msg).decode(),**{**fields,'rent':rent})
    def test_local_intent_tamper_is_not_recovered(self):
        self.execute();p=self.plan();i=p['intent'];i['amountLamports']=1001
        with sqlite3.connect(self.home/CHILD/'lifecycle.sqlite') as db:db.execute('UPDATE run SET intent=?',(json.dumps(i),))
        fake=FakeTokenRpc(self.home)
        with self.assertRaises(ValueError):recover(self.home,self.wallet,opener=fake)
        self.assertEqual(fake.calls,[])
    def test_crash_after_intent_does_not_sign_or_reprepare(self):
        real=signer
        def crash(home,action,**fields):
            if action=='sign':raise SystemExit('synthetic')
            return real(home,action,**fields)
        with patch('token_lifecycle.signer',side_effect=crash),self.assertRaises(SystemExit):self.execute()
        r=self.execute();self.assertEqual(r['state'],'intent-recorded');self.assertEqual(r['networkRequests'],0)
        self.assertIsNone(self.plan()['signed_wire'])
    def test_abrupt_process_exit_after_durable_send_boundary(self):
        code='''import os,json
from pathlib import Path
from token_lifecycle import execute
from token_lifecycle_fixtures import FakeTokenRpc
class Crash(FakeTokenRpc):
 def open(self,request,timeout):
  if json.loads(request.data)['method']=='sendTransaction':
   assert self.plan()['boundary']==1
   os._exit(79)
  return super().open(request,timeout)
home=Path(os.environ['TEST_WALLET_HOME'])
execute(home,os.environ['TEST_WALLET_PUBLIC'],opener=Crash(home),sleeper=lambda _:None)
'''
        env={**os.environ,'TEST_WALLET_HOME':str(self.home),'TEST_WALLET_PUBLIC':self.wallet}
        p=subprocess.run([sys.executable,'-E','-s','-c',code],cwd=ROOT,env=env,capture_output=True)
        self.assertEqual(p.returncode,79,p.stderr)
        r=recover(self.home,self.wallet,opener=FakeTokenRpc(self.home,sent=True),sleeper=lambda _:None)
        self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['sendRequestsThisRun'],0)
        self.assertEqual(r['submissionAttempts'],1)
    def test_cli_requires_explicit_submit_and_private_new_output(self):
        out=Path(self.temp.name)/'report.json.gz'
        base=[sys.executable,str(ROOT/'token_lifecycle_cli.py'),'--directory',str(self.home),'--wallet',self.wallet,'--output',str(out)]
        p=subprocess.run(base+['--action','execute'],capture_output=True)
        self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())
        with TokenSession(self.home,self.wallet,create=True):pass
        p=subprocess.run(base+['--action','status'],capture_output=True);self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(out.stat().st_mode&0o777,0o600)
        before=out.read_bytes();p=subprocess.run(base+['--action','status'],capture_output=True)
        self.assertNotEqual(p.returncode,0);self.assertEqual(out.read_bytes(),before)
    def test_missing_transient_rows_are_not_synthesized_as_observed(self):
        r=self.execute();p=self.plan();st={'slot':110,'err':None}
        fake=FakeTokenRpc(self.home,sent=True)
        # Reuse the bounded reader to obtain the synthetic receipt.
        rpc=TokenRecoveryRpc(fake);tx=rpc.request('getTransaction',[p['simulation']['signature'],{'encoding':'base64'}])['result']
        for field in ('preTokenBalances','fee','preBalances'):
            changed=copy.deepcopy(tx);del changed['meta'][field]
            with self.assertRaises(ValueError):receipt(changed,st,p)
        self.assertFalse(r['result']['intermediateTokenBalancesObserved'])
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'wallet';wallet=initialize(home)['wallet']
            r=execute(home,wallet,opener=FakeTokenRpc(home,'sim-zero-accounts'),sleeper=lambda _:None)
            self.assertEqual(r['state'],'finalized-success')
            self.assertEqual(r['simulation']['temporaryAccountSnapshots'],['zero-empty-system-account']*2)


if __name__=='__main__':unittest.main()
