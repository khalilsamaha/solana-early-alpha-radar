"""Explicit command permissions, safe reports, real journal status and routing."""
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

import controlled_acceptance as m
import controlled_acceptance_cli as cli
from controlled_acceptance_checks import boundaries
from fresh_entry_checks import case
import test_fresh_entry as full


class BoundaryTests(unittest.TestCase):
    def test_portable_boundaries(self): self.assertEqual(len(boundaries()), 8)

    def test_unknown_failed_or_late_actions_have_nonzero_exit_without_retry(self):
        for action in m.ACTIONS:
            for state in ('submission-unknown','exit-submission-unknown','quarantined','future-state','inspection-required'):
                self.assertEqual(cli.exit_code(action,dict(state=state,dispatchCompleted=True,result={})),2)
        for action in m.SIGNING:
            r=dict(state='rpc-acknowledged',dispatchCompleted=True,result={'completedWithinOriginalDeadline':True})
            self.assertEqual(cli.exit_code(action,r),0)
            r['result']['completedWithinOriginalDeadline']=False
            self.assertEqual(cli.exit_code(action,r),2)

    def test_accounting_projection_preserves_null_and_zero_without_raw_fields(self):
        r=m.projection(dict(scopedAccounting={'feeHeldLamports':'0','feePaidLamports':None,
            'sourceProceedsReleasedAtomic':'123','private':'PRIVATE'},
            recordIdentity={'closureSha256':'a'*64,'entryAccountingSha256':None,'wire':'PRIVATE'}))
        self.assertEqual(r['scopedAccounting'],dict(feeHeldLamports='0',feePaidLamports=None,sourceProceedsReleasedAtomic='123'))
        self.assertEqual(r['recordIdentity'],dict(closureSha256='a'*64,entryAccountingSha256=None))
        self.assertNotIn('PRIVATE',json.dumps(r))

    def test_invalid_flags_refused_before_any_source_or_action(self):
        with patch.object(m,'directory',side_effect=AssertionError('source')):
            for action in m.SIGNING|m.RECONCILING:
                with self.assertRaises(ValueError): m.dispatch(action,'/missing','wallet','pool')

    def test_action_routing_and_exact_caps(self):
        with tempfile.TemporaryDirectory() as d:
            caps=dict(maximum_exit_attempts=2,maximum_exit_fee_lamports='10000',maximum_total_fee_lamports='30000')
            for action in m.ACTIONS-{'status'}:
                with self.subTest(action=action):
                    target=Mock(return_value={'state':'test-observed','networkRequests':0,'signedWireBase64':'PRIVATE'})
                    flags=dict(allow_private_key_signing=True,allow_devnet_submit=True) if action in m.SIGNING else dict(allow_reconcile=True)
                    with patch.dict(m.OPERATIONS,{action:target}):
                        r=m.dispatch(action,d,'wallet','pool',**flags,**(caps if action=='entry' else {}))
                    target.assert_called_once()
                    expected=dict(allow_private_key_signing=True,allow_devnet_submit=True) if action in m.SIGNING else {}
                    if action=='entry': expected.update(caps)
                    self.assertEqual(target.call_args.kwargs,expected)
                    self.assertEqual(r['result'],{'state':'test-observed','networkRequests':0})
                    self.assertFalse(r['automaticNextAction']);self.assertFalse(r['executionApproved'])

    def test_reconciliation_targets_cannot_prepare_or_send(self):
        self.assertEqual(m.OPERATIONS['settle-entry'].keywords,{'prepare_exit':False})
        self.assertEqual(m.OPERATIONS['settle-exit'].keywords,{'close_exit':False})
        self.assertEqual(m.OPERATIONS['close-exit'].keywords,{'close_exit':True})
        self.assertIs(m.OPERATIONS['recover-entry-signature'],m.fresh_entry.signing.recover)
        self.assertIs(m.OPERATIONS['recover-exit-signature'],m.fresh_exit.backend.recover)

    def test_exception_does_not_claim_no_effects_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as d:
            target=Mock(side_effect=OSError('PRIVATE response lost after commit'))
            with patch.dict(m.OPERATIONS,{'close-exit':target}):
                r=m.dispatch('close-exit',d,'wallet','pool',allow_reconcile=True)
            self.assertEqual(target.call_count,1);self.assertIsNone(r['result'])
            self.assertFalse(r['dispatchCompleted']);self.assertNotIn('transactionsSent',r)
            self.assertNotIn('PRIVATE',json.dumps(r))

    def test_output_inside_source_or_handoff_is_refused_before_action(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'source';home.mkdir(mode=0o700)
            for directory in (home,Path(str(home)+'-entry-handoff-v1'),Path(str(home)+'-unsigned-admission-rehearsal-v1')):
                directory.mkdir(mode=0o700,exist_ok=True)
                for output in (directory/'bad.gz',):
                    args=['cli','--action','status','--directory',str(home),'--wallet','wallet','--pool','pool','--output',str(output)]
                    with patch.object(sys,'argv',args),patch.object(m,'dispatch',side_effect=AssertionError('action')):
                        with self.assertRaises(ValueError): cli.main()
                    self.assertFalse(output.exists())
            link=Path(d)/'alias';link.symlink_to(home,target_is_directory=True)
            args[-1]=str(link/'bad.gz')
            with patch.object(sys,'argv',args),patch.object(m,'dispatch',side_effect=AssertionError('action')):
                with self.assertRaises(ValueError):cli.main()

    def test_check_refuses_scope_optins_endpoint_and_report_import(self):
        with tempfile.TemporaryDirectory() as d:
            base=[sys.executable,'-E','-s',str(Path(cli.__file__)),'--output',str(Path(d)/'no.gz')]
            for option in (['--directory',d],['--wallet','wallet'],['--allow-devnet-submit'],
                           ['--allow-private-key-signing'],['--allow-reconcile'],['--endpoint','https://example.test'],
                           ['--input','report.gz'],['--action','retry']):
                self.assertNotEqual(subprocess.run(base+option,capture_output=True).returncode,0)
                self.assertFalse(Path(d,'no.gz').exists())

    def test_existing_report_prevents_action_and_partial_report_exits_two(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz'; home=Path(d)/'source'; home.mkdir(mode=0o700)
            args=['cli','--action','status','--directory',str(home),'--wallet','wallet','--pool','pool','--output',str(out)]
            report=dict(state='inspection-required',dispatchCompleted=False,result=None)
            with patch.object(sys,'argv',args),patch.object(m,'dispatch',return_value=report) as action:
                self.assertEqual(cli.main(),2);action.assert_called_once()
                saved=out.read_bytes();self.assertEqual(out.stat().st_mode&0o777,0o600)
                self.assertEqual(json.loads(gzip.decompress(saved))['state'],'inspection-required')
                with self.assertRaises(ValueError):cli.main()
                self.assertEqual(action.call_count,1);self.assertEqual(out.read_bytes(),saved)

    def test_report_publish_failure_does_not_retry_committed_action(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'source';home.mkdir(mode=0o700)
            args=['cli','--action','close-exit','--allow-reconcile','--directory',str(home),'--wallet','wallet','--pool','pool','--output',str(Path(d)/'report.gz')]
            with patch.object(sys,'argv',args),patch.object(m,'dispatch',return_value={'state':'closed'}) as action, \
                 patch.object(cli,'publish',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):cli.main()
                action.assert_called_once()

    def test_full_offline_cli_routes_connected_lifecycle_and_cleans_private_fixtures(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'check.gz'
            cmd=[sys.executable,'-E','-s',str(Path(cli.__file__)),'--output',str(out)]
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            raw=out.read_bytes();r=json.loads(gzip.decompress(raw))
            self.assertEqual(r['state'],'offline-acceptance-passed')
            self.assertEqual(r['boundaryChecksPassed'],8);self.assertEqual(r['connectedChecksPassed'],9)
            self.assertTrue(r['lifecycle']['temporaryLedgersRemoved'])
            self.assertTrue(r['lifecycle']['originalSourceUnchanged'])
            self.assertEqual([x['action'] for x in r['routedActions']],['entry','settle-entry','exit','close-exit','close-exit'])
            self.assertEqual(r['transactionsSent'],r['realNetworkRequests']);self.assertEqual(r['realNetworkRequests'],0)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),raw)
            for field in ('signedWireBase64','signedTransactionBase64','rpcEvidence','wallet','pool'):
                self.assertNotIn('"'+field+'"',gzip.decompress(raw).decode())

    def test_actual_entry_routing_holds_unknown_and_repeat_is_not_a_send(self):
        with case() as c:
            def run(*args,**kwargs):return c.run(rpc=c.opener(lost=True))
            caps=dict(maximum_exit_attempts=2,maximum_exit_fee_lamports='10000',maximum_total_fee_lamports='30000')
            with patch.dict(m.OPERATIONS,{'entry':run}):
                a=m.dispatch('entry',c.home,c.wallet,c.pool,allow_private_key_signing=True,allow_devnet_submit=True,**caps)
                b=m.dispatch('entry',c.home,c.wallet,c.pool,allow_private_key_signing=True,allow_devnet_submit=True,**caps)
            self.assertEqual(a['state'],'submission-unknown');self.assertEqual(a['result']['sendRequestsThisRun'],1)
            self.assertEqual(b['result']['sendRequestsThisRun'],0);self.assertEqual(b['result']['networkRequests'],0)


class RealSourceStatusTests(unittest.TestCase):
    setUpClass=full.FullSourceEntryTests.__dict__['setUpClass']
    tearDownClass=full.FullSourceEntryTests.__dict__['tearDownClass']
    setUp=full.FullSourceEntryTests.setUp
    tearDown=full.FullSourceEntryTests.tearDown
    files=full.FullSourceEntryTests.files
    pipeline=full.FullSourceEntryTests.pipeline
    integrate=full.FullSourceEntryTests.integrate

    def test_vacant_stopped_source_is_read_only_and_not_spending_approval(self):
        (self.home/'STOP').touch(mode=0o600);before=self.files()
        with patch('socket.socket',side_effect=AssertionError('network')),patch.object(m.fresh_entry.signing.backend,'_invoke',side_effect=AssertionError('key')):
            r=m.dispatch('status',self.home,self.wallet,self.pool)
        self.assertEqual(r['state'],'local-scope-consistent',r)
        self.assertFalse(r['result']['slotOccupied']);self.assertTrue(r['result']['stopRequested'])
        self.assertFalse(r['result']['newEntryAuthorized']);self.assertEqual(self.files(),before)

    def test_occupied_status_has_no_nested_lock_and_preserves_journals(self):
        self.integrate(lost=True);(self.home/'signer.pk8').unlink()
        sibling=self.home.parent/(self.home.name+'-entry-handoff-v1')
        before=self.files();data={str(p):p.read_bytes() for p in sibling.rglob('*') if p.is_file()}
        with patch('socket.socket',side_effect=AssertionError('network')):
            r=m.dispatch('status',self.home,self.wallet,self.pool)
        self.assertEqual(r['state'],'lifecycle-consistent',r);self.assertTrue(r['result']['slotOccupied'])
        self.assertEqual(self.files(),before)
        self.assertEqual(data,{str(p):p.read_bytes() for p in sibling.rglob('*') if p.is_file()})

    def test_partial_sibling_is_not_repaired_or_treated_as_vacant(self):
        sibling=self.home.parent/(self.home.name+'-entry-handoff-v1');sibling.mkdir(mode=0o700)
        before=self.files();r=m.dispatch('status',self.home,self.wallet,self.pool)
        self.assertEqual(r['state'],'lifecycle-unavailable');self.assertTrue(r['result']['slotOccupied'])
        self.assertEqual(list(sibling.iterdir()),[]);self.assertEqual(before,self.files())

    def test_wrong_wallet_pool_or_symlink_cannot_claim_consistent_scope(self):
        for wallet,pool in (('wrong',self.pool),(self.wallet,'wrong')):
            r=m.dispatch('status',self.home,wallet,pool)
            self.assertEqual(r['state'],'inspection-required')
        alias=self.home.parent/'alias';alias.symlink_to(self.home,target_is_directory=True)
        try:
            with self.assertRaises(ValueError):m.dispatch('status',alias,self.wallet,self.pool)
        finally:alias.unlink()


if __name__=='__main__':unittest.main()
