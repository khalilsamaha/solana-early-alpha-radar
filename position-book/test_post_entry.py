from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import post_entry as m
from post_entry_checks import fixture, mutate_row, run, simulation_response, edit, NOW


class PostEntryTests(unittest.TestCase):
    def rejected(self,args,request):
        r=m.assess(args,request)
        self.assertEqual(r['state'],'unavailable',r)
        self.assertIsNone(r['projection'])
        self.assertEqual(r['reasons'],['post-entry-evidence-rejected'])
        self.assertFalse(r['executionApproved'])

    def test_hand_calculated_nonzero_shares_and_reverse_after_entry(self):
        args,req=fixture();before=deepcopy((args,req))
        r=m.assess(args,req);p=r['projection']
        self.assertEqual(r['state'],'simulated-post-entry-projection-consistent',r)
        self.assertEqual(p['acquiredInputAtomic'],'79')
        self.assertEqual(p['protocolFeeAddedAtomic'],'10')
        self.assertEqual(p['fundFeeAddedAtomic'],'5')
        self.assertEqual(p['vaultAmountsToken0Token1Atomic'],['10100','9921'])
        self.assertEqual(p['reservesToken0Token1Atomic'],['10085','9921'])
        # Exit fee ceil(79*.2)=16; floor(63*10085/(9921+63))=63.
        self.assertEqual(p['projectedOutputAtomic'],'63')
        self.assertEqual(p['projectedMinimumOutputAtomic'],'63')
        self.assertEqual(p['arithmetic']['tradeFeeAtomic'],'16')
        self.assertEqual((args,req),before)

    def test_reverse_orientation_uses_input_side_fee_counters(self):
        args,req=fixture(True);r=m.assess(args,req)
        self.assertEqual(r['state'],'simulated-post-entry-projection-consistent',r)
        p=r['projection']
        self.assertEqual(p['reservesToken0Token1Atomic'],['9923','10083'])
        self.assertEqual(p['acquiredInputAtomic'],'77')
        self.assertEqual(p['projectedOutputAtomic'],'61')

    def test_complete_simulation_and_request_identities_retained_without_raw_payload(self):
        args,req=fixture();r=m.assess(args,req);e=r['evidence']
        self.assertEqual(e['fullSimulationSha256'],m.digest(args['simulation_item']))
        self.assertEqual(e['requestParametersSha256'],m.digest(req))
        self.assertEqual(e['postPoolAccountSha256'],m.digest(args['simulation_item']['result']['value']['accounts'][8]))
        text=json.dumps(r)
        self.assertNotIn('unsignedTransactionBase64',text)
        self.assertNotIn(args['packet']['unsignedTransactionBase64'],text)
        for k in ('executionApproved','signingApproved','actualEntryExecuted','exitSimulationVerified',
                  'liveCollectorVerified','roundTripFundingEstablished','sourceEquivalenceVerified','mainnetSupported'):
            self.assertFalse(r[k],k)
        self.assertIsNone(r['netProfit']);self.assertFalse(r['projection']['validForSubmission'])

    def test_pool_owner_shape_lamports_and_immutable_bytes_are_not_trusted(self):
        for key in ('owner','size','lamports',329,333,349,365,373,389,397,636):
            args,req=fixture();row=args['simulation_item']['result']['value']['accounts'][8]
            if key=='owner':row['owner']=args['packet']['policy']['accounts']['wallet']
            elif key=='size':row['data'][0]='AA=='
            elif key=='lamports':row['lamports']+=1
            else:mutate_row(row,key,b'\xff')
            self.rejected(args,req)

    def test_exact_shares_required_not_merely_increasing_fee_totals(self):
        for protocol,fund in [(9,5),(11,5),(10,4),(10,6),(15,0),(0,15)]:
            args,req=fixture();pool=args['simulation_item']['result']['value']['accounts'][8]
            mutate_row(pool,341,protocol.to_bytes(8,'little'));mutate_row(pool,357,fund.to_bytes(8,'little'))
            self.rejected(args,req)

    def test_request_has_exact_account_order_bytes_and_options(self):
        for key in ('reorder','message','signatures','count','type'):
            args,req=fixture()
            if key=='reorder':req[1]['accounts']['addresses'].reverse()
            if key=='message':req[0]='AA=='
            if key=='signatures':req[1]['sigVerify']=True
            if key=='count':req[1]['accounts']['addresses'].append(req[1]['accounts']['addresses'][-1])
            if key=='type':req[1]['sigVerify']=0
            self.rejected(args,req)

    def test_pool_must_come_in_same_response_not_independent_leg_summary(self):
        for key in ('absent','extra','slot','summary'):
            args,req=fixture();v=args['simulation_item']['result']['value']
            if key=='absent':v['accounts'].pop()
            if key=='extra':v['accounts'].append(deepcopy(v['accounts'][-1]))
            if key=='slot':args['simulation_item']['result']['context']['slot']=1
            if key=='summary':args['simulation_item']={'state':'independent-leg-costs-consistent'}
            self.rejected(args,req)

    def test_prior_balance_fee_deployment_and_clock_guards_still_apply(self):
        for key in ('pre','fee','deployment','expired','reservation','vault'):
            args,req=fixture();v=args['simulation_item']['result']['value']
            if key=='pre':v.pop('preTokenBalances')
            if key=='fee':v['fee']+=1
            if key=='deployment':v['accounts'][7]['lamports']+=1
            if key=='expired':args['now_ms']=NOW+20000
            if key=='reservation':args['reservations']['nativeHeldLamports']=None
            if key=='vault':mutate_row(v['accounts'][3],64,(10101).to_bytes(8,'little'))
            self.rejected(args,req)

    def test_existing_destination_inventory_is_not_added_to_exit_quantity(self):
        args,req=fixture();pool=deepcopy(args['simulation_item']['result']['value']['accounts'][8])
        edit(args['capture'],10,64,(500).to_bytes(8,'little'))
        response=simulation_response(args['capture'],args['price']['quote']['outAmount'])
        response['value']['failed']=False;response['value'].pop('err')
        response['value']['accounts'].append(pool);args['simulation_item']['result']=response
        r=m.assess(args,req)
        self.assertEqual(r['state'],'simulated-post-entry-projection-consistent',r)
        self.assertEqual(r['projection']['acquiredInputAtomic'],'79')
        self.assertEqual(r['projection']['projectedOutputAtomic'],'63')

    def test_epoch_is_non_regression_only_and_default_transport_stays_eight_accounts(self):
        args,req=fixture();pool=args['simulation_item']['result']['value']['accounts'][8]
        mutate_row(pool,381,(40).to_bytes(8,'little'))
        self.assertEqual(m.assess(args,req)['state'],'simulated-post-entry-projection-consistent')
        mutate_row(pool,381,(39).to_bytes(8,'little'));self.rejected(args,req)
        self.assertEqual(len(m.unsigned_simulation.parameters(args['packet'],args['capture'])[1]['accounts']['addresses']),8)
        self.assertEqual(len(req[1]['accounts']['addresses']),9)

    def test_creator_fee_enabled_pool_is_explicitly_out_of_scope_even_at_zero_rate(self):
        args,req=fixture(creator=True)
        original=deepcopy(args);original['simulation_item']['result']['value']['accounts'].pop()
        self.assertEqual(m.cost_readiness.assess(**original)['state'],'single-leg-cost-evidence-consistent')
        self.rejected(args,req)

    def test_offline_self_check_does_not_open_network(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            r=run()
        self.assertEqual(r['casesPassed'],9)
        self.assertEqual(r['networkRequests'],0)

    def test_cli_has_no_live_scope_and_preserves_existing_output(self):
        cli=Path(__file__).with_name('post_entry_cli.py')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'report.gz';cmd=[sys.executable,str(cli),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            before=out.read_bytes();report=json.loads(gzip.decompress(before))
            self.assertEqual(report['mode'],'synthetic-offline')
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),before)
            self.assertEqual(out.stat().st_mode & 0o777,0o600)
            for flag in ('--simulate-devnet','--allow-devnet-submit','--directory','--wallet','--input'):
                self.assertNotEqual(subprocess.run(cmd+[flag],capture_output=True).returncode,0)


if __name__=='__main__':unittest.main()
