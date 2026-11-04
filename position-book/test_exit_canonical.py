"""Exact serialization reuse does not cache authorization or source reads."""
import json
import unittest
from unittest.mock import patch
import unsigned_exit_replacement as replacement
import canonical_replay
from preserved_exit_checks import case
from unsigned_exit_replacement_checks import case as original_case


class ExitCanonicalTests(unittest.TestCase):
    def test_observation_equivalence_and_unchanged_private_sources(self):
        results = []
        real_scope = canonical_replay.scope
        for enabled in (False, True):
            with case() as c:
                before = {str(p): p.read_bytes() for p in c.home.rglob('*') if p.is_file()}
                with patch.object(canonical_replay, 'scope', lambda: real_scope(enabled=enabled)):
                    r = c.observe()
                self.assertEqual(r['state'], 'preserved-exit-observation-complete')
                self.assertEqual(r['networkRequests'], 20)
                self.assertEqual(before, {str(p): p.read_bytes() for p in c.home.rglob('*') if p.is_file()})
                self.assertFalse(any(r[k] for k in ('preparationPersisted', 'replacementAppended',
                    'signaturesCreated', 'transactionsSent', 'privateKeyAccessed', 'reservationReleased',
                    'validForSubmission')))
                if enabled:
                    self.assertGreater(r['canonicalDigestReplay']['hits'], 0)
                    self.assertLessEqual(r['canonicalDigestReplay']['retainedBytes'], canonical_replay.MAX_BYTES)
                # Fixtures have their own generated keys and signatures. Compare
                # policy, amounts, headroom and complete RPC method order, not IDs.
                results.append((r['binding'], r['observationTiming'], [x['method'] for x in c.rpc.calls]))
        for field in ('quantityAtomic', 'protectedInventoryAtomic',
                      'feeCommitmentRemainingLamports', 'validUntilExclusiveMs'):
            self.assertEqual(results[0][0][field], results[1][0][field])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(results[0][2], results[1][2])

    def test_rehashed_ownership_change_rejected_after_cache_warmed(self):
        with original_case() as c, canonical_replay.scope() as stats:
            book = c.book()
            try:
                self.assertIsNotNone(replacement.preparation.original_saved(book, c.clock()))
                row = book.db.execute('SELECT value FROM admission_entry_accounting').fetchone()
                changed = json.loads(row[0]); changed['accounting']['ownedAcquiredAtomic'] = '999999'
                book.db.execute('UPDATE admission_entry_accounting SET value=?,hash=?',
                    (replacement.preparation.encoded(changed), replacement.digest(changed)))
                with self.assertRaisesRegex(ValueError, 'entry-accounting-source-conflict'):
                    replacement.preparation.original_saved(book, c.clock())
                self.assertGreater(stats()['hits'], 0)
            finally: book.close()



if __name__ == '__main__': unittest.main()
