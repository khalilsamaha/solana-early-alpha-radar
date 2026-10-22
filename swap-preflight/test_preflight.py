import base64
import copy
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from preflight import audit,_review,split_capture,flags,BASELINE,GENESIS,digest
from preflight_checks import fixture,edit,run,NOW,fake_key,decode
from preflight_capture import collect,_collect,PreflightClient
from preflight_cli import read,MAX_REPORT
from contract import decode_wire
from program import MAX_BASE64


def replies(c):
    names=['genesisBefore','programBootstrap','poolBootstrap','accounts','blockTime']
    if c['packet'] is not None:names+=['blockhash','fee']
    names+=['genesisAfter']
    return [copy.deepcopy(c['evidence'][n]['result']) for n in names]


class Opener:
    def __init__(self,responses):self.responses=list(responses);self.calls=[]
    def open(self,request,timeout):
        body=json.loads(request.data);self.calls.append((request,body,timeout))
        value=self.responses.pop(0)
        if isinstance(value,Exception):raise value
        return io.BytesIO(json.dumps({'jsonrpc':'2.0','id':body['id'],'result':value}).encode())


class PreflightTests(unittest.TestCase):
    def blocked(self,c,b,reason=None,at=NOW):
        r=_review(c,b,at)
        self.assertNotIn(r['state'],('pinned-pool-snapshot','preflight-evidence-consistent'),r)
        if reason:self.assertEqual(r['reason'],reason)
        for k,v in flags().items():self.assertEqual(r[k],v)
        return r

    def test_fifteen_host_cases(self):
        r=run();self.assertEqual(r['casesPassed'],15);self.assertEqual(r['networkRequests'],0)
        self.assertTrue(r['syntheticBaselineUsed'])

    def test_packet_and_pool_have_distinct_results_without_authorization(self):
        for packet in (True,False):
            c,b=fixture(packet);before=copy.deepcopy(c);r=_review(c,b,NOW)
            self.assertEqual(r['state'],'preflight-evidence-consistent' if packet else 'pinned-pool-snapshot')
            self.assertEqual(r['walletAndFeeChecked'],packet)
            for k,v in flags().items():self.assertEqual(r[k],v)
            self.assertEqual(before,c)

    def test_default_audit_never_uses_caller_baseline_or_review(self):
        c,b=fixture();c['baseline']=b;c['review']={'signingApproved':True};c['baselineSha256']=digest(BASELINE)
        self.assertNotIn(audit(c,now_ms=NOW)['state'],('pinned-pool-snapshot','preflight-evidence-consistent'))

    def test_both_subreaders_share_one_batch(self):
        c,b=fixture();s,p=split_capture(c)
        self.assertIs(s['evidence']['accounts']['result']['value'][7],p['evidence']['accounts']['result']['value'][0])
        self.assertEqual(s['evidence']['accounts']['result']['context'],p['evidence']['accounts']['result']['context'])
        self.assertEqual(s['packet'],c['packet'])

    def test_wrong_key_count_order_and_program_pointer(self):
        for mode in ('extra','missing','reorder','pointer'):
            c,b=fixture()
            if mode=='extra':c['accountKeys'].append(fake_key('extra'))
            if mode=='missing':c['accountKeys'].pop()
            if mode=='reorder':c['accountKeys'][2:4]=reversed(c['accountKeys'][2:4])
            if mode=='pointer':edit(c,7,4,decode(fake_key('new-data')))
            self.blocked(c,b)

    def test_missing_accounts_never_zero_filled(self):
        for index in range(12):
            c,b=fixture();c['evidence']['accounts']['result']['value'][index]=None;self.blocked(c,b)

    def test_deployment_bytes_authority_and_redeployment_block(self):
        for offset,value in ((120,b'\x01'),(13,decode(fake_key('new-auth'))),(4,(100).to_bytes(8,'little'))):
            c,b=fixture();self.blocked(edit(c,-1,offset,value),b,'deployment-differs-from-pinned-observation')

    def test_baseline_slot_and_time_lower_bounds(self):
        c,b=fixture();b['observedSlot']=102;self.blocked(c,b,'capture-predates-baseline')
        c,b=fixture();b['observedAtMs']=NOW;self.blocked(c,b,'capture-predates-baseline')

    def test_bootstrap_order_cannot_regress(self):
        c,b=fixture();c['evidence']['programBootstrap']['result']['context']['slot']=101
        self.blocked(c,b,'bootstrap-slot-regression')

    def test_snapshot_must_not_regress_from_pool_bootstrap(self):
        c,b=fixture();c['evidence']['poolBootstrap']['result']['context']['slot']=102
        self.blocked(c,b,'snapshot-slot-regression')

    def test_finished_recent_does_not_refresh_old_accounts(self):
        c,b=fixture(False);c['finishedAtMs']=NOW+11000
        self.blocked(c,b,'account-evidence-stale',NOW+11000)

    def test_account_timestamp_required_and_bounded(self):
        for value in (None,True,NOW+1,NOW-501):
            c,b=fixture();c['evidence']['accounts']['receivedAtMs']=value
            self.blocked(c,b,'account-observation-clock')

    def test_message_timestamp_cannot_precede_accounts_or_follow_finish(self):
        for field in ('fee','blockhash'):
            for at in (None,NOW-1,NOW+1,True):
                c,b=fixture();c['evidence'][field]['receivedAtMs']=at
                self.blocked(c,b,'message-evidence-clock')

    def test_freshness_and_policy_boundaries_are_exclusive(self):
        c,b=fixture(False)
        self.assertEqual(_review(c,b,NOW+10000)['state'],'pinned-pool-snapshot')
        self.blocked(c,b,'evidence-stale-or-future',NOW+10001)
        c,b=fixture();c['packet']['policy']['expiresAtMs']=NOW+1
        self.assertEqual(_review(c,b,NOW)['validUntilExclusiveMs'],NOW+1)
        self.blocked(c,b,'packet-expired-or-invalid-at-review',NOW+1)

    def test_fee_and_blockhash_contexts_and_message_binding(self):
        for field in ('fee','blockhash'):
            c,b=fixture();c['evidence'][field]['result']['context']['slot']=100;self.blocked(c,b)
        c,b=fixture();c['messageSha256']='0'*64;self.blocked(c,b,'pool-check-capture-message-binding')

    def test_pool_blockers_and_mint_authority_are_separate(self):
        c,b=fixture();self.blocked(edit(c,0,329,b'\x04'),b,'pool-eligibility-blocked')
        c,b=fixture();edit(c,2,0,b'\x01\0\0\0');edit(c,2,4,decode(fake_key('mint-authority')))
        r=_review(c,b,NOW);self.assertEqual(r['state'],'preflight-evidence-consistent')
        self.assertIn('mint-authority-present',r['riskObservations']);self.assertFalse(r['simulationApproved'])

    def test_stopped_capture_cannot_pass_from_remaining_good_fields(self):
        c,b=fixture();c['stoppedReason']='interrupted';self.blocked(c,b,'capture-incomplete')

    def test_transport_pool_six_requests_packet_eight(self):
        for with_packet in (True,False):
            c,b=fixture(with_packet);opener=Opener(replies(c));b['kind']='observed-devnet-deployment'
            capture=_collect(packet=c['packet'] if with_packet else None,pool=c['pool'] if not with_packet else None,
                             opener=opener,now=lambda:NOW,baseline=b)
            self.assertNotIn('stoppedReason',capture)
            self.assertEqual(len(opener.calls),8 if with_packet else 6)
            self.assertEqual(_review(capture,b,NOW)['state'],'preflight-evidence-consistent' if with_packet else 'pinned-pool-snapshot')
            batch=opener.calls[3][1]
            self.assertEqual(batch['method'],'getMultipleAccounts')
            self.assertEqual(batch['params'][0],c['accountKeys'])
            self.assertEqual(batch['params'][1]['minContextSlot'],100)
            for request,body,timeout in opener.calls:
                self.assertEqual(request.full_url,'https://api.devnet.solana.com')
                self.assertEqual(timeout,10);self.assertNotIn('Authorization',request.headers)
                self.assertIn(body['method'],PreflightClient.METHODS)
            if with_packet:
                fee=opener.calls[6][1]
                self.assertEqual(base64.b64decode(fee['params'][0]),decode_wire(c['packet']['unsignedTransactionBase64'])[1])

    def test_live_collection_stops_before_fee_reads_on_code_drift(self):
        c,b=fixture();edit(c,-1,120,b'\x01');opener=Opener(replies(c))
        r=_collect(packet=c['packet'],opener=opener,now=lambda:NOW,baseline=b)
        self.assertEqual(r['stoppedReason'],'deployment-differs-from-pinned-observation')
        self.assertEqual(len(opener.calls),4)

    def test_each_transport_failure_stops_without_retry(self):
        c,b=fixture()
        for i in range(8):
            values=replies(c);values[i]=urllib.error.URLError('private provider detail');opener=Opener(values)
            r=_collect(packet=c['packet'],opener=opener,now=lambda:NOW,baseline=b)
            self.assertEqual(r['rpcRequestsAttempted'],i+1);self.assertIn('stoppedReason',r)
            self.assertNotIn('private provider detail',json.dumps(r))

    def test_rate_limit_is_visible_without_retry(self):
        c,b=fixture();opener=Opener([urllib.error.HTTPError('url',429,'private',{},None)])
        r=_collect(packet=c['packet'],opener=opener,now=lambda:NOW,baseline=b)
        self.assertEqual(r['rpcRequestsAttempted'],1)
        self.assertEqual(r['evidence']['genesisBefore']['httpStatus'],429)

    def test_stale_packet_stops_before_network(self):
        c,b=fixture();opener=Opener([])
        with self.assertRaises(ValueError):_collect(packet=c['packet'],opener=opener,now=lambda:NOW+15000,baseline=b)
        self.assertEqual(len(opener.calls),0)

    def test_packet_expiring_in_capture_is_not_refreshed(self):
        c,b=fixture();calls=iter([NOW,NOW,NOW,NOW+15000,NOW+15000]);opener=Opener(replies(c))
        r=_collect(packet=c['packet'],opener=opener,now=lambda:next(calls),baseline=b)
        self.assertEqual(r['rpcRequestsAttempted'],1)
        self.assertEqual(r['stoppedReason'],'packet-expired-during-capture')
        self.assertEqual(r['packet'],c['packet'])

    def test_caller_mutation_cannot_change_frozen_packet_or_baseline(self):
        c,b=fixture();original=copy.deepcopy(c['packet']);base=copy.deepcopy(b)
        class Mutator(Opener):
            def open(self,request,timeout):
                c['packet']['policy']['amountIn']='999';b['identity']['payloadSha256']='0'*64
                return super().open(request,timeout)
        opener=Mutator(replies(c))
        r=_collect(packet=c['packet'],opener=opener,now=lambda:NOW,baseline=b)
        self.assertNotIn('stoppedReason',r);self.assertEqual(r['packet'],original)
        base['kind']='observed-devnet-deployment';self.assertEqual(_review(r,base,NOW)['state'],'preflight-evidence-consistent')

    def test_monotonic_capture_budget(self):
        c,b=fixture(False);ticks=iter([0,0,31]);opener=Opener(replies(c))
        r=_collect(pool=c['pool'],opener=opener,now=lambda:NOW,monotonic=lambda:next(ticks),baseline=b)
        self.assertEqual(r['rpcRequestsAttempted'],1);self.assertEqual(r['stoppedReason'],'capture-time-budget')

    def test_method_batch_and_full_program_byte_caps(self):
        client=PreflightClient(Opener([]))
        for method in ('sendTransaction','simulateTransaction','requestAirdrop'):
            with self.assertRaises(ValueError):client.request(method,[])
        with self.assertRaises(ValueError):client.request('getMultipleAccounts',[['a']*13,{}])
        c,b=fixture();c['evidence']['accounts']['result']['value'][-1]['data'][0]='A'*(MAX_BASE64+1)
        r=_collect(packet=c['packet'],opener=Opener(replies(c)),now=lambda:NOW,baseline=b)
        self.assertEqual(r['evidence']['accounts']['state'],'invalid-preflight-response')
        self.assertEqual(r['rpcRequestsAttempted'],4)

    def test_cli_default_selfcheck_no_network_and_exclusive_private_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'check.json.gz'
            subprocess.run([sys.executable,'preflight_cli.py','--output',str(output)],check=True,capture_output=True)
            r=json.loads(gzip.decompress(output.read_bytes()));r.pop('capturedAt');self.assertEqual(r,run())
            self.assertEqual(output.stat().st_mode&0o777,0o600)
            again=subprocess.run([sys.executable,'preflight_cli.py','--output',str(output)],capture_output=True)
            self.assertNotEqual(again.returncode,0)

    def test_cli_replay_recomputes_and_never_trusts_embedded_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input.json';output=root/'report.json.gz';c,b=fixture()
            source.write_text(json.dumps({'format':'swap-preflight-report-1','capture':c,'baseline':b,
                                          'review':{'state':'preflight-evidence-consistent','signingApproved':True}}))
            subprocess.run([sys.executable,'preflight_cli.py','--input',str(source),'--output',str(output)],check=True,capture_output=True)
            r=json.loads(gzip.decompress(output.read_bytes()))
            self.assertTrue(r['replayOnly']);self.assertEqual(r['currentRunNetworkRequests'],0)
            self.assertEqual(r['review'],audit(c,now_ms=NOW));self.assertEqual(r['capture']['finishedAtMs'],NOW)
            self.assertFalse(r['signingApproved'])

    def test_cli_input_caps_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.gz';p.write_bytes(gzip.compress(b' '*(MAX_REPORT+1)))
            with self.assertRaises(ValueError):read(p)
            p.write_bytes(gzip.compress(b'{"a":1,"a":2}'))
            with self.assertRaises(ValueError):read(p)


if __name__=='__main__':unittest.main()
