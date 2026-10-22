import copy,json,sqlite3,tempfile,unittest
from pathlib import Path
from engine import Lab,LIMITS
from run import event,prepare,buy,scenarios
class EngineTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.sim.sqlite';self.lab=Lab(self.path,True)
 def tearDown(self):self.lab.close();self.temp.cleanup()
 def test_unknown_buy_survives_restart_and_cannot_be_resubmitted_or_cancelled(self):
  prepare(self.lab);event(self.lab,'submit','submit_buy',1001);event(self.lab,'wait','reconcile_buy',1002,simulation=True,transaction='sim-buy-p',status='unknown')
  self.lab.close();self.lab=Lab(self.path)
  self.assertEqual(self.lab.snapshot()['positions']['p']['state'],'BUY_UNKNOWN')
  for kind in ['submit_buy','cancel_prepared','prepare_sell']:
   self.assertFalse(event(self.lab,kind,kind,1003)['accepted'])
  self.assertEqual(self.lab.snapshot()['cashAtomic'],100_000_000)
 def test_duplicate_receipt_has_no_second_balance_effect_conflict_halts(self):
  buy(self.lab);e={'id':'stop','kind':'halt','at':1003};a=self.lab.apply(e);self.assertEqual(self.lab.apply(e),a)
  n=self.lab.db.execute('SELECT COUNT(*) FROM events').fetchone()[0];e['at']+=1
  self.assertEqual(self.lab.apply(e)['reason'],'conflicting-idempotency-key')
  self.assertEqual(self.lab.db.execute('SELECT COUNT(*) FROM events').fetchone()[0],n)
 def test_partial_or_wrong_balance_and_wrong_transaction_halt_without_spend(self):
  prepare(self.lab);event(self.lab,'submit','submit_buy',1001)
  fields={'simulation':True,'transaction':'sim-buy-p','status':'confirmed','amountAtomic':10_000_000,'feeAtomic':0,'cashAfter':90_000_000,'tokenAfter':999}
  self.assertEqual(event(self.lab,'receipt','reconcile_buy',1002,**fields)['reason'],'unreconciled-balances')
  self.assertEqual(self.lab.snapshot()['cashAtomic'],100_000_000);self.assertEqual(self.lab.snapshot()['positions']['p']['state'],'BUY_UNKNOWN')
  fields['tokenAfter']=1000;fields['transaction']='other'
  self.assertEqual(event(self.lab,'wrong','reconcile_buy',1003,**fields)['reason'],'transaction-binding-mismatch')
 def test_no_real_receipt_or_boolean_amounts(self):
  e={'id':'bad','kind':'prepare_buy','at':1000,'position':'p','signalAt':900,'quoteAt':950,'amountAtomic':True,'quantityAtomic':1000}
  self.assertFalse(self.lab.apply(e)['accepted']);prepare(self.lab);event(self.lab,'submit','submit_buy',1001)
  self.assertEqual(event(self.lab,'actual','reconcile_buy',1002,transaction='sim-buy-p',status='unknown')['reason'],'non-simulated-receipt-refused')
 def test_stale_future_and_prepared_buy_expiration(self):
  for i,clock in enumerate([0,2000]):
   self.assertFalse(event(self.lab,'bad'+str(i),'prepare_buy',10000,signalAt=0,quoteAt=clock,amountAtomic=1,quantityAtomic=1)['accepted'])
  prepare(self.lab)
  self.assertEqual(event(self.lab,'expired','submit_buy',6000)['reason'],'prepared-buy-expired')
  self.assertTrue(event(self.lab,'cancel','cancel_prepared',6001)['accepted'])
 def test_stop_prevents_buys_but_allows_reconciliation_and_exit(self):
  buy(self.lab);event(self.lab,'stop','halt',1003)
  self.assertTrue(event(self.lab,'exit','prepare_sell',1004,quoteAt=1003,quantityAtomic=1000)['accepted'])
  self.assertTrue(event(self.lab,'send','submit_sell',1005)['accepted'])
  self.assertTrue(event(self.lab,'sold','reconcile_sell',1006,simulation=True,transaction='sim-sell-p-1',status='confirmed',proceedsAtomic=8_000_000,feeAtomic=0,cashAfter=98_000_000,tokenAfter=0)['accepted'])
  self.assertEqual(self.lab.snapshot()['grossLossAtomic'],2_000_000)
  self.assertEqual(event(self.lab,'new','prepare_buy',1007,position='q',amountAtomic=1,quantityAtomic=1,signalAt=1007,quoteAt=1007)['reason'],'new-buys-halted')
 def test_exposure_limits_reserve_pending_buy_and_release_only_cancelled(self):
  prepare(self.lab)
  self.assertTrue(event(self.lab,'q','prepare_buy',1001,position='q',amountAtomic=10_000_000,quantityAtomic=100,signalAt=1000,quoteAt=1000)['accepted'])
  self.assertEqual(event(self.lab,'r','prepare_buy',1002,position='r',amountAtomic=1,quantityAtomic=1,signalAt=1000,quoteAt=1000)['reason'],'exposure-limit')
  event(self.lab,'cancel','cancel_prepared',1003)
  self.assertTrue(event(self.lab,'r2','prepare_buy',1004,position='r',amountAtomic=1,quantityAtomic=1,signalAt=1000,quoteAt=1000)['accepted'])
 def test_failed_sell_fee_reconciles_and_next_attempt_has_new_identity(self):
  buy(self.lab);event(self.lab,'exit','prepare_sell',1003,quoteAt=1003,quantityAtomic=1000);event(self.lab,'send','submit_sell',1004)
  self.assertTrue(event(self.lab,'failed','reconcile_sell',1005,simulation=True,transaction='sim-sell-p-1',status='failed',feeAtomic=100_000,cashAfter=89_900_000,tokenAfter=1000)['accepted'])
  self.assertEqual(self.lab.snapshot()['grossLossAtomic'],100_000)
  event(self.lab,'exit2','prepare_sell',1006,quoteAt=1006,quantityAtomic=1000);event(self.lab,'send2','submit_sell',1007)
  self.assertTrue(event(self.lab,'sold','reconcile_sell',1008,simulation=True,transaction='sim-sell-p-2',status='confirmed',feeAtomic=0,proceedsAtomic=10_000_000,cashAfter=99_900_000,tokenAfter=0)['accepted'])
  self.assertEqual(self.lab.snapshot()['grossLossAtomic'],100_000);self.assertEqual(self.lab.snapshot()['positions']['p']['realizedChangeAtomic'],-100_000)
 def test_failed_buy_charges_only_reconciled_fee(self):
  prepare(self.lab);event(self.lab,'submit','submit_buy',1001)
  self.assertTrue(event(self.lab,'failed','reconcile_buy',1002,simulation=True,transaction='sim-buy-p',status='failed',feeAtomic=100_000,cashAfter=99_900_000,tokenAfter=0)['accepted'])
  self.assertEqual(self.lab.snapshot()['positions']['p']['state'],'CANCELLED');self.assertEqual(self.lab.snapshot()['grossLossAtomic'],100_000)
 def test_rejects_other_ledgers_and_never_overwrites(self):
  with self.assertRaises(FileExistsError):Lab(self.path,True)
  with self.assertRaises(ValueError):Lab(Path(self.temp.name)/'radar.sqlite',True)
  other=Path(self.temp.name)/'other.sim.sqlite';other.write_bytes(b'')
  with self.assertRaises(sqlite3.Error):Lab(other)
 def test_database_error_rolls_back_every_state_change(self):
  self.lab.db.execute("CREATE TRIGGER fail BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'test failure'); END")
  before=self.lab.snapshot()
  with self.assertRaises(sqlite3.IntegrityError):prepare(self.lab)
  self.assertEqual(self.lab.snapshot(),before)
 def test_insufficient_simulated_cash_refuses_without_reservation(self):
  state=self.lab.snapshot();state['cashAtomic']=10_000_000
  self.lab.db.execute('UPDATE state SET data=? WHERE id=1',(json.dumps(state),))
  self.assertEqual(prepare(self.lab)['reason'],'insufficient-cash');self.assertEqual(self.lab.snapshot()['positions'],{})
 def test_loss_limit_blocks_new_entries_but_not_required_exits(self):
  for i in range(2):
   pid='loss'+str(i);at=1000+i*20
   for key,kind,extra in [('p','prepare_buy',dict(amountAtomic=10_000_000,quantityAtomic=1000,signalAt=at,quoteAt=at)),('s','submit_buy',{}),('b','reconcile_buy',dict(simulation=True,transaction='sim-buy-'+pid,status='confirmed',amountAtomic=10_000_000,feeAtomic=0,cashAfter=90_000_000-i*10_000_000,tokenAfter=1000)),('e','prepare_sell',dict(quoteAt=at+3,quantityAtomic=1000)),('x','submit_sell',{}),('r','reconcile_sell',dict(simulation=True,transaction='sim-sell-'+pid+'-1',status='confirmed',proceedsAtomic=0,feeAtomic=0,cashAfter=90_000_000-i*10_000_000,tokenAfter=0))]:
    self.assertTrue(event(self.lab,pid+key,kind,at,position=pid,**extra)['accepted']);at+=1
  self.assertEqual(self.lab.snapshot()['grossLossAtomic'],20_000_000)
  self.assertEqual(event(self.lab,'new','prepare_buy',2000,position='new',amountAtomic=1,quantityAtomic=1,signalAt=2000,quoteAt=2000)['reason'],'loss-limit')
 def test_unknown_sell_survives_restart_and_prepared_sell_expires(self):
  buy(self.lab);event(self.lab,'exit','prepare_sell',1003,quoteAt=1003,quantityAtomic=1000)
  self.assertEqual(event(self.lab,'late','submit_sell',7000)['reason'],'prepared-sell-expired')
  event(self.lab,'cancel','cancel_prepared',7001);event(self.lab,'again','prepare_sell',7002,quoteAt=7002,quantityAtomic=1000);event(self.lab,'send','submit_sell',7003)
  self.lab.close();self.lab=Lab(self.path)
  self.assertEqual(self.lab.snapshot()['positions']['p']['state'],'SELL_UNKNOWN')
  self.assertFalse(event(self.lab,'retry','submit_sell',7004)['accepted'])
  self.assertFalse(event(self.lab,'cancel-unknown','cancel_prepared',7005)['accepted'])
 def test_driver_runs_offline_scenarios(self):
  r=scenarios();self.assertEqual(r['transactionsSent'],0);self.assertTrue(all(s['passed'] for s in r['scenarios']))
if __name__=='__main__':unittest.main()
