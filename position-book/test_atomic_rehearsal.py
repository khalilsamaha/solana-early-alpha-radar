import base64
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import atomic_rehearsal as m
from atomic_rehearsal_checks import fixture, run, trace_quantity, wire_edit
from contract import TOKEN, PROGRAM, ROLES, b58, decode_wire, validate
from post_entry_checks import NOW


def encode_with_instructions(draft, instructions):
    raw, msg, _, _, tx = decode_wire(draft['unsignedTransactionBase64'])
    keys = tx['transaction']['message']['accountKeys']
    prefix_len = 3 + 1 + 32*len(keys) + 32
    encoded = b''.join(bytes([v['programIdIndex'], len(v['accounts']), *v['accounts'],
                             len(m.decode(v['data']))])+m.decode(v['data']) for v in instructions)
    draft['unsignedTransactionBase64'] = base64.b64encode(
        b'\x01'+bytes(64)+msg[:prefix_len]+bytes([len(instructions)])+encoded).decode()


class AtomicRehearsalTests(unittest.TestCase):
    def reject(self, a, p, d):
        r = m.assess(a,p,d)
        self.assertEqual(r['state'], 'unavailable', r)
        self.assertIsNone(r['binding']); self.assertFalse(r['executionApproved'])

    def reject_trace(self, a, p, d, g):
        r = m.assess_trace(a,p,d,g)
        self.assertEqual(r['state'], 'unavailable', r)
        self.assertIsNone(r['trace']); self.assertIsNone(r['binding'])
        self.assertFalse(r['orderedTokenFlowsMatched']); self.assertFalse(r['simulationVerified'])

    def test_both_directions_ordered_roles_and_one_shared_budget(self):
        for reverse in (False, True):
            a,p,d,g = fixture(reverse); before = deepcopy((a,p,d,g))
            r = m.assess(a,p,d); self.assertEqual(r['state'], 'atomic-draft-consistent', r)
            b = r['binding']; self.assertEqual(b['transactionBytes'],650)
            self.assertEqual(b['transactionCount'],1); self.assertEqual(b['signatureCount'],1)
            self.assertEqual(b['computeUnitsShared'],300000)
            _,_,_,signatures,tx=decode_wire(d['unsignedTransactionBase64'])
            self.assertEqual(signatures,[bytes(64)])
            msg=tx['transaction']['message'];keys=msg['accountKeys'];ix=msg['instructions']
            self.assertEqual(len(ix),4)
            for instruction,scope in zip(ix[2:],(d['entryScope'],d['exitScope'])):
                roles=dict(scope['accounts'],inputTokenProgram=TOKEN,outputTokenProgram=TOKEN)
                self.assertEqual(keys[instruction['programIdIndex']],PROGRAM)
                self.assertEqual([keys[i] for i in instruction['accounts']],[roles[k] for k in ROLES])
            self.assertEqual((a,p,d,g),before)

    def test_reversed_order_duplicate_swap_and_copied_indices_fail(self):
        for mode in ('reverse','duplicate','copied-reverse-indices','extra','missing'):
            a,p,d,g=fixture()
            _,_,_,_,tx=decode_wire(d['unsignedTransactionBase64']);ix=tx['transaction']['message']['instructions']
            if mode=='reverse':ix[2],ix[3]=ix[3],ix[2]
            if mode=='duplicate':ix[3]=deepcopy(ix[2])
            if mode=='copied-reverse-indices':
                reverse=m.projected_exit.build(a,p)
                _,_,_,_,rtx=decode_wire(reverse['unsignedTransactionBase64'])
                ix[3]=rtx['transaction']['message']['instructions'][2]
            if mode=='extra':ix.append(deepcopy(ix[3]))
            if mode=='missing':ix.pop()
            encode_with_instructions(d,ix);self.reject(a,p,d)

    def test_wire_weakening_extra_privilege_and_signature_rejected(self):
        for mode in ('amount','minimum','signature','readonly','blockhash','priority','limit','oversized'):
            a,p,d,g=fixture();length=len(base64.b64decode(d['unsignedTransactionBase64']))
            if mode=='amount':wire_edit(d,length-16,(78).to_bytes(8,'little'))
            if mode=='minimum':wire_edit(d,length-8,(1).to_bytes(8,'little'))
            if mode=='signature':wire_edit(d,1,b'\x01')
            if mode=='readonly':wire_edit(d,67,b'\x06')
            if mode=='blockhash':wire_edit(d,65+4+14*32,bytes(32))
            if mode in ('priority','limit'):
                _,_,_,_,tx=decode_wire(d['unsignedTransactionBase64']);ix=tx['transaction']['message']['instructions']
                i=1 if mode=='priority' else 0
                ix[i]['data']=b58(b'\x03'+(1).to_bytes(8,'little') if i else b'\x02'+(600000).to_bytes(4,'little'))
                encode_with_instructions(d,ix)
            if mode=='oversized':d['unsignedTransactionBase64']='A'*1648
            self.reject(a,p,d)

    def test_cannot_borrow_fees_or_enter_existing_sender_contract(self):
        a,p,d,g=fixture();r=m.assess(a,p,d)
        self.assertEqual(validate(d,now_ms=NOW)['state'],'rejected')
        self.assertIsNone(r['combinedFeeLamports'])
        self.assertEqual(r['binding']['feeBasis'],'combined-message-not-yet-priced')
        self.assertNotEqual(r['binding']['messageSha256'],a['packet']['feeAssertion']['messageSha256'])
        for k in ('executionApproved','validForSubmission','signingApproved','simulationVerified',
                  'exitSimulationVerified','feeVerified','roundTripFundingEstablished',
                  'twoTransactionExecutionVerified','liveCollectorVerified','mainnetSupported'):
            self.assertFalse(r[k],k)
        d['feeAssertion']=a['packet']['feeAssertion'];self.reject(a,p,d)

    def test_balances_replay_acquired_only_and_preserve_existing_inventory(self):
        for reverse in (False,True):
            a,p,d,g=fixture(reverse);before=deepcopy((a,p,d,g));r=m.assess_trace(a,p,d,g)
            self.assertEqual(r['state'],'atomic-transfer-trace-consistent',r)
            t=r['trace'];b=t['balances'];self.assertEqual(t['orderedTransfers'],4)
            self.assertEqual(t['originalTokenChangeAtomic'],'-37');self.assertEqual(t['residualAcquiredAtomic'],'0')
            self.assertEqual(b['destination']['afterExitAtomic'],b['destination']['beforeAtomic'])
            self.assertEqual(b['destination']['beforeAtomic'],'1000' if reverse else '0')
            self.assertEqual((a,p,d,g),before)
            self.assertFalse(r['simulationVerified']);self.assertFalse(r['oracleEffectsReviewed'])
            self.assertIsNone(r['netProfit'])

    def test_inventory_cannot_mask_entry_shortfall_even_if_exit_could_spend_it(self):
        a,p,d,g=fixture(True)  # 1,000 pre-existing output tokens could cover this deficit.
        trace_quantity(g[0]['instructions'][1],76)
        self.reject_trace(a,p,d,g)

    def test_partial_exit_unexpected_output_and_unexpected_transfers_rejected(self):
        for mode in ('partial','output','extra','missing'):
            a,p,d,g=fixture()
            if mode=='partial':trace_quantity(g[1]['instructions'][0],78)
            if mode=='output':trace_quantity(g[1]['instructions'][1],64)
            if mode=='extra':g[1]['instructions'].append(deepcopy(g[1]['instructions'][0]))
            if mode=='missing':g[0]['instructions'].pop()
            self.reject_trace(a,p,d,g)

    def test_trace_role_mint_authority_program_and_decimal_confusion_rejected(self):
        for mode in ('source','mint','authority','program','decimals','opcode','index-bool','depth','parsed','huge','invalid-base58'):
            a,p,d,g=fixture();ix=g[0]['instructions'][0]
            if mode in ('source','mint','authority'):
                idx={'source':0,'mint':1,'authority':3}[mode]
                ix['accounts'][idx]=ix['accounts'][(idx+1)%4]
            if mode=='program':ix['programIdIndex']=0
            if mode in ('decimals','opcode'):
                raw=bytearray(m.decode(ix['data']));raw[9 if mode=='decimals' else 0]^=1;ix['data']=b58(raw)
            if mode=='index-bool':ix['accounts'][0]=True
            if mode=='depth':ix['stackHeight']=3
            if mode=='parsed':ix['parsed']={'type':'transferChecked'}
            if mode=='huge':ix['data']='1'*100000
            if mode=='invalid-base58':ix['data']='0'
            self.reject_trace(a,p,d,g)

    def test_missing_duplicate_or_out_of_order_outer_trace_indices_rejected(self):
        for mode in ('missing','duplicate','reorder','bool','unknown'):
            a,p,d,g=fixture()
            if mode=='missing':g.pop()
            if mode=='duplicate':g[1]['index']=2
            if mode=='reorder':g.reverse()
            if mode=='bool':g[0]['index']=True
            if mode=='unknown':g[1]['index']=4
            self.reject_trace(a,p,d,g)

    def test_parent_changes_reject_and_snapshot_copies_do_not_leak(self):
        a,p,d,g=fixture();review=m._Review(a,p);snapshot=review.build()
        a['now_ms']+=20000
        self.reject(a,p,d)
        self.assertEqual(review.build(),snapshot)
        snapshot['entryScope']['amountIn']='1'
        self.assertNotEqual(review.build(),snapshot)
        with self.assertRaises(ValueError):review.binding(snapshot)
        a,p,d,g=fixture();d['parentProjectionSha256']='f'*64;self.reject(a,p,d)
        a,p,d,g=fixture();a['reservations']['nativeHeldLamports']=None;self.reject(a,p,d)

    def test_portable_checks_without_network_and_no_private_wire_in_report(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(run()['casesPassed'],18)
        a,p,d,g=fixture();report=json.dumps(m.assess_trace(a,p,d,g))
        self.assertNotIn('unsignedTransactionBase64',report)
        self.assertNotIn(d['unsignedTransactionBase64'],report)

    def test_cli_no_live_input_modes_and_exclusive_private_report(self):
        cli=Path(__file__).with_name('atomic_rehearsal_cli.py')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'report.gz';cmd=[sys.executable,str(cli),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            data=out.read_bytes();j=json.loads(gzip.decompress(data));self.assertEqual(j['casesPassed'],18)
            self.assertEqual(out.stat().st_mode & 0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(data,out.read_bytes())
            for flag in ('--simulate-devnet','--allow-devnet-submit','--input','--directory','--wallet'):
                target=Path(tmp)/'absent.gz'
                self.assertNotEqual(subprocess.run([sys.executable,str(cli),'--output',str(target),flag],capture_output=True).returncode,0)
                self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
