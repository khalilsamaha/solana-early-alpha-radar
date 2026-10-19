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
from state import (audit,account,decode_pool,discover_pool,StateError,GENESIS,PROGRAM,TOKEN,LOADER,AUTHORITY,NATIVE,
                   decode,b58,U64)
from state_fixtures import fixture,change_row,fake_key,NOW,received
from state_checks import run
from state_capture import collect,StateClient
from contract import decode_wire


def rows(c):return c['evidence']['accounts']['result']['value']


class FakeOpener:
    def __init__(self,responses):self.responses=list(responses);self.calls=[]
    def open(self,request,timeout):
        body=json.loads(request.data);self.calls.append((request,body,timeout))
        value=self.responses.pop(0)
        if isinstance(value,Exception):raise value
        return io.BytesIO(json.dumps({'jsonrpc':'2.0','id':body['id'],'result':value}).encode())


def replies(c,packet=False):
    names=['genesisBefore','bootstrap','accounts','blockTime']
    if packet:names+=['blockhash','fee']
    names+=['genesisAfter']
    return [copy.deepcopy(c['evidence'][n]['result']) for n in names]


def discovery(c):
    packet=fixture(with_packet=True)['packet']
    tx=decode_wire(packet['unsignedTransactionBase64'])[4];tx['slot']=100
    tx['meta'].update(err=None,innerInstructions=[])
    found=[{'signature':tx['transaction']['signatures'][0],'slot':100,'err':None,'confirmationStatus':'finalized'}]
    return found,tx


