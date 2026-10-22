import base64
import copy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from lookup import collect_lookups, review_lookups, decode_account, LookupClient, PROGRAM, U64
from recorded_capture import GENESIS, Client, SYSTEM
from recorded_checks import synthetic
from test_recorded import FakeOpener
from reconcile import digest
from wire import b58

ROOT = Path(__file__).resolve().parent
ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def raw58(text):
    n = 0
    for ch in text: n = n * 58 + ALPHABET.index(ch)
    return b'\0' * (len(text) - len(text.lstrip('1'))) + n.to_bytes((n.bit_length()+7)//8, 'big')


def source():
    return json.loads((ROOT / 'devnet-two-table-fixture.json').read_text())


def account(addresses, extended=0, start=0, deactivation=U64, authority=True):
    raw = (1).to_bytes(4,'little') + deactivation.to_bytes(8,'little') + extended.to_bytes(8,'little')
    raw += bytes([start, int(authority)]) + (bytes([9])*32 if authority else b'') + bytes(2)
    raw = raw.ljust(56,b'\0') + b''.join(raw58(a) for a in addresses)
    return {'owner':PROGRAM,'executable':False,'data':[base64.b64encode(raw).decode(),'base64']}


def fixture(s=None):
    # Synthetic account state for a real signed message. Not a chain-state fixture.
    s = source() if s is None else s
    tx = s['evidence']['transactionJson']['result']
    descriptors = tx['transaction']['message'].get('addressTableLookups',[])
    keys = list(dict.fromkeys(d['accountKey'] for d in descriptors))
    maps = {k:{} for k in keys}
    for kind in ('writable','readonly'):
        cursor = iter(tx['meta']['loadedAddresses'][kind])
        for d in descriptors:
            for i in d[kind+'Indexes']: maps[d['accountKey']][i] = next(cursor)
    rows = [account([maps[k].get(i,SYSTEM) for i in range(max(maps[k],default=-1)+1)],tx['slot']-1) for k in keys]
    recv=lambda v:{'state':'received','result':v}
    c={'format':'lookup-capture-1','network':s['network'],'signature':s['signature'],
       'transactionSlot':tx['slot'],'accountKeys':keys,'sourceCaptureSha256':digest(s),
       'startedAtMs':s['finishedAtMs']+1,'finishedAtMs':s['finishedAtMs']+2,
       'evidence':{'genesisBefore':recv(GENESIS['devnet']),'genesisAfter':recv(GENESIS['devnet']),
       'accounts':recv({'context':{'slot':tx['slot']+10},'value':rows})},'rpcRequestsAttempted':0,'requests':[]}
    return s,c


def rows(c): return c['evidence']['accounts']['result']['value']
def mutate(c, offset, value):
    r=rows(c)[0]; b=bytearray(base64.b64decode(r['data'][0])); b[offset:offset+len(value)]=value
    r['data'][0]=base64.b64encode(b).decode()


class LookupReviewTests(unittest.TestCase):
    def test_recorded_public_account_bytes_and_temporal_uncertainty(self):
        c=json.loads((ROOT/'devnet-lookup-fixture.json').read_text())
        with patch('socket.socket',side_effect=AssertionError('no network')):
            r=review_lookups(source(),c)
        self.assertEqual(r['state'],'current-lookup-addresses-consistent')
        self.assertEqual(r['resolvedAddressCount'],14)
        self.assertEqual(r['temporalAssessment'],'unknown')
        self.assertEqual(r['tables'][1]['temporalAssessment'],'unknown-later-extension')
        self.assertFalse(r['historicalStateProven'])

    def test_two_tables_resolve_in_writable_then_readonly_order(self):
        s,c=fixture(); before=copy.deepcopy((s,c))
        with patch('socket.socket',side_effect=AssertionError('network')): r=review_lookups(s,c)
        self.assertEqual(r['state'],'current-lookup-addresses-consistent'); self.assertTrue(r['addressesMatched'])
        self.assertEqual(len(r['tables']),2); self.assertFalse(r['historicalStateProven'])
        self.assertFalse(r['executionApproved']); self.assertFalse(r['ledgerUpdated']); self.assertEqual((s,c),before)

    def test_no_lookup_is_not_required_and_zero_requests(self):
        s=synthetic(); opener=FakeOpener([]); c=collect_lookups(s,opener)
        self.assertEqual(review_lookups(s,c)['state'],'not-required'); self.assertEqual(opener.calls,[])

    def test_bad_source_never_calls_rpc(self):
        s=source(); s['signature']=b58(bytes([1])*64); opener=FakeOpener([])
        with self.assertRaises(Exception): collect_lookups(s,opener)
        self.assertEqual(opener.calls,[])

    def test_source_hash_network_signature_keys_slot_are_bound(self):
        for field,value in [('sourceCaptureSha256','x'),('network','mainnet-beta'),('signature','x'),('accountKeys',[]),('transactionSlot',True)]:
            s,c=fixture(); c[field]=value
            self.assertEqual(review_lookups(s,c)['reason'],'capture-source-disagreement')

    def test_missing_and_closed_accounts_stay_unknown(self):
        s,c=fixture(); rows(c)[0]=None
        self.assertEqual(review_lookups(s,c)['state'],'unknown')

    def test_owner_and_executable_checks(self):
        for field,value in [('owner',SYSTEM),('executable',True),('executable',0)]:
            s,c=fixture(); rows(c)[0][field]=value
            self.assertEqual(review_lookups(s,c)['state'],'mismatch')

    def test_encoding_length_variant_and_padding(self):
        for offset,data in [(0,bytes(4)),(21,b'\x02'),(54,b'\x01')]:
            s,c=fixture(); mutate(c,offset,data)
            self.assertIn(review_lookups(s,c)['state'],('unsupported','invalid-input'))
        for data in [['AA','base64'],['','jsonParsed'],['A'*11001,'base64']]:
            s,c=fixture(); rows(c)[0]['data']=data
            self.assertIn(review_lookups(s,c)['state'],('unsupported','invalid-input'))

    def test_frozen_authority_and_max_addresses(self):
        a=account([SYSTEM]*256,authority=False)
        self.assertEqual(len(decode_account(a,100)['addresses']),256)
        with self.assertRaises(Exception): decode_account(account([SYSTEM]*257),100)

    def test_boolean_future_context_and_slot_metadata(self):
        for context in (True,-1,0,2**64):
            s,c=fixture(); c['evidence']['accounts']['result']['context']['slot']=context
            self.assertEqual(review_lookups(s,c)['state'],'mismatch')
        s,c=fixture(); mutate(c,12,(c['transactionSlot']+11).to_bytes(8,'little'))
        self.assertEqual(review_lookups(s,c)['state'],'invalid-input')

    def test_account_count_and_order(self):
        s,c=fixture(); rows(c).reverse()
        self.assertEqual(review_lookups(s,c)['state'],'mismatch')
        s,c=fixture(); rows(c).pop()
        self.assertEqual(review_lookups(s,c)['reason'],'account-count-mismatch')

    def test_address_substitution_is_mismatch(self):
        s,c=fixture(); tx=s['evidence']['transactionJson']['result']
        d=tx['transaction']['message']['addressTableLookups'][0]
        i=(d['writableIndexes']+d['readonlyIndexes'])[0]
        mutate(c,56+32*i,bytes([7])*32)
        self.assertEqual(review_lookups(s,c)['reason'],'loaded-address-disagreement')

    def test_truncated_table_cannot_resolve_index(self):
        s,c=fixture(); rows(c)[0]=account([])
        self.assertEqual(review_lookups(s,c)['reason'],'lookup-index-out-of-range')

    def test_same_slot_extension_of_used_index_is_incompatible(self):
        s,c=fixture(); mutate(c,12,c['transactionSlot'].to_bytes(8,'little'))
        self.assertEqual(review_lookups(s,c)['reason'],'same-slot-address-not-active')

    def test_same_slot_older_prefix_can_be_compatible(self):
        s,c=fixture(); mutate(c,12,c['transactionSlot'].to_bytes(8,'little'))
        n=(len(base64.b64decode(rows(c)[0]['data'][0]))-56)//32
        self.assertLess(n,256); mutate(c,20,bytes([n]))
        self.assertEqual(review_lookups(s,c)['state'],'current-lookup-addresses-consistent')

    def test_later_extension_and_deactivation_remain_unknown(self):
        for offset,value in [(12,1),(4,-1)]:
            s,c=fixture(); mutate(c,offset,(c['transactionSlot']+value).to_bytes(8,'little'))
            r=review_lookups(s,c)
            self.assertEqual(r['state'],'current-lookup-addresses-consistent')
            self.assertEqual(r['temporalAssessment'],'unknown'); self.assertFalse(r['historicalStateProven'])

    def test_genesis_both_ends_and_missing_evidence(self):
        for k in ('genesisBefore','genesisAfter'):
            s,c=fixture(); c['evidence'][k]['result']=GENESIS['mainnet-beta']
            self.assertEqual(review_lookups(s,c)['state'],'mismatch')
            c['evidence'][k]={'state':'not-requested'}
            self.assertEqual(review_lookups(s,c)['state'],'unknown')

    def test_malformed_shapes_are_explicit(self):
        for c in (None,{},[],{'format':'lookup-capture-1'}):
            self.assertEqual(review_lookups(source(),c)['state'],'invalid-input')


class LookupTransportTests(unittest.TestCase):
    def test_exact_three_reads_min_context_and_projection(self):
        s,c=fixture(); response=copy.deepcopy(c['evidence']['accounts']['result'])
        response['value'][0]['privateMarker']='do-not-export'
        op=FakeOpener([GENESIS['devnet'],response,GENESIS['devnet']]); capture=collect_lookups(s,op)
        self.assertEqual(capture['rpcRequestsAttempted'],3)
        self.assertEqual([v[2]['method'] for v in op.calls],['getGenesisHash','getMultipleAccounts','getGenesisHash'])
        self.assertEqual(op.calls[1][2]['params'],[c['accountKeys'],{'encoding':'base64','commitment':'finalized','minContextSlot':c['transactionSlot']}])
        self.assertNotIn('privateMarker',json.dumps(capture))
        self.assertEqual(review_lookups(s,capture)['state'],'current-lookup-addresses-consistent')

    def test_wrong_cluster_stops_after_one(self):
        op=FakeOpener([GENESIS['mainnet-beta']]); c=collect_lookups(source(),op)
        self.assertEqual(len(op.calls),1); self.assertEqual(review_lookups(source(),c)['state'],'mismatch')

    def test_http_failure_no_retry(self):
        op=FakeOpener([GENESIS['devnet'],urllib.error.HTTPError('url',429,'secret',{},None)])
        c=collect_lookups(source(),op)
        self.assertEqual(len(op.calls),2); self.assertNotIn('secret',json.dumps(c))
        self.assertEqual(review_lookups(source(),c)['state'],'unknown')

    def test_bad_account_count_stops(self):
        op=FakeOpener([GENESIS['devnet'],{'context':{'slot':1},'value':[]}])
        c=collect_lookups(source(),op); self.assertEqual(len(op.calls),2)
        self.assertEqual(c['evidence']['accounts']['state'],'invalid-account-response')

    def test_old_client_still_rejects_accounts_and_lookup_rejects_send(self):
        for client,method in [(Client('devnet'), 'getMultipleAccounts'),(LookupClient('devnet'),'sendTransaction')]:
            with self.assertRaises(ValueError): client.request(method,[])
        op=FakeOpener([GENESIS['devnet']]*3); client=LookupClient('devnet',op)
        for _ in range(3): client.request('getGenesisHash',[])
        with self.assertRaises(ValueError): client.request('getGenesisHash',[])

    def test_cli_replay_private_output_and_no_overwrite(self):
        s,c=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json'; out=Path(tmp)/'output.json.gz'
            p.write_text(json.dumps({'format':'lookup-report-1','sourceCapture':s,'lookupCapture':c}))
            args=[sys.executable,str(ROOT/'lookup_cli.py'),'--replay',str(p),'--output',str(out)]
            subprocess.run(args,check=True,capture_output=True)
            result=json.load(gzip.open(out,'rt'))
            self.assertEqual(result['currentRunNetworkRequests'],0); self.assertEqual(out.stat().st_mode & 0o777,0o600)
            self.assertEqual(result['review'],review_lookups(s,c))
            self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)

if __name__=='__main__': unittest.main()
