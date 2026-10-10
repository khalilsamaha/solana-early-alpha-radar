import unittest,copy,tempfile,sqlite3,json,time
from pathlib import Path
from quality_report import shadow_summary,quote_movements,capture
class Tests(unittest.TestCase):
 def data(self):return {'fast-shadow-entries':[{'id':'e','at':100000}],'fast-shadow-outcomes':[],'fast-shadow-links':[],'cutoffAt':120000}
 def quotes(self):
  buy={'leg':'buy','status':'quoted','outAmount':'100'}
  def sell(off,out):return {'leg':'sell','status':'quoted','targetOffsetMs':off,'inputMint':'mint','outputMint':'usdc','inAmount':'100','outAmount':str(out),'startedAt':100000+off,'receivedAt':100050+off}
  return {'format':'quote-observer-report-0.2.0','sourceIdentity':'source','probes':[{'baseMint':'usdc','signal':{'seq':1,'entryId':'e','mint':'mint','cohort':'baseline','signalAt':90000},'observations':[buy,sell(0,1000),sell(30000,500),sell(60000,1500)]}]}
 def test_pending_overdue_missing_gapped_distinct(self):
  d=self.data();self.assertEqual(shadow_summary(d)['horizons']['30s']['states'],{'pending':1});d['cutoffAt']=200000
  self.assertEqual(shadow_summary(d)['horizons']['30s']['states'],{'overdue':1})
  d['fast-shadow-outcomes']=[{'entryId':'e','horizon':'30s','status':'missing'}]
  self.assertEqual(shadow_summary(d)['horizons']['30s']['states'],{'missing':1})
  d['fast-shadow-outcomes'][0].update(status='observed',coverage='gapped',returnPct=999)
  self.assertIsNone(shadow_summary(d)['horizons']['30s']['meanGrossPriceChangePct'])
 def test_zero_not_missing_and_duplicate_refused(self):
  d=self.data();d['fast-shadow-outcomes']=[{'entryId':'e','horizon':'30s','status':'observed','coverage':'sampled','returnPct':0}]
  self.assertEqual(shadow_summary(d)['horizons']['30s']['meanGrossPriceChangePct'],0)
  d['fast-shadow-outcomes']*=2
  with self.assertRaises(ValueError):shadow_summary(d)
 def test_fixed_quantity_normalization_and_actual_clock(self):
  q=self.quotes();before=copy.deepcopy(q);r=quote_movements(q);i=r['cases'][0]['intervals']
  self.assertEqual(i[0]['quotedProceedsChangePct'],-50);self.assertEqual(i[1]['quotedProceedsChangePct'],200);self.assertEqual(i[1]['elapsedRequestMs'],30000);self.assertEqual(q,before)
 def test_failed_interval_not_imputed_or_bridged(self):
  q=self.quotes();q['probes'][0]['observations'][2]['status']='failed';i=quote_movements(q)['cases'][0]['intervals']
  self.assertTrue(all(x['state']=='unavailable' for x in i))
 def test_quantity_mint_and_clock_mismatch_remain_unavailable(self):
  for field,value in [('inAmount','99'),('outputMint','other'),('startedAt',1),('outAmount','0')]:
   q=self.quotes();q['probes'][0]['observations'][2][field]=value
   self.assertEqual(quote_movements(q)['cases'][0]['intervals'][0]['state'],'unavailable')
 def test_duplicate_probe_or_offset_rejected(self):
  q=self.quotes();q['probes']*=2
  with self.assertRaises(ValueError):quote_movements(q)
  q=self.quotes();q['probes'][0]['observations'].append(q['probes'][0]['observations'][1])
  with self.assertRaises(ValueError):quote_movements(q)
 def test_readonly_capture_excludes_unrelated_and_preserves_db(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'db.sqlite';now=int(time.time()*1000)
   with sqlite3.connect(p) as db:
    db.executescript('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,at INTEGER,data TEXT); CREATE INDEX events_at ON events(kind,at); CREATE TABLE kv(key TEXT PRIMARY KEY,data TEXT);')
    db.execute('INSERT INTO events VALUES(1,?,?,?)',('fast-shadow-entries',now,json.dumps({'id':'e','at':now})))
    db.execute('INSERT INTO events VALUES(2,?,?,?)',('outbox',now,'do not read'))
   before=p.read_bytes();r=capture(p);self.assertEqual(len(r['fast-shadow-entries']),1);self.assertEqual(before,p.read_bytes())
 def test_missing_registration_is_visible(self):
  d=self.data();d['fast-shadow-entries']=[];self.assertEqual(shadow_summary(d)['entries'],0)
if __name__=='__main__':unittest.main()
