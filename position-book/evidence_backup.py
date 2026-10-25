"""Local, key-excluded snapshots of closed controlled-devnet evidence.

This is not wallet recovery or an executable restore. The only restore operation
uses a disposable directory, injects STOP, replays receipts, and removes the copy.
"""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile

import readiness as r
from core import check, directory, private_file, loads, sync_directory, write_new
from journal import read_only_journals

VERSION = 'private-devnet-evidence-backup-1'
MANIFEST = 'manifest.json'
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_FILES = 512
MAX_DIRS = 64
KEY = 'signer.pk8'
EXCLUDED_KEYS = frozenset([KEY] + [f'test-token-pair-v1/{name}.pk8'
                                 for name in ('mintA', 'mintB', 'holderA', 'holderB')]
                         + [f'token-lifecycle-v1/{name}.pk8' for name in ('source', 'destination')])


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def safe_name(name):
    check(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', name) is not None,
          'unsupported-evidence-name')


def metadata(path, *, folder=False):
    s = path.lstat()
    check(s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == (0o700 if folder else 0o600)
          and (stat.S_ISDIR(s.st_mode) if folder else stat.S_ISREG(s.st_mode) and s.st_nlink == 1),
          'unsafe-evidence-entry')
    return s


def inventory(root, *, source=False):
    """Bounded tree walk; never follows links or reads the excluded key."""
    root = directory(root)
    files = {}; dirs = []; total = 0
    def walk(parent, depth):
        nonlocal total
        check(depth <= 4, 'evidence-depth-cap')
        with os.scandir(parent) as entries:
            for item in entries:
                check(len(files) + len(dirs) < MAX_FILES + MAX_DIRS, 'evidence-entry-cap')
                p = Path(item.path); name = p.relative_to(root).as_posix()
                safe_name(p.name)
                if source and name in EXCLUDED_KEYS:
                    metadata(p)  # permissions/type only; never open the key
                    continue
                check(p.suffix != '.pk8' and not p.name.endswith(('-wal', '-shm', '-journal')),
                      'key-or-database-recovery-file-refused')
                s = p.lstat()
                if stat.S_ISDIR(s.st_mode):
                    metadata(p, folder=True); dirs.append(name)
                    check(len(dirs) <= MAX_DIRS, 'directory-cap')
                    walk(p, depth + 1)
                else:
                    metadata(p)
                    check(p.suffix in ('.json', '.sqlite') or p.name in ('STOP', 'session.lock'),
                          'unsupported-evidence-file')
                    check(len(files) < MAX_FILES and s.st_size <= MAX_FILE, 'file-cap')
                    total += s.st_size; check(total <= MAX_TOTAL, 'total-byte-cap')
                    raw = private_file(p, MAX_FILE)
                    check(len(raw) == s.st_size, 'evidence-size-changed')
                    files[name] = dict(bytes=len(raw), sha256=sha(raw))
    walk(root, 0)
    return dict(directories=sorted(dirs), files=dict(sorted(files.items())), bytes=total)


def write_bytes(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    sync_directory(path.parent)


def copy_inventory(source, target, inv):
    for name in sorted(inv['directories'], key=lambda n: (n.count('/'), n)):
        (target / name).mkdir(mode=0o700)
        sync_directory((target / name).parent)
    for name, expected in inv['files'].items():
        raw = private_file(source / name, MAX_FILE)
        check(dict(bytes=len(raw), sha256=sha(raw)) == expected, 'evidence-changed-during-copy')
        write_bytes(target / name, raw)


def sqlite_integrity(root, inv):
    count = 0
    for name in inv['files']:
        if not name.endswith('.sqlite'):
            continue
        # All SQLite checks run on the isolated copy. No immutable mode or repair.
        path = root / name
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)
        try:
            db.execute('PRAGMA query_only=ON')
            check(db.execute('PRAGMA journal_mode').fetchone()[0] == 'delete', 'unsupported-journal-mode')
            budget = [0]
            def progress():
                budget[0] += 1
                return int(budget[0] > 100000)
            db.set_progress_handler(progress, 1000)
            check(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'sqlite-integrity-failed')
            count += 1
        finally:
            db.close()
    check(count > 0, 'missing-databases')
    return count


def historical_ok(report):
    check(report['blockingReasons'] in ([], ['stop-marker-present']), 'closed-evidence-required')


