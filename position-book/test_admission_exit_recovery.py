"""Closed historical source -> acquired entry -> delayed preparation -> restore."""
import base64
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

import admission_exit as m
import admission_recovery as recovery
import test_admission_recovery as recovery_tests
from paired_checks import shift,edit,simulation_response
from contract import digest
from fresh_packet import message
from state_fixtures import fake_key


def delayed(capture,accounting,now):
    initial=deepcopy(capture)
    offset=now-1500-initial['finishedAtMs'];shift(initial,offset,10)
    initial['evidence']['blockTime']['result']=initial['finishedAtMs']//1000
    # Synthetic fresh account batch includes the settled entry's balances and a
    # changed pool. Exact simulation is regenerated from those bytes below.
    for idx,delta in ((9,-int(accounting['sourcePrincipalSpentAtomic'])),
                      (10,int(accounting['ownedAcquiredAtomic']))):
        row=initial['evidence']['accounts']['result']['value'][idx]
        amount=int.from_bytes(base64.b64decode(row['data'][0])[64:72],'little')
        edit(initial,idx,64,(amount+delta).to_bytes(8,'little'))
    initial['evidence']['accounts']['result']['value'][8]['lamports']-=int(accounting['entryFeePaidLamports'])
    scope=m.scope_for(initial['packet']['policy'])
    for left,right in (('source','destination'),('inputMint','outputMint'),('inputVault','outputVault')):
        scope['accounts'][left],scope['accounts'][right]=scope['accounts'][right],scope['accounts'][left]
    scope['amountIn']=accounting['ownedAcquiredAtomic']
    # The quote-only capture must not carry an entry packet after its balances changed.
    raw,_=m.preflight.split_capture(initial)
    raw['packet']=None;raw['selection']='explicit-pool';raw['accountKeys']=raw['accountKeys'][:8]
    raw['evidence']['accounts']['result']['value']=raw['evidence']['accounts']['result']['value'][:8]
    raw['evidence']['blockhash']={'state':'not-requested'};raw['evidence']['fee']={'state':'not-requested'}
    price=m.derive(raw,scope,slippage_bps=100,now_ms=now)
    scope['minimumAmountOut']=price['quote']['minimumOutAmount']
    c=deepcopy(initial);shift(c,1000,1);c['evidence']['blockTime']['result']=c['finishedAtMs']//1000
    c['accountKeys'][9],c['accountKeys'][10]=c['accountKeys'][10],c['accountKeys'][9]
    rows=c['evidence']['accounts']['result']['value'];rows[9],rows[10]=rows[10],rows[9]
    packet=c['packet'];packet['policy'].update({k:v for k,v in scope.items() if k!='format'})
    packet['policy']['blockhash']=fake_key('delayed-historical-exit')
    packet['policy']['issuedAtMs']=initial['finishedAtMs']
    packet['policy']['expiresAtMs']=now+5000
    msg=message(scope,packet['policy']['blockhash'])
    packet['unsignedTransactionBase64']=base64.b64encode(b'\x01'+bytes(64)+msg).decode()
    packet['feeAssertion']['messageSha256']=hashlib.sha256(msg).hexdigest()
    c['messageSha256']=packet['feeAssertion']['messageSha256']
    sim=simulation_response(c,price['quote']['outAmount']);sim['value']['failed']=False;sim['value'].pop('err')
    return dict(initialPool=raw,packet=packet,capture=c,price=price,
        simulationItem=dict(state='received',result=sim),simulationStartedAtMs=now-400,
        simulationReceivedAtMs=now-300,completedAtMs=now-200)


class EndToEndExitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):recovery_tests.RecoveryTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):recovery_tests.RecoveryTests.tearDownClass.__func__(cls)
    setUp=recovery_tests.RecoveryTests.setUp
    tearDown=recovery_tests.RecoveryTests.tearDown
    clock=recovery_tests.RecoveryTests.clock
    submit=recovery_tests.RecoveryTests.submit
    collect=recovery_tests.RecoveryTests.collect
    settle=recovery_tests.RecoveryTests.settle
    capture=recovery_tests.RecoveryTests.capture
    verify=recovery_tests.RecoveryTests.verify
    source_bytes=recovery_tests.RecoveryTests.source_bytes
    edit_db=recovery_tests.RecoveryTests.edit_db

    def test_real_source_binding_exit_recovery_and_tamper_replay(self):
        self.collect();r=self.settle();self.stamp+=30000
        e=delayed(self.e['costInputs']['capture'],r['accounting'],self.stamp)
        baseline=self.e['costInputs']['baseline']
        with patch.object(m,'BASELINE',baseline):
            prepared=m.prepare(self.home,self.wallet,self.pool,e,clock=self.clock)
            self.assertEqual(prepared['binding']['quantityAtomic'],'996')
            self.assertGreater(int(prepared['binding']['protectedInventoryAtomic']),0)
            before=self.source_bytes();self.capture();self.assertEqual(before,self.source_bytes())
            manifest=json.loads((self.snapshot/recovery.MANIFEST).read_text())
            self.assertEqual(manifest['projection']['exitPreparationSha256'],prepared['recordSha256'])
            self.verify()
            # Snapshot cannot hide corrupted raw exit evidence behind new hashes.
            path=self.snapshot/recovery.SIBLING/'entry.admission.sqlite'
            def corrupt(db):
                row=json.loads(db.execute('SELECT value FROM admission_exit_preparation').fetchone()[0])
                row['binding']['quantityAtomic']='1'
                db.execute('UPDATE admission_exit_preparation SET value=?,hash=?',(m.encoded(row),digest(row)))
            self.edit_db(corrupt,path)
            manifest['inventories']=recovery.inventories(self.snapshot/recovery.SOURCE,self.snapshot/recovery.SIBLING)
            (self.snapshot/recovery.MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'exit-record-source-conflict'):self.verify()


if __name__=='__main__':unittest.main()
