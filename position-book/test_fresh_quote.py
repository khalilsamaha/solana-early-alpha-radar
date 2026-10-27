"""Real collectors and raw parsers over bounded fake HTTP, never a real RPC call."""
from contextlib import ExitStack, nullcontext
from copy import deepcopy
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

import fresh_quote as m
from preflight_checks import fixture, edit, NOW, GENESIS, fake_key


class Clock:
    def __init__(self):self.at=NOW
    def __call__(self):self.at+=5;return self.at


class Opener:
    def __init__(self,responses,hook=None):self.responses=responses;self.calls=[];self.hook=hook
    def open(self,request,timeout):
        body=json.loads(request.data);self.calls.append(body)
        if self.hook:self.hook(len(self.calls),body)
        value=self.responses.pop(0)
        if isinstance(value,Exception):raise value
        return io.BytesIO(json.dumps({'jsonrpc':'2.0','id':body['id'],'result':value}).encode())


def replies(c):
    names=['genesisBefore','programBootstrap','poolBootstrap','accounts','blockTime']
    if c['packet'] is not None:names+=['blockhash','fee']
    names+=['genesisAfter']
    return [deepcopy(c['evidence'][n]['result']) for n in names]


def setup():
    first,baseline=fixture(False);second,_=fixture(True)
    baseline.update(kind='observed-devnet-deployment',observedAtMs=0)
    scope={k:deepcopy(v) for k,v in second['packet']['policy'].items()
           if k not in ('issuedAtMs','expiresAtMs','blockhash')}
    scope.update(format='devnet-swap-scope-1',amountIn='1000',minimumAmountOut='990',
                 maxMicroLamportsPerCU='0',maxPriorityFeeLamports='0',maxTotalFeeLamports='10000')
    second['evidence']['fee']['result']['value']=5000
    return first,second,baseline,scope


def responses(first,second):
    return replies(first)+[GENESIS['devnet'],{'context':{'slot':101},'value':{
        'blockhash':fake_key('fresh-blockhash'),'lastValidBlockHeight':200}},
        {'context':{'slot':101},'value':5000},GENESIS['devnet']]+replies(second)


