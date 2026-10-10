import copy
import unittest
from exit_evidence import probe_evidence,summarize,OFFSETS
from evidence_audit import audit

class ExitTests(unittest.TestCase):
    def probe(self,seq=1):
        return {'state':'complete','samplingPolicy':'cohort-budgets-v2',
          'signal':{'seq':seq,'entryId':f'e{seq}','signalAt':1000000,'cohort':'baseline','features':{}},
          'observations':[{'leg':'buy','status':'quoted','startedAt':1001000,'receivedAt':1001250}]+
          [{'leg':'sell','status':'quoted','targetOffsetMs':t,
            'startedAt':1001250+max(t,9750),'receivedAt':1001500+max(t,9750),
            'quotedUsdcChangePct':0 if t==0 else -10} for t in OFFSETS]}

    def report(self,ps):
        return {'format':'quote-observer-report-0.2.0','capturedAt':1200000,'probes':ps}

    def test_actual_clocks_and_zero_returns_preserved_without_mutation(self):
        p=self.probe();before=copy.deepcopy(p);out=probe_evidence(p,1200000)
        first=out['exits'][0]
        self.assertEqual(first['timing']['requestFromSignalMs'],11000)
        self.assertEqual(first['timing']['requestFromBuyResponseMs'],9750)
        self.assertEqual(first['quotedUsdcChangePct'],0)
        self.assertFalse(first['executionVerified']);self.assertEqual(p,before)

    def test_buy_failed_does_not_invent_sell_attempts_or_returns(self):
        p=self.probe();p['state']='buy-quote-failed';p['observations']=[{'leg':'buy','status':'http-error'}]
        out=summarize(self.report([p]));h=out['groups']['cohort-budgets-v2/baseline']['horizons']['120000']
        self.assertEqual(h['states'],{'not-sampled-buy-failed':1})
        self.assertEqual(h['quotedReturns'],0);self.assertEqual(h['withoutQuotedReturn'],1)
        self.assertIsNone(h['meanQuotedChangePct'])

    def test_sell_failures_not_silently_changed_to_absent_routes(self):
        p=self.probe();p['state']='complete-with-failures'
        for o in p['observations'][1:]:o.update(status='http-error',providerCategory='quote-generation-failure-reported')
        out=probe_evidence(p,1200000)
        self.assertTrue(all(e['state']=='sell-quote-failed' and e['quotedUsdcChangePct'] is None for e in out['exits']))
        self.assertEqual(out['exits'][0]['providerCategory'],'quote-generation-failure-reported')

    def test_pending_overdue_interrupted_and_skipped_remain_distinct(self):
        p=self.probe();p['state']='running';p['observations']=p['observations'][:1]
        self.assertEqual(probe_evidence(p,1002000)['exits'][-1]['state'],'pending')
        self.assertEqual(probe_evidence(p,1300000)['exits'][-1]['state'],'overdue-unrecorded')
        p['observations'][0]['startedAt']=None
        self.assertEqual(probe_evidence(p,1002000)['exits'][-1]['state'],'pending')
        p['state']='interrupted-restart'
        self.assertEqual(probe_evidence(p,1300000)['exits'][-1]['state'],'incomplete-unrecorded')
        p['observations'].append({'leg':'sell','targetOffsetMs':120000,'status':'skipped','reason':'rate-limited'})
        self.assertEqual(probe_evidence(p,1300000)['exits'][-1]['state'],'not-sampled')

    def test_bad_clocks_are_flagged_and_duplicate_offsets_fail(self):
        p=self.probe();p['observations'][1]['startedAt']=1
        self.assertTrue(probe_evidence(p,1200000)['exits'][0]['invalidTiming'])
        p['observations'][2]['targetOffsetMs']=0
        with self.assertRaises(ValueError):probe_evidence(p,1200000)

    def test_legacy_and_new_capture_group_separately_no_backfill(self):
        old=self.probe();new=self.probe(2);new['signal']['features']['averageReportedTradeUsd']=2
        new['signal']['featureCapture']={'version':'entry-features-1'}
        report=self.report([old,new]);report['featureCaptureRegistration']={
          'id':'entry-features-1','registeredAt':999000,
          'shadow':{'id':'average-reported-trade-5-v1','thresholdUsd':5}}
        before=copy.deepcopy(report);out=summarize(report)
        groups=out['activityShadow']['groups']
        self.assertEqual(groups['cohort-budgets-v2/baseline/prospective/below-5']['admitted'],1)
        self.assertEqual(groups['cohort-budgets-v2/baseline/not-prospective/unknown']['admitted'],1)
        self.assertEqual(report,before)
        report['featureCaptureRegistration']['registeredAt']=1000001
        self.assertNotIn('cohort-budgets-v2/baseline/prospective/below-5',summarize(report)['activityShadow']['groups'])

    def test_denominators_preserve_all_failures_and_sampling_policies(self):
        ps=[self.probe(i) for i in range(3)];ps[1]['observations'][-1].update(status='http-error')
        ps[2]['samplingPolicy']='old-policy'
        out=summarize(self.report(ps))
        h=out['groups']['cohort-budgets-v2/baseline']['horizons']['120000']
        self.assertEqual((h['admitted'],h['quotedReturns'],h['withoutQuotedReturn']),(2,1,1))
        self.assertEqual(h['meanQuotedChangePct'],-10)
        self.assertIn('old-policy/baseline',out['groups'])
        with self.assertRaises(ValueError):summarize(self.report([ps[0],ps[0]]))

    def test_model_clock_comparison_keeps_delayed_entry_and_exit(self):
        p=self.probe();p['signal'].update(mint='m',originalPool='pool')
        q=self.report([p]);q.update(signalCounts=[],probeCounts=[])
        e={'id':'e1','at':1000000,'mint':'m','cohort':'baseline','pairAddress':'pool','price':1,'path':[]}
        row={'entryId':'e1','cohort':'baseline','policy':'time-120','delayMs':10000,'costBpsPerSide':0,
          'status':'observed-model','simulatedEntryAt':1016000,'simulatedExitAt':1151000,'grossReturnPct':-60}
        r={'format':'radar-research-tools-1.1.0','window':{},'entries':[e],'evaluation':{'results':[row]}}
        before=copy.deepcopy((q,r));out=audit(q,r);c=out['clockComparisons'][0]
        self.assertEqual(c['modelEntryFromSignalMs'],16000)
        self.assertEqual(c['quoteSellRequestFromSignalMs'],121250)
        self.assertEqual(c['modelExitFromSignalMs'],151000)
        self.assertEqual(c['modelExitMinusQuoteSellRequestMs'],29750)
        self.assertFalse(c['comparableAsSameExecution']);self.assertEqual((q,r),before)

if __name__=='__main__':unittest.main()
