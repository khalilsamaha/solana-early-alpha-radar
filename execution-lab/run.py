#!/usr/bin/env python3
"""Run synthetic fault scenarios in temporary simulation ledgers; save only a report."""
import argparse,hashlib,json,sys,tempfile
from pathlib import Path
from engine import Lab,LIMITS,VERSION
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish

def event(lab,key,kind,at,**kwargs):return lab.apply({'id':key,'kind':kind,'at':at,'position':'p',**kwargs})
def prepare(lab):
 return event(lab,'prepare','prepare_buy',1000,amountAtomic=10_000_000,quantityAtomic=1000,signalAt=900,quoteAt=950)
def buy(lab):
 assert prepare(lab)['accepted'];assert event(lab,'submit','submit_buy',1001)['accepted']
 assert event(lab,'buy-result','reconcile_buy',1002,simulation=True,transaction='sim-buy-p',status='confirmed',amountAtomic=10_000_000,feeAtomic=0,cashAfter=90_000_000,tokenAfter=1000)['accepted']
def scenarios():
 results=[]
 with tempfile.TemporaryDirectory(prefix='radar-simulation-') as temp:
  path=Path(temp)/'unknown.sim.sqlite';l=Lab(path,True);prepare(l);event(l,'submit','submit_buy',1001)
  event(l,'timeout','reconcile_buy',1002,simulation=True,transaction='sim-buy-p',status='unknown');l.close();l=Lab(path)
  refused=event(l,'retry','submit_buy',1003);assert not refused['accepted'];assert l.snapshot()['positions']['p']['state']=='BUY_UNKNOWN'
  results.append({'scenario':'restart-after-uncertain-buy','passed':True,'state':l.snapshot()['positions']['p']['state'],'retry':refused});l.close()
  l=Lab(Path(temp)/'mismatch.sim.sqlite',True);prepare(l);event(l,'submit','submit_buy',1001)
  bad=event(l,'bad','reconcile_buy',1002,simulation=True,transaction='sim-buy-p',status='confirmed',amountAtomic=10_000_000,feeAtomic=0,cashAfter=90_000_001,tokenAfter=1000)
  assert not bad['accepted'];assert l.snapshot()['cashAtomic']==100_000_000
  results.append({'scenario':'balance-mismatch-halts-buying','passed':True,'haltReason':l.snapshot()['haltReason']});l.close()
  l=Lab(Path(temp)/'stop.sim.sqlite',True);buy(l);event(l,'stop','halt',1003)
  assert event(l,'exit','prepare_sell',1004,quoteAt=1003,quantityAtomic=1000)['accepted'];event(l,'send-exit','submit_sell',1005)
  receipt={'id':'sold','kind':'reconcile_sell','at':1006,'position':'p','simulation':True,'transaction':'sim-sell-p-1','status':'confirmed','proceedsAtomic':8_000_000,'feeAtomic':100_000,'cashAfter':97_900_000,'tokenAfter':0}
  assert l.apply(receipt)['accepted'];before=l.snapshot();l.apply(receipt);assert l.snapshot()==before
  results.append({'scenario':'stop-allows-exit-and-duplicate-receipt-is-idempotent','passed':True,'finalState':l.snapshot()});l.close()
 return {'format':VERSION,'simulationOnly':True,'scenarios':results,'limits':LIMITS,'networkRequests':0,'transactionsSent':0,
  'implementationSha256':hashlib.sha256(Path(__file__).with_name('engine.py').read_bytes()).hexdigest(),
  'limitations':['Synthetic receipts and balances only, not Solana transaction simulation or execution.',
   'No RPC, signing, provider integration, fees estimate or live kill switch exists in this harness.',
   'Passing scenarios does not prove profitability, on-chain reliability or live-trading readiness.',
   'Full-quantity single-position receipts only; unexpected partial/external balances halt for reconciliation.']}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();report=scenarios();publish(a.output,report)
 print('SIMULATION ONLY:',len(report['scenarios']),'scenarios passed; 0 transactions; 0 network requests.');print('Report:',a.output.resolve())
if __name__=='__main__':main()
