import base64
import copy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from audit import audit, FLAGS
from checks import fixture, run
from reconcile import reconcile, NATIVE, TOKEN, SYSTEM, binding
from wire import b58

ROOT = Path(__file__).resolve().parent


def tx(p): return p['bundle']['rpcEvidence']['transaction']['result']
def ops(p): return tx(p)['meta']['innerInstructions'][0]['instructions']


class AccountingTests(unittest.TestCase):
    def assert_state(self, p, state, reason=None):
        result = audit(p)
        self.assertEqual(result['state'], state, result)
        if reason: self.assertEqual(result['reason'], reason)
        for k,v in FLAGS.items(): self.assertEqual(result[k],v)
        if state not in ('signed-token-accounting-consistent','finalized-failure-fee-only'):
            self.assertNotIn('transferFlows',result)
        return result

    def test_twelve_case_public_selfcheck(self):
        result=run(); self.assertEqual(result['casesPassed'],12)
        self.assertTrue(all(r['signatureVerified'] for r in result['cases'].values()))

    def test_existing_wsol_source_and_destination_integer_accounting(self):
        for side in ('source','destination'):
            r=self.assert_state(fixture('wsol-'+side),'signed-token-accounting-consistent')
            self.assertEqual(r['wrappedNative'][side]['impliedBackingReserveLamports'],'2039280')
            self.assertEqual(r['native']['walletDeltaLamports'],'-5000')
            self.assertEqual(r['transferFlows']['source']['amountAtomic'],'100')
            self.assertEqual(r['transferFlows']['destination']['amountAtomic'],'200')

    def test_old_lab_and_journal_validation_still_reject_wsol(self):
        from reconcile import validate_intent, EvidenceError
        for side in ('source','destination'):
            b=fixture('wsol-'+side)['bundle']
            self.assertEqual(reconcile(b)['state'],'unsupported')
            with self.assertRaises(EvidenceError): validate_intent(b['intent'])

    def test_signature_message_and_full_vector_tampering(self):
        p=fixture(); raw=bytearray(base64.b64decode(p['signedTransactionBase64'])); raw[20]^=1
        p['signedTransactionBase64']=base64.b64encode(raw).decode()
        self.assert_state(p,'unsupported-or-invalid-wire')
        p=fixture(); p['bundle']['intent']['messageSha256']='0'*64
        self.assert_state(p,'mismatch','signed-intent-identity-mismatch')
        p=fixture('multisigner'); tx(p)['transaction']['signatures'][1]=fixture()['bundle']['intent']['signature']
        self.assert_state(p,'mismatch','receipt-signature-vector-mismatch')

    def test_rpc_message_replacement(self):
        p=fixture(); tx(p)['transaction']['message']['instructions'][0]['data']='3'
        self.assert_state(p,'mismatch','prepared-message-mismatch')

    def test_transfer_values_must_match_each_account(self):
        for index,amount in ((0,99),(0,101),(1,199),(1,201)):
            p=fixture(); ops(p)[index]['data']=b58(bytes([3])+amount.to_bytes(8,'little'))
            self.assert_state(p,'mismatch','transfer-flow-balance-mismatch')

    def test_zero_missing_or_null_transfer_evidence(self):
        p=fixture(); ops(p)[0]['data']=b58(bytes([3])+bytes(8))
        self.assert_state(p,'unsupported','zero-transfer-not-supported')
        for value in (None,[]):
            p=fixture();tx(p)['meta']['innerInstructions']=value
            self.assert_state(p,'unknown')

    def test_multiple_transfers_sum_without_floating_point(self):
        p=fixture(); rows=ops(p); first=copy.deepcopy(rows[0]); first['data']=b58(bytes([3])+(40).to_bytes(8,'little'))
        second=copy.deepcopy(first); second['data']=b58(bytes([3])+(60).to_bytes(8,'little'))
        rows[:1]=[first,second]
        r=self.assert_state(p,'signed-token-accounting-consistent')
        self.assertEqual(r['transferFlows']['source']['transfers'],2)

    def test_wrong_wallet_authority_and_reverse_direction(self):
        p=fixture();ops(p)[0]['accounts'][-1]=5
        self.assert_state(p,'mismatch','unexpected-source-direction-or-authority')
        p=fixture();ops(p)[0]['accounts'][:2]=list(reversed(ops(p)[0]['accounts'][:2]))
        self.assert_state(p,'unsupported','unsupported-wallet-token-operation')
        p=fixture();ops(p)[1]['accounts'][:2]=list(reversed(ops(p)[1]['accounts'][:2]))
        self.assert_state(p,'mismatch','unexpected-destination-direction')

    def test_counterparty_identity_and_delegation(self):
        p=fixture();ops(p)[1]['accounts'][-1]=0
        self.assert_state(p,'unsupported','counterparty-authority-not-supported')
        p=fixture()
        for field in ('preTokenBalances','postTokenBalances'):tx(p)['meta'][field][2]['mint']=p['bundle']['intent']['destination']['mint']
        self.assert_state(p,'mismatch','counterparty-token-identity-mismatch')
        p=fixture()
        for field in ('preTokenBalances','postTokenBalances'):tx(p)['meta'][field]=[r for r in tx(p)['meta'][field] if r['accountIndex']!=3]
        self.assert_state(p,'unknown','counterparty-token-identity-unavailable')

    def test_checked_transfer_mint_and_decimals(self):
        p=fixture();o=ops(p)[0];o['accounts']=[1,6,3,0];o['data']=b58(bytes([12])+(100).to_bytes(8,'little')+bytes([6]))
        self.assert_state(p,'signed-token-accounting-consistent')
        for which in ('mint','decimals'):
            q=copy.deepcopy(p)
            if which=='mint':ops(q)[0]['accounts'][1]=7
            else:ops(q)[0]['data']=b58(bytes([12])+(100).to_bytes(8,'little')+bytes([9]))
            self.assert_state(q,'mismatch','checked-transfer-mint-or-decimals-mismatch')

    def test_wsol_backing_delta_and_positive_reserve(self):
        for side,index in (('source',1),('destination',2)):
            p=fixture('wsol-'+side);tx(p)['meta']['postBalances'][index]+=1
            self.assert_state(p,'mismatch','wrapped-native-backing-mismatch')
            p=fixture('wsol-'+side)
            for field in ('preBalances','postBalances'):tx(p)['meta'][field][index]-=2039280
            self.assert_state(p,'mismatch','wrapped-native-backing-mismatch')

    def test_wsol_lifecycle_decimals_and_sync_unsupported(self):
        p=fixture('wsol-source');p['bundle']['intent']['source']['lifecycle']='close'
        self.assert_state(p,'unsupported','wrapped-native-lifecycle-not-supported')
        p=fixture('wsol-destination');p['bundle']['intent']['destination']['lifecycle']='create'
        self.assert_state(p,'unsupported','wrapped-native-lifecycle-not-supported')
        p=fixture('wsol-source');p['bundle']['intent']['source']['decimals']=6
        self.assert_state(p,'mismatch','wrapped-native-decimals-mismatch')
        p=fixture('wsol-source');ops(p).append({'programIdIndex':8,'accounts':[1],'data':b58(bytes([17]))})
        self.assert_state(p,'unsupported','unsupported-token-account-operation')

    def test_create_order_rent_cap_and_close_proof(self):
        p=fixture('create'); rows=ops(p);rows[1],rows[3]=rows[3],rows[1]
        self.assert_state(p,'mismatch','transfer-before-initialization')
        p=fixture('create');p['bundle']['intent']['maximumRentLamports']='1'
        self.assert_state(p,'mismatch','rent-cap-exceeded')
        p=fixture('close');ops(p).pop()
        self.assert_state(p,'unknown','closure-instruction-unproven')
        r=self.assert_state(fixture('close'),'signed-token-accounting-consistent')
        self.assertEqual(r['native']['rentRefundedLamports'],'2039280')

    def test_fee_only_failure_does_not_infer_a_fill(self):
        p=fixture('failed');r=self.assert_state(p,'finalized-failure-fee-only')
        self.assertEqual(r['transferFlows'],{})
        self.assertTrue(all(a['deltaAtomic']=='0' for a in r['tokenAccounts'].values()))
        p=fixture('failed');tx(p)['meta']['postBalances'][0]-=1
        self.assert_state(p,'mismatch','unexplained-native-wallet-change')

    def test_failure_wsol_still_checks_backing(self):
        p=fixture('wsol-source');m=tx(p)['meta'];error={'InstructionError':[0,'InvalidArgument']}
        m.update(err=error,postTokenBalances=copy.deepcopy(m['preTokenBalances']),postBalances=m['preBalances'].copy(),innerInstructions=[])
        m['postBalances'][0]-=5000;p['bundle']['rpcEvidence']['signatureStatus']['result']['value'][0]['err']=error
        self.assert_state(p,'finalized-failure-fee-only')
        m['preBalances'][1]=m['postBalances'][1]=0
        self.assert_state(p,'mismatch','wrapped-native-backing-mismatch')

    def test_unknown_or_nonfinal_receipt_never_a_pass(self):
        p=fixture();p['bundle']['rpcEvidence']['transaction']['result']=None
        self.assert_state(p,'unknown')
        p=fixture();p['bundle']['rpcEvidence']['signatureStatus']['result']['value'][0]['confirmationStatus']='confirmed'
        self.assert_state(p,'unknown')

    def test_owner_program_token2022_and_minimum_output(self):
        p=fixture();tx(p)['meta']['postTokenBalances'][1]['owner']=tx(p)['transaction']['message']['accountKeys'][5]
        self.assert_state(p,'mismatch','token-account-identity-mismatch')
        p=fixture();p['bundle']['intent']['source']['programId']='TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'
        self.assert_state(p,'unsupported','token-program-not-supported')
        p=fixture();p['bundle']['intent']['minimumOutputAtomic']='201'
        self.assert_state(p,'mismatch','minimum-output-not-met')

    def test_malformed_package_amounts_and_redaction(self):
        for p in (None,[],{}, {'format':'signed-token-evidence-1','bundle':{},'signedTransactionBase64':'bad'}):
            r=audit(p);self.assertNotEqual(r['state'],'signed-token-accounting-consistent')
        for value in (True,1.1,'-1','01','18446744073709551616'):
            p=fixture();p['bundle']['intent']['inputAtomic']=value
            self.assert_state(p,'invalid-input')
        p=fixture();tx(p)['meta']['logMessages']=['DO-NOT-EXPORT-THIS']
        self.assertNotIn('DO-NOT-EXPORT-THIS',json.dumps(audit(p)))

    def test_offsetting_native_transfers_still_unsupported(self):
        p=fixture();rows=ops(p)
        for accounts in ([0,11],[11,0]):
            rows.append({'programIdIndex':9,'accounts':accounts,'data':b58((2).to_bytes(4,'little')+(100).to_bytes(8,'little'))})
        self.assert_state(p,'unsupported','unsupported-wallet-native-operation')

    def test_unrelated_approval_cannot_hide_in_unchanged_balances(self):
        p=fixture();ops(p).append({'programIdIndex':8,'accounts':[11,5,0],'data':b58(bytes([4])+(100).to_bytes(8,'little'))})
        self.assert_state(p,'unsupported','unsupported-wallet-token-operation')

    def test_other_wallet_account_lamports_checked_even_on_failure(self):
        for name in ('existing','failed'):
            p=fixture(name);m=tx(p)['meta']
            extra=copy.deepcopy(m['preTokenBalances'][1]);extra.update(accountIndex=11)
            m['preTokenBalances'].append(copy.deepcopy(extra));m['postTokenBalances'].append(extra)
            m['postBalances'][11]+=1
            self.assert_state(p,'mismatch','unexpected-other-wallet-account-native-change')

    def test_missing_fields_and_pool_switch_do_not_become_zero(self):
        p=fixture();del tx(p)['meta']['postTokenBalances']
        self.assert_state(p,'unknown')
        p=fixture();tx(p)['meta']['postTokenBalances'][0]['mint']=p['bundle']['intent']['destination']['mint']
        self.assert_state(p,'mismatch','token-account-identity-mismatch')
        p=fixture();tx(p)['meta']['postTokenBalances'].pop(1)
        self.assert_state(p,'unknown','existing-account-balance-missing')

    def test_strict_alt_rejection_precedes_accounting(self):
        p=fixture('v0');raw=bytearray(base64.b64decode(p['signedTransactionBase64']))
        raw[-1:]=bytes([1])+bytes([12])*32+bytes([1,0,0])
        p['signedTransactionBase64']=base64.b64encode(raw).decode()
        self.assert_state(p,'unsupported-or-invalid-wire')

    def test_input_remains_unchanged_and_no_transport_is_used(self):
        from unittest.mock import patch
        p=fixture('wsol-source');before=copy.deepcopy(p)
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            self.assert_state(p,'signed-token-accounting-consistent')
        self.assertEqual(p,before)

    def test_cli_private_gzip_overwrite_input_cap_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.json.gz'
            args=[sys.executable,str(ROOT/'cli.py'),'--output',str(out)]
            good=subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(good.returncode,0,good.stderr)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertEqual(json.load(gzip.open(out))['casesPassed'],12)
            before=out.read_bytes();self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),before)
            for content in (b'{"format":1,"format":2}',b'x'*(4*1024*1024+1)):
                inp=Path(d)/'input.json.gz';inp.write_bytes(gzip.compress(content));target=Path(d)/'no.json.gz'
                r=subprocess.run([sys.executable,str(ROOT/'cli.py'),'--input',str(inp),'--output',str(target)],capture_output=True)
                self.assertNotEqual(r.returncode,0);self.assertFalse(target.exists())


if __name__=='__main__': unittest.main()
