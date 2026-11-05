"""Command routing, durable one-attempt behavior and public output handling."""
import gzip,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import controlled_continuation as m
import controlled_continuation_cli as cli
from controlled_continuation_checks import run

FLAGS=dict(expected_original_sha256='a'*64,expected_current_sha256='b'*64,allow_unsigned_continuation=True,
    allow_private_key_signing=True,allow_devnet_submit=True)

class CommandTests(unittest.TestCase):
    def args(self,home,out):
        return ['cli','--action','execute','--directory',str(home),'--wallet','wallet','--pool','pool',
            '--expected-original-sha256','a'*64,'--expected-current-sha256','b'*64,'--allow-unsigned-continuation',
            '--allow-private-key-signing','--allow-devnet-submit','--output',str(out)]

    def test_portable_boundaries(self):
        r=run();self.assertEqual(r['casesPassed'],8);self.assertEqual(set(r['cases'].values()),{'passed'})

    def test_fixed_backend_and_no_injection_or_caps(self):
        self.assertIs(m.EXECUTE,m.fresh_exit.continue_sign_submit)
        with patch.object(m,'directory',side_effect=AssertionError('source')):
            for key in ('opener','clock','signer_adapter','collection_opener','maximum_total_fee_lamports'):
                with self.assertRaises(TypeError):m.execute('/missing','w','p',**FLAGS,**{key:'bad'})

    def test_check_cli_exclusive_private_output_and_scope_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out.gz';base=[sys.executable,'-E','-s',cli.__file__,'--output',str(out)]
            for flags in (['--directory',d],['--expected-original-sha256','a'*64,'--expected-current-sha256','b'*64],
                ['--allow-unsigned-continuation'],['--allow-private-key-signing'],['--allow-devnet-submit'],
                ['--endpoint','https://example.test'],['--input','report.gz'],['--action','retry']):
                self.assertNotEqual(subprocess.run(base+flags,capture_output=True).returncode,0)
                self.assertFalse(out.exists())
            p=subprocess.run(base,capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
            raw=out.read_bytes();r=json.loads(gzip.decompress(raw));self.assertEqual(r['casesPassed'],8)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(base,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),raw)

    def test_output_collision_and_private_path_refuse_before_action(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'source';home.mkdir(mode=0o700)
            for private in (home,Path(str(home)+'-entry-handoff-v1'),Path(str(home)+'-unsigned-admission-rehearsal-v1')):
                private.mkdir(mode=0o700,exist_ok=True)
                with patch.object(sys,'argv',self.args(home,private/'out.gz')),patch.object(m,'execute',side_effect=AssertionError('action')):
                    with self.assertRaises(ValueError):cli.main()
            alias=Path(d)/'alias';alias.symlink_to(home,target_is_directory=True)
            with patch.object(sys,'argv',self.args(home,alias/'out.gz')),patch.object(m,'execute',side_effect=AssertionError('action')):
                with self.assertRaises(ValueError):cli.main()
            out=Path(d)/'out.gz';out.write_bytes(b'preserve')
            with patch.object(sys,'argv',self.args(home,out)),patch.object(m,'execute',side_effect=AssertionError('action')):
                with self.assertRaises(ValueError):cli.main()
            self.assertEqual(out.read_bytes(),b'preserve')

    def test_publish_failure_never_retries_or_claims_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'source';home.mkdir(mode=0o700)
            target=Mock(return_value=dict(state='exit-submission-unknown',dispatchCompleted=True,result={}))
            with patch.object(sys,'argv',self.args(home,Path(d)/'out.gz')),patch.object(m,'execute',target),patch.object(cli,'publish',side_effect=OSError('disk')):
                with self.assertRaises(OSError):cli.main()
            target.assert_called_once()

    def test_public_execution_report_exits_unknown_without_another_action(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'source';home.mkdir(mode=0o700);out=Path(d)/'out.gz'
            target=Mock(return_value=dict(state='exit-submission-unknown',sendRequestsThisRun=1,privateKeyAccessed=None,signaturesCreated=None))
            with patch.object(sys,'argv',self.args(home,out)),patch.object(m,'EXECUTE',target):
                self.assertEqual(cli.main(),2)
            r=json.loads(gzip.decompress(out.read_bytes()));target.assert_called_once()
            self.assertIsNone(r['result']['privateKeyAccessed']);self.assertEqual(r['result']['sendRequestsThisRun'],1)
            self.assertFalse(r['automaticNextAction'])

    def test_connected_dispatch_actual_signer_unknown_send_and_repeat_refusal(self):
        import continuation_exit_checks as connected
        original=m.EXECUTE;routed=[]
        def bridge(home,wallet,pool,**kwargs):
            opts={k:kwargs.pop(k) for k in tuple(kwargs) if k in ('collection_opener','submission_opener','clock')}
            def operation(*args,**flags):return original(*args,**flags,**opts)
            with patch.object(m,'EXECUTE',operation):r=m.execute(home,wallet,pool,**kwargs)
            routed.append(r)
            self.assertTrue(r['dispatchCompleted'],r)
            return dict(r['result'],preparation=r['preparation'],canonicalDigestReplay=r.get('canonicalDigestReplay'))
        # Only trusted synthetic transports in this test. The production wrapper
        # has no corresponding injection parameters or CLI flags.
        faults=connected.fault_checks()
        with patch.object(connected,'fault_checks',return_value=faults),patch.object(connected.m,'continue_sign_submit',bridge):
            r=connected.run()
        self.assertEqual(r['state'],'offline-integration-passed',r)
        self.assertEqual(r['casesPassed'],16)
        self.assertEqual(len(routed),2)
        self.assertEqual(routed[0]['result']['sendRequestsThisRun'],1)
        self.assertEqual(routed[1]['result']['networkRequests'],0)
        self.assertEqual(routed[1]['result']['signerInvocationAttempts'],0)
        self.assertEqual(r['recovery']['sendRequests'],0)
        self.assertFalse(r['recovery']['reservationReleased'])
        self.assertTrue(r['temporaryLedgersRemoved'])


    def test_read_only_inspect_preserves_real_fixture_and_no_key_or_network(self):
        from preserved_exit_checks import case
        with case() as c:
            before=c.path.read_bytes();source={p.name:p.read_bytes() for p in c.home.iterdir()}
            with patch.object(m.fresh_exit.view,'now',c.clock),patch.object(m,'EXECUTE',side_effect=AssertionError('execute')),patch('socket.socket',side_effect=AssertionError('network')):
                r=m.inspect(c.home,c.wallet,c.pool,expected_original_sha256=c.expected,expected_current_sha256=c.current)
                self.assertTrue(r['eligibleNow'],r)
                self.assertEqual(r['heldConstraints']['quantityAtomic'],'98')
                self.assertEqual(r['heldConstraints']['protectedInventoryAtomic'],'902')
                self.assertEqual(r['heldConstraints']['feeCommitmentRemainingLamports'],'20999')
                self.assertFalse(r['executionApproved'])
                for original,current in ((c.expected,'b'*64),('a'*64,c.current)):
                    denied=m.inspect(c.home,c.wallet,c.pool,expected_original_sha256=original,expected_current_sha256=current)
                    self.assertFalse(denied['eligibleNow'])
                    self.assertNotIn('heldConstraints',denied)
                (c.path.parent/m.fresh_exit.backend.ATTEMPT).symlink_to('missing')
                denied=m.inspect(c.home,c.wallet,c.pool,expected_original_sha256=c.expected,expected_current_sha256=c.current)
                self.assertFalse(denied['eligibleNow'])
                self.assertEqual(denied['diagnosticCode'],'preserved-exit-backend-marker')
            self.assertEqual(c.path.read_bytes(),before)
            self.assertEqual({p.name:p.read_bytes() for p in c.home.iterdir()},source)

    def test_inspection_cleanup_failure_cannot_remain_eligible(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        @contextmanager
        def locked(*args):yield Path('/disposable')
        record={'binding':dict(quantityAtomic='1',protectedInventoryAtomic='2',feeCommitmentRemainingLamports='3',feeCapLamports='1')}
        book=SimpleNamespace(close=Mock(side_effect=OSError('private path')))
        with patch.object(m.fresh_exit.view.cycles.c,'source_lock',locked), \
             patch.object(m.fresh_exit.submission.transport,'_open',return_value=book), \
             patch.object(m.fresh_exit.continuation,'eligible',return_value=record):
            r=m.inspect('/disposable','w','p',expected_original_sha256='a'*64,expected_current_sha256='b'*64)
        self.assertFalse(r['eligibleNow']);self.assertNotIn('heldConstraints',r)
        self.assertEqual(r['diagnosticCode'],'continuation-inspection-unavailable')
        self.assertNotIn('private path',json.dumps(r))

    def test_inspect_cli_rejects_execution_flags_and_private_output(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'source';home.mkdir(mode=0o700)
            args=self.args(home,Path(d)/'out.gz');args[2]='inspect'
            with patch.object(sys,'argv',args),patch.object(m,'inspect',side_effect=AssertionError('inspection')):
                with self.assertRaises(ValueError):cli.main()
            args=[v for v in args if not v.startswith('--allow-')]
            target=Mock(return_value=dict(state='continuation-eligible-research-only',eligibleNow=True,diagnosticCode=None))
            with patch.object(sys,'argv',args),patch.object(m,'inspect',target),patch.object(m,'execute',side_effect=AssertionError('execute')):
                self.assertEqual(cli.main(),0)
            target.assert_called_once()
            args[-1]=str(home/'private.gz')
            with patch.object(sys,'argv',args),patch.object(m,'inspect',side_effect=AssertionError('inspection')):
                with self.assertRaises(ValueError):cli.main()

if __name__=='__main__':unittest.main()
