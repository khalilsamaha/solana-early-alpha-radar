"""Simulation-only state machine. No RPC, network, wallet, signing or order adapter."""
import copy,hashlib,json,os,re,sqlite3
from pathlib import Path
VERSION='execution-simulation-1'
LIMITS={'initialCashAtomic':100_000_000,'maxOrderAtomic':10_000_000,'maxExposureAtomic':20_000_000,
 'maxPositions':2,'maxGrossLossAtomic':20_000_000,'maxFeeAtomic':100_000,'maxSignalAgeMs':15000,'maxQuoteAgeMs':5000,'maxEvents':500}
ACTIVE={'BUY_PREPARED','BUY_UNKNOWN','OPEN','SELL_PREPARED','SELL_UNKNOWN'}
def integer(v):return type(v) is int and 0<=v<=2**63-1
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
class Refused(Exception):pass
class Uncertain(Exception):pass
class Lab:
 def __init__(self,path,create=False):
  self.path=Path(path)
  if self.path.is_symlink() or not self.path.name.endswith('.sim.sqlite'):raise ValueError('Use a dedicated .sim.sqlite file')
  if create:
   fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
  elif not self.path.is_file():raise ValueError('Simulation ledger missing')
  if self.path.stat().st_size>8*1024*1024:raise ValueError('Simulation ledger size cap')
  self.db=sqlite3.connect(self.path,timeout=3,isolation_level=None)
  try:
   if create:
    self.db.executescript('BEGIN; CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL); CREATE TABLE events (seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, digest TEXT NOT NULL, event TEXT NOT NULL, result TEXT NOT NULL); COMMIT;')
    self.db.execute('INSERT INTO state VALUES(1,?)',(json.dumps({'version':VERSION,'simulationOnly':True,'limits':LIMITS,'cashAtomic':LIMITS['initialCashAtomic'],'grossLossAtomic':0,'haltReason':None,'lastAt':0,'positions':{}}),))
   s=self.snapshot()
   if s.get('version')!=VERSION or s.get('simulationOnly') is not True or s.get('limits')!=LIMITS:raise ValueError('Not a supported simulation ledger')
  except BaseException:self.db.close();raise
 def close(self):self.db.close()
 def snapshot(self):return json.loads(self.db.execute('SELECT data FROM state WHERE id=1').fetchone()[0])
 def apply(self,e):
  raw=json.dumps(e,sort_keys=True,separators=(',',':'),allow_nan=False)
  if len(raw)>4096 or not isinstance(e,dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',str(e.get('id',''))) or not integer(e.get('at')):raise ValueError('Invalid simulation event')
  self.db.execute('BEGIN IMMEDIATE')
  try:
   old=self.db.execute('SELECT digest,result FROM events WHERE id=?',(e['id'],)).fetchone();s=self.snapshot()
   if old:
    if old[0]==digest(e):self.db.execute('COMMIT');return json.loads(old[1])
    s['haltReason']='conflicting-idempotency-key';self.db.execute('UPDATE state SET data=? WHERE id=1',(json.dumps(s),));self.db.execute('COMMIT');return {'accepted':False,'reason':s['haltReason'],'simulationOnly':True}
   if self.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]>=LIMITS['maxEvents']:raise ValueError('Simulation event cap')
   next_state=copy.deepcopy(s)
   try:
    if e['at']<s['lastAt']:raise Refused('backwards-clock')
    self._reduce(next_state,e);next_state['lastAt']=e['at'];s=next_state
    result={'accepted':True,'simulationOnly':True}
   except Refused as error:result={'accepted':False,'reason':str(error),'simulationOnly':True}
   except Uncertain as error:s['haltReason']=str(error);result={'accepted':False,'reason':str(error),'simulationOnly':True}
   self.db.execute('UPDATE state SET data=? WHERE id=1',(json.dumps(s),))
   self.db.execute('INSERT INTO events(id,digest,event,result) VALUES(?,?,?,?)',(e['id'],digest(e),raw,json.dumps(result)))
   self.db.execute('COMMIT');return result
  except BaseException:self.db.execute('ROLLBACK');raise
 def _reduce(self,s,e):
  k=e.get('kind')
  if k=='halt':s['haltReason']='manual-stop';return
  pid=e.get('position')
  if not isinstance(pid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',pid):raise Refused('invalid-position-id')
  p=s['positions'].get(pid)
  if k=='prepare_buy':
   if s['haltReason']:raise Refused('new-buys-halted')
   if p:raise Refused('position-already-recorded')
   if s['grossLossAtomic']>=LIMITS['maxGrossLossAtomic']:raise Refused('loss-limit')
   if not all(integer(e.get(x)) for x in ('amountAtomic','quantityAtomic','signalAt','quoteAt')):raise Refused('invalid-buy-fields')
   amount=e['amountAtomic'];quantity=e['quantityAtomic']
   if not 0<amount<=LIMITS['maxOrderAtomic'] or quantity<=0:raise Refused('order-limit-or-quantity')
   if not e['signalAt']<=e['quoteAt']<=e['at'] or e['at']-e['signalAt']>LIMITS['maxSignalAgeMs'] or e['at']-e['quoteAt']>LIMITS['maxQuoteAgeMs']:raise Refused('stale-or-future-buy')
   active=[p for p in s['positions'].values() if p['state'] in ACTIVE];reserved=sum(p['amountAtomic']+LIMITS['maxFeeAtomic'] for p in active if p['state'].startswith('BUY'))
   exposure=sum(p['amountAtomic'] for p in active)
   if len(active)>=LIMITS['maxPositions'] or exposure+amount>LIMITS['maxExposureAtomic']:raise Refused('exposure-limit')
   if s['cashAtomic']-reserved<amount+LIMITS['maxFeeAtomic']:raise Refused('insufficient-cash')
   s['positions'][pid]={'state':'BUY_PREPARED','amountAtomic':amount,'quantityAtomic':quantity,'costAtomic':None,'failedExitFeesAtomic':0,'validUntil':min(e['signalAt']+LIMITS['maxSignalAgeMs'],e['quoteAt']+LIMITS['maxQuoteAgeMs']),'buyTransaction':'sim-buy-'+pid,'sellTransaction':None,'sellAttempts':0};return
  if p is None:raise Refused('position-not-found')
  if k=='submit_buy':
   if s['haltReason']:raise Refused('new-buys-halted')
   if p['state']!='BUY_PREPARED':raise Refused('buy-not-prepared')
   if e['at']>p['validUntil']:raise Refused('prepared-buy-expired')
   p['state']='BUY_UNKNOWN';return
  if k=='prepare_sell':
   if p['state']!='OPEN':raise Refused('position-not-open')
   if not integer(e.get('quoteAt')) or not e['quoteAt']<=e['at']<=e['quoteAt']+LIMITS['maxQuoteAgeMs']:raise Refused('stale-or-future-sell')
   if type(e.get('quantityAtomic')) is not int or e['quantityAtomic']!=p['quantityAtomic']:raise Refused('sell-quantity-mismatch')
   p['state']='SELL_PREPARED';p['validUntil']=e['quoteAt']+LIMITS['maxQuoteAgeMs'];p['sellAttempts']+=1;p['sellTransaction']='sim-sell-'+pid+'-'+str(p['sellAttempts']);return
  if k=='submit_sell':
   if p['state']!='SELL_PREPARED':raise Refused('sell-not-prepared')
   if e['at']>p['validUntil']:raise Refused('prepared-sell-expired')
   p['state']='SELL_UNKNOWN';return
  if k=='cancel_prepared':
   if p['state']=='BUY_PREPARED':p['state']='CANCELLED'
   elif p['state']=='SELL_PREPARED':p['state']='OPEN'
   else:raise Refused('cannot-cancel-uncertain-or-open-position')
   return
  if k in ('reconcile_buy','reconcile_sell'):
   buy=k=='reconcile_buy';expected='BUY_UNKNOWN' if buy else 'SELL_UNKNOWN'
   if p['state']!=expected:raise Refused('no-uncertain-submission')
   if e.get('simulation') is not True:raise Uncertain('non-simulated-receipt-refused')
   if e.get('transaction')!=p['buyTransaction' if buy else 'sellTransaction']:raise Uncertain('transaction-binding-mismatch')
   status=e.get('status')
   if status=='unknown':return
   # Every terminal receipt, including a failure, requires balance reconciliation.
   if status not in ('confirmed','failed'):raise Uncertain('unsupported-receipt-status')
   if not all(integer(e.get(x)) for x in ('feeAtomic','cashAfter','tokenAfter')) or e['feeAtomic']>LIMITS['maxFeeAtomic']:raise Uncertain('invalid-receipt-balances')
   fee=e['feeAtomic']
   if status=='failed':
    cash=s['cashAtomic']-fee;tokens=0 if buy else p['quantityAtomic']
   elif buy:
    if type(e.get('amountAtomic')) is not int or e['amountAtomic']!=p['amountAtomic']:raise Uncertain('buy-amount-mismatch')
    cash=s['cashAtomic']-p['amountAtomic']-fee;tokens=p['quantityAtomic']
   else:
    if not integer(e.get('proceedsAtomic')):raise Uncertain('invalid-sell-proceeds')
    cash=s['cashAtomic']+e['proceedsAtomic']-fee;tokens=0
   if cash<0 or e['cashAfter']!=cash or e['tokenAfter']!=tokens:raise Uncertain('unreconciled-balances')
   s['cashAtomic']=cash
   if status=='failed':
    p['state']='CANCELLED' if buy else 'OPEN'
    if buy:s['grossLossAtomic']+=fee
    else:p['failedExitFeesAtomic']+=fee;s['grossLossAtomic']+=fee
   elif buy:p['state']='OPEN';p['costAtomic']=p['amountAtomic']+fee
   else:
    p['state']='CLOSED';p['realizedChangeAtomic']=e['proceedsAtomic']-fee-p['costAtomic']-p['failedExitFeesAtomic'];s['grossLossAtomic']+=max(0,p['costAtomic']+fee-e['proceedsAtomic'])
   return
  raise Refused('unsupported-event')
