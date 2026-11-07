"""An existing retirement object can deny execution, never grant it."""
from core import check
TABLE='admission_exit_retirement'


def present(book):
    # Even a malformed table or view must block before preflight/signing.
    return book.db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(TABLE,)).fetchone() is not None


def require_active(book):
    check(not present(book),'exit-attempt-retired-or-marker-invalid')
