import base64
import contextlib
import copy
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import deployment_probe as d
from test_accounting_inspect import fixture
from test_event_inspect import accepted, key

DATA_KEYS = [key(777), key(888)]
INPUTS = {"rpc_report_sha256": "a"*64, "evidence_sha256": "b"*64, "evidence_decoded_sha256": "c"*64}


def row(raw, executable, space):
    return {"owner": d.LOADER, "executable": executable, "lamports": 10000, "space": space,
            "data": [base64.b64encode(raw).decode(), "base64"]}


def program_rows():
    return [row((2).to_bytes(4,"little")+d.base.b58decode(k), True, 36) for k in DATA_KEYS]


def data_rows(slots=(50,60)):
    return [row((3).to_bytes(4,"little")+slot.to_bytes(8,"little")+b'\1'+bytes([i+1])*32+b'\x7fELF', False, 1000)
            for i,slot in enumerate(slots)]


class Opener:
    def __init__(self, change=None, slots=(50,60)):
        self.requests=[];self.change=change;self.slots=slots
    def open(self, request, timeout):
        payload=json.loads(request.data);self.requests.append(payload)
        n=payload['id']
        value=d.rpc.GENESIS if n in (1,5) else {
            'context':{'slot':198+n},'value':program_rows()+(data_rows(self.slots) if n in (3,4) else [])}
        if self.change:value=self.change(n,value)
        return io.BytesIO(json.dumps({'jsonrpc':'2.0','id':n,'result':value}).encode())


