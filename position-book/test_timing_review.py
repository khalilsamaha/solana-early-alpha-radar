import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import timing_review as t


def fixture():
    return dict(format='continuation-exit-integration-1', mode='synthetic-offline',
        state='offline-integration-passed', **{k:False for k in t.FALSE_FLAGS},
        realNetworkRequests=0, transactionsSent=0, temporaryLedgersRemoved=True,
        continuationStarted=True, requestedProgramFixtureBytes=1048576, programFixtureBytes=1048576,
        cases={k:'passed' for k in t.EXPECTED_CASES}, casesPassed=len(t.EXPECTED_CASES),
        independentContractCases={k:'passed' for k in t.EXPECTED_CONTRACTS},
        diagnosticsVersion='continuation-rehearsal-diagnostics-1',
        integrationElapsedMs=7000, deadlineHeadroomMs=100,
        diagnosticPhases=[dict(phase=k,completed=True,elapsedMs=2000) for k in t.PHASES]+
            [dict(phase='continuation-sign-send',completed=True,elapsedMs=7000),
             dict(phase='synthetic-sender-adapter-setup',completed=True,elapsedMs=500)])


class TimingReviewTests(unittest.TestCase):
    def test_pair_requires_explicit_environment_attestation(self):
        a=t.summarize(fixture());b=copy.deepcopy(a);b['integrationElapsedMs']=6500
        self.assertEqual(t.compare(a,b)['comparison'],'not-comparable')
        out=t.compare(a,b,True)
        self.assertEqual(out['afterMinusBefore']['integrationElapsedMs'],-500)
        self.assertFalse(out['executionApproved'])
        self.assertNotIn('synthetic-sender-adapter-setup',out['afterMinusBefore']['phasesMs'])

    def test_failed_and_partial_evidence_retained_without_delta(self):
        for mutate in (lambda d:d.update(state='review-required'),
                       lambda d:d['cases'].pop(next(iter(d['cases']))),
                       lambda d:d.update(independentContractCases={}),
                       lambda d:d.update(deadlineHeadroomMs=None),
                       lambda d:d.update(temporaryLedgersRemoved=False),
                       lambda d:d.update(deadlineHeadroomMs=-1),
                       lambda d:d['diagnosticPhases'][0].update(completed=False)):
            d=fixture();mutate(d);a=t.summarize(d)
            out=t.compare(a,t.summarize(fixture()),True)
            self.assertEqual(a['functionalEvidence'],'review-required')
            self.assertIsNone(out['afterMinusBefore'])

    def test_different_fixture_and_clock_not_compared(self):
        a=t.summarize(fixture())
        for field,value in (('fixtureBytes',2048),('clockDefinition',None)):
            b=copy.deepcopy(a);b[field]=value
            self.assertIsNone(t.compare(a,b,True)['afterMinusBefore'])

    def test_nested_phase_not_flattened_and_inconsistent_timing_flagged(self):
        d=fixture();self.assertEqual(t.summarize(d)['functionalEvidence'],'complete-offline-pass')
        d['diagnosticPhases'][-1]['elapsedMs']=3000
        self.assertIn('nested-setup-exceeds-submission',t.summarize(d)['reviewReasons'])
        d=fixture();d['integrationElapsedMs']=4000
        self.assertIn('phase-times-exceed-parent',t.summarize(d)['reviewReasons'])

    def test_unknown_payload_never_exported(self):
        d=fixture();d['secret']='private';d['diagnosticPhases'][0]['error']='private'
        d['diagnosticPhases'].append(dict(phase='private',completed=True,elapsedMs=1))
        self.assertNotIn('private',json.dumps(t.summarize(d)))

    def test_strict_boundary_types_and_supported_source(self):
        for key,value in (('format','other'),('mode','live'),('realNetworkRequests',False),
                          ('executionApproved',0),('integrationElapsedMs',True),
                          ('deadlineHeadroomMs',float('inf'))):
            d=fixture();d[key]=value
            with self.assertRaises(ValueError):t.summarize(d)
        d=fixture();d['requestedProgramFixtureBytes']=True
        self.assertIsNone(t.summarize(d)['fixtureBytes'])

    def test_duplicate_or_invalid_phases_rejected(self):
        d=fixture();d['diagnosticPhases'].append(copy.deepcopy(d['diagnosticPhases'][0]))
        with self.assertRaises(ValueError):t.summarize(d)
        for value in (True,-1,float('nan')):
            d=fixture();d['diagnosticPhases'][0]['elapsedMs']=value
            with self.assertRaises(ValueError):t.summarize(d)

    def test_bounded_read_duplicate_keys_nonfinite_and_truncated_gzip(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'input.json.gz'
            for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{}'*100):
                p.write_bytes(gzip.compress(raw))
                with patch.object(t,'MAX_BYTES',100),self.assertRaises(ValueError):t.read(p)
            p.write_bytes(gzip.compress(json.dumps(fixture()).encode())[:-8])
            with self.assertRaises(EOFError):t.read(p)
            p.write_bytes(gzip.compress(json.dumps(fixture()).encode()))
            self.assertEqual(len(t.read(p)['sourceDigest']),64)

    def test_cli_publishes_private_report_exclusively_without_network(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'in.gz';out=Path(root)/'out.gz'
            p.write_bytes(gzip.compress(json.dumps(fixture()).encode()))
            args=['timing_review.py','--before',str(p),'--after',str(p),'--output',str(out)]
            with patch('sys.argv',args),patch('socket.socket',side_effect=AssertionError('network')):
                t.main()
                self.assertEqual(out.stat().st_mode & 0o777,0o600)
                with self.assertRaises(FileExistsError):t.main()
            self.assertEqual(json.loads(gzip.decompress(out.read_bytes()))['comparison'],'not-comparable')

if __name__=='__main__':unittest.main()
