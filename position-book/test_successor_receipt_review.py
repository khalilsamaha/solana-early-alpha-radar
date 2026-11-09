"""Exact successor effects with disposable journals and synthetic receipts."""
from copy import deepcopy
import io
import json
import socket
import unittest
from unittest.mock import patch

import successor_receipt_review as m
import test_successor_submission as fixture
from admission_receipt_checks import receipt, failed, other_vault
from test_signed_exit_timing import files


class ReceiptReplies(fixture.Replies):
    def __init__(self, case, package):
        super().__init__(case); self.package = deepcopy(package)
    def open(self, request, timeout=None):
        with super().open(request, timeout) as response: result = json.load(response)
        method = json.loads(request.data)['method']
        if method == 'getSignatureStatuses':
            result['result'] = self.package['bundle']['rpcEvidence']['signatureStatus']['result']
        if method == 'getTransaction':
            tx = self.package['bundle']['rpcEvidence']['transaction']['result']
            result['result'] = None if tx is None else dict(deepcopy(tx),
                transaction=[self.package['signedTransactionBase64'], 'base64'])
        return io.BytesIO(json.dumps(result).encode())


class ReceiptReviewTests(unittest.TestCase):
    setUpClass = classmethod(fixture.SuccessorSubmissionTests.setUpClass.__func__)
    tearDownClass = classmethod(fixture.SuccessorSubmissionTests.tearDownClass.__func__)
    setUp = fixture.SuccessorSubmissionTests.setUp
    tearDown = fixture.SuccessorSubmissionTests.tearDown
    dispatch = fixture.SuccessorSubmissionTests.dispatch
    lost = fixture.SuccessorSubmissionTests.lost
    boundary = fixture.SuccessorSubmissionTests.boundary
    markers = fixture.SuccessorSubmissionTests.markers
    rows = fixture.SuccessorSubmissionTests.rows
    submit = fixture.SuccessorSubmissionTests.submit
    recover = fixture.SuccessorSubmissionTests.recover
    rewrite = fixture.SuccessorSubmissionTests.rewrite

    def package(self):
        book = self.c.book()
        try:
            record, _, _, signed, _ = m.submission.load(self.c.home, book, self.c.wallet,
                self.c.pool, self.candidate, lambda: self.c.now)
            private, scope = m.original.private_intent(book, signed, record['candidate'])
            evidence = record['candidate']['evidence']
            package = receipt(dict(scope=scope, costInputs=dict(
                simulation_item=evidence['simulationItem'], price=evidence['price'])), private)
            package['bundle']['rpcEvidence']['signatureStatus']['result']['value'][0]['confirmations'] = None
            return package, scope
        finally: book.close()

    def review(self):
        before = files(self.c)
        with (patch.object(socket.socket, 'connect', side_effect=AssertionError('network')),
              patch.object(m.submission.backend, '_invoke', side_effect=AssertionError('signer'))):
            result = m.status(self.c.home, self.c.wallet, self.c.pool, self.candidate, clock=lambda: self.c.now)
        self.assertEqual(files(self.c), before)
        for flag in ('accountingApplied', 'receiptEffectsReconciled', 'scopedClosureRecorded',
                     'currentWalletBalanceEstablished', 'retiredAttemptNonExecutionProven',
                     'sourceStateChanged', 'reservationsReleased', 'fundsAvailableForNewEntry',
                     'nextCycleAuthorized', 'executionApproved', 'networkRequests',
                     'privateKeyAccessed', 'signaturesCreated', 'transactionsSent'):
            self.assertFalse(result[flag], flag)
        for secret in (self.signed['signed']['signedWireBase64'], self.signed['signed']['signature'], self.c.wallet):
            self.assertNotIn(secret, json.dumps(result))
        return result

    def test_no_submission_ack_or_minimal_finalized_claim_is_not_effects(self):
        self.assertFalse(self.review()['receiptEffectsValidated'])
        self.submit()
        self.assertFalse(self.review()['receiptEffectsValidated'])
        self.recover()
        result = self.review()
        self.assertEqual(result['transportState'], 'successor-finalized-evidence')
        self.assertFalse(result['receiptEffectsValidated']); self.assertIsNone(result['effects'])

    def test_success_preserves_retired_exposure_and_does_not_apply_projected_fees(self):
        self.submit(); package, _ = self.package(); self.recover(ReceiptReplies(self, package))
        result = self.review()
        self.assertEqual(result['state'], 'successor-effects-observed-held', result)
        effects = result['effects']
        self.assertEqual(effects['ownedAcquiredResidualAtomic'], '0')
        self.assertEqual(effects['acquiredSpentAtomic'], self.held['ownedAcquiredHeldAtomic'])
        # The disposable successor capture has 1,000 units, of which 98 are owned.
        self.assertEqual(effects['protectedAcquiredInventoryAtomic'], '902')
        # Both synthetic receipts paid 5,001; the transport preflight quotes 5,000.
        self.assertEqual(effects['successorFeePaidLamports'], '5001')
        self.assertEqual(effects['knownFeesPaidLamports'], '10002')
        self.assertEqual(effects['retiredFeeExposureHeldLamports'], '10000')
        self.assertEqual(effects['journalFeeHeldLamports'], '20999')
        self.assertEqual(effects['projectedFeeHoldAfterKnownFeesLamports'], '15998')
        self.assertEqual(effects['projectedOtherFeeHeldLamports'], '5998')
        self.assertEqual(effects['attemptNumber'], 2)
        again = self.review()
        for key, value in result.items():
            # Per-call verifier timings are telemetry, not durable state.
            if key != 'signatureVerification': self.assertEqual(again[key], value, key)

    def test_finalized_failure_preserves_inventory_and_accounts_only_this_fee(self):
        self.submit(); package, _ = self.package()
        self.recover(ReceiptReplies(self, failed(package)))
        result = self.review()
        self.assertEqual(result['state'], 'successor-failure-effects-observed-held', result)
        self.assertEqual(result['effects']['ownedAcquiredResidualAtomic'], self.held['ownedAcquiredHeldAtomic'])
        self.assertEqual(result['effects']['acquiredSpentAtomic'], '0')
        self.assertEqual(result['effects']['sourceProceedsObservedAtomic'], '0')
        self.assertEqual(result['effects']['retiredFeeExposureHeldLamports'], '10000')

    def test_expiry_and_stop_allow_keyless_historical_review(self):
        self.submit(); package, _ = self.package(); self.recover(ReceiptReplies(self, package))
        self.c.now += 30000; (self.c.home/'STOP').touch(mode=0o600)
        self.assertFalse((self.c.home/'signer.pk8').exists())
        self.assertTrue(self.review()['receiptEffectsValidated'])

    def test_rehashed_bad_economic_metadata_never_becomes_usable(self):
        self.submit(); package, scope = self.package(); self.recover(ReceiptReplies(self, package))
        saved = self.c.path.read_bytes()
        changed = []
        p = deepcopy(package); p['bundle']['rpcEvidence']['transaction']['result']['meta']['fee'] = 10001; changed.append(p)
        p = deepcopy(package); p['bundle']['rpcEvidence']['transaction']['result']['meta'].pop('preTokenBalances'); changed.append(p)
        changed.append(other_vault(package, scope))
        p = deepcopy(package)
        tx = p['bundle']['rpcEvidence']['transaction']['result']
        index = tx['transaction']['message']['accountKeys'].index(scope['accounts']['source'])
        next(x for x in tx['meta']['postTokenBalances'] if x['accountIndex'] == index)['uiTokenAmount']['amount'] = '499999999'
        changed.append(p)
        for p in changed:
            with self.subTest(metadata=p['bundle']['rpcEvidence']['transaction']['result']['meta'].keys()):
                self.c.path.write_bytes(saved)
                def mutate(seq, value):
                    if value['kind'] == 'capture':
                        value['rpcEvidence']['transaction']['result']['meta'] = p['bundle']['rpcEvidence']['transaction']['result']['meta']
                self.rewrite(mutate)
                self.assertFalse(self.review()['receiptEffectsValidated'])

    def test_wrong_generation_is_rejected_without_writes(self):
        self.submit(); package, _ = self.package(); self.recover(ReceiptReplies(self, package))
        before = files(self.c)
        with self.assertRaises(ValueError):
            m.status(self.c.home, self.c.wallet, self.c.pool, '0'*64, clock=lambda: self.c.now)
        self.assertEqual(files(self.c), before)
        self.rewrite(lambda seq, v: v['rpcEvidence']['transaction']['result'].update(
            transaction=[self.c.exit_wire, 'base64']) if v['kind'] == 'capture' else None)
        self.assertFalse(self.review()['receiptEffectsValidated'])


if __name__ == '__main__': unittest.main()
