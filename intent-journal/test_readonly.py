"""Read-only contexts cannot create, recover or modify journal databases."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import journal


class ReadOnlyCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name);self.home.chmod(0o700)
        self.path=self.home/'journal #?.sqlite';j=journal.Journal(self.path);j.close()
    def tearDown(self):self.tmp.cleanup()
    def test_reads_work_and_database_bytes_remain_identical(self):
        before=self.path.read_bytes()
        with journal.read_only_journals():
            j=journal.Journal(self.path,create=False)
            try:
                with j.transaction():self.assertEqual(j.db.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)
            finally:j.close()
        self.assertEqual(before,self.path.read_bytes())
    def test_no_creation_even_when_create_default_true(self):
        path=self.home/'missing.sqlite'
        with journal.read_only_journals():
            with self.assertRaises(FileNotFoundError):journal.Journal(path)
        self.assertFalse(path.exists())
    def test_writes_fail_even_after_query_only_is_disabled(self):
        with journal.read_only_journals():
            j=journal.Journal(self.path)
            try:
                j.db.execute('PRAGMA query_only=OFF')
                with self.assertRaises(sqlite3.OperationalError):
                    with j.transaction():j.db.execute('CREATE TABLE forbidden(x)')
            finally:j.close()
        j=journal.Journal(self.path)
        try:self.assertIsNone(j.db.execute("SELECT name FROM sqlite_master WHERE name='forbidden'").fetchone())
        finally:j.close()
    def test_recovery_sidecars_refused_and_preserved(self):
        for suffix in ('-journal','-wal','-shm'):
            p=Path(str(self.path)+suffix);p.write_bytes(b'preserve');p.chmod(0o600)
            try:
                with journal.read_only_journals():
                    with self.assertRaisesRegex(ValueError,'recovery-files'):journal.Journal(self.path)
                self.assertEqual(p.read_bytes(),b'preserve')
            finally:p.unlink()
    def test_context_resets_after_exception(self):
        with self.assertRaises(RuntimeError):
            with journal.read_only_journals():raise RuntimeError('exit')
        p=self.home/'new.sqlite';j=journal.Journal(p);j.close();self.assertTrue(p.exists())
    def test_symlink_permissions_and_hardlink_refused(self):
        self.path.chmod(0o644)
        with journal.read_only_journals():
            with self.assertRaises(ValueError):journal.Journal(self.path)
        self.path.chmod(0o600);p=self.home/'link';p.symlink_to(self.path)
        with journal.read_only_journals():
            with self.assertRaises(ValueError):journal.Journal(p)
        p.unlink();os.link(self.path,p)
        with journal.read_only_journals():
            with self.assertRaises(ValueError):journal.Journal(self.path)


if __name__=='__main__':unittest.main()
