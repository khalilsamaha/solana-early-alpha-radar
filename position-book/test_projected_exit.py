import base64
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import projected_exit as m
from projected_exit_checks import fixture,wire_edit,run,NOW
from fresh_packet import message
import test_fresh_quote as f
from test_post_entry_live import PoolOpener


class ProjectedExitTests(unittest.TestCase):
    def rejected(self,a,p,d):
        r=m.assess(a,p,d)
        self.assertEqual(r['state'],'unavailable',r);self.assertIsNone(r['binding'])
        self.assertFalse(r['executionApproved'])

    def observe(self,**kwargs):
        def observer(*args,**kw):return f.m.observe(*args,**kw,post_entry_projection=True,projected_exit_message=True)
        return f.FreshQuoteTests().run_observe(simulate=True,assess_costs=True,
            opener_factory=PoolOpener,observer=observer,**kwargs)

    def test_exact_reverse_roles_acquired_quantity_minimum_and_no_fee_invention(self):
        for reverse in (False,True):
            a,p=fixture(reverse);before=deepcopy((a,p));d=m.build(a,p);r=m.assess(a,p,d)
            self.assertEqual(r['state'],'projected-reverse-message-consistent',r)
            b=r['binding'];old=a['packet']['policy']['accounts']
            for x,y in (('source','destination'),('inputMint','outputMint'),('inputVault','outputVault')):
                self.assertEqual(b['accounts'][x],old[y]);self.assertEqual(b['accounts'][y],old[x])
            for k in ('wallet','authority','config','pool','observation'):self.assertEqual(b['accounts'][k],old[k])
            self.assertEqual((b['inputAtomic'],b['projectedOutputAtomic'],b['minimumOutputAtomic']),
                             ('77','61','61') if reverse else ('79','63','63'))
            self.assertEqual(b['instructionCount'],3);self.assertEqual(b['priorityPriceMicroLamports'],'0')
            self.assertIsNone(r['exitFeeLamports']);self.assertNotIn('feeAssertion',d)
            for k in ('validForSubmission','signingApproved','executionApproved','exitSimulationVerified',
                      'exitFeeVerified','blockhashValidityVerified','actualEntryExecuted','roundTripFundingEstablished'):
                self.assertFalse(r[k],k)
            self.assertEqual((a,p),before)
            self.assertNotIn(d['unsignedTransactionBase64'],json.dumps(r))
            self.assertNotEqual(b['messageSha256'],b['parentMessageSha256'])

    def test_semantic_wire_validation_rejects_changed_minimum_amount_privileges_and_signature(self):
        for kind in ('minimum','amount','header','signature','discriminator','blockhash','extra'):
            a,p=fixture();d=m.build(a,p);n=len(base64.b64decode(d['unsignedTransactionBase64']))
            if kind=='minimum':wire_edit(d,n-8,(1).to_bytes(8,'little'))
            if kind=='amount':wire_edit(d,n-16,(78).to_bytes(8,'little'))
            if kind=='header':wire_edit(d,67,b'\x06')
            if kind=='signature':wire_edit(d,1,b'\x01')
            if kind=='discriminator':wire_edit(d,n-24,b'\x00')
            if kind=='blockhash':wire_edit(d,65+4+14*32,bytes(32))
            if kind=='extra':d['unsignedTransactionBase64']=base64.b64encode(base64.b64decode(d['unsignedTransactionBase64'])+b'\0').decode()
            self.rejected(a,p,d)

    def test_changed_role_even_with_valid_rebuilt_wire_is_not_the_expected_reverse(self):
        for x,y in (('source','destination'),('inputMint','outputMint'),('inputVault','outputVault'),('config','observation')):
            a,p=fixture();d=m.build(a,p);s=d['scope'];s['accounts'][x],s['accounts'][y]=s['accounts'][y],s['accounts'][x]
            d['unsignedTransactionBase64']=base64.b64encode(b'\x01'+bytes(64)+message(s,d['referenceBlockhash'])).decode()
            self.rejected(a,p,d)

    def test_parent_expiry_tampering_summary_and_fee_assertion_block(self):
        self.assertEqual(run()['casesPassed'],10)
        a,p=fixture();d=m.build(a,p)
        from contract import validate
        self.assertEqual(validate(d,now_ms=NOW)['state'],'rejected')
        d['parentProjectionSha256']='0'*64;self.rejected(a,p,d)

    def test_entry_and_reverse_wire_hashes_bound_to_same_raw_projection(self):
        a,p=fixture();d=m.build(a,p);r=m.assess(a,p,d);post=m.post_entry.assess(a,p)
        self.assertEqual(r['binding']['parentSimulationSha256'],post['evidence']['fullSimulationSha256'])
        self.assertEqual(r['binding']['parentProjectionSha256'],post['evidence']['projectionSha256'])
        self.assertEqual(r['binding']['draftSha256'],m.digest(d))

    def test_end_to_end_no_extra_requests_no_wire_export(self):
        r,o=self.observe()
        self.assertEqual(r['state'],'controlled-projected-exit-observation-consistent',r)
        self.assertEqual(len(o.calls),20);self.assertEqual(r['requestMethods'].count('simulateTransaction'),1)
        b=r['projectedExitMessage']['binding'];p=r['postEntryProjection']['projection']
        self.assertEqual((b['inputAtomic'],b['projectedOutputAtomic'],b['minimumOutputAtomic']),
                         (p['acquiredInputAtomic'],p['projectedOutputAtomic'],p['projectedMinimumOutputAtomic']))
        self.assertTrue(r['postEntryObservedInSimulation']);self.assertFalse(r['exitSimulationVerified'])
        self.assertNotIn('unsignedTransactionBase64',json.dumps(r))
        self.assertEqual(r['transactionsSent'],0);self.assertFalse(r['sourceStateChanged'])

    def test_late_draft_rejection_and_stop_publish_no_exit_binding(self):
        for kind in ('late','rejected','stop'):
            clock=f.Clock();original=m.assess;stop=[False]
            def review(*args):
                r=original(*args)
                if kind=='late':clock.at+=10001
                if kind=='rejected':r['state']='unavailable'
                if kind=='stop':stop[0]=True
                return r
            with patch('projected_exit.assess',review):r,_=self.observe(clock=clock,stop=lambda _:stop[0])
            self.assertEqual(r['state'],'unavailable',r);self.assertIsNone(r['projectedExitMessage'])
            self.assertFalse(r['simulationVerified']);self.assertFalse(r['liveCollectorVerified'])

    def test_offline_cli_has_no_execution_flag_and_protects_output(self):
        cli=Path(__file__).with_name('projected_exit_cli.py')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'report.gz';cmd=[sys.executable,str(cli),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            data=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(data))['casesPassed'],10)
            self.assertEqual(out.stat().st_mode & 0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),data)
            for flag in ('--allow-devnet-submit','--input','--wallet','--simulate-devnet'):
                absent=[sys.executable,str(cli),'--output',str(Path(tmp)/'absent.gz'),flag]
                self.assertNotEqual(subprocess.run(absent,capture_output=True).returncode,0)
            self.assertFalse((Path(tmp)/'absent.gz').exists())

    def test_no_network_in_pure_self_checks_and_explicit_mode_required(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):self.assertEqual(run()['casesPassed'],10)
        with self.assertRaises(ValueError):f.m.observe(Path('/unused'),'w','p',projected_exit_message=True)


if __name__=='__main__':unittest.main()
