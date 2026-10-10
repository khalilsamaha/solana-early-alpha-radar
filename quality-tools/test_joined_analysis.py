import copy
import unittest
from joined_analysis import join_quotes, USDC
from entry_shadows import entry_shadows, missing_diagnostics, RULES, VERSION

class JoinedTests(unittest.TestCase):
    def fixture(self):
        e={'id':'entry','mint':'mint','at':100000,'pairAddress':'pool','priceUsd':2,'liquidityUsd':None,'decision':{'return30sPct':20},'quality':{'lastObservedAt':99500},'followup':{'policy':'fast-followup-1','admitted':True}}
        o={'entryId':'entry','horizon':'30s','status':'observed','coverage':'sampled','pairAddress':'pool','sampleAt':132000,'priceUsd':2.2,'returnPct':10}
        s={'seq':1,'entryId':'entry','cohort':'fast30-shadow','mint':'mint','signalAt':100000,'originalPool':'pool','entryPriceUsd':2}
        buy={'leg':'buy','status':'quoted','startedAt':101000,'receivedAt':102000,'inputMint':USDC,'outputMint':'mint','inAmount':'10000000','outAmount':'5000000000','tokenPools':['pool']}
        sell={'leg':'sell','status':'quoted','targetOffsetMs':30000,'startedAt':132000,'receivedAt':132300,'inputMint':'mint','outputMint':USDC,'inAmount':'5000000000','outAmount':'9000000','tokenPools':['pool'],'originalPoolInRoute':True}
        d={'sourceIdentity':'source','cutoffAt':500000,'fast-shadow-entries':[e],'fast-shadow-outcomes':[o],'fast-shadow-links':[]}
        q={'sourceIdentity':'source','format':'quote-observer-report-0.2.0','probes':[{'signal':s,'baseMint':USDC,'inputAtomic':'10000000','samplingPolicy':'policy','observations':[buy,sell]}]}
        return d,q

    def test_exact_join_preserves_clocks_and_recalculates_atomic_proceeds(self):
        d,q=self.fixture();before=copy.deepcopy(d);q['probes'][0]['observations'][1]['quotedUsdcChangePct']=999
        c=join_quotes(d,q)['cases'][0];h=c['horizons'][1]
        self.assertEqual(h['quotedChangePct'],-10);self.assertEqual(h['paperChangePct'],10);self.assertEqual(h['differencePercentagePoints'],20)
        self.assertEqual(h['paperMinusQuoteReceiptMs'],-300);self.assertTrue(h['oppositeSigns']);self.assertIsNone(c['buyUnitPriceUsd']);self.assertEqual(d,before)

    def test_identity_mismatch_never_joins_returns(self):
        for field,value in [('sourceIdentity','other'),('originalPool','other'),('mint','other'),('signalAt',99999),('entryPriceUsd',3)]:
            d,q=self.fixture()
            if field=='sourceIdentity':q[field]=value
            else:q['probes'][0]['signal'][field]=value
            self.assertIsNone(join_quotes(d,q)['cases'][0]['horizons'][1]['differencePercentagePoints'])
        d,q=self.fixture();d.pop('sourceIdentity');self.assertEqual(join_quotes(d,q)['sourceIdentityState'],'unavailable-legacy')

    def test_failures_missing_and_inconsistent_quantities_remain_explicit(self):
        for patch in [{'status':'http-error'},{'inAmount':'3'},{'outAmount':'0'},{'receivedAt':99999},{'startedAt':103000}]:
            d,q=self.fixture();q['probes'][0]['observations'][1].update(patch);h=join_quotes(d,q)['cases'][0]['horizons'][1]
            self.assertIsNone(h['quotedChangePct']);self.assertIsNone(h['differencePercentagePoints'])
        d,q=self.fixture();q['probes'][0]['observations'].pop();self.assertEqual(join_quotes(d,q)['cases'][0]['horizons'][1]['quoteState'],'not-recorded')

    def test_duplicate_probes_offsets_and_outcomes_fail(self):
        for kind in ['probe','offset','outcome']:
            d,q=self.fixture()
            if kind=='probe':q['probes']*=2
            elif kind=='offset':q['probes'][0]['observations'].append(copy.deepcopy(q['probes'][0]['observations'][1]))
            else:d['fast-shadow-outcomes']*=2
            with self.assertRaises(ValueError):join_quotes(d,q)

    def test_gapped_invalid_prices_cannot_enter_paired_comparisons(self):
        for patch in [{'coverage':'gapped'},{'returnPct':0},{'sampleAt':200000},{'pairAddress':'other'}]:
            d,q=self.fixture();d['fast-shadow-outcomes'][0].update(patch);h=join_quotes(d,q)['cases'][0]['horizons'][1]
            self.assertIsNone(h['paperChangePct']);self.assertIsNone(h['differencePercentagePoints'])

    def register(self,d):
        e=d['fast-shadow-entries'][0];d['evidenceRegistration']={'id':VERSION,'registeredAt':90000,'rules':RULES}
        e['shadowEvaluation']={'version':VERSION,'registeredAt':90000,'featureAt':e['at'],'features':{'liquidityUsd':None,'return30sPct':20},'groups':{'known-liquidity-5000-v1':'unknown','return30-at-most-50-v1':'selected'}}

    def test_forward_unknown_and_exploratory_results_separate(self):
        d,q=self.fixture();self.assertEqual(entry_shadows(d)['entries'][0]['period'],'exploratory');self.register(d)
        r=entry_shadows(d,join_quotes(d,q));self.assertEqual(r['entries'][0]['period'],'forward');self.assertEqual(r['entries'][0]['groups']['known-liquidity-5000-v1'],'unknown')
        e=copy.deepcopy(d['fast-shadow-entries'][0]);e.update(id='old',at=80000);e.pop('shadowEvaluation');d['fast-shadow-entries'].append(e)
        self.assertEqual({x['period']for x in entry_shadows(d)['entries']},{'forward','exploratory'})

    def test_forward_labels_cannot_use_backdated_or_later_features(self):
        for change in ['time','features','rule','group','missing']:
            d,q=self.fixture();self.register(d);e=d['fast-shadow-entries'][0]
            if change=='time':e['shadowEvaluation']['registeredAt']=1
            elif change=='features':e['shadowEvaluation']['features']['liquidityUsd']=50000
            elif change=='rule':d['evidenceRegistration']['rules']=[]
            elif change=='group':e['shadowEvaluation']['groups']['known-liquidity-5000-v1']='selected'
            else:e.pop('shadowEvaluation')
            self.assertNotEqual(entry_shadows(d)['entries'][0]['period'],'forward')

    def test_legacy_missing_reasons_are_not_inferred(self):
        d,q=self.fixture();o=d['fast-shadow-outcomes'][0];o.update(status='missing',reason='no timely original-pool observation')
        self.assertEqual(missing_diagnostics(d)['cases'][0]['reasonCode'],'legacy-unspecified')
        o.update(reasonCode='provider-error',diagnostics={'window':{'attempts':2}})
        self.assertEqual(missing_diagnostics(d)['cases'][0]['reasonCode'],'provider-error')

if __name__=='__main__':unittest.main()
