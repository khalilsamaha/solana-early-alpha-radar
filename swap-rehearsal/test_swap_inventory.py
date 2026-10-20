import copy
import io
import json
import unittest
from swap_inventory import _collect_inventory,review,InventoryRpc
from preflight_checks import fixture
from preflight import _review,GENESIS
from state import TOKEN
from swap_rehearsal_fixtures import Response


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.c,self.b=fixture(False);full,_=fixture(True)
        self.wallet=full['packet']['policy']['accounts']['wallet']
        rows=full['evidence']['accounts']['result']['value']
        self.walletrow=rows[8];self.tokens=[rows[9],rows[10]];self.calls=[];self.empty=False;self.mutate=None
        self.reviewer=lambda c,now_ms:_review(c,self.b,now_ms)
    def open(self,req,timeout=None):
        r=json.loads(req.data);self.calls.append(r);m=r['method']
        if m=='getGenesisHash':value=GENESIS['devnet']
        elif m=='getMultipleAccounts':value={'context':{'slot':102},'value':[self.walletrow]}
        else:
            i=0 if r['params'][1]['mint']==self.c['accountKeys'][2] else 1
            value={'context':{'slot':103+i},'value':[] if self.empty else [dict(pubkey=self.c['accountKeys'][i+4],account=copy.deepcopy(self.tokens[i]))]}
        if self.mutate:value=self.mutate(m,value)
        return Response(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':value}).encode())
    def run_inventory(self):return _collect_inventory(self.c,self.wallet,opener=self,pool_reviewer=self.reviewer)
    def test_exact_five_read_requests_and_supported_accounts(self):
        r=self.run_inventory();self.assertEqual(r['review']['state'],'inventory-observed',r)
        self.assertEqual(len(self.calls),5);self.assertEqual([x['hasFundedAccount'] for x in r['review']['mints']],[True,False])
        self.assertFalse(r['review']['currentPoolPreflightVerified']);self.assertFalse(r['review']['walletKeyRead'])
        for call in self.calls[2:4]:self.assertEqual(call['params'][0],self.wallet);self.assertEqual(set(call['params'][1]),{'mint'})
    def test_no_accounts_not_rpc_failure(self):
        self.empty=True;r=self.run_inventory();self.assertEqual(r['review']['state'],'inventory-observed')
        self.assertTrue(all(not m['existingSupportedAccounts'] for m in r['review']['mints']))
    def test_wrong_cluster_stops_at_one(self):
        self.mutate=lambda m,v:GENESIS['mainnet-beta'] if m=='getGenesisHash' else v
        r=self.run_inventory();self.assertEqual(len(self.calls),1);self.assertEqual(r['review']['state'],'unavailable')
    def test_oversized_inventory_stops_without_partial_pass(self):
        def change(m,v):
            if m=='getTokenAccountsByOwner':v['value']*=33
            return v
        self.mutate=change;r=self.run_inventory();self.assertEqual(len(self.calls),3);self.assertEqual(r['review']['state'],'unavailable')
    def test_duplicate_account_rejected(self):
        def change(m,v):
            if m=='getTokenAccountsByOwner':v['value']*=2
            return v
        self.mutate=change;self.assertEqual(self.run_inventory()['review']['state'],'unavailable')
    def test_regressed_context_stops(self):
        def change(m,v):
            if m=='getTokenAccountsByOwner':v['context']['slot']=1
            return v
        self.mutate=change;r=self.run_inventory();self.assertEqual(r['review']['state'],'unavailable');self.assertEqual(len(self.calls),3)
    def test_unknown_token_owner_counted_unsupported(self):
        self.tokens[0]['owner']=self.wallet;r=self.run_inventory()
        self.assertEqual(r['review']['state'],'inventory-observed');self.assertEqual(r['review']['mints'][0]['unsupportedAccounts'],1)
    def test_no_send_no_airdrop_method(self):
        rpc=InventoryRpc(self)
        for method in ('sendTransaction','requestAirdrop','simulateTransaction'):
            with self.assertRaises(ValueError):rpc.request(method,[])
        self.assertFalse(self.calls)
    def test_tampered_pool_review_does_not_supply_identity(self):
        self.c['review']={'state':'pinned-pool-snapshot'};self.c['accountKeys'][0]=self.wallet
        with self.assertRaises(ValueError):self.run_inventory()
        self.assertFalse(self.calls)


if __name__=='__main__':unittest.main()
