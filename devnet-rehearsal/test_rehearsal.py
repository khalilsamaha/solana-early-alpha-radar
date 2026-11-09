from contextlib import closing
import base64
import gzip
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import core
from rehearsal_fixtures import FakeRpc

HERE=Path(__file__).resolve().parent

class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)/'wallet'; self.initial=core.initialize(self.home)
    def test_initialization_permissions_and_no_overwrite(self):
        self.assertEqual(self.home.stat().st_mode&0o777,0o700)
        for p in self.home.iterdir(): self.assertEqual(p.stat().st_mode&0o777,0o600)
        self.assertEqual(self.initial['networkRequests'],0)
        self.assertFalse(self.initial['privateKeyExported'])
        with self.assertRaises(FileExistsError): core.initialize(self.home)
    def test_fixed_message_signature_verified_independently(self):
        m=core.message(self.initial['wallet'],core.SYSTEM)
        s=core.signer(self.home,'sign',messageBase64=base64.b64encode(m).decode())
        wire=base64.b64encode(b'\x01'+base64.b64decode(s['signatureBase64'])+m).decode()
        self.assertTrue(core.verify_wire(wire)['signatureVerified'])
        decoded=core.decode_wire(wire)
        self.assertEqual(len(decoded[1]),118)
        self.assertEqual(decoded[4]['version'],'legacy')
        self.assertEqual(decoded[4]['transaction']['message']['instructions'][0]['accounts'],[0,0])
    def test_signer_rejects_other_message_shapes(self):
        m=core.message(self.initial['wallet'],core.SYSTEM)
        for offset in (0,2,4,36,101,103,104,106,110):
            changed=bytearray(m); changed[offset]^=1
            with self.subTest(offset=offset),self.assertRaises(ValueError):
                core.signer(self.home,'sign',messageBase64=base64.b64encode(changed).decode())
        with self.assertRaises(ValueError): core.signer(self.home,'sign',messageBase64=base64.b64encode(m+b'\0').decode())
        with self.assertRaises(ValueError): core.signer(self.home,'public',network='mainnet-beta')
    def test_prior_commit_six_requests_and_public_projection(self):
        rpc=FakeRpc(home=self.home); result=core.prepare(self.home,rpc)
        self.assertEqual(result['state'],'simulation-passed-not-submitted')
        self.assertEqual(result['networkRequests'],6)
        self.assertEqual(result['transactionsSent'],0)
        options=rpc.calls[4]['params'][1]
        self.assertTrue(options['sigVerify']); self.assertFalse(options['replaceRecentBlockhash'])
        self.assertEqual(options['accounts']['addresses'],[self.initial['wallet']])
        self.assertEqual(options['minContextSlot'],100)
        with core.Session(self.home) as session: public=session.status()
        self.assertNotIn('private-error-marker',json.dumps(public))
        self.assertNotIn(rpc.calls[4]['params'][0],json.dumps(public))
        self.assertEqual(public['plans'][0]['state'],result['state'])
    def test_incomplete_simulations_never_pass(self):
        for i,mode in enumerate(('sim-error','timeout','missing-balances','replacement','fee-mismatch',
            'bad-post','bad-system','missing-account','account-mismatch','boolean-balance','last-cluster')):
            home=Path(self.tmp.name)/str(i); core.initialize(home); rpc=FakeRpc(mode,home)
            with self.subTest(mode=mode):
                result=core.prepare(home,rpc)
                self.assertEqual(result['state'],'preparation-incomplete')
                self.assertFalse(result['simulationPassed']); self.assertTrue(result['signed'])
                self.assertNotIn('private-error-marker',json.dumps(result))
                self.assertNotIn('sendTransaction',[p['method'] for p in rpc.calls])
    def test_unfunded_stops_before_signing(self):
        for mode in ('unfunded','poor'):
            result=core.prepare(self.home,FakeRpc(mode))
            self.assertEqual(result['networkRequests'],2); self.assertFalse(result['signed'])
            self.assertEqual(result['state'],'needs-devnet-funding')
        with core.Session(self.home) as session: self.assertEqual(session.status()['plans'],[])
    def test_preflight_failures_leave_no_plan(self):
        for mode in ('wrong-cluster','wrong-owner','null-fee','high-fee','regressed-context'):
            with self.subTest(mode=mode):
                r=core.prepare(self.home,FakeRpc(mode)); self.assertEqual(r['state'],'blocked')
                self.assertFalse(r['signed'])
        with core.Session(self.home) as session: self.assertEqual(session.status()['plans'],[])
    def test_simulation_uses_its_own_prebalance(self):
        r=core.prepare(self.home,FakeRpc('changed-between-reads'))
        self.assertTrue(r['simulationPassed']); self.assertEqual(r['simulationWalletBeforeLamports'],'2000000')
        self.assertEqual(r['walletLamports'],'1000000')
    def test_repeat_refused_before_requests(self):
        core.prepare(self.home,FakeRpc()); rpc=FakeRpc()
        with self.assertRaisesRegex(ValueError,'plan-already'): core.prepare(self.home,rpc)
        self.assertEqual(rpc.calls,[])
    def test_recorded_intent_preserved_after_reopen(self):
        with core.Session(self.home) as session: session.record({'blockhash':core.SYSTEM},100)
        with core.Session(self.home) as session: self.assertEqual(session.status()['plans'][0]['state'],'intent-recorded')
        rpc=FakeRpc()
        with self.assertRaisesRegex(ValueError,'plan-already'): core.prepare(self.home,rpc)
        self.assertEqual(rpc.calls,[])
    def test_signer_failure_preserves_committed_intent(self):
        original=core.signer
        def fail(home,action,**kw):
            if action=='sign': raise ValueError('local-signer-refused')
            return original(home,action,**kw)
        with patch.object(core,'signer',side_effect=fail): r=core.prepare(self.home,FakeRpc())
        self.assertEqual(r['state'],'preparation-incomplete'); self.assertFalse(r['signed'])
        with core.Session(self.home) as session: self.assertEqual(session.status()['plans'][0]['state'],'preparation-incomplete')
    def test_concurrent_session_rejected(self):
        with core.Session(self.home):
            with self.assertRaises(BlockingIOError): core.Session(self.home)
    def test_unsafe_key_permissions_links_rejected(self):
        key=self.home/'signer.pk8'; key.chmod(0o644)
        with self.assertRaises(ValueError): core.signer(self.home,'public')
        key.chmod(0o600); alias=self.home/'alias'; os.link(key,alias)
        with self.assertRaises(ValueError): core.signer(self.home,'public')
        alias.unlink(); key.rename(alias); key.symlink_to(alias)
        with self.assertRaises(ValueError): core.signer(self.home,'public')
    def test_wrong_metadata_and_database_identity_rejected(self):
        path=self.home/'wallet.json'; data=json.loads(path.read_text()); data['network']='mainnet-beta'; path.write_text(json.dumps(data))
        with self.assertRaises(ValueError): core.Session(self.home)
        data['network']='devnet'; path.write_text(json.dumps(data))
        with closing(sqlite3.connect(self.home/'rehearsal.sqlite')) as db, db: db.execute('PRAGMA application_id=1')
        with self.assertRaises(ValueError): core.Session(self.home)
    def test_rpc_allowlist_and_fixed_network(self):
        rpc=core.Rpc(FakeRpc()); self.assertEqual(rpc.network,'devnet')
        for method in ('sendTransaction','requestAirdrop','getProgramAccounts'):
            with self.assertRaises(ValueError): rpc.request(method,[])
        self.assertEqual(rpc.calls,[])
    def test_timeout_retains_public_state_without_raw_errors(self):
        r=core.prepare(self.home,FakeRpc('timeout')); self.assertEqual(r['networkRequests'],5)
        with core.Session(self.home) as session: public=session.status()
        self.assertNotIn('signed_wire',json.dumps(public)); self.assertNotIn('private-error-marker',json.dumps(public))
    def test_public_signer_output_only_public_key(self):
        r=core.signer(self.home,'public'); self.assertEqual(set(r),{'publicKeyBase64'})
        self.assertEqual(len(base64.b64decode(r['publicKeyBase64'])),32)

class CliRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
    def cli(self,*args):
        return subprocess.run([sys.executable,'-E','-s',str(HERE/'rehearsal_cli.py'),*map(str,args)],capture_output=True,text=True)
    def test_offline_self_check(self):
        output=self.root/'report.json.gz'; p=self.cli('--output',output)
        self.assertEqual(p.returncode,0,p.stderr)
        with gzip.open(output,'rt') as f: r=json.load(f)
        self.assertEqual(r['casesPassed'],9); self.assertEqual(r['networkRequests'],0)
        self.assertTrue(r['temporaryKeysAndJournalsRemoved']); self.assertEqual(output.stat().st_mode&0o777,0o600)
    def test_prepare_requires_explicit_flag_and_send_unavailable(self):
        for action in ('prepare','send'):
            p=self.cli('--action',action,'--directory',self.root/'wallet','--output',self.root/'r.gz')
            self.assertNotEqual(p.returncode,0); self.assertFalse((self.root/'wallet').exists())
    def child(self,home,body):
        script='import os,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom core import Session,SYSTEM\nhome=Path(sys.argv[2])\n'+body
        p=subprocess.run([sys.executable,'-c',script,str(HERE),str(home)],capture_output=True,text=True)
        self.assertEqual(p.returncode,77,p.stderr)
    def test_abrupt_exit_after_commit_recovers_without_retry(self):
        home=self.root/'wallet'; core.initialize(home)
        self.child(home,"s=Session(home)\ns.record({'blockhash':SYSTEM},100)\nos._exit(77)\n")
        with core.Session(home) as s: self.assertEqual(s.status()['plans'][0]['state'],'intent-recorded')
        rpc=FakeRpc()
        with self.assertRaises(ValueError): core.prepare(home,rpc)
        self.assertEqual(rpc.calls,[])
    def test_abrupt_exit_before_commit_rolls_back(self):
        home=self.root/'wallet'; core.initialize(home)
        self.child(home,"s=Session(home)\ns.db.execute('BEGIN IMMEDIATE')\ns.db.execute(\"INSERT INTO plans(at_ms,intent,state) VALUES (100,'{}','intent-recorded')\")\nos._exit(77)\n")
        with core.Session(home) as s: self.assertEqual(s.status()['plans'],[])
    def test_existing_output_prevents_key_creation(self):
        output=self.root/'r.gz'; output.write_text('preserve')
        p=self.cli('--action','initialize','--directory',self.root/'wallet','--output',output)
        self.assertNotEqual(p.returncode,0); self.assertFalse((self.root/'wallet').exists())
        self.assertEqual(output.read_text(),'preserve')
    def test_failed_plan_repeat_preserves_database_bytes(self):
        home=self.root/'wallet'; core.initialize(home); core.prepare(home,FakeRpc('timeout'))
        db=home/'rehearsal.sqlite'; before=db.read_bytes(); rpc=FakeRpc()
        with self.assertRaises(ValueError): core.prepare(home,rpc)
        self.assertEqual(db.read_bytes(),before); self.assertEqual(rpc.calls,[])

if __name__=='__main__': unittest.main()
