import copy
import gzip
import hashlib
import test_study
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from capture import capture, project_entry, project_price_evidence
from joined_report import build
from reconcile import PROTOCOL
from test_join_quotes import fixture
from test_study import T, P, outcome


def audited(c,q):
    return build({'format':'launch-study-report-1','capture':c},q)['reconciliation']


def history(c,points=None):
    c['entries'][0]['data']['priceEvidence']=project_price_evidence({'evidence':{
        'basis':'provider-response-time','poolAddress':P,'samples':points if points is not None else [{'at':T-100,'price':2}]}})


def clock(q,at=T-100,source='quality.lastObservedAt'):
    s=q['signals'][0];s['features']={'marketObservedAt':at}
    s['featureCapture']={'version':'fast-entry-features-1','signalAt':T,'sources':{'marketObservedAt':{'state':'recorded','source':source}}}


class ReconcileTests(unittest.TestCase):
    def test_projection_allowlists_prices_and_caps_tail(self):
        row={'id':'x','evidence':{'basis':'provider-response-time','poolAddress':P,'secret':'omit',
            'samples':[{'at':T-100+i,'price':i+1,'secret':'omit'} for i in range(30)]}}
        p=project_entry(row)['priceEvidence']
        self.assertEqual(len(p['samples']),24);self.assertEqual(p['samples'][0],{'at':T-94,'price':7})
        self.assertTrue(p['truncated']);self.assertEqual(p['sourceSampleCount'],30)
        self.assertNotIn('secret',json.dumps(p))
        with self.assertRaises(ValueError):project_price_evidence({'evidence':{'samples':[{}]*257}})
        with self.assertRaises(ValueError):project_price_evidence({'evidence':{'samples':[None]}})

    def test_database_history_projection_preserves_source_and_primary_results(self):
        with tempfile.TemporaryDirectory() as d:
            c,q=fixture();e=c['entries'][0]
            e['data']['evidence']={'basis':'provider-response-time','poolAddress':P,'samples':[{'at':T-100,'price':2,'volume':500}]}
            f=test_study.StudyTests().database(Path(d)/'db',[e])
            before=hashlib.sha256(f.read_bytes()).hexdigest();captured=capture(f,now=T+400000)
            q['sourceIdentity']=captured['sourceIdentity'];r=audited(captured,q)
            self.assertEqual(r['cases'][0]['entryReference']['localReceiptAt'],T-100)
            self.assertEqual(r['cases'][0]['horizons']['30000']['paperReturnPct'],50)
            self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),before)
            self.assertEqual(captured['collectorVersion'],'launch-study-1.0.2')

    def test_unknown_buy_pool_does_not_enter_original_pool_triage(self):
        c,q=fixture();q['probes'][0]['observations'][0]['routePlanTruncated']=True
        r=audited(c,q)
        self.assertEqual(r['summary']['horizons']['30000']['largeCloseOriginalPoolOnTime'],0)
        self.assertIsNone(r['cases'][0]['horizons']['30000']['buyOriginalPoolReported'])

    def test_old_exports_have_unknown_history_and_no_inferred_decimals(self):
        c,q=fixture();r=audited(c,q)['cases'][0]['entryReference']
        self.assertEqual(r['historyState'],'not-exported');self.assertIsNone(r['localReceiptAt'])
        self.assertIsNone(r['absoluteQuoteUnitPriceUsd']);self.assertEqual(r['tokenDecimals'],'not-verified')
        self.assertIsNone(r['providerMarketTimestamp'])

    def test_same_pool_history_records_actual_receipt_and_matches_price(self):
        c,q=fixture();history(c);r=audited(c,q)['cases'][0]['entryReference']
        self.assertEqual(r['historyState'],'recorded');self.assertEqual(r['localReceiptAgeAtSignalMs'],100)
        self.assertTrue(r['latestHistoryMatchesEntryPrice']);self.assertEqual(r['providerFreshness'],'not-established')

    def test_history_price_difference_is_flagged_without_rewriting_returns(self):
        c,q=fixture();history(c,[{'at':T-100,'price':1}]);a=audited(c,q)
        self.assertEqual(a['summary']['entryHistoryPriceMismatches'],1)
        self.assertEqual(a['cases'][0]['horizons']['30000']['paperReturnPct'],50)

    def test_future_duplicate_invalid_or_other_pool_history_is_unusable(self):
        for mutate in [lambda p:p.update(poolAddress='other'),lambda p:p.update(basis='exchange-time'),
            lambda p:p['samples'][0].update(at=T+1),lambda p:p['samples'][0].update(price=0),
            lambda p:p.update(samples=p['samples']*2,sourceSampleCount=2),lambda p:p.update(sourceSampleCount=True)]:
            c,q=fixture();history(c);mutate(c['entries'][0]['data']['priceEvidence'])
            r=audited(c,q)['cases'][0]['entryReference'];self.assertEqual(r['historyState'],'invalid');self.assertIsNone(r['latestHistoryObservation'])

    def test_observer_clock_has_provenance_and_conflicting_clock_remains_unknown(self):
        c,q=fixture();clock(q);r=audited(c,q)['cases'][0]['entryReference']
        self.assertEqual(r['localReceiptAt'],T-100)
        history(c,[{'at':T-200,'price':2}]);r=audited(c,q)['cases'][0]['entryReference']
        self.assertEqual(r['receiptState'],'conflicting-recorded-receipts');self.assertIsNone(r['localReceiptAt'])

    def test_future_or_wrong_source_clock_is_not_treated_as_fresh(self):
        for at,source in [(T+1,'quality.lastObservedAt'),(T-1,'fabricated')]:
            c,q=fixture();clock(q,at,source);r=audited(c,q)['cases'][0]['entryReference']
            self.assertEqual(r['receiptState'],'invalid-observer-receipt');self.assertIsNone(r['localReceiptAt'])

    def test_no_receipt_features_from_mismatched_signal(self):
        c,q=fixture();clock(q);q['signals'][0]['entryPriceUsd']=99
        r=audited(c,q)['cases'][0]['entryReference'];self.assertIsNone(r['localReceiptAt'])

    def test_difference_uses_percentage_points_and_actual_receipt_difference(self):
        c,q=fixture();a=audited(c,q);x=a['cases'][0]['horizons']['30000']
        self.assertEqual(x['paperPriceUsd'],3);self.assertEqual(x['differencePercentagePoints'],40)
        self.assertEqual(x['paperMinusQuoteReceiptMs'],-1300);self.assertTrue(x['largeDifference'])
        self.assertEqual(a['summary']['horizons']['30000']['largeCloseOriginalPoolOnTime'],1)

    def test_large_discrepancy_is_not_close_when_receipts_far_apart(self):
        c,q=fixture();o=c['outcomes'][0];o['data'].update(at=T+55000,sampleAt=T+55000);o['eventAt']=T+55000
        a=audited(c,q);self.assertEqual(a['summary']['horizons']['30000']['largeCloseOriginalPoolOnTime'],0)
        self.assertTrue(a['cases'][0]['horizons']['30000']['largeDifference'])

    def test_unknown_alternate_route_or_late_quote_does_not_enter_strict_triage(self):
        for mutate in [lambda o:o.update(routePlanTruncated=True),lambda o:o['routePlan'][0].update(pool='other'),
            lambda o:o.update(startedAt=T+37000,receivedAt=T+37300)]:
            c,q=fixture();mutate(q['probes'][0]['observations'][2]);a=audited(c,q)
            self.assertEqual(a['summary']['horizons']['30000']['largeCloseOriginalPoolOnTime'],0)
            self.assertEqual(a['summary']['horizons']['30000']['paired'],1)

    def test_rebase_removes_constant_entry_basis_without_inventing_unit_price(self):
        c,q=fixture();c['outcomes'].append(outcome(c['entries'][0],'60s',60000,101,price=3.3))
        sell=q['probes'][0]['observations'][3];sell.update(outAmount='12100000',quotedUsdcChangePct=21)
        a=audited(c,q);x=a['cases'][0]['rebased']['60000']
        self.assertEqual(x['state'],'paired-rebased');self.assertAlmostEqual(x['paperChangePct'],10)
        self.assertAlmostEqual(x['quotedProceedsChangePct'],10);self.assertAlmostEqual(x['differencePercentagePoints'],0)
        self.assertFalse(x['entryDisagreementAndRebasedDisagreement'])

    def test_persistent_disagreement_after_rebase_stays_visible(self):
        c,q=fixture();c['outcomes'].append(outcome(c['entries'][0],'60s',60000,101,price=6))
        a=audited(c,q);x=a['cases'][0]['rebased']['60000']
        self.assertEqual(x['paperChangePct'],100);self.assertEqual(x['quotedProceedsChangePct'],0)
        self.assertTrue(x['entryDisagreementAndRebasedDisagreement'])
        self.assertEqual(a['summary']['rebased']['60000']['largeCloseOriginalPoolOnTime'],1)

    def test_rebase_requires_both_valid_paper_and_quote_endpoints(self):
        for mutate in [lambda c,q:c['outcomes'][0]['data'].update(coverage='gapped'),
            lambda c,q:q['probes'][0]['observations'][2].update(status='http-error'),
            lambda c,q:q.update(capturedAt=T+20000)]:
            c,q=fixture();c['outcomes'].append(outcome(c['entries'][0],'60s',60000,101,price=6));mutate(c,q)
            a=audited(c,q);self.assertEqual(a['cases'][0]['rebased']['60000']['state'],'unavailable')

    def test_skipped_and_failed_records_keep_denominators(self):
        c,q=fixture();q['signals'][0]['decision']='hour-budget';q['probes']=[];a=audited(c,q)
        self.assertEqual(a['summary']['entries'],1);self.assertEqual(a['summary']['admitted'],0)
        self.assertEqual(a['summary']['horizons']['30000']['quoteStates'],{'not-admitted':1})
        c,q=fixture();q['probes'][0]['observations'][2].update(status='http-error',providerCategory='quote-generation-failure-reported')
        x=audited(c,q)['cases'][0]['horizons']['30000'];self.assertIsNone(x['quotedChangePct']);self.assertEqual(x['providerCategory'],'quote-generation-failure-reported')

    def test_reconciliation_is_recomputed_ignoring_tampered_derived_results(self):
        c,q=fixture();study={'format':'launch-study-report-1','capture':c};a=build(study,q)
        old=copy.deepcopy(a);old['analysis']={'fake':1};old['reconciliation']={'fake':1}
        b=build({'format':'launch-study-report-1','capture':old['studyCapture']},old['quoteEvidence'])
        self.assertEqual(a,b)

if __name__=='__main__':unittest.main()
