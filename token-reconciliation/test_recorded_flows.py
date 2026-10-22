import copy
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recorded_flows import analyze
from token_capture_checks import capture, sync_meta, self_check
from recorded_capture import collect, TOKEN, SYSTEM, GENESIS, Client
from wire import b58

ROOT=Path(__file__).resolve().parent


def meta(c):return c['evidence']['transactionJson']['result']['meta']
def ops(c):return meta(c)['innerInstructions'][0]['instructions']


class Opener:
    def __init__(self,c,discovery=True):
        e=c['evidence'];self.calls=[]
        self.values=[GENESIS['devnet']]+([[
            {'signature':c['signature'],'slot':100,'err':None,'confirmationStatus':'finalized','memo':'omit-me'}]] if discovery else [])
        self.values += [e[k]['result'] for k in ('transactionJson','transactionBase64','signatureStatus')]+[GENESIS['devnet']]
    def open(self,request,timeout):
        p=json.loads(request.data);self.calls.append(p);value=self.values[len(self.calls)-1]
        return io.BytesIO(json.dumps({'jsonrpc':'2.0','id':p['id'],'result':value}).encode())


class RecordedTests(unittest.TestCase):
    def check(self,c,state,reason=None):
        sync_meta(c);r=analyze(c)
        self.assertEqual(r['state'],state,r)
        if reason:self.assertEqual(r['reason'],reason)
        for key in ('intentProven','executionApproved','resubmitAllowed','productionLedgerUpdated'):
            self.assertIs(r[key],False)
        self.assertEqual(r['reviewNetworkRequests'],0)
        return r

    def test_eleven_case_selfcheck(self):self.assertEqual(self_check()['casesPassed'],11)

    def test_existing_movements_do_not_reconstruct_trade_intent(self):
        c=capture();before=copy.deepcopy(c)
        with patch('socket.socket',side_effect=AssertionError('no network')):
            r=analyze(c)
        self.assertEqual(r['state'],'recorded-token-flows-consistent')
        self.assertEqual(len(r['transfers']),2)
        self.assertEqual(r['transfers'][0]['amountAtomic'],'100')
        self.assertNotIn('intent',r);self.assertNotIn('profit',r)
        self.assertEqual(c,before)

    def test_creation_and_closure_native_ledger(self):
        r=self.check(capture('create'),'recorded-token-flows-consistent')
        self.assertEqual(r['accountFunding'][0]['lamports'],'2039280')
        self.assertEqual(sum(a['lifecycle']=='created' for a in r['accounts']),1)
        r=self.check(capture('close'),'recorded-token-flows-consistent')
        self.assertEqual(r['accountRefunds'][0]['lamports'],'2039280')
        closed=[a for a in r['accounts'] if a['lifecycle']=='closed'][0]
        self.assertIsNone(closed['postAtomic']) # absence remains absence in exported raw endpoints

    def test_wrapped_native_transfer_lamports_move_with_tokens(self):
        for side in ('source','destination'):
            self.check(capture('wsol-'+side),'recorded-token-flows-consistent')
            c=capture('wsol-'+side);meta(c)['postBalances'][1 if side=='source' else 2]+=1
            self.check(c,'mismatch','wrapped-native-backing-mismatch')

    def test_wrong_amount_and_underflow(self):
        for amount,reason in ((101,'transfer-flow-balance-mismatch'),(1001,'transfer-intermediate-underflow')):
            c=capture();ops(c)[0]['data']=b58(bytes([3])+amount.to_bytes(8,'little'))
            self.check(c,'mismatch',reason)

    def test_split_transfers_and_order_preserved(self):
        c=capture();rows=ops(c);first=copy.deepcopy(rows[0]);second=copy.deepcopy(first)
        first['data']=b58(bytes([3])+(40).to_bytes(8,'little'));second['data']=b58(bytes([3])+(60).to_bytes(8,'little'))
        rows[:1]=[first,second]
        r=self.check(c,'recorded-token-flows-consistent')
        self.assertEqual([x['amountAtomic'] for x in r['transfers']],['40','60','200'])

    def test_initialize_before_creation_or_transfer_before_initialize(self):
        c=capture('create');rows=ops(c);rows[0],rows[1]=rows[1],rows[0]
        self.check(c,'unknown','initialization-without-unique-creation')
        c=capture('create');rows=ops(c);rows[1],rows[3]=rows[3],rows[1]
        self.check(c,'unknown','transfer-account-not-initialized-or-recorded')

    def test_create_wrong_owner_space_and_funding(self):
        for position in (4,12,20):
            from reconcile import decode
            c=capture('create');data=bytearray(decode(ops(c)[0]['data']));data[position]^=1
            ops(c)[0]['data']=b58(data)
            self.check(c,'mismatch')

    def test_missing_and_duplicate_lifecycle_operations(self):
        c=capture('create');ops(c).pop(1)
        self.check(c,'unknown')
        c=capture('create');ops(c).insert(1,copy.deepcopy(ops(c)[0]))
        self.check(c,'unknown','unproved-or-repeated-creation')
        c=capture('close');ops(c).pop()
        self.check(c,'unknown','closure-evidence-incomplete')
        c=capture('close');rows=ops(c);rows.insert(0,rows.pop())
        self.check(c,'mismatch','closure-balance-mismatch')

    def test_closure_wrong_authority_recipient_and_refund(self):
        c=capture('close');ops(c)[-1]['accounts'][-1]=5
        self.check(c,'unsupported','close-authority-not-supported')
        c=capture('close');ops(c)[-1]['accounts'][1]=11
        self.check(c,'mismatch','unexplained-native-balance-change')
        c=capture('close');meta(c)['postBalances'][0]-=1
        self.check(c,'mismatch','unexplained-native-balance-change')

    def test_missing_counterparty_and_owner_change(self):
        c=capture()
        for field in ('preTokenBalances','postTokenBalances'):meta(c)[field]=[r for r in meta(c)[field] if r['accountIndex']!=3]
        self.check(c,'unknown','transfer-account-not-initialized-or-recorded')
        c=capture();meta(c)['postTokenBalances'][0]['owner']=meta(c)['postTokenBalances'][2]['owner']
        self.check(c,'mismatch','token-identity-changed')

    def test_checked_transfer_mint_decimals_and_authority(self):
        c=capture();ops(c)[0].update(accounts=[1,6,3,0],data=b58(bytes([12])+(100).to_bytes(8,'little')+bytes([6])))
        self.check(c,'recorded-token-flows-consistent')
        wrong=copy.deepcopy(c);ops(wrong)[0]['accounts'][1]=7
        self.check(wrong,'mismatch','checked-transfer-identity-mismatch')
        wrong=copy.deepcopy(c);ops(wrong)[0]['accounts'][-1]=5
        self.check(wrong,'unsupported','transfer-authority-not-supported')
        wrong=copy.deepcopy(c);ops(wrong)[0]['data']=b58(bytes([12])+(100).to_bytes(8,'little')+bytes([9]))
        self.check(wrong,'mismatch','checked-transfer-identity-mismatch')

    def test_failed_transaction_must_not_replay_attempted_transfers(self):
        c=capture('failed');meta(c)['innerInstructions']=meta(capture())['innerInstructions']
        r=self.check(c,'recorded-failure-fee-only');self.assertNotIn('transfers',r)
        meta(c)['postTokenBalances'][0]['uiTokenAmount']['amount']='999'
        self.check(c,'mismatch','failed-transaction-token-change')
        c=capture('failed');meta(c)['postBalances'][3]+=1
        self.check(c,'mismatch','failed-transaction-not-fee-only')

    def test_unavailable_evidence_is_not_empty(self):
        c=capture();meta(c)['innerInstructions']=None
        self.check(c,'unknown')
        c=capture();del meta(c)['postTokenBalances']
        self.check(c,'unknown')
        c=capture();meta(c)['preTokenBalances']=[];meta(c)['postTokenBalances']=[]
        self.check(c,'unknown','no-recorded-token-accounts')

    def test_other_token_operations_and_programs_unsupported(self):
        for tag in (4,7,8,14,15,17,22):
            c=capture();ops(c).append({'programIdIndex':8,'accounts':[1], 'data':b58(bytes([tag]))})
            self.check(c,'unsupported','unsupported-token-instruction')
        c=capture()
        for field in ('preTokenBalances','postTokenBalances'):meta(c)[field][0]['programId']='TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'
        self.check(c,'unsupported','token-program-not-supported')

    def test_unaccounted_native_balance_any_account_fails(self):
        for index in (0,1,4,11):
            c=capture();meta(c)['postBalances'][index]+=1
            self.check(c,'mismatch','unexplained-native-balance-change')

    def test_missing_signature_or_cross_encoding_change_is_not_accounting_pass(self):
        c=capture();c['evidence']['transactionBase64']['result']['meta']['fee']+=1
        self.assertEqual(analyze(c)['reason'],'cross-encoding-metadata-disagreement')
        c=capture();c['evidence']['signatureStatus']['result']['value']=[None]
        self.assertEqual(analyze(c)['state'],'unknown')

    def test_real_public_lookup_fixture_remains_blocked(self):
        c=json.loads((ROOT.parent/'recorded-chain/devnet-two-table-fixture.json').read_text())
        r=analyze(c)
        self.assertEqual(r['state'],'unsupported');self.assertEqual(r['reason'],'historical-lookup-resolution-unproven')
        self.assertTrue(r['identity']['signatureVerified']);self.assertFalse(r['intentProven'])

    def test_actual_host_token_capture_replays_without_network(self):
        c=json.loads((ROOT/'devnet-token-fixture.json').read_text())
        with patch('socket.socket',side_effect=AssertionError('offline fixture')):
            r=analyze(c)
        self.assertEqual(r['state'],'recorded-token-flows-consistent')
        self.assertEqual(r['identity']['captureSha256'],'b371549550e88146ee057c98a766005a46b9e96735b78db2ae27ef6376ce5153')
        self.assertEqual(r['identity']['requiredSignatures'],2)
        self.assertEqual(r['identity']['slot'],512559524)
        self.assertEqual(r['feeLamports'],'10000')
        self.assertEqual([x['amountAtomic'] for x in r['transfers']],['10'])
        self.assertEqual(r['accountFunding'],[]);self.assertEqual(r['accountRefunds'],[])

    def test_sample_one_token_program_signature_six_reads(self):
        opener=Opener(capture());c=collect(sample=True,opener=opener,sample_program=TOKEN)
        self.assertEqual(c['rpcRequestsAttempted'],6)
        self.assertEqual(c['selection'],'recent-token-program-devnet')
        self.assertEqual(opener.calls[1]['params'],[TOKEN,{'limit':1,'commitment':'finalized'}])
        self.assertNotIn('omit-me',json.dumps(c))
        self.assertEqual(analyze(c)['state'],'recorded-token-flows-consistent')
        self.assertNotIn('sendTransaction',[x['method'] for x in opener.calls])

    def test_original_system_discovery_and_explicit_signature_unchanged(self):
        for sampled in (True,False):
            c=capture();opener=Opener(c,discovery=sampled)
            out=collect(signature=None if sampled else c['signature'],sample=sampled,opener=opener)
            self.assertEqual(out['rpcRequestsAttempted'],6 if sampled else 5)
            self.assertEqual(out['selection'],'recent-system-program-devnet' if sampled else 'explicit-signature')

    def test_wrong_cluster_discovery_never_continues(self):
        opener=Opener(capture());opener.values[0]=GENESIS['mainnet-beta']
        c=collect(sample=True,opener=opener,sample_program=TOKEN)
        self.assertEqual(c['rpcRequestsAttempted'],1)
        self.assertEqual(analyze(c)['state'],'mismatch')
        self.assertEqual(analyze(c)['reason'],'network-genesis-mismatch')

    def test_invalid_sample_program_fails_before_network(self):
        opener=Opener(capture())
        for args in ({'sample':True,'sample_program':'bad'}, {'signature':capture()['signature'],'sample_program':TOKEN}):
            with self.assertRaises(ValueError):collect(opener=opener,**args)
        self.assertEqual(opener.calls,[])

    def test_no_resampling_after_unsupported_selected_transaction(self):
        c=capture();ops(c).append({'programIdIndex':8,'accounts':[1], 'data':b58(bytes([7]))});sync_meta(c)
        opener=Opener(c);out=collect(sample=True,opener=opener,sample_program=TOKEN)
        self.assertEqual(analyze(out)['state'],'unsupported')
        self.assertEqual(sum(x['method']=='getSignaturesForAddress' for x in opener.calls),1)

    def test_cli_offline_report_replay_and_private_output(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);c=capture();source=path/'input.json.gz';source.write_bytes(gzip.compress(json.dumps(c).encode()))
            out=path/'report.json.gz'
            cmd=[sys.executable,str(ROOT/'capture_cli.py'),'--input',str(source),'--output',str(out)]
            p=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
            r=json.load(gzip.open(out));self.assertEqual(r['review'],analyze(c));self.assertEqual(r['currentRunNetworkRequests'],0)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            replay=path/'replay.json.gz';cmd[3]=str(out);cmd[5]=str(replay)
            self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(json.load(gzip.open(replay))['review'],r['review'])

    def test_cli_default_selfcheck_and_invalid_modes(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out.json.gz';cmd=[sys.executable,str(ROOT/'capture_cli.py'),'--output',str(out)]
            p=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.load(gzip.open(out))['casesPassed'],11)
            p=subprocess.run(cmd+['--sample-devnet','--network','devnet'],capture_output=True)
            self.assertNotEqual(p.returncode,0)


if __name__=='__main__':unittest.main()
