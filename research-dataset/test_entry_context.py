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