def replay(payload, inv, wallet, pool, temp_parent):
    """No caller-supplied restore destination and no persistent executable copy."""
    with tempfile.TemporaryDirectory(prefix='.restore-check-', dir=temp_parent) as tmp:
        root = Path(tmp)
        copy_inventory(payload, root, inv)
        check(inventory(root) == inv, 'restore-bytes-mismatch')
        databases = sqlite_integrity(root, inv)
        if not (root / 'STOP').exists():
            write_bytes(root / 'STOP', b'restore verification only\n')
        before = inventory(root)
        report = r.inspect(root, wallet, pool)
        historical_ok(report)
        check(report['stopRequested'] and report['blockingReasons'] == ['stop-marker-present'],
              'restore-must-remain-stopped')
        check(inventory(root) == before, 'restore-replay-mutated-evidence')
    return databases


def public_report(inv, databases, manifest_hash, created):
    return dict(format=VERSION, state='isolated-restore-verified', capturedAt=stamp(),
        snapshotCreatedAt=created, manifestSha256=manifest_hash,
        files=len(inv['files']), bytes=inv['bytes'], sqliteDatabasesChecked=databases,
        closedCyclesVerified=2, byteHashesVerified=True, receiptReplayVerified=True,
        temporaryRestoreRemoved=True, restoredCopyStopped=True,
        signingKeyIncluded=False, privateKeyAccessed=False, sourceStateChanged=False,
        networkRequests=0, signaturesCreated=0, transactionsSent=0, cloudRequests=0,
        executionApproved=False, mainnetEnabled=False,
        limitations=[
            'Local private evidence snapshot only; not an off-machine backup or signing-key recovery.',
            'Contains private signed transaction evidence. Do not upload the snapshot or its manifest.',
            'Hashes detect corruption, not malicious replacement of both evidence and manifest.',
            'Historical replay cannot prove current chain state or that this is the latest snapshot.',
            'Never replace active journals with this snapshot or use it to reset spending reservations.',
            'Only the fixed two closed cycles are semantically replayed; other retained SQLite files receive integrity checks.',
            'No scanner, observer, frozen-study, key-custody or execution policy is changed.'])


@r.cycles.binding.operation
def capture(home, wallet, pool, destination):
    home = directory(home)
    destination = Path(destination).absolute()
    parent = directory(destination.parent)
    check(not destination.is_relative_to(home) and not home.is_relative_to(destination), 'snapshot-source-overlap')
    check(not os.path.lexists(destination), 'snapshot-already-exists')
    with r.cycles.c.source_lock(home, wallet), read_only_journals():
        inv = inventory(home, source=True)
        historical_ok(r.inspect_locked(home, wallet, pool))
        # mkdir is exclusive. An interrupted/failed capture stays visibly incomplete;
        # never overwrite or remove it automatically. Manifest is the final seal.
        destination.mkdir(mode=0o700); sync_directory(parent)
        payload = destination / 'evidence'; payload.mkdir(mode=0o700)
        copy_inventory(home, payload, inv)
        check(inventory(home, source=True) == inv, 'source-changed-during-capture')
        databases = replay(payload, inv, wallet, pool, destination)
        check(inventory(payload) == inv, 'snapshot-changed-during-check')
        created = stamp()
        manifest = dict(format=VERSION, createdAt=created, wallet=wallet, pool=pool,
                        inventory=inv, excludedSigningKeys=sorted(EXCLUDED_KEYS))
        write_new(destination / MANIFEST, manifest)
        sync_directory(destination)
        return public_report(inv, databases, sha(private_file(destination / MANIFEST, 262144)), created)


def verify(snapshot, wallet, pool):
    snapshot = directory(snapshot)
    check(set(p.name for p in snapshot.iterdir()) == {'evidence', MANIFEST}, 'incomplete-or-unexpected-snapshot')
    raw = private_file(snapshot / MANIFEST, 262144)
    manifest = loads(raw)
    check(set(manifest) == {'format', 'createdAt', 'wallet', 'pool', 'inventory', 'excludedSigningKeys'}
          and manifest['format'] == VERSION and manifest['wallet'] == wallet and manifest['pool'] == pool
          and manifest['excludedSigningKeys'] == sorted(EXCLUDED_KEYS) and isinstance(manifest['createdAt'], str),
          'snapshot-manifest-mismatch')
    check(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00', manifest['createdAt']) is not None,
          'invalid-snapshot-timestamp')
    datetime.fromisoformat(manifest['createdAt'])
    payload = snapshot / 'evidence'
    # Enumerate actual safe paths; never extract or trust a manifest path.
    inv = inventory(payload)
    check(inv == manifest['inventory'], 'snapshot-integrity-mismatch')
    databases = replay(payload, inv, wallet, pool, snapshot.parent)
    check(inventory(payload) == inv and private_file(snapshot / MANIFEST, 262144) == raw,
          'snapshot-changed-during-check')
    return public_report(inv, databases, sha(raw), manifest['createdAt'])
