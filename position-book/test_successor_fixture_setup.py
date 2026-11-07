"""Disposable history reuse ends before successor timing; failures stay explicit."""
import json
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import successor_signing_rehearsal as m
from contract import Rejected
from locked_admission_checks import fixture
import pre_sign_admission as admission


class FixtureSetupTests(unittest.TestCase):
    def test_scopes_active_only_inside_setup_and_real_clock_functions_unchanged(self):
        clocks=(time.time,time.monotonic,m.m.view.now)
        calls=[]
        def construct():
            scopes=(m.m.canonical_replay._SCOPE,m.m.serialization_replay._SCOPE,
                m.m.encoding_replay._SCOPE,m.m.admission_history_replay._SCOPE,
                m.m.successor.history.fresh_signing.timing.wire._SIGNATURE_SCOPE)
            self.assertTrue(all(s.get() is not None for s in scopes))
            self.assertEqual(clocks,(time.time,time.monotonic,m.m.view.now))
            calls.append('setup')
        r=m.setup_history(SimpleNamespace(setUpClass=construct))
        self.assertEqual(calls,['setup']);m.require_cold_reuse_scopes()
        self.assertTrue(r['canonicalTextReplay']['enabled'])
        self.assertTrue(r['canonicalDigestReplay']['enabled'])
        self.assertFalse(r['canonicalDigestReplay']['reusesValidationOrAuthorization'])

    def test_failed_setup_clears_every_scope_without_retry(self):
        calls=[]
        def fail():calls.append('setup');raise Rejected('quote-read-stale-or-future')
        with self.assertRaisesRegex(Rejected,'quote-read-stale-or-future'):
            m.setup_history(SimpleNamespace(setUpClass=fail))
        self.assertEqual(calls,['setup']);m.require_cold_reuse_scopes()

    def test_exact_reuse_does_not_accept_expired_real_validator_input(self):
        e,p,_=fixture();stamp=e['completedAtMs']
        def build():
            with patch.object(admission,'BASELINE',e['costInputs']['baseline']):
                admission.review(e,p,stamp)
                # Same raw evidence, later clock: reuse is not an authorization cache.
                with self.assertRaisesRegex(Rejected,'quote-read-stale-or-future'):
                    admission.review(e,p,stamp+10001)
        m.setup_history(SimpleNamespace(setUpClass=build));m.require_cold_reuse_scopes()

    def test_known_contract_rejection_is_bounded_without_arbitrary_error_text(self):
        for exc,expected in ((Rejected('quote-read-stale-or-future'),'quote-read-stale-or-future'),
                (Rejected('PRIVATE PROVIDER DETAIL'),'unclassified'),
                (ValueError('PRIVATE KEY DETAIL'),'unclassified'),
                (ValueError({'private':'DETAIL'}),'unclassified')):
            report={'phases':[]}
            with self.assertRaises(type(exc)):
                with m.phase(report,'fixture-class-setup'):raise exc
            row=report['phases'][0]
            self.assertFalse(row['completed']);self.assertEqual(row['diagnosticCode'],expected)
            self.assertNotIn('PRIVATE',json.dumps(report));self.assertNotIn('DETAIL',json.dumps(report))


if __name__=='__main__':unittest.main()
