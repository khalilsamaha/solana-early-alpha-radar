from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import fresh_quote
import post_entry_simulation as sim
from post_entry_checks import mutate_row, fixture
import test_fresh_quote as fixtures
from test_fresh_quote import Clock, Opener, NOW, GENESIS
from test_unsigned_simulation import SimulationOpener


class PoolOpener(SimulationOpener):
    def __init__(self,first,second,scope,change=None,hook=None,cluster=None):
        def pool_return(value):
            pool=deepcopy(self.capture['evidence']['accounts']['result']['value'][0])
            # Standard synthetic entry: 1,000 input, 3 trade fee; both shares floor to zero.
            mutate_row(pool,381,(1).to_bytes(8,'little'))
            value['value']['accounts'].append(pool)
            if change:change(value)
        super().__init__(first,second,scope,pool_return,hook,cluster)


class PostEntryLiveTests(unittest.TestCase):
    def observe(self,change=None,hook=None,cluster=None,**kwargs):
        def observer(*args,**kw):return fresh_quote.observe(*args,**kw,post_entry_projection=True)
        return fixtures.FreshQuoteTests().run_observe(simulate=True,assess_costs=True,observer=observer,
            opener_factory=lambda f,s,scope:PoolOpener(f,s,scope,change,hook,cluster),**kwargs)

    def rejected(self,r):
        self.assertEqual(r['state'],'unavailable',r)
        self.assertFalse(r['simulationVerified']);self.assertFalse(r['liveCollectorVerified'])
        self.assertFalse(r['postEntryObservedInSimulation']);self.assertIsNone(r['postEntryProjection'])

    def test_end_to_end_same_armed_request_response_and_projected_state(self):
        r,o=self.observe()
        self.assertEqual(r['state'],'controlled-post-entry-observation-consistent',r)
        self.assertEqual(r['networkRequests'],20)
        self.assertEqual(r['requestMethods'].count('simulateTransaction'),1)
        q=r['postEntryProjection'];p=q['projection'];s=r['simulation']
        self.assertEqual(p['acquiredInputAtomic'],'906')
        self.assertEqual(p['reservesToken0Token1Atomic'],['11000','9094'])
        self.assertEqual(p['projectedOutputAtomic'],'993')
        self.assertEqual(q['evidence']['fullSimulationSha256'],s['fullSimulationEvidenceSha256'])
        self.assertEqual(q['evidence']['requestParametersSha256'],s['requestParametersSha256'])
        self.assertTrue(q['liveCollectorVerified']);self.assertTrue(s['postEntryPoolReviewed'])
        self.assertTrue(r['postEntryObservedInSimulation'])
        params=o.calls[18]['params']
        self.assertEqual(len(params[1]['accounts']['addresses']),9)
        self.assertEqual(params[1]['accounts']['addresses'][-1],p['pool'])
        for k in ('executionApproved','privateKeyAccessed','sourceStateChanged','exitSimulationVerified'):
            self.assertFalse(r[k],k)
        self.assertEqual((r['signaturesCreated'],r['transactionsSent']),(0,0))
        self.assertNotIn('unsignedTransactionBase64',json.dumps(r))

    def test_missing_extra_null_oversized_or_wrong_pool_is_rejected(self):
        changes=[lambda v:v['value']['accounts'].pop(),
            lambda v:v['value']['accounts'].append(deepcopy(v['value']['accounts'][8])),
            lambda v:v['value']['accounts'].__setitem__(8,None),
            lambda v:v['value']['accounts'][8]['data'].__setitem__(0,'A'*6004),
            lambda v:v['value']['accounts'][8].update(owner=GENESIS['devnet']),
            lambda v:mutate_row(v['value']['accounts'][8],636,b'\x01'),
            lambda v:mutate_row(v['value']['accounts'][8],341,(1).to_bytes(8,'little'))]
        for change in changes:
            r,o=self.observe(change);self.rejected(r)
            self.assertLessEqual(len(o.calls),20)
            self.assertEqual(sum(x['method']=='simulateTransaction' for x in o.calls),1)

    def test_late_simulation_cluster_change_and_late_final_local_read(self):
        clock=Clock()
        def late(n,b):
            if n==19:clock.at+=10001
        r,o=self.observe(clock=clock,hook=late);self.rejected(r);self.assertEqual(len(o.calls),19)
        r,_=self.observe(cluster=GENESIS['mainnet-beta']);self.rejected(r)
        clock=Clock()
        def late_ledger(n,v):
            if n==3:clock.at+=10001
        r,_=self.observe(clock=clock,ledger_hook=late_ledger);self.rejected(r)

    def test_final_journal_change_stop_and_unknown_reservation_block(self):
        for mode in ('ledger','reservation','stop'):
            stop=[False]
            def ledger(n,v):
                if n==3:
                    if mode=='ledger':v['ledgerHeadSha256']='c'*64
                    if mode=='reservation':v['nativeHeldLamports']=None
                    if mode=='stop':stop[0]=True
            r,_=self.observe(ledger_hook=ledger,stop=lambda _:stop[0]);self.rejected(r)

    def test_provider_errors_are_sanitized_no_retry(self):
        r,o=self.observe(lambda v:v['value'].update(err={'private':'sensitive-value'}))
        self.rejected(r);self.assertEqual(len(o.calls),19)
        self.assertNotIn('sensitive-value',json.dumps(r))

    def test_projection_work_cannot_extend_original_deadline(self):
        import post_entry
        clock=Clock();original=post_entry.assess
        def slow(*args):
            r=original(*args);clock.at+=10001;return r
        with patch('post_entry.assess',slow):r,_=self.observe(clock=clock)
        self.rejected(r)

    def test_shared_time_budget_and_no_provider_payload_in_public_output(self):
        t=sim.Transport(Opener([None]),monotonic=lambda:1)
        t.monotonic=lambda:32
        request=urllib.request.Request(fresh_quote.ENDPOINTS['devnet'],
            data=json.dumps(dict(method='getGenesisHash',params=[],id=1)).encode())
        with self.assertRaises(ValueError):t.open(request,10)
        self.assertEqual(t.calls,[])
        def logs(v):v['value'].update(logs=['private provider log'],arbitrarySecret='do-not-export')
        r,_=self.observe(logs)
        self.assertEqual(r['state'],'controlled-post-entry-observation-consistent',r)
        self.assertNotIn('private provider log',json.dumps(r));self.assertNotIn('do-not-export',json.dumps(r))

    def test_exact_transport_rejects_send_rearm_other_parameters_and_extra_calls(self):
        args,_=fixture();c=args['capture'];t=sim.Transport(Opener([None]*30),monotonic=lambda:1)
        def req(method,p):return urllib.request.Request(fresh_quote.ENDPOINTS['devnet'],
            data=json.dumps(dict(method=method,params=p,id=1)).encode())
        with self.assertRaises(ValueError):t.open(req('simulateTransaction',[]),10)
        t.calls=['getGenesisHash']*18;t.arm(c['packet'],c,NOW)
        with self.assertRaises(ValueError):t.arm(c['packet'],c,NOW)
        for kind in ('send','type','account'):
            p=deepcopy(t.expected);method='simulateTransaction'
            if kind=='send':method='sendTransaction'
            if kind=='type':p[1]['sigVerify']=0
            if kind=='account':p[1]['accounts']['addresses'].pop()
            with self.assertRaises(ValueError):t.open(req(method,p),10)
        t.open(req('simulateTransaction',t.expected),10)
        with self.assertRaises(ValueError):t.open(req('simulateTransaction',t.expected),10)
        t.open(req('getGenesisHash',[]),10)
        with self.assertRaises(ValueError):t.open(req('getGenesisHash',[]),10)

    def test_old_rpc_parser_rejects_ninth_account_and_new_parser_requires_it(self):
        import unsigned_simulation as old
        args,params=fixture();value=deepcopy(args['simulation_item']['result'])
        value['value']['err']=None
        self.assertEqual(old.SimulationRpc(Opener([value])).request('simulateTransaction',params)['state'],
                         'invalid-simulation-response')
        good=sim.SimulationRpc(Opener([value])).request('simulateTransaction',params)
        self.assertEqual(good['state'],'received')
        value['value']['accounts'].pop()
        self.assertEqual(sim.SimulationRpc(Opener([value])).request('simulateTransaction',params)['state'],
                         'invalid-simulation-response')

    def test_mode_is_explicit_not_reverse_or_paired_handoff(self):
        for options in ({},{'simulate':True},{'simulate':True,'assess_costs':True,'reverse_reference':True},
                        {'simulate':True,'assess_costs':True,'_evidence_sink':lambda _:None}):
            with self.assertRaises(ValueError):
                fresh_quote.observe(Path('/unused'),'wallet','pool',post_entry_projection=True,**options)

    def test_cli_offline_and_rejects_incomplete_scope_execution_and_existing_output(self):
        cli=Path(__file__).with_name('post_entry_live_cli.py')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'report.gz';cmd=[sys.executable,str(cli),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            original=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(original))['casesPassed'],9)
            self.assertEqual(out.stat().st_mode & 0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),original)
            other=[sys.executable,str(cli),'--output',str(Path(tmp)/'absent.gz')]
            for flags in (['--simulate-devnet'],['--allow-devnet-submit'],['--wallet','w'],
                          ['--directory',tmp,'--simulate-devnet','--wallet','w','--pool','p']):
                self.assertNotEqual(subprocess.run(other+flags,capture_output=True).returncode,0)
            self.assertFalse((Path(tmp)/'absent.gz').exists())


if __name__=='__main__':unittest.main()