class ProbeTests(unittest.TestCase):
    def run_probe(self, change=None, slots=(50,60)):
        opener=Opener(change,slots);client=d.Client(opener,pause=lambda _:None)
        result=d.reconcile([100,110],client)
        return result,client,opener

    def test_five_fixed_reads_finalized_monotonic_and_no_binary_acceptance(self):
        result,client,opener=self.run_probe()
        self.assertEqual(result['status'],'deployment-metadata-predates-sample-live-blocked')
        self.assertEqual(len(client.calls),5)
        self.assertEqual([p['method'] for p in opener.requests],['getGenesisHash','getMultipleAccounts','getMultipleAccounts','getMultipleAccounts','getGenesisHash'])
        for p,minimum in zip(opener.requests[1:4],[110,200,201]):
            self.assertEqual(p['params'][1],{'encoding':'base64','commitment':'finalized','minContextSlot':minimum,'dataSlice':{'offset':0,'length':49}})
        self.assertEqual(opener.requests[2]['params'][0],d.programs()+DATA_KEYS)
        for flag in ('bytecode_verified','source_binary_equivalence_verified','historical_fee_config_verified',
                     'deployed_program_version_verified','programdata_pda_verified','curve_reconstruction_accepted'):
            self.assertIs(result[flag],False)

    def test_same_slot_and_later_modification_remain_unresolved(self):
        for slot in (100,101,110,120):
            result,_,_=self.run_probe(slots=(slot,60))
            self.assertEqual(result['status'],'historical-deployment-window-unresolved')
            self.assertEqual(result['programs'][0]['modification_strictly_before_each_sample'],[slot<100,slot<110])

    def test_genesis_mismatch_before_or_after_never_exports_partial_pass(self):
        for at in (1,5):
            result,client,_=self.run_probe(lambda n,v:'wrong-chain' if n==at else v)
            self.assertEqual(result['status'],'deployment-metadata-unavailable')
            self.assertEqual(result['programs'],[])
            self.assertFalse(result['genesis_verified_before_and_after'])
            self.assertEqual(len(client.calls),at)

    def test_owner_executable_space_encoding_and_null_rows_rejected(self):
        for field,value in [('owner',key(4)),('executable',False),('space',37),('lamports',True),('lamports',0),
                            ('data',['AA==','base64']),('data',['x'*69,'base64']),('data',['AAAA','base64+zstd'])]:
            def change(n,v):
                if n==2:v['value'][0][field]=value
                return v
            self.assertEqual(self.run_probe(change)[0]['status'],'deployment-metadata-unavailable')
        self.assertEqual(self.run_probe(lambda n,v:{'context':{'slot':200},'value':[None,None]} if n==2 else v)[0]['programs'],[])

    def test_tags_options_elf_and_future_slots_rejected(self):
        for offset,value in ((0,2),(12,2),(45,0)):
            def change(n,v):
                if n==3:
                    raw=bytearray(base64.b64decode(v['value'][2]['data'][0]));raw[offset]=value
                    v['value'][2]['data'][0]=base64.b64encode(raw).decode()
                return v
            self.assertEqual(self.run_probe(change)[0]['status'],'deployment-metadata-unavailable')
        self.assertEqual(self.run_probe(slots=(300,60))[0]['status'],'deployment-metadata-unavailable')

    def test_context_regression_missing_rows_bool_and_order_changes_rejected(self):
        for kind in ('stale','regression','bool','missing','order'):
            def change(n,v):
                if n==3:
                    if kind in ('stale','regression','bool'):v['context']['slot']={'stale':99,'regression':199,'bool':True}[kind]
                    elif kind=='missing':v['value'].pop()
                    else:v['value'][0],v['value'][1]=v['value'][1],v['value'][0]
                return v
            self.assertEqual(self.run_probe(change)[0]['status'],'deployment-metadata-unavailable')

    def test_changed_pointer_header_or_space_on_recheck_rejected(self):
        for kind in ('pointer','slot','authority','space'):
            def change(n,v):
                if n==4:
                    if kind=='pointer':v['value'][0]=row((2).to_bytes(4,'little')+d.base.b58decode(key(999)),True,36)
                    elif kind=='space':v['value'][2]['space']+=1
                    else:
                        raw=bytearray(base64.b64decode(v['value'][2]['data'][0]));raw[4 if kind=='slot' else 13]+=1
                        v['value'][2]['data'][0]=base64.b64encode(raw).decode()
                return v
            self.assertEqual(self.run_probe(change)[0]['programs'],[])

    def test_immutable_authority_option_supported_without_identity_claim(self):
        def change(n,v):
            if n in (3,4):
                for account in v['value'][2:]:
                    raw=bytearray(base64.b64decode(account['data'][0]));raw[12]=0
                    account['data'][0]=base64.b64encode(raw).decode()
            return v
        result,_,_=self.run_probe(change)
        self.assertEqual(result['status'],'deployment-metadata-predates-sample-live-blocked')
        self.assertFalse(result['programs'][0]['upgrade_authority_present'])
        self.assertFalse(result['bytecode_verified'])

    def test_method_budget_deadline_and_invalid_slots_start_no_extra_requests(self):
        _,client,opener=self.run_probe()
        self.assertEqual(client.request('getGenesisHash',[])['state'],'request-budget-exhausted')
        with self.assertRaises(d.CaptureError):client.request('sendTransaction',[])
        self.assertEqual(len(opener.requests),5)
        client=d.Client(Opener(),clock=lambda:0,pause=lambda _:None);client.deadline=0
        self.assertEqual(d.reconcile([100],client)['status'],'deployment-metadata-unavailable')
        self.assertEqual(client.calls,[])
        for slots in ([],[True],[0],[2**64],[1,2,3,4]):
            with self.assertRaises(d.CaptureError):d.reconcile(slots,client)
        self.assertEqual(client.calls,[])

    def test_transport_failure_stops_without_retry_or_provider_text(self):
        opener=Opener()
        def failure(n,v):
            if n==2:raise HTTPError('https://invalid/',429,'SECRET-provider-error',None,io.BytesIO(b'SECRET'))
            return v
        opener.change=failure;client=d.Client(opener,pause=lambda _:None)
        result=d.reconcile([100],client)
        self.assertEqual(result['status'],'deployment-metadata-unavailable')
        self.assertEqual(len(client.calls),2)
        self.assertNotIn('SECRET',json.dumps([result,client.calls,client.evidence]))

    def test_replay_binds_requests_inputs_and_all_records(self):
        result,client,_=self.run_probe()
        original={'schema_version':1,'sample_slots':[100,110],'source_input_sha256':INPUTS,'rpc_evidence':client.evidence}
        self.assertEqual(d.replay(original,[100,110],INPUTS),result)
        for kind in ('input','slot','method','params','extra'):
            bundle=copy.deepcopy(original)
            if kind=='input':bundle['source_input_sha256']['rpc_report_sha256']='bad'
            elif kind=='slot':bundle['sample_slots']=[100]
            elif kind=='method':bundle['rpc_evidence'][1]['method']='getAccountInfo'
            elif kind=='params':bundle['rpc_evidence'][1]['params'][1]['commitment']='processed'
            else:bundle['rpc_evidence'].append(copy.deepcopy(bundle['rpc_evidence'][-1]))
            with self.assertRaises(d.CaptureError):d.replay(bundle,[100,110],INPUTS)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        report,_,compressed=accepted(fixture())
        self.report=self.root/'input.json';self.report.write_text(json.dumps(report))
        self.evidence=self.root/'input.json.gz';self.evidence.write_bytes(compressed)
        self.out=self.root/'out';self.client=d.Client(Opener(),pause=lambda _:None)
    def tearDown(self):self.temp.cleanup()
    def call(self,mode=('--read-public-rpc',)):
        self.messages=io.StringIO()
        with patch.object(d,'Client',return_value=self.client),patch('socket.socket',side_effect=AssertionError('network forbidden')),contextlib.redirect_stdout(self.messages),contextlib.redirect_stderr(self.messages):
            return d.main(['--rpc-report',str(self.report),'--evidence',str(self.evidence),'--output-directory',str(self.out),*mode])
    def test_mocked_capture_is_private_replayable_and_preserves_source_inputs(self):
        before=[p.read_bytes() for p in (self.report,self.evidence)]
        self.assertEqual(self.call(),0)
        r=json.loads((self.out/'report.json').read_text())
        self.assertEqual(len(r['rpc_requests']),5);self.assertTrue(r['local_replay_verified'])
        self.assertEqual(r['status'],'deployment-metadata-predates-sample-live-blocked')
        for p in (self.out/'report.json',self.out/'evidence.json.gz'):self.assertEqual(p.stat().st_mode&0o777,0o600)
        self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        self.assertEqual(before,[p.read_bytes() for p in (self.report,self.evidence)])
        saved=self.out/'evidence.json.gz';self.out=self.root/'replayed'
        self.assertEqual(self.call(('--replay-evidence',str(saved))),0)
        replay=json.loads((self.out/'report.json').read_text())
        self.assertFalse(replay['network_used']);self.assertEqual(replay['rpc_requests'],[])
        self.assertEqual(replay['reconciliation'],r['reconciliation'])
        self.assertEqual(replay['evidence_sha256'],r['evidence_sha256'])
    def test_unavailable_capture_is_retained_and_not_a_pass(self):
        self.client=d.Client(Opener(lambda n,v:'wrong-chain' if n==1 else v),pause=lambda _:None)
        self.assertEqual(self.call(),0)
        r=json.loads((self.out/'report.json').read_text())
        self.assertEqual(r['status'],'deployment-metadata-unavailable')
        self.assertTrue(r['local_replay_verified']);self.assertEqual(len(r['rpc_requests']),1)
    def test_invalid_inputs_and_missing_mode_do_not_start_network(self):
        self.assertEqual(self.call(()),1)
        self.assertFalse(self.out.exists())
        self.evidence.write_bytes(self.evidence.read_bytes()+b'x')
        self.assertEqual(self.call(),1);self.assertEqual(self.client.calls,[])
        self.assertFalse(self.out.exists())
    def test_existing_directory_and_unknown_arguments_preserved_and_sanitized(self):
        self.out.mkdir();(self.out/'keep').write_text('preserve')
        self.assertEqual(self.call(),1);self.assertEqual((self.out/'keep').read_text(),'preserve')
        self.assertEqual(self.client.calls,[])
        self.assertEqual(self.call(('--read-public-rpc','--api-key','SENSITIVE-KEY')),1)
        self.assertNotIn('SENSITIVE-KEY',self.messages.getvalue())