class StateTests(unittest.TestCase):
    def blocked(self,c,reason=None):
        r=audit(c)
        self.assertNotIn(r['state'],('pool-state-consistent','policy-state-consistent'),r)
        if reason:self.assertEqual(r['reason'],reason)
        self.assertFalse(r['signingApproved']);self.assertFalse(r['executionApproved'])
        return r

    def test_pool_packet_reverse_and_native_read_only(self):
        for options in ({},{'with_packet':True},{'with_packet':True,'reverse':True},{'native':True}):
            c=fixture(**options);original=copy.deepcopy(c);r=audit(c)
            self.assertEqual(r['state'],'policy-state-consistent' if options.get('with_packet') else 'pool-state-consistent')
            self.assertTrue(r['poolRelationsMatched']);self.assertEqual(c,original)
            for name in ('signingApproved','executionApproved','simulationVerified','deployedBinaryVerified',
                         'historicalStateProven','independentConsensusVerified','signatureVerified','priorPolicyProven'):
                self.assertIs(r[name],False)

    def test_fixed_authority_and_bump_not_caller_selected(self):
        self.assertEqual(audit(fixture())['authority'],AUTHORITY)
        for bump in (0,254):self.blocked(change_row(fixture(),0,328,bytes([bump])),'pool-authority-bump')

    def test_every_account_owner_and_executable_checked(self):
        for i in range(11):
            c=fixture(with_packet=True);rows(c)[i]['owner']=fake_key('wrong-owner');self.blocked(c,'account-owner-or-executable')
            c=fixture(with_packet=True);rows(c)[i]['executable']=not rows(c)[i]['executable'];self.blocked(c,'account-owner-or-executable')

    def test_missing_accounts_not_zero_balances(self):
        for i in range(11):
            c=fixture(with_packet=True);rows(c)[i]=None;self.blocked(c,'account-unavailable')

    def test_all_account_lengths_and_base64_are_strict(self):
        for i in range(11):
            c=fixture(with_packet=True);row=rows(c)[i]
            row['data'][0]=base64.b64encode(base64.b64decode(row['data'][0])+b'\0').decode()
            self.blocked(c,'account-layout-size')
        for value in (['!','base64'],['A'*6001,'base64'],['','base64+zstd'],{},None):
            c=fixture();rows(c)[0]['data']=value;self.blocked(c)

    def test_discriminators_pool_config_observation(self):
        for i in (0,1,6):self.blocked(change_row(fixture(),i,0,b'\0'*8),'account-discriminator')

    def test_pool_token_program_and_role_alias_rejected(self):
        self.blocked(change_row(fixture(),0,8+7*32,decode(fake_key('token2022'))),'token-program-unsupported')
        self.blocked(change_row(fixture(),0,8+3*32,decode(fake_key('inputVault'))),'pool-role-alias')

    def test_pool_discovery_and_batch_binding_must_agree(self):
        self.blocked(change_row(fixture(),0,8,decode(fake_key('new-config'))),'pool-bindings-changed')
        c=fixture();c['accountKeys'][2]=fake_key('another-mint');self.blocked(c,'snapshot-key-binding')

    def test_genesis_before_and_after(self):
        for name in ('genesisBefore','genesisAfter'):
            c=fixture();c['evidence'][name]['result']=GENESIS['mainnet-beta'];self.blocked(c,'wrong-cluster')

    def test_slots_shape_order_and_block_time(self):
        c=fixture();c['evidence']['accounts']['result']['context']['slot']=99;self.blocked(c,'snapshot-slot-regression')
        for value in (None,True,0,-1,1.5):
            c=fixture();c['evidence']['accounts']['result']['context']['slot']=value;self.blocked(c,'snapshot-shape')
        c=fixture();c['blockTimeSlot']=102;self.blocked(c,'block-time-slot-binding')
        c=fixture();c['evidence']['blockTime']['result']=None;self.blocked(c,'block-time-unavailable')

    def test_capture_time_shape_and_budget(self):
        for value in (NOW-501,NOW+45000,True,'bad'):
            c=fixture();c['finishedAtMs']=value;self.blocked(c,'capture-time-window')

    def test_mint_initialization_coptions_and_decimals(self):
        for i in (2,3):
            self.blocked(change_row(fixture(),i,45,b'\0'),'mint-uninitialized-or-invalid')
            self.blocked(change_row(fixture(),i,0,(2).to_bytes(4,'little')),'invalid-coption')
            self.blocked(change_row(fixture(),i,44,b'\x09'),'pool-mint-decimals')

    def test_vault_mints_owners_states(self):
        for i in (4,5):
            for offset in (0,32):self.blocked(change_row(fixture(),i,offset,decode(fake_key('wrong'))),'token-mint-or-authority')
            for state in (0,2,3):self.blocked(change_row(fixture(),i,108,bytes([state])),'token-uninitialized-frozen-or-invalid')

    def test_native_backing_is_checked_without_enabling_native_swap(self):
        c=fixture(native=True);rows(c)[4]['lamports']=1;self.blocked(c,'native-vault-backing')
        self.blocked(change_row(fixture(native=True),4,109,bytes(4)),'native-vault-backing')
        self.blocked(change_row(fixture(),4,109,(1).to_bytes(4,'little')),'unexpected-native-token')
        c=fixture(native=True);rows(c)[4]['lamports']+=7
        self.assertEqual(audit(c)['vaults'][0]['nativeSurplus'],'7')
        c=change_row(fixture(native=True),2,44,b'\x06');change_row(c,0,331,b'\x06')
        self.blocked(c,'native-mint-decimals')

    def test_coption_tags_in_token_accounts(self):
        for offset in (72,109,129):self.blocked(change_row(fixture(),4,offset,(2).to_bytes(4,'little')),'invalid-coption')

    def test_accrued_fees_and_supply_not_silently_clamped(self):
        self.blocked(change_row(fixture(),0,341,(10001).to_bytes(8,'little')),'vault-accrued-fees-exceed-balance')
        self.blocked(change_row(fixture(),2,36,(9999).to_bytes(8,'little')),'vault-balance-exceeds-mint-supply')
        c=change_row(fixture(),0,341,(123).to_bytes(8,'little'))
        self.assertEqual(audit(c)['effectiveReservesAtomic'],['9877','10000'])

    def test_pool_blockers_remain_visible_in_consistent_data(self):
        cases=[(0,329,b'\x04','pool-swaps-disabled'),
               (0,373,(NOW//1000+1).to_bytes(8,'little'),'pool-not-open-at-snapshot-time'),
               (4,64,bytes(8),'empty-effective-reserve'),
               (2,46,(1).to_bytes(4,'little')+decode(fake_key('freeze')),'mint-freeze-authority-present'),
               (4,72,(1).to_bytes(4,'little')+decode(fake_key('delegate')),'vault-delegate-or-close-authority')]
        for i,offset,data,blocker in cases:
            r=audit(change_row(fixture(),i,offset,data));self.assertEqual(r['state'],'pool-state-consistent')
            self.assertIn(blocker,r['eligibilityBlockers']);self.assertFalse(r['executionApproved'])

    def test_unknown_status_or_creator_fee_layout_rejected(self):
        for offset,value in ((329,8),(389,3),(390,2)):
            self.blocked(change_row(fixture(),0,offset,bytes([value])),'pool-status-or-fee-layout')

    def test_config_rates_and_layout(self):
        for offset,value in ((12,1000000),(108,1000000),(116,1000001),(20,1000000)):
            self.blocked(change_row(fixture(),1,offset,value.to_bytes(8,'little')),'config-fee-range')

    def test_observation_pool_index_and_program_pointer(self):
        self.blocked(change_row(fixture(),6,11,decode(fake_key('other-pool'))),'observation-pool-binding')
        self.blocked(change_row(fixture(),6,9,(100).to_bytes(2,'little')),'observation-pool-binding')
        self.blocked(change_row(fixture(),7,0,(3).to_bytes(4,'little')),'program-account-layout')

    def test_wallet_roles_balances_and_options(self):
        self.blocked(change_row(fixture(with_packet=True),9,32,decode(fake_key('attacker'))),'token-mint-or-authority')
        self.blocked(change_row(fixture(with_packet=True),10,0,decode(fake_key('inputMint'))),'token-mint-or-authority')
        self.blocked(change_row(fixture(with_packet=True),9,64,(99).to_bytes(8,'little')),'insufficient-source-balance')
        c=fixture(with_packet=True);rows(c)[8]['lamports']=5999;self.blocked(c,'insufficient-native-fee-balance')
        self.blocked(change_row(fixture(with_packet=True),10,129,(1).to_bytes(4,'little')+decode(fake_key('close'))),'wallet-authority-options')

    def test_destination_overflow_and_output_reserve(self):
        self.blocked(change_row(fixture(with_packet=True),10,64,U64.to_bytes(8,'little')),'destination-minimum-overflow')
        self.blocked(change_row(fixture(with_packet=True),5,64,(189).to_bytes(8,'little')),'insufficient-output-reserve-for-minimum')

    def test_packet_cannot_be_swapped_or_expired(self):
        c=fixture(with_packet=True);c['packet']['policy']['amountIn']='101';self.blocked(c,'instruction-policy-not-current')
        c=fixture(with_packet=True);c['finishedAtMs']=NOW+14000;self.blocked(c,'instruction-policy-not-current')
        c=fixture(with_packet=True);c['messageSha256']='0'*64;self.blocked(c,'capture-message-binding')

    def test_exact_rpc_fee_and_blockhash_context(self):
        c=fixture(with_packet=True);c['evidence']['blockhash']['result']['value']=False;self.blocked(c,'blockhash-not-valid-at-capture')
        c=fixture(with_packet=True);c['evidence']['fee']['result']['value']=None;self.blocked(c,'message-fee-unavailable')
        c=fixture(with_packet=True);c['evidence']['fee']['result']['value']=5002;self.blocked(c,'rpc-message-fee-mismatch')
        for name in ('fee','blockhash'):
            c=fixture(with_packet=True);c['evidence'][name]['result']['context']['slot']=100;self.blocked(c,'preflight-context')

    def test_discovery_is_one_hint_not_authenticated_intent(self):
        c=fixture();found,tx=discovery(c)
        self.assertEqual(discover_pool(found,tx),c['pool'])
        tx['transaction']['message']['instructions']=[]
        with self.assertRaisesRegex(StateError,'no-supported-swap'):discover_pool(found,tx)

    def test_default_host_check_exact_and_repeatable(self):
        r=run();self.assertEqual(r['casesPassed'],15);self.assertEqual(r,run())


class CaptureTests(unittest.TestCase):
    def test_explicit_pool_uses_five_ordered_read_requests(self):
        c=fixture();op=FakeOpener(replies(c));r=collect(pool=c['pool'],opener=op,now=lambda:NOW)
        self.assertEqual(audit(r)['state'],'pool-state-consistent')
        self.assertEqual([x[1]['method'] for x in op.calls],['getGenesisHash','getMultipleAccounts','getMultipleAccounts','getBlockTime','getGenesisHash'])
        self.assertEqual(op.calls[2][1]['params'][1]['minContextSlot'],100)
        for request,body,timeout in op.calls:
            self.assertEqual(request.full_url,'https://api.devnet.solana.com');self.assertEqual(request.method,'POST')
            self.assertNotIn('Authorization',request.headers);self.assertEqual(timeout,10)
        self.assertEqual(r['transactionsSent'],0)

    def test_bound_packet_fee_request_uses_exact_serialized_message(self):
        c=fixture(with_packet=True);op=FakeOpener(replies(c,True))
        r=collect(packet=c['packet'],opener=op,now=lambda:NOW)
        self.assertEqual(audit(r)['state'],'policy-state-consistent')
        self.assertEqual(len(op.calls),7)
        message=decode_wire(c['packet']['unsignedTransactionBase64'])[1]
        self.assertEqual(base64.b64decode(op.calls[5][1]['params'][0]),message)
        self.assertEqual(op.calls[4][1]['params'][0],c['packet']['policy']['blockhash'])

    def test_capture_freezes_packet_before_transport_and_rejects_invalid_packet_before_reads(self):
        c=fixture(with_packet=True);original=copy.deepcopy(c['packet'])
        class MutatingOpener(FakeOpener):
            def open(self,request,timeout):
                c['packet']['policy']['amountIn']='999'
                return super().open(request,timeout)
        op=MutatingOpener(replies(c,True));r=collect(packet=c['packet'],opener=op,now=lambda:NOW)
        self.assertEqual(r['packet'],original);self.assertEqual(audit(r)['state'],'policy-state-consistent')
        op=FakeOpener([])
        with self.assertRaises(ValueError):collect(packet=c['packet'],opener=op,now=lambda:NOW)
        self.assertEqual(op.calls,[])

    def test_sample_is_one_latest_hint_and_seven_requests(self):
        c=fixture();found,tx=discovery(c)
        responses=[GENESIS['devnet'],found,tx]+replies(c)[1:]
        op=FakeOpener(responses);r=collect(sample=True,opener=op,now=lambda:NOW)
        self.assertEqual(audit(r)['state'],'pool-state-consistent');self.assertEqual(len(op.calls),7)
        self.assertEqual(op.calls[1][1]['params'],[PROGRAM,{'limit':1,'commitment':'finalized'}])
        self.assertFalse(audit(r)['signatureVerified'])

    def test_no_resample_when_latest_has_no_supported_instruction(self):
        c=fixture();found,tx=discovery(c);tx['transaction']['message']['instructions']=[]
        op=FakeOpener([GENESIS['devnet'],found,tx]);r=collect(sample=True,opener=op,now=lambda:NOW)
        self.assertEqual(len(op.calls),3);self.assertEqual(r['stoppedReason'],'no-supported-swap-in-latest-transaction')

    def test_wrong_cluster_stops_after_one_request(self):
        op=FakeOpener([GENESIS['mainnet-beta']]);r=collect(pool=fixture()['pool'],opener=op,now=lambda:NOW)
        self.assertEqual(len(op.calls),1);self.assertEqual(r['stoppedReason'],'wrong-cluster')

    def test_rate_errors_and_network_errors_are_sanitized_no_retry(self):
        for error in (urllib.error.HTTPError('secret-url',429,'secret-token',{},None),urllib.error.URLError('secret')):
            op=FakeOpener([error]);r=collect(pool=fixture()['pool'],opener=op,now=lambda:NOW)
            self.assertEqual(len(op.calls),1);self.assertNotIn('secret',json.dumps(r))

    def test_request_and_account_caps_and_send_rejection(self):
        client=StateClient(FakeOpener([GENESIS['devnet']]*7))
        for _ in range(7):client.request('getGenesisHash',[])
        with self.assertRaises(ValueError):client.request('getGenesisHash',[])
        for method in ('sendTransaction','requestAirdrop','simulateTransaction'):
            with self.assertRaises(ValueError):StateClient(FakeOpener([])).request(method,[])
        with self.assertRaises(ValueError):StateClient().request('getMultipleAccounts',[['x']*12,{}])

    def test_deadline_prevents_later_reads(self):
        ticks=iter([0,0,31]);op=FakeOpener([GENESIS['devnet']])
        r=collect(pool=fixture()['pool'],opener=op,now=lambda:NOW,monotonic=lambda:next(ticks))
        self.assertEqual(len(op.calls),1);self.assertEqual(r['stoppedReason'],'capture-time-budget')

    def test_packet_expiry_before_next_read(self):
        c=fixture(with_packet=True);ticks=iter([NOW,NOW,NOW+14000,NOW+14000]);op=FakeOpener([GENESIS['devnet']])
        r=collect(packet=c['packet'],opener=op,now=lambda:next(ticks))
        self.assertEqual(len(op.calls),1);self.assertEqual(r['stoppedReason'],'packet-expired-during-capture')

    def test_oversized_account_and_bad_scalar_not_exported(self):
        c=fixture();boot=c['evidence']['bootstrap']['result'];boot['value'][0]['data'][0]='x'*6001
        op=FakeOpener([GENESIS['devnet'],boot]);r=collect(pool=c['pool'],opener=op,now=lambda:NOW)
        self.assertEqual(r['evidence']['bootstrap']['state'],'invalid-account-response')
        self.assertNotIn('x'*100,json.dumps(r))
        r=StateClient(FakeOpener([{'secret':'oops'}])).request('getGenesisHash',[])
        self.assertEqual(r,{'state':'invalid-scalar-response'})

    def test_cli_offline_report_permissions_replay_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'check.json.gz';cli=str(Path(__file__).with_name('cli.py'))
            command=[sys.executable,cli,'--output',str(out)]
            p=subprocess.run(command,capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
            raw=out.read_bytes();r=json.loads(gzip.decompress(raw));r.pop('capturedAt');self.assertEqual(r,run())
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
            src=Path(tmp)/'capture.json';src.write_text(json.dumps(fixture()));dest=Path(tmp)/'replay.json.gz'
            p=subprocess.run([sys.executable,cli,'--input',str(src),'--output',str(dest)],capture_output=True)
            self.assertEqual(p.returncode,0);report=json.loads(gzip.decompress(dest.read_bytes()))
            self.assertEqual(report['review'],audit(fixture()));self.assertEqual(report['currentRunNetworkRequests'],0)

    def test_cli_duplicate_input_has_no_partial_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'bad.json';out=Path(tmp)/'report.json.gz';src.write_text('{"a":1,"a":2}')
            p=subprocess.run([sys.executable,str(Path(__file__).with_name('cli.py')),'--input',str(src),'--output',str(out)],capture_output=True)
            self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
