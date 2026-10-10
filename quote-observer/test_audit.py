import unittest,copy
from evidence_audit import liquidity_evidence,align_quote,audit
class EvidenceTests(unittest.TestCase):
    def test_known_zero_unknown_and_conflict_separate(self):
        p={'at':10,'pairAddress':'p','price':2}
        self.assertEqual(liquidity_evidence([p],10,'p')['status'],'unknown')
        self.assertEqual(liquidity_evidence([{**p,'liquidityUsd':0}],10,'p')['status'],'near-zero')
        self.assertEqual(liquidity_evidence([{**p,'liquidityUsd':0},{**p,'liquidityUsd':100}],10,'p')['status'],'conflicting')
        self.assertEqual(liquidity_evidence([{**p,'liquidityUsd':100}],11,'p')['status'],'unknown')
    def test_alignment_never_uses_future_point_as_prior(self):
        e={'price':1,'pairAddress':'p','path':[{'at':10,'price':1,'pairAddress':'p'},{'at':30,'price':2,'pairAddress':'p'},{'at':19,'price':8,'pairAddress':'q'}]}
        r=align_quote(e,{'startedAt':20,'status':'quoted'})
        self.assertEqual(r['lastPriorObservation']['at'],10);self.assertEqual(r['nextObservationRetrospectiveOnly']['at'],30)
        self.assertEqual(r['lastPriorObservation']['priceChangeFromSignalPct'],0)
    def fixture(self):
        e={'id':'e','at':10,'mint':'m','cohort':'baseline','pairAddress':'p','price':1,'path':[{'at':10,'price':1,'pairAddress':'p'},{'at':20,'price':20,'pairAddress':'p','liquidityUsd':.01}]}
        r={'format':'radar-research-tools-1.1.0','entries':[e],'window':{},'evaluation':{'results':[{'entryId':'e','cohort':'baseline','policy':'time-60','delayMs':10000,'costBpsPerSide':0,'status':'observed-model','simulatedEntryAt':10,'simulatedExitAt':20,'grossReturnPct':1900}]}}
        q={'format':'quote-observer-report-0.2.0','capturedAt':30,'signalCounts':[],'probeCounts':[],'probes':[{'signal':{'seq':1,'entryId':'e','mint':'m','signalAt':10,'cohort':'baseline','originalPool':'p'},'state':'complete-with-failures','observations':[{'leg':'sell','status':'http-error','httpStatus':400,'startedAt':20,'targetOffsetMs':120000}]}]}
        return q,r
    def test_extreme_price_return_preserved_with_liquidity_flag(self):
        q,r=self.fixture();before=copy.deepcopy((q,r));out=audit(q,r)
        self.assertEqual(out['modelExitEvidence'][0]['grossReturnPct'],1900);self.assertEqual(out['modelExitEvidence'][0]['exitEvidence']['status'],'near-zero');self.assertEqual((q,r),before)
        group=out['quoteGroups']['first-arrival-v0.2.0/baseline/120000'];self.assertEqual(group['notObserved'],1);self.assertEqual(group['observed'],0)
    def test_same_flags_apply_to_losses(self):
        q,r=self.fixture();r['evaluation']['results'][0]['grossReturnPct']=-99
        self.assertEqual(audit(q,r)['modelExitEvidence'][0]['exitEvidence']['status'],'near-zero')
    def test_duplicate_or_mismatched_identity_rejected(self):
        q,r=self.fixture();q['probes']*=2
        with self.assertRaises(ValueError):audit(q,r)
        q,r=self.fixture();q['probes'][0]['signal']['mint']='other'
        with self.assertRaises(ValueError):audit(q,r)
    def test_unmatched_quote_retained(self):
        q,r=self.fixture();q['probes'][0]['signal']['entryId']='old'
        out=audit(q,r);self.assertEqual(out['matchingSummary']['outsideResearchExport'],1);self.assertEqual(len(out['unmatchedProbes']),1)
if __name__=='__main__':unittest.main()