class FreshQuoteTests(unittest.TestCase):
    def run_observe(self,mutate=None,clock=None,ledger_hook=None,stop=None,http_hook=None,
                    opener_factory=None,simulate=False):
        first,second,base,scope=setup(); clock=clock or Clock()
        if mutate:mutate(first,second,scope)
        opener=(opener_factory(first,second,scope) if opener_factory else
                Opener(responses(first,second),http_hook))
        a=scope['accounts']; reads=[]
        def read(root,wallet,pool,cl):
            v=dict(phase='closed',wallet=wallet,pool=pool,nativeHeldLamports='0',
                   tokenAccounts=[dict(account=a['source'],mint=a['inputMint'],heldAtomic='0')],
                   observedAtMs=cl(),ledgerHeadSha256='a'*64,cycleBindingSha256='b'*64)
            v['readStartedAtMs']=v['observedAtMs']
            reads.append(v)
            if ledger_hook:ledger_hook(len(reads),v)
            return v
        with ExitStack() as stack:
            for target,value in (
                ('preflight.BASELINE',base),('preflight_capture.BASELINE',base),
                ('fresh_quote.view.cycles.c.source_lock',lambda *args:nullcontext(Path('/synthetic'))),
                ('fresh_quote.view.read_locked',read),
                ('fresh_quote.view.cycles.c.submit.bridge.source_scope',lambda *args:(deepcopy(scope),{})),
                ('fresh_quote.view.cycles.c.submit.swap.stop',stop or (lambda root:False))):
                stack.enter_context(patch(target,value))
            stack.enter_context(patch('core.signer',side_effect=AssertionError('signer called')))
            stack.enter_context(patch('fresh_packet.prepare_fresh',side_effect=AssertionError('prepare called')))
            r=m.observe(Path('/synthetic'),a['wallet'],a['pool'],opener=opener,clock=clock,simulate=simulate)
        return r,opener

    def test_full_collect_price_reprice_fee_account_binding_has_no_send(self):
        r,o=self.run_observe()
        self.assertEqual(r['state'],'fresh-quote-observation-consistent',r)
        self.assertEqual(r['networkRequests'],18)
        self.assertEqual(r['quote']['quote']['outAmount'],'906')
        self.assertEqual(r['quote']['quote']['minimumOutAmount'],'897')
        self.assertEqual(r['binding']['binding']['rpcMessageFeeLamports'],'5000')
        self.assertFalse(r['executionApproved']);self.assertFalse(r['nextCycleAuthorized'])
        self.assertEqual(r['transactionsSent'],0);self.assertEqual(r['signaturesCreated'],0)
        self.assertTrue(all(x['method'] in m.METHODS for x in o.calls))

    def test_pool_change_blocks_even_if_rounded_output_stays_the_same(self):
        def mutate(first,second,scope):edit(second,4,64,(10001).to_bytes(8,'little'))
        r,_=self.run_observe(mutate)
        self.assertEqual(r['state'],'unavailable');self.assertEqual(r['stage'],'local-binding')

    def test_program_drift_stops_without_packet_requests(self):
        r,o=self.run_observe(lambda f,s,scope:edit(f,-1,120,b'\x01'))
        self.assertEqual(r['state'],'unavailable');self.assertEqual(r['stage'],'pool-quote')
        self.assertEqual(len(o.calls),4)

    def test_new_account_shortfall_and_blockhash_failure_block(self):
        for what in ('token','native','blockhash'):
            def mutate(f,s,scope):
                if what=='token':edit(s,9,64,(999).to_bytes(8,'little'))
                if what=='native':s['evidence']['accounts']['result']['value'][8]['lamports']=9999
                if what=='blockhash':s['evidence']['blockhash']['result']['value']=False
            r,_=self.run_observe(mutate)
            self.assertEqual(r['state'],'unavailable',what)

    def test_unknown_changed_and_reserved_ledger_still_block(self):
        for what in ('unknown','changed','token','native','open'):
            def change(n,v):
                if what=='open':v['phase']='open'
                if n==2:
                    if what=='unknown':v['tokenAccounts'][0]['heldAtomic']=None
                    if what=='changed':v['ledgerHeadSha256']='c'*64
                    if what=='token':v['tokenAccounts'][0]['heldAtomic']='1'
                    if what=='native':v['nativeHeldLamports']='90001'
            r,o=self.run_observe(ledger_hook=change)
            self.assertEqual(r['state'],'unavailable',what)
            if what=='open':self.assertEqual(len(o.calls),0)

    def test_stale_original_quote_is_not_refreshed_by_later_reads(self):
        clock=Clock()
        def late(n,body):
            if n==11:clock.at+=10001
        r,_=self.run_observe(clock=clock,http_hook=late)
        self.assertEqual(r['state'],'unavailable')

    def test_stop_after_packet_stops_before_final_reads(self):
        r,o=self.run_observe(stop=lambda root:True)
        self.assertEqual(r['state'],'unavailable');self.assertEqual(len(o.calls),10)

    def test_deadline_and_request_allowlist(self):
        o=Opener([None]*20);transport=m.ReadTransport(o,monotonic=lambda:1)
        def req(method,url=m.ENDPOINTS['devnet']):
            return urllib.request.Request(url,data=json.dumps({'id':1,'method':method}).encode())
        for method in ('sendTransaction','simulateTransaction','requestAirdrop'):
            with self.assertRaises(ValueError):transport.open(req(method),10)
        with self.assertRaises(ValueError):transport.open(req('getGenesisHash','https://api.mainnet-beta.solana.com'),10)
        self.assertEqual(o.calls,[])
        for _ in range(18):transport.open(req('getGenesisHash'),10)
        with self.assertRaises(ValueError):transport.open(req('getGenesisHash'),10)
        clock=iter([1,31]);t=m.ReadTransport(o,monotonic=lambda:next(clock))
        with self.assertRaises(ValueError):t.open(req('getGenesisHash'),10)

    def test_offline_cli_no_state_or_network_and_private_output(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'check.json.gz'
            args=[sys.executable,'-E','-s',str(Path(__file__).with_name('fresh_quote_cli.py')),'--output',str(path)]
            r=subprocess.run(args,capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr)
            v=json.loads(gzip.decompress(path.read_bytes()))
            self.assertEqual(v['casesPassed'],11);self.assertEqual(v['networkRequests'],0)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            original=path.read_bytes()
            self.assertNotEqual(subprocess.run(args,capture_output=True,timeout=15).returncode,0)
            self.assertEqual(path.read_bytes(),original)


if __name__=='__main__':unittest.main()
