import copy
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import confirmation as s
from audit import digest, publish
from model import freeze, seal
from test_model import training
from failure_audit import analyze
from model import evaluate as old_evaluate


class StudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data, reg, now = training()
        for i, r in enumerate(data['rows']):
            r['cohort'] = 'early-activity'
            if i % 2:
                r['exitAvailability']['30000'] = 'provider-reported-quote-failure'
                r['targets']['30000'].update(state='sell-quote-failed',returnPct=None,onTime=None)
        cls.model = freeze(data, reg, now)
        cls.train = data
        cls.now = now+s.DAY

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.old = self.root/'old'; self.new = self.root/'new'
        self.capture = self.root/'capture'; self.capture.mkdir()
        (self.capture/'capture-index.json.gz').write_bytes(gzip.compress(b'{"fixture":1}'))
        self.source = self.root/'source.gz'; publish(self.source,seal(self.model))
        self.pins = patch.object(s.frozen,'ARTIFACT_SHA256',digest(self.model)); self.pins.start(); self.addCleanup(self.pins.stop)
        s.frozen.install(self.source,self.old,self.model['frozenAt'])
        _, self.old_reg = s.frozen.load(self.old,self.now)
        self.data = copy.deepcopy(self.train)
        self.data['capturedAt'] = self.now-1000
        self.evidence = dict(inputs=[{'indexSha256':s.index_hash(self.capture)}],coveredIntervals=[],captureCount=1)
        reviewed = old_evaluate({**self.data,'rows':[]},self.model)
        reviewed.update(experiment=self.old_reg,evidenceMerge=self.evidence,
                        beforeExperimentStartExcluded={'early-activity':120},networkRequests=0)
        diagnostic = analyze(self.data,self.model,self.old_reg,self.evidence,reviewed)
        self.reviewed = self.root/'review.gz';publish(self.reviewed,reviewed)
        self.diagnostic = self.root/'diagnostic.gz';publish(self.diagnostic,diagnostic)
        for key,value in [('REVIEW_HASH',digest(reviewed)),('DIAGNOSTIC_HASH',digest(diagnostic))]:
            p=patch.object(s,key,value);p.start();self.addCleanup(p.stop)

    def register(self):
        with patch.object(s,'combine',return_value=(self.data,self.evidence)), patch('model.fit',side_effect=AssertionError('no refit')):
            return s.register(self.old,[self.capture],self.reviewed,self.diagnostic,self.new,self.now)

    def evaluation(self, count=8):
        self.register(); model,r=s.load(self.new,self.now)
        rows=[]
        for i in range(count):
            x=copy.deepcopy(self.train['rows'][0])
            x.update(id='new'+str(i),mint='new'+str(i),seq=1000+i,
                     signalAt=r['startAt']+(i%7)*s.DAY+1000+i,
                     utcDay='2030-01-'+str(10+i%7))
            x['targets']['30000']['availableAt']=x['signalAt']+31000
            if i%3==1:
                x['exitAvailability']['30000']='provider-reported-quote-failure'
                x['targets']['30000'].update(state='sell-quote-failed',returnPct=None,onTime=None)
            if i%3==2:
                x['exitAvailability']['30000']='transport-or-service-failure'
                x['targets']['30000'].update(state='sell-quote-failed',returnPct=None,onTime=None)
            rows.append(x)
        data=dict(sourceIdentity=model['sourceIdentity'],capturedAt=r['reviewNotBeforeAt'],rows=rows)
        evidence=dict(coveredIntervals=[[r['startAt'],r['reviewNotBeforeAt']]])
        return data,evidence,model,r

    def test_registration_replays_and_preserves_original_with_future_fixed_window(self):
        before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        out=self.register();model,r=s.load(self.new,self.now)
        self.assertEqual(out['state'],'registered-observation-only')
        self.assertGreater(r['startAt'],self.now+300000)
        self.assertEqual(r['endAt']-r['startAt'],7*s.DAY)
        self.assertEqual(r['startAt']%s.DAY,0)
        self.assertEqual(r['modelSha256'],digest(s.group(self.model)['models']['legacy']))
        self.assertTrue(set(self.model['seenTrainingMints']).issubset(r['excludedMints']))
        for p,b in before.items():self.assertEqual(Path(p).read_bytes(),b)
        self.assertEqual(self.new.stat().st_mode&0o777,0o700)
        self.assertEqual((self.new/'registration.json.gz').stat().st_mode&0o777,0o600)

    def test_idempotent_registration_does_not_reset_dates(self):
        a=self.register()
        b=s.register(self.old,[],None,None,self.new,self.now+3*s.DAY)
        for key in ('registeredAt','startAt','endAt','registrationSha256'):self.assertEqual(a[key],b[key])

    def test_wrong_reports_fail_before_directory_creation(self):
        self.diagnostic.write_bytes(gzip.compress(b'{}'))
        with self.assertRaises(ValueError):self.register()
        self.assertFalse(self.new.exists())

    def test_missing_duplicate_and_changed_capture_rejected(self):
        with patch.object(s,'combine',return_value=(self.data,{**self.evidence,'inputs':[]})):
            with self.assertRaises(ValueError):s.register(self.old,[self.capture],self.reviewed,self.diagnostic,self.new,self.now)
        self.assertFalse(self.new.exists())
        with patch.object(s,'combine',return_value=(self.data,{**self.evidence,'inputs':self.evidence['inputs']*2})):
            with self.assertRaises(ValueError):s.register(self.old,[self.capture]*2,self.reviewed,self.diagnostic,self.new,self.now)
        changed=copy.deepcopy(self.data);changed['capturedAt']-=1
        with patch.object(s,'combine',return_value=(changed,self.evidence)):
            with self.assertRaises(ValueError):s.register(self.old,[self.capture],self.reviewed,self.diagnostic,self.new,self.now)

    def test_partial_install_and_symlink_never_overwritten(self):
        self.new.mkdir(mode=0o700)
        with self.assertRaises(FileNotFoundError):self.register()
        self.new.rmdir();self.new.symlink_to(self.old,target_is_directory=True)
        with self.assertRaises(ValueError):self.register()

    def test_registration_and_model_tamper_or_clock_regression_refused(self):
        self.register();p=self.new/'registration.json.gz';raw=p.read_bytes()
        with self.assertRaises(ValueError):s.load(self.new,self.now-1)
        for key,val in [('startAt',0),('protocol',{}),('excludedMints',[])]:
            r=json.loads(gzip.decompress(raw));r[key]=val
            r['registrationSha256']=digest({k:v for k,v in r.items() if k!='registrationSha256'})
            p.write_bytes(gzip.compress(json.dumps(r).encode()))
            with self.assertRaises(ValueError):s.load(self.new,self.now)
        p.write_bytes(raw);(self.new/'model.json.gz').write_bytes(gzip.compress(b'{}'))
        with self.assertRaises(ValueError):s.load(self.new,self.now)

    def test_no_early_evaluation_or_source_reads(self):
        self.register();_,r=s.load(self.new,self.now)
        with patch.object(s,'combine',side_effect=AssertionError('do not read')):
            with self.assertRaisesRegex(ValueError,'not complete'):s.review(self.new,[self.capture],r['reviewNotBeforeAt']-1)

    def test_unknowns_not_losses_or_failures_and_denominators_preserved(self):
        args=self.evaluation();before=copy.deepcopy(args)
        with patch.object(s,'predict',return_value=[.8,.2,.8,.2,.8,.2,.8,.2]):out=s.evaluate(*args)
        self.assertEqual(args,before)
        self.assertEqual(out['knownLabels'],6);self.assertEqual(out['unknownLabels'],2)
        self.assertEqual(out['providerFailuresExcluded']['numerator'],2)
        self.assertEqual(out['providerFailuresExcluded']['denominator'],3)
        self.assertEqual(out['successfulQuotesRetained']['numerator'],2)
        for h in ('30000','120000'):
            self.assertEqual(out['outcomes']['all'][h]['watches'],8)
            self.assertEqual(sum(out['outcomes'][p][h]['watches'] for p in ('selected','excluded')),8)
        self.assertFalse(out['liveUseAllowed']);self.assertFalse(out['modelRefitted'])

    def test_development_repeat_window_and_incompatible_exclusions_are_feature_only(self):
        data,e,model,r=self.evaluation()
        data['rows'][0]['mint']=r['excludedMints'][0]
        data['rows'][1]['signalAt']=r['startAt']-1
        data['rows'][2]['signalAt']=r['endAt']
        data['rows'][3]['samplingPolicy']='other'
        data['rows'][5]['mint']=data['rows'][4]['mint']
        out=s.evaluate(data,e,model,r)
        self.assertEqual(out['watches'],3)
        self.assertEqual(out['excluded'],{'outside-fixed-window':2,'development-or-repeat-token':2,'different-sampling-policy':1})

    def test_outcome_changes_do_not_change_predictions_or_selection(self):
        args=self.evaluation();a=s.evaluate(*args)
        for row in args[0]['rows']:
            if row['exitAvailability']['30000']=='on-time-validated-quote':row['targets']['30000']['returnPct']=-99
        b=s.evaluate(*args)
        self.assertEqual([(p['probability'],p['selected']) for p in a['predictions']],[(p['probability'],p['selected']) for p in b['predictions']])

    def test_coverage_and_maturity_and_counts_independently_block(self):
        data,e,m,r=self.evaluation();e['coveredIntervals']=[[r['startAt'],r['endAt']]];data['capturedAt']=r['endAt']
        out=s.evaluate(data,e,m,r)
        for reason in ('query-window-coverage-incomplete','evidence-cutoff-before-maturity','too-few-known-labels','too-few-provider-failures','too-few-excluded-known-labels'):
            self.assertIn(reason,out['blockingReasons'])
        self.assertEqual(out['state'],'insufficient-fixed-window-evidence')

    def test_review_source_change_and_future_capture_refused(self):
        data,e,m,r=self.evaluation()
        with patch.object(s,'combine',return_value=(data,e)):
            out=s.review(self.new,[self.capture],r['reviewNotBeforeAt']);self.assertEqual(out['watches'],8)
            data['capturedAt']+=1
            with self.assertRaises(ValueError):s.review(self.new,[self.capture],r['reviewNotBeforeAt'])
        data['capturedAt']-=1;data['sourceIdentity']='changed'
        with self.assertRaises(ValueError):s.evaluate(data,e,m,r)

    def test_rate_intervals_keep_empty_unknown_and_extremes(self):
        self.assertIsNone(s.rate(0,0)['fraction'])
        self.assertLess(s.rate(10,10)['wilson95'][0],1)
        self.assertGreater(s.rate(0,10)['wilson95'][1],0)

    def test_empty_and_guard_satisfying_results_never_promote(self):
        args=self.evaluation(0);out=s.evaluate(*args)
        self.assertEqual(out['watches'],0);self.assertIsNone(out['providerFailuresExcluded']['fraction'])
        data,e,m,r=args
        for i in range(210):
            row=copy.deepcopy(self.train['rows'][0])
            row.update(id='n'+str(i),seq=i+1000,mint='n'+str(i),signalAt=r['startAt']+(i%7)*s.DAY+1000+i,utcDay='2030-01-'+str(10+i%7))
            row['targets']['30000']['availableAt']=row['signalAt']+31000
            if i%2:
                row['exitAvailability']['30000']='provider-reported-quote-failure'
                row['targets']['30000'].update(state='sell-quote-failed',returnPct=None,onTime=None)
            data['rows'].append(row)
        with patch.object(s,'predict',return_value=[.8 if i%2==0 else .2 for i in range(210)]):out=s.evaluate(data,e,m,r)
        self.assertEqual(out['blockingReasons'],[])
        self.assertEqual(out['state'],'fixed-window-reviewed-not-promotion');self.assertFalse(out['liveUseAllowed'])

    def test_actual_capture_replay_registration_and_status_without_mocked_merge(self):
        from test_audit import sample
        from test_history import ledger
        import history
        q=sample()
        for signal in (q['signals'][0],q['probes'][0]['signal']):signal['cohort']='early-activity'
        at=q['signals'][0]['signalAt']
        model=copy.deepcopy(self.model)
        model.update(frozenAt=at-600000,trainingCutoffAt=at-900000,testNotBeforeAt=at-300000)
        source=self.root/'real-model.gz';publish(source,seal(model))
        old=self.root/'real-old';db=self.root/'ledger';capture=self.root/'real-capture';new=self.root/'real-new'
        ledger(db,[q]);history.capture(db,capture,hours=3,chunk_hours=1,evidence_cutoff=at+3600000)
        with patch.object(s.frozen,'ARTIFACT_SHA256',digest(model)):
            s.frozen.install(source,old,at-600000)
            reviewed=s.frozen.review(old,[capture],at+3600000)
            data,evidence=s.combine([capture]);_,reg=s.frozen.load(old,at+3600000)
            diagnostic=analyze(data,model,reg,evidence,reviewed)
            review_path=self.root/'real-review.gz';publish(review_path,reviewed)
            diag_path=self.root/'real-diagnostic.gz';publish(diag_path,diagnostic)
            with patch.object(s,'REVIEW_HASH',digest(reviewed)),patch.object(s,'DIAGNOSTIC_HASH',digest(diagnostic)):
                before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
                with patch('model.fit',side_effect=AssertionError('no fit')):
                    out=s.register(old,[capture],review_path,diag_path,new,at+7200000)
                self.assertEqual(out['state'],'registered-observation-only')
                _,r=s.load(new,at+7200000)
                self.assertIn(q['signals'][0]['mint'],r['excludedMints'])
                for p,content in before.items():self.assertEqual(Path(p).read_bytes(),content)

    def test_cli_status_and_refused_early_review_publish_no_partial_output(self):
        self.register();_,r=s.load(self.new,self.now)
        output=self.root/'status.gz'
        with patch.object(sys,'argv',['confirmation.py','status','--directory',str(self.new),'--output',str(output)]),patch.object(s.frozen,'clock',return_value=self.now):
            s.main()
            self.assertTrue(output.is_file())
            with self.assertRaises(SystemExit):s.main()
        early=self.root/'early.gz'
        with patch.object(sys,'argv',['confirmation.py','review','--directory',str(self.new),'--capture-dir',str(self.capture),'--output',str(early)]),patch.object(s.frozen,'clock',return_value=r['reviewNotBeforeAt']-1):
            with self.assertRaises(ValueError):s.main()
        self.assertFalse(early.exists())


if __name__=='__main__':unittest.main()
