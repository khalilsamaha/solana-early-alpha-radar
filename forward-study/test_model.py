import copy,gzip,json,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from audit import PROTOCOL,build,digest
from test_audit import sample
from model import freeze,evaluate,fit,predict,seal,read_artifact,paired_interval

def training():
 data=build([sample()]);template=data['rows'][0];start=template['signalAt'];data['rows']=[]
 for i in range(120):
  r=copy.deepcopy(template);r.update(id=str(i),seq=i+1,mint='train'+str(i),signalAt=start+i*3600000,utcDay='2026-10-'+str(10+i//24));r['targets']['30000'].update(returnPct=20 if i%2 else -20,availableAt=r['signalAt']+31000);r['supplementalEntryContext']['predictors']['liquidityUsd']=100+i%7;r['predictors']['return30sPct']=i%5;r['supplementalEntryContext']['predictors']['organicScore']=i%13;data['rows'].append(r)
 data['capturedAt']=data['rows'][-1]['signalAt']+32000
 now=data['capturedAt']+600000;reg={'format':'forward-protocol-registration-1','protocolSha256':digest(PROTOCOL),'registeredAt':now-1}
 return data,reg,now
class ModelTests(unittest.TestCase):
 def test_freeze_separate_targets_guard_failure_classes(self):
  data,reg,now=training();a=freeze(data,reg,now);self.assertTrue(a['modelFrozen']);self.assertIsNotNone(a['groups'][0]['models']);self.assertIsNone(a['groups'][1]['models']);self.assertIn('class-count',a['groups'][1]['blockingReasons'])
 def test_availability_fit_is_independent_of_return_fit(self):
  data,reg,now=training()
  for i,r in enumerate(data['rows']):
   if i%2:
    r['exitAvailability']['30000']='provider-reported-quote-failure'
    r['targets']['30000'].update(state='sell-quote-failed',returnPct=None,onTime=None)
  a=freeze(data,reg,now)
  self.assertIsNone(a['groups'][0]['models']);self.assertIsNotNone(a['groups'][1]['models'])
  self.assertEqual(a['groups'][1]['classes'],{'0':60,'1':60})
 def test_train_only_transform_and_serialization_have_stable_predictions(self):
  data,reg,now=training();rows=data['rows'];y=[i%2 for i in range(len(rows))];w=fit(rows,y,'baseline','context');p=predict(rows,'baseline','context',w)
  self.assertEqual(len(p),120);self.assertTrue(np.isfinite(p).all());self.assertGreater(np.std(p),0)
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'model.json.gz';a=freeze(data,reg,now);path.write_bytes(gzip.compress(json.dumps(seal(a)).encode()));b=read_artifact(path)
   self.assertEqual(a,b);self.assertTrue(np.allclose(p,predict(rows,'baseline','context',b['groups'][0]['models']['context'])))
   altered=seal(a);altered['frozenAt']+=1;path.write_bytes(gzip.compress(json.dumps(altered).encode()))
   with self.assertRaisesRegex(ValueError,'integrity'):read_artifact(path)
 def test_future_evaluation_labels_never_change_frozen_weights(self):
  data,reg,now=training();a=freeze(data,reg,now);before=copy.deepcopy(a);test=copy.deepcopy(data);r=test['rows'][0];r.update(mint='new',signalAt=now+400000);r['targets']['30000']['availableAt']=now+431000;test['rows']=[r];test['capturedAt']=now+500000
  out=evaluate(test,a);r['targets']['30000']['returnPct']=-999;changed=evaluate(test,a)
  self.assertEqual(a,before);self.assertEqual(out['groups'][0]['predictions'][0]['probabilities'],changed['groups'][0]['predictions'][0]['probabilities']);self.assertFalse(out['modelRefitted'])
 def test_training_tokens_embargo_and_repeated_forward_mints_excluded(self):
  data,reg,now=training();a=freeze(data,reg,now);test=copy.deepcopy(data);r=copy.deepcopy(test['rows'][0]);test['rows']=[]
  for i,(mint,at) in enumerate([('train0',now+400000),('new',now+200000),('fresh',now+400000),('fresh',now+500000)]):
   x=copy.deepcopy(r);x.update(id='t'+str(i),seq=1000+i,mint=mint,signalAt=at);test['rows'].append(x)
  out=evaluate(test,a)['groups'][0];self.assertEqual(out['forwardWatches'],1);self.assertEqual(out['excluded'],{'before-freeze-plus-embargo':1,'token-seen-in-training-period':1,'repeat-forward-token':1})
 def test_quote_failure_remains_in_prediction_and_selected_denominators(self):
  data,reg,now=training();a=freeze(data,reg,now);test=copy.deepcopy(data);r=test['rows'][0];r.update(mint='new',signalAt=now+400000);r['exitAvailability']['30000']='provider-reported-quote-failure';test['rows']=[r]
  out=evaluate(test,a)['groups'][0];self.assertEqual(out['metrics']['context']['unknown'],1);self.assertEqual(len(out['predictions']),1);self.assertEqual(out['allForwardOutcomes']['30000']['onTimeReturned'],0)
 def test_future_input_clock_and_registration_protocol_refused(self):
  data,reg,now=training();data['capturedAt']=now+1
  with self.assertRaises(ValueError):freeze(data,reg,now)
  data['capturedAt']=now-1;reg['protocolSha256']='wrong'
  with self.assertRaises(ValueError):freeze(data,reg,now)
 def test_train_label_after_cutoff_excluded(self):
  data,reg,now=training();data['rows'][0]['targets']['30000']['availableAt']=now+1
  self.assertEqual(freeze(data,reg,now)['groups'][0]['trainingRows'],119)
 def test_wrong_model_dimensions_and_source_rejected(self):
  data,reg,now=training();a=freeze(data,reg,now);bad=copy.deepcopy(a['groups'][0]['models']['context']);bad['scale']=[0]
  with self.assertRaises(ValueError):predict(data['rows'],'baseline','context',bad)
  data['sourceIdentity']='other'
  with self.assertRaises(ValueError):evaluate(data,a)
 def test_bootstrap_requires_distinct_days_and_is_repeatable(self):
  data,_,_=training();rows=data['rows'];small=paired_interval(rows,[.5]*120,[.5]*120,'positiveReturnedQuote');self.assertEqual(small['state'],'insufficient-days')
  for i,r in enumerate(rows):r['utcDay']='2026-10-'+str(10+i%8)
  out=paired_interval(rows,[.5]*120,[.5]*120,'positiveReturnedQuote');self.assertEqual(out['interval95'],[0,0]);self.assertEqual(out,paired_interval(rows,[.5]*120,[.5]*120,'positiveReturnedQuote'))
if __name__=='__main__':unittest.main()
