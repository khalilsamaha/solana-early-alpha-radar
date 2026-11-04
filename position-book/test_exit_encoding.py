"""Warm pure conversions do not hide rehashed accounting changes."""
import json
import unittest
import unsigned_exit_replacement as replacement
import encoding_replay
from unsigned_exit_replacement_checks import case


class ExitEncodingTests(unittest.TestCase):
    def test_rehashed_ownership_change_is_replayed_with_warm_encodings(self):
        with case() as c, encoding_replay.scope() as statistics:
            book=c.book()
            try:
                saved=replacement.preparation.original_saved(book,c.clock())
                self.assertIsNotNone(saved)
                row=book.db.execute('SELECT value FROM admission_entry_accounting').fetchone()
                changed=json.loads(row[0]);changed['accounting']['ownedAcquiredAtomic']='999999'
                book.db.execute('UPDATE admission_entry_accounting SET value=?,hash=?',
                    (replacement.preparation.encoded(changed),replacement.digest(changed)))
                with self.assertRaisesRegex(ValueError,'entry-accounting-source-conflict'):
                    replacement.preparation.original_saved(book,c.clock())
                self.assertGreater(statistics()['hits'],0)
                self.assertLessEqual(statistics()['entries'],encoding_replay.MAX_ENTRIES)
            finally:book.close()


if __name__=='__main__':unittest.main()
