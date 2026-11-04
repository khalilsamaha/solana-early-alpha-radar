"""Fresh diagnostics for one exact expired pair; no preparation, signer or sender."""
import os
import time
import unsigned_exit_replacement as replacement
import admission_exit_capture as capture
import encoding_replay
import fresh_signing
from contract import digest
from core import check

VERSION = 'preserved-exit-observation-1'
view = capture.view


def identities(pair):
    check(type(pair) is tuple and len(pair) == 2 and all(
        type(x) is str and len(x) == 64 and all(c in '0123456789abcdef' for c in x)
        for x in pair) and pair[0] != pair[1], 'preserved-exit-identities')


def guard(book, root, pair, now):
    """Called only under the source lock and read-only journal context."""
    identities(pair)
    check(book.j.read_only is True, 'preserved-exit-read-only-required')
    check(not view.cycles.c.submit.swap.stop(root) and book.read()[0]['state'] == 'signed-recorded',
          'preserved-exit-stopped')
    from admission_lifecycle import KNOWN
    tables = book.db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'admission_%' LIMIT 65").fetchall()
    check(len(tables) <= 64 and all(row[0] in KNOWN for row in tables), 'preserved-exit-schema')
    check(not any(row[0] in replacement.BLOCKED_TABLES for row in tables), 'preserved-exit-later-evidence')
    check(not any(os.path.lexists(book.j.path.parent / name) for name in replacement.MARKERS),
          'preserved-exit-backend-marker')
    old = replacement.preparation.original_saved(book, now)
    check(old is not None and digest(old) == pair[0], 'preserved-exit-original-mismatch')
    check(replacement.exists(book) is not None, 'preserved-exit-replacement-required')
    current = replacement.replay(book, old, now)
    check(digest(current) == pair[1], 'preserved-exit-current-mismatch')
    check(now >= current['binding']['validUntilExclusiveMs'], 'preserved-exit-not-expired')
    replacement.preparation.owner(book, now)
    return current


def validate(book, root, pair, evidence, collection, binding, clock, monotonic, started):
    """Full fresh provenance and unchanged ownership; hypothetical record stays in memory."""
    from admission_exit_collection import review
    now = clock()
    binding = review(book, evidence, collection, now, binding)
    current = guard(book, root, pair, clock())
    hypothetical = dict(format=replacement.preparation.COLLECTED_FORMAT,
                        recordedAtMs=now, evidence=evidence, collection=collection, binding=binding)
    replacement.relationship(current, hypothetical)
    check(not view.cycles.c.submit.swap.stop(root), 'preserved-exit-stopped')
    check(not any(os.path.lexists(book.j.path.parent / name) for name in replacement.MARKERS),
          'preserved-exit-backend-marker')
    end = clock()
    check(now <= end < binding['validUntilExclusiveMs'], 'preserved-exit-validation-expired')
    check(0 <= monotonic() - started < 30, 'preserved-exit-time-budget')
    return end


@view.cycles.binding.operation
@fresh_signing.timing.signature_replay
@encoding_replay.operation
def observe(home, wallet, pool, *, expected_original_sha256, expected_current_sha256,
            allow_devnet_observation=False, opener=None, clock=view.now, monotonic=time.monotonic):
    check(allow_devnet_observation is True, 'explicit-devnet-observation-required')
    pair = (expected_original_sha256, expected_current_sha256)
    identities(pair)
    r = capture.collect(home, wallet, pool, opener=opener, clock=clock, monotonic=monotonic,
                        _preserved_expected=pair)
    r['format'] = VERSION
    r['state'] = ('preserved-exit-observation-complete' if r['state'] ==
                  'exit-evidence-collected-research-only' else 'preserved-exit-observation-unavailable')
    r.update(expectedOriginalSha256=pair[0], expectedCurrentSha256=pair[1],
             replacementAppended=False, existingReplacementLimitUnchanged=True,
             signerInvocationAttempts=0, persistenceAndSigningHeadroomMs=None)
    r['limitations'] = [
        'Fresh evidence is a diagnostic observation, not a preparation or execution authorization.',
        'At most twenty fixed devnet RPC requests including unsigned simulation; no retries.',
        'The original ten-second observation deadline and all ownership checks remain enforced.',
        'No original or replacement record is modified; the existing replacement slot stays consumed.',
        'Remaining time excludes persistence, signing and sending; success does not prove live execution fits.',
        'Source lock covers cooperating local tools, not unrelated wallet activity.']
    return r
