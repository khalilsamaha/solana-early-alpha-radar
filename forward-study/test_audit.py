import copy,datetime as dt,gzip,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from audit import PROTOCOL,assess,features,eligibility,labels,digest,build
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research-dataset'))
from test_dataset import fixture
import test_entry_context as context_fixture

def sample():
 q=fixture();s=context_fixture.ContextTests().signal()
 for x in [q['signals'][0],q['probes'][0]['signal']]:x['entryContext']=copy.deepcopy(s['entryContext'])
 return q
class AuditTests(unittest.TestCase):
 def test_rebuild_compatible_context_and_preserve_unknown_metadata(self):
  r=build([sample()]);row=r['rows'][0];self.assertEqual(eligibility(row),'compatible')
  x=features(row);self.assertEqual(x['liquidityUsd'],0);self.assertIsNone(x['organicScore']);self.assertIsNone(x['organicAgeMs']);self.assertIsNone(x['freezeAuthorityActive'])
  a=assess(r);g=a['cohorts'][0];self.assertEqual(g['compatibleAdmitted'],1);self.assertFalse(g['targets']['positiveReturnedQuote']['fitGuardsPassed'])
 def test_no_identity_post_entry_price_or_label_becomes_feature(self):
  row=build([sample()])['rows'][0];x=features(row);other=copy.deepcopy(row)
  other['targets']['30000']['returnPct']=-99;other['mint']='changed';other['seq']=999;other['exitAvailability']['30000']='transport-or-service-failure'
  self.assertEqual(features(other),x);self.assertEqual(set(x),set(PROTOCOL['features']))
  self.assertFalse({'seq','signalAt','mint','returnPct','buyQuoteState'}&set(x))
 def test_both_targets_keep_transport_missing_and_late_unknown(self):
  r=build([sample()])['rows'][0]
  self.assertEqual(labels(r),{'positiveReturnedQuote':1,'exitQuoteAvailable':1})
  r['exitAvailability']['30000']='provider-reported-quote-failure';self.assertEqual(labels(r),{'positiveReturnedQuote':None,'exitQuoteAvailable':0})
  for state in ['missing-observation','interrupted','late-validated-quote','transport-or-service-failure','no-validated-buy','not-admitted']:
   r['exitAvailability']['30000']=state;self.assertEqual(labels(r),{'positiveReturnedQuote':None,'exitQuoteAvailable':None})
 def test_old_and_invalid_context_excluded_without_backfill(self):
  r=build([fixture()])['rows'][0];self.assertEqual(eligibility(r),'missing-or-invalid-entry-context')
  r=build([sample()])['rows'][0];r['supplementalEntryContext']['metadataProvenance']['fields']['organicScore']['state']='invalid'
  self.assertEqual(eligibility(r),'invalid-metadata-provenance')
 def test_skipped_signals_do_not_supply_training_labels(self):
  q=sample();q['probes']=[];q['signals'][0]['decision']='observer-busy';r=assess(build([q]))
  self.assertEqual(r['cohorts'][0]['compatibleSignals'],1);self.assertEqual(r['cohorts'][0]['compatibleAdmitted'],0)
 def test_fit_guards_need_classes_days_and_count_independently(self):
  d=build([sample()]);r=d['rows'][0]
  d['rows']=[]
  for i in range(100):
   x=copy.deepcopy(r);x['id']=str(i);x['utcDay']='2026-10-'+str(16+i%3);x['targets']['30000']['returnPct']=1 if i%2 else -1;d['rows'].append(x)
  a=assess(d)['cohorts'][0]['targets'];self.assertTrue(a['positiveReturnedQuote']['fitGuardsPassed']);self.assertFalse(a['exitQuoteAvailable']['fitGuardsPassed'])
  for x in d['rows']:x['utcDay']='2026-10-16'
  self.assertIn('too-few-distinct-utc-days',assess(d)['cohorts'][0]['targets']['positiveReturnedQuote']['blockingReasons'])
 def test_registration_binds_protocol_but_is_not_model_freeze(self):
  r=build([sample()]);reg={'format':'forward-protocol-registration-1','protocolSha256':digest(PROTOCOL),'registeredAt':123}
  out=assess(r,reg);self.assertFalse(out['modelTrained']);self.assertFalse(out['liveUseAllowed']);reg['protocolSha256']='wrong'
  with self.assertRaisesRegex(ValueError,'Registration mismatch'):assess(r,reg)
 def test_real_cli_register_and_source_audit_refuse_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);src=root/'source.json.gz';src.write_bytes(gzip.compress(json.dumps(sample()).encode()));reg=root/'registration.json.gz';out=root/'audit.json.gz';script=Path(__file__).with_name('audit.py')
   subprocess.run([sys.executable,str(script),'register','--output',str(reg)],check=True,capture_output=True)
   args=[sys.executable,str(script),'audit','--source',str(src),'--registration',str(reg),'--output',str(out)]
   subprocess.run(args,check=True,capture_output=True);result=json.loads(gzip.decompress(out.read_bytes()));self.assertEqual(result['cohorts'][0]['compatibleAdmitted'],1)
   self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)
   # A derived dataset is not an original source export.
   src.write_bytes(gzip.compress(json.dumps(build([sample()])).encode()));args[-1]=str(root/'wrong.json.gz')
   self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0);self.assertFalse((root/'wrong.json.gz').exists())
if __name__=='__main__':unittest.main()
