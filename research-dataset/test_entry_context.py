import copy,json,subprocess,unittest
from pathlib import Path
from entry_context import context
from build import build,merge
from test_dataset import fixture
ROOT=Path(__file__).resolve().parents[1]
class ContextTests(unittest.TestCase):
 def signal(self):
  s=fixture()['signals'][0]
  # Use the actual scanner serializer as a cross-language contract fixture.
  script="import {captureEntryContext} from './scanner/src/core/entry-context.js';const s=JSON.parse(process.argv[1]); console.log(JSON.stringify({state:'recorded',data:captureEntryContext({mint:s.mint,pairAddress:s.originalPool,liquidityUsd:0,volume:{m5:200},txns:{m5:{buys:10,sells:10}},marketObservedAt:s.signalAt-1,securityCheckedAt:s.signalAt-400000,mintAuthority:null},s.signalAt,{freshMs:120000,securityTtlMs:300000})}));"
  s['entryContext']=json.loads(subprocess.check_output(['node','--input-type=module','-e',script,json.dumps(s)],cwd=ROOT))
  return s
 def test_scanner_serialization_and_python_validation_agree(self):
  s=self.signal();out=context(s)
  self.assertEqual(out['state'],'recorded');self.assertEqual(out['predictors']['transactions5m'],20)
  self.assertEqual(out['predictors']['averageReportedTradeUsd'],10);self.assertEqual(out['predictors']['liquidityUsd'],0)
  self.assertEqual(out['clockStates']['securityCheckedAt'],'stale');self.assertIsNone(out['predictors']['freezeAuthorityActive'])
 def test_future_wrong_identity_malformed_and_false_freshness_rejected(self):
  s=self.signal()
  for mutate in [lambda d:d.update(signalAt=s['signalAt']+1),lambda d:d.update(pairAddress='other'),
                 lambda d:d['clocks']['securityCheckedAt'].update(state='within-ttl'),
                 lambda d:d['values']['buys5m'].update(value=True),lambda d:d['authorities'].pop('mintAuthority')]:
   x=copy.deepcopy(s);mutate(x['entryContext']['data']);self.assertEqual(context(x)['state'],'invalid')
  self.assertEqual(context({})['state'],'absent');self.assertEqual(context({'entryContext':[]})['state'],'invalid')
 def test_additive_fields_leave_frozen_predictors_and_targets_unchanged(self):
  q=fixture();old=build([q]);s=self.signal()
  for x in [q['signals'][0],q['probes'][0]['signal']]:x['entryContext']=copy.deepcopy(s['entryContext'])
  new=build([q]);self.assertEqual(new['rows'][0]['predictors'],old['rows'][0]['predictors'])
  self.assertEqual(new['rows'][0]['targets'],old['rows'][0]['targets'])
  self.assertEqual(new['rows'][0]['supplementalEntryContext']['state'],'recorded')
 def test_conflicting_context_is_not_silently_deduplicated(self):
  q=fixture();s=self.signal()
  for x in [q['signals'][0],q['probes'][0]['signal']]:x['entryContext']=copy.deepcopy(s['entryContext'])
  other=copy.deepcopy(q)
  for x in [other['signals'][0],other['probes'][0]['signal']]:x['entryContext']['data']['values']['liquidityUsd']['value']=1
  with self.assertRaisesRegex(ValueError,'immutable'):merge([q,other])
  q['probes'][0]['signal']['entryContext']['state']='invalid'
  with self.assertRaises(ValueError):build([q])

class MetadataTests(unittest.TestCase):
 def test_metadata_ages_are_per_field_and_never_replace_dedicated_check_clock(self):
  s=ContextTests().signal();d=s['entryContext']['data'];at=s['signalAt']
  for key,v in [('organicScore',12),('holderCount',20)]:d['values'][key]={'value':v,'state':'recorded'}
  d['metadataProvenance']={'version':'metadata-provenance-1','fields':{
   'organicScore':{'state':'recorded','value':12,'source':'jupiter:recent','receivedAt':at-100,'appliedAt':at-99,'ageMs':100},
   'holderCount':{'state':'recorded','value':20,'source':'jupiter:top-organic','receivedAt':at-200,'appliedAt':at-199,'ageMs':200}}}
  out=context(s);self.assertIsNone(out['predictors']['jupiterCheckedAtAgeMs'])
  self.assertEqual(out['metadataProvenance']['fields']['organicScore']['ageMs'],100)
  self.assertEqual(out['metadataProvenance']['fields']['holderCount']['ageMs'],200)
  for mutate in [lambda x:x.update(value=13),lambda x:x.update(receivedAt=at+1),lambda x:x.update(ageMs=0),lambda x:x.update(source='other'),lambda x:x.update(source={'unexpected':'shape'})]:
   bad=copy.deepcopy(s);mutate(bad['entryContext']['data']['metadataProvenance']['fields']['organicScore'])
   self.assertEqual(context(bad)['metadataProvenance']['fields']['organicScore']['state'],'invalid')
   self.assertEqual(context(bad)['state'],'recorded')
