"""Bounded diagnostics, transaction semantics and read-only historical evidence."""
from contextlib import contextmanager
from copy import deepcopy
import gzip,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import exit_profile as m
import exit_profile_rehearsal as rehearsal
import exit_history_timing as history
import exit_profile_cli as cli
from unsigned_exit_replacement_checks import case

class ProfileTests(unittest.TestCase):
    def test_nested_spans_exclusive_time_and_noop(self):
        with patch.object(m.time,'time_ns',side_effect=AssertionError('clock')):
            with m.measure('collection'):pass
        wall=iter([1000,1010,1020,1030]);tick=iter([1,1.01,1.02,1.03])
        p=m.Profile(clock=lambda:next(wall),monotonic=lambda:next(tick))
        with m.capture(p),m.measure('collection'):
            with m.measure('source-replay'):pass
        p.pin(1100);r=p.report();self.assertTrue(r['valid'])
        self.assertEqual([x['elapsedMs'] for x in r['spans']],[30,10])
        self.assertEqual([x['exclusiveMs'] for x in r['spans']],[20,10])
        self.assertEqual(r['spans'][0]['remainingAtEndMs'],70)
        r['spans'].clear();self.assertEqual(len(p.report()['spans']),2)

    def test_diagnostic_failure_caps_and_scope_do_not_change_result(self):
        p=m.Profile(clock=lambda:(_ for _ in ()).throw(OSError('PRIVATE')))
        with m.capture(p):
            with m.measure('replacement-write'):value='durable'
            with self.assertRaises(ValueError),m.capture(m.Profile()):pass
            with self.assertRaisesRegex(OSError,'PRIVATE'),m.measure('collection'):raise OSError('PRIVATE')
            with m.measure({'PRIVATE':1}):pass
            for _ in range(m.MAX_SPANS+1):
                with m.measure('source-replay'):pass
        self.assertEqual(value,'durable');self.assertFalse(p.report()['valid'])
        self.assertEqual(len(p.report()['spans']),m.MAX_SPANS);self.assertNotIn('PRIVATE',json.dumps(p.report()))
        with self.assertRaises(ValueError),m.capture(p):pass
        self.assertIsNone(m._current.get())
        q=m.Profile(monotonic=lambda:float('nan'))
        with m.capture(q),m.measure('collection'):pass
        q.pin(100);q.pin(200);self.assertFalse(q.report()['valid']);self.assertEqual(q.deadline,100)

    def test_transaction_wrapping_preserves_commit_rollback_suppression_and_errors(self):
        for fail,suppress in ((False,False),(True,False),(True,True)):
            calls=[]
            @contextmanager
            def original(obj):
                calls.append('begin')
                try:yield 'value'
                except BaseException:
                    calls.append('rollback')
                    if not suppress:raise
                else:calls.append('commit')
            wrapped=rehearsal.transaction(original);p=m.Profile()
            try:
                with m.capture(p),wrapped(None) as v:
                    self.assertEqual(v,'value')
                    if fail:raise KeyboardInterrupt()
            except KeyboardInterrupt:self.assertTrue(fail and not suppress)
            else:self.assertTrue(not fail or suppress)
            self.assertEqual(calls,['begin','rollback' if fail else 'commit'])
        @contextmanager
        def bad(obj):
            raise ValueError('begin-failed');yield
        with self.assertRaisesRegex(ValueError,'begin-failed'),rehearsal.transaction(bad)(None):pass

    def test_readonly_transactions_remain_inside_parent_phase(self):
        from types import SimpleNamespace
        calls=[]
        @contextmanager
        def original(obj):
            calls.append('begin')
            try:yield
            finally:calls.append('close')
        p=m.Profile()
        with m.capture(p),m.measure('collection'),rehearsal.transaction(original)(SimpleNamespace(read_only=True)):pass
        self.assertEqual(calls,['begin','close'])
        self.assertEqual([x['stage'] for x in p.report()['spans']],['collection'])

    def test_connected_cli_profiles_actual_backend_and_expiry_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'profile.gz'
            result=subprocess.run([sys.executable,'-E','-s',cli.__file__,'--output',str(out)],capture_output=True,text=True,timeout=240)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            r=json.loads(gzip.decompress(out.read_bytes()))
            self.assertEqual(r['state'],'offline-exit-profile-passed')
            self.assertEqual(r['connected']['casesPassed'],12)
            reuse=r['connected']['encodingReplay']
            self.assertEqual(reuse['version'],'exact-public-encoding-1')
            self.assertGreater(reuse['hits'],0)
            self.assertLessEqual(reuse['entries'],512)
            self.assertFalse(reuse['storesStateOrAuthorization'])
            self.assertEqual(len(r['connected']['independentContractCases']),10)
            self.assertTrue(r['connected']['temporaryLedgersRemoved'])
            self.assertEqual(len(r['profiles']),2)
            self.assertTrue(all(p['valid'] for p in r['profiles']))
            self.assertEqual(r['expiry']['state'],'persisted-expiry-reproduced')
            self.assertEqual(r['realNetworkRequests'],0);self.assertFalse(r['productionWalletAccessed'])
            self.assertEqual(out.stat().st_mode&0o777,0o600)

    def test_instrumentation_restored_on_failure_and_no_nested_patching(self):
        before=rehearsal.m.replacement.replace;txn=rehearsal.journal.Journal.transaction
        with self.assertRaises(OSError),rehearsal.instrument():
            self.assertIsNot(rehearsal.m.replacement.replace,before)
            with self.assertRaises(ValueError),rehearsal.instrument():pass
            raise OSError()
        self.assertIs(rehearsal.m.replacement.replace,before)
        self.assertIs(rehearsal.journal.Journal.transaction,txn)

    def test_saved_history_is_readonly_and_preserves_unknown_commit_time(self):
        with case() as c:
            result=c.run();self.assertTrue(result['createdThisRun'])
            before=c.path.read_bytes()
            source={p.name:p.read_bytes() for p in c.home.iterdir() if p.is_file()}
            with patch.object(history.view,'now',c.clock):r=history.inspect(c.home,c.wallet,c.pool)
            self.assertEqual(r['state'],'saved-exit-timing-observed',r)
            t=r['timing'];self.assertEqual(t['preparationSha256'],result['recordSha256'])
            self.assertEqual(len(t['requests']),20)
            self.assertEqual(t['collectionElapsedMs'],t['summedRecordedRequestIntervalsMs']+t['summedInterRequestGapsMs']+t['finalResponseToDeliveryMs'])
            self.assertEqual(t['collectionWindowMs'],t['collectionElapsedMs']+t['deliveryToRecordTimestampMs']+t['remainingAtRecordTimestampMs'])
            self.assertIsNone(t['commitCompletedAtMs']);self.assertIsNone(t['postCommitHeadroomMs'])
            self.assertEqual(c.path.read_bytes(),before)
            self.assertEqual(source,{p.name:p.read_bytes() for p in c.home.iterdir() if p.is_file()})
            self.assertEqual(r['networkRequests'],0);self.assertFalse(r['privateKeyAccessed'])
            self.assertNotIn('signedWire',json.dumps(r));self.assertNotIn(c.wallet,json.dumps(r))
            b=c.book()
            try:b.db.execute("UPDATE admission_exit_replacement SET hash=?",('0'*64,))
            finally:b.close()
            damaged=c.path.read_bytes()
            with patch.object(history.view,'now',c.clock):bad=history.inspect(c.home,c.wallet,c.pool)
            self.assertEqual(bad['state'],'history-unavailable');self.assertIsNone(bad['timing'])
            self.assertEqual(c.path.read_bytes(),damaged)

    def test_saved_timing_rejects_inconsistent_intervals(self):
        with case() as c:
            c.run();b=c.book()
            try:record=history.lifecycle.preparation.saved(b,c.now)
            finally:b.close()
            bad=deepcopy(record);bad['collection']['requestTrace'][0]['requestedAtMs']=0
            with self.assertRaises(ValueError):history.summarize(bad)
            bad=deepcopy(record);bad['recordedAtMs']=bad['binding']['validUntilExclusiveMs']
            with self.assertRaises(ValueError):history.summarize(bad)

    def test_persisted_expiry_is_reproduced_without_signing_or_second_collection(self):
        r=rehearsal.expiry_reproduction()
        self.assertEqual(r['state'],'persisted-expiry-reproduced');self.assertTrue(r['profile']['valid'])
        rows=r['profile']['spans'];self.assertIn('transaction-commit',[x['stage'] for x in rows])
        self.assertNotIn('signer-backend',[x['stage'] for x in rows])
        self.assertEqual(r['sendRequests'],0);self.assertEqual(r['repeatRequests'],0)

    def test_cli_no_execution_scope_and_private_output_guard(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';base=[sys.executable,'-E','-s',cli.__file__,'--output',str(out)]
            for args in (['--allow-devnet-submit'],['--action','execute'],['--directory',d],['--wallet','anything'],['--input','report.gz']):
                self.assertNotEqual(subprocess.run(base+args,capture_output=True).returncode,0)
                self.assertFalse(out.exists())
            home=Path(d)/'source';home.mkdir(mode=0o700)
            args=['cli','--action','inspect','--directory',str(home),'--wallet','w','--pool','p','--output',str(home/'out.gz')]
            with patch.object(sys,'argv',args),patch.object(history,'inspect',side_effect=AssertionError('read')):
                with self.assertRaises(ValueError):cli.main()
            args[-1]=str(out)
            with patch.object(sys,'argv',args),patch.object(history,'inspect',return_value=dict(state='history-unavailable',timing=None)):
                self.assertEqual(cli.main(),2)
            self.assertEqual(out.stat().st_mode&0o777,0o600);raw=out.read_bytes()
            with patch.object(sys,'argv',args),patch.object(history,'inspect',side_effect=AssertionError('read')):
                with self.assertRaises(ValueError):cli.main()
            self.assertEqual(out.read_bytes(),raw)

if __name__=='__main__':unittest.main()
