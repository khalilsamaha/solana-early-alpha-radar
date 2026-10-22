#!/usr/bin/env python3
"""Read bounded historical quote windows from a live ledger or verified LOCAL backup."""
import argparse
import contextlib
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time

from build import ROOT, review, stamp, publish, read, MAX_TOTAL_BYTES
sys.path.insert(0, str(ROOT / 'operations-tools'))
import quote_backup

FORMAT = 'quote-history-capture-1'
BACKUPS = Path('/var/backups/solana-radar-quotes')
ARCHIVE_PATTERN = r'quote-\d{8}T\d{6}Z-[0-9a-f]{8}\.sqlite\.gz'
ROW_BYTES = 1024 * 1024
CHUNK_BYTES = 16 * 1024 * 1024
TOTAL_BYTES = 96 * 1024 * 1024
CHUNK_ROWS = 5000
TOTAL_ROWS = 20000
WAL_GROWTH = 32 * 1024 * 1024


def iso_ms(value):
    t = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.utcoffset() is None:
        raise ValueError('Timestamp requires an explicit timezone')
    result = int(t.timestamp() * 1000)
    if not stamp(result):
        raise ValueError('Invalid timestamp')
    return result


def sha(path):
    return quote_backup.sha(path)


def small_json(path, limit=262144):
    with path.open('rb') as f:
        raw = f.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Metadata cap reached')
    return json.loads(raw)


def backup_inventory(directory=BACKUPS):
    if not directory.exists():
        return []
    if directory.is_symlink():
        raise ValueError('Symlink backup directory refused')
    result = []
    # Own backup names only; inventory is not a claim that the archive is valid.
    names = sorted(p for p in directory.iterdir() if re.fullmatch(ARCHIVE_PATTERN, p.name))
    if len(names) > 100:
        raise ValueError('Backup inventory cap reached')
    for p in names:
        m = p.with_name(p.name + '.json')
        if p.is_symlink() or m.is_symlink() or not m.is_file():
            continue
        data = small_json(m)
        if data.get('format') == quote_backup.VERSION and data.get('archive') == p.name:
            result.append({'archive': p.name, 'snapshotCompletedAt': data.get('snapshotCompletedAt'),
                           'archiveBytes': p.stat().st_size, 'verification': 'not-yet-checked'})
    return result


@contextlib.contextmanager
def restored(archive):
    """Verify a local cloud-backup copy without calling rclone or starting a service."""
    archive = Path(archive)
    manifest_path = archive.with_name(archive.name + '.json')
    if archive.is_symlink() or manifest_path.is_symlink():
        raise ValueError('Symlink archive/manifest refused')
    manifest = small_json(manifest_path)
    if (manifest.get('format') != quote_backup.VERSION or manifest.get('archive') != archive.name
            or archive.stat().st_size > quote_backup.MAX_BYTES
            or sha(archive) != manifest.get('sha256')):
        raise ValueError('Archive identity, format or checksum mismatch')
    cutoff = iso_ms(manifest['snapshotCompletedAt'])
    if cutoff > int(time.time() * 1000):
        raise ValueError('Backup completion is in the future')
    with tempfile.TemporaryDirectory(prefix='radar-history-restore-') as temp:
        target = Path(temp) / 'observer.sqlite'
        size = 0
        with gzip.open(archive, 'rb') as source, target.open('xb') as out:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > quote_backup.MAX_BYTES:
                    raise ValueError('Restored database cap reached')
                out.write(chunk)
        os.chmod(target, 0o600)
        if size != manifest.get('databaseBytes') or quote_backup.logical_summary(target) != manifest.get('ledger'):
            raise ValueError('Restored table hashes, metadata or size differ from manifest')
        yield target, cutoff, {'kind': 'verified-local-quote-backup', 'archive': archive.name,
                              'sha256': manifest['sha256'], 'snapshotCompletedAt': manifest['snapshotCompletedAt'],
                              'cutoffMeaning': 'Backup completion upper bound; exact snapshot start was not stored.'}


def own_directory(path):
    os.chmod(path, 0o700)
    if os.geteuid() == 0 and os.environ.get('SUDO_UID', '').isdigit() and os.environ.get('SUDO_GID', '').isdigit():
        os.chown(path, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))


def capture(database, output, *, hours=72, chunk_hours=6, end_at=None, evidence_cutoff=None, source=None):
    if type(hours) is not int or not 1 <= hours <= 72 or type(chunk_hours) is not int or not 1 <= chunk_hours <= 12:
        raise ValueError('Hours must be 1..72; chunk hours 1..12')
    if (hours + chunk_hours - 1) // chunk_hours > 16:
        raise ValueError('More than 16 chunks requested')
    database = Path(database)
    if database.is_symlink() or not database.is_file():
        raise ValueError('Missing ledger or symlink ledger refused')
    output = Path(output).absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError('Output must be a new directory under an existing parent')
    if database.stat().st_size > quote_backup.MAX_BYTES:
        raise ValueError('Ledger exceeds 512 MiB capture budget')
    identity = (database.stat().st_dev, database.stat().st_ino)
    wal = Path(str(database) + '-wal')
    initial_wal = wal.stat().st_size if wal.exists() else 0
    deadline = time.monotonic() + 60

    def guard():
        if time.monotonic() > deadline:
            raise TimeoutError('Capture exceeded 60 seconds')
        if wal.exists() and wal.stat().st_size - initial_wal > WAL_GROWTH:
            raise ValueError('Capture WAL-growth cap reached')

    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.quote-history-') as tmp:
        stage = Path(tmp)
        with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=1) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA cache_size=-4096')
            db.execute('PRAGMA trusted_schema=OFF')
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            db.execute('BEGIN')
            meta = {}
            for key in ('sourceIdentity', 'registeredAt', 'version', 'limits', 'samplingRegistration', 'featureCaptureRegistration'):
                row = db.execute('SELECT v FROM meta WHERE k=?', (key,)).fetchone()
                if row:
                    if len(row[0].encode()) > 65536:
                        raise ValueError('Ledger metadata cap reached')
                    meta[key] = json.loads(row[0])
            captured = evidence_cutoff if evidence_cutoff is not None else int(time.time() * 1000)
            end = end_at if end_at is not None else captured
            if not stamp(captured) or not stamp(end) or end > captured:
                raise ValueError('Entry end must not exceed evidence cutoff')
            start = end - hours * 3600000
            if not stamp(start) or not isinstance(meta.get('sourceIdentity'), str) or not meta['sourceIdentity']:
                raise ValueError('Invalid start or missing source identity')
            retained = db.execute('SELECT min(detected),max(detected) FROM signals INDEXED BY signals_at').fetchone()
            index = {'format': FORMAT, 'sourceIdentity': meta['sourceIdentity'], 'capturedAt': captured,
                     'requestedStartAt': start, 'entryWindowEndAt': end, 'windowClock': 'observer-detected-time',
                     'source': source or {'kind': 'live-ledger', 'cutoffMeaning': 'Time of pinned read snapshot; not a historical observation timestamp.'},
                     'retainedDetectedBounds': list(retained), 'registeredAt': meta.get('registeredAt'),
                     'requestedStartPrecedesEarliestRetained': retained[0] is None or start < retained[0],
                     'chunks': [], 'complete': False,
                     'limitations': ['Requested windows are fully queried but do not prove the observer was continuously running.',
                                     'Pruned and never-recorded signals cannot be recovered from this source.',
                                     'Entry windows are half-open [start,end); outcomes use the later evidence cutoff.',
                                     'No new market requests, training, trading or cloud transfer.']}
            total_bytes, totals = 0, {'signals': 0, 'probes': 0}
            left = start
            while left < end:
                guard()
                right = min(left + chunk_hours * 3600000, end)
                report = {'format': 'quote-observer-report-0.2.0', 'sourceIdentity': meta['sourceIdentity'],
                          'capturedAt': captured, 'windowStartAt': left, 'entryWindowEndAt': right,
                          'observerVersion': meta.get('version'), 'registeredAt': meta.get('registeredAt'),
                          'limits': meta.get('limits'), 'samplingRegistration': meta.get('samplingRegistration'),
                          'featureCaptureRegistration': meta.get('featureCaptureRegistration'),
                          'capture': {'format': FORMAT, 'windowClock': 'observer-detected-time', 'sourceKind': index['source']['kind']},
                          'signals': [], 'probes': []}
                raw_bytes = 0
                for table, column, idx, tag in [('signals', 'detected', 'signals_at', 'decision'), ('probes', 'at', 'probes_at', 'state')]:
                    sql = f'SELECT seq,{column},CASE WHEN length(CAST(data AS BLOB))<={ROW_BYTES} THEN data END,{tag} FROM {table} INDEXED BY {idx} WHERE {column}>=? AND {column}<? ORDER BY {column},seq LIMIT {CHUNK_ROWS + 1}'
                    for seq, detected, raw, value in db.execute(sql, (left, right)):
                        guard()
                        if raw is None:
                            raise ValueError('Historical row byte cap reached; no capture published')
                        size = len(raw.encode())
                        raw_bytes += size
                        total_bytes += size
                        totals[table] += 1
                        if (size > ROW_BYTES or raw_bytes > CHUNK_BYTES or total_bytes > TOTAL_BYTES
                                or len(report[table]) >= CHUNK_ROWS or totals[table] > TOTAL_ROWS):
                            raise ValueError('Historical capture cap reached; reduce --chunk-hours or --hours. No capture published')
                        row = json.loads(raw)
                        record = row if table == 'signals' else row.get('signal', {})
                        if record.get('seq') != seq or record.get('detectedAt') != detected:
                            raise ValueError('Ledger index fields differ from stored event identity')
                        row[tag] = value
                        report[table].append(row)
                review(report)
                name = f'part-{len(index["chunks"]):02d}.json.gz'
                publish(stage / name, report)
                index['chunks'].append({'file': name, 'sha256': sha(stage / name), 'startAt': left, 'endAt': right,
                                         'signals': len(report['signals']), 'probes': len(report['probes'])})
                left = right
            db.rollback()
        guard()
        if identity != (database.stat().st_dev, database.stat().st_ino):
            raise ValueError('Source replaced during capture')
        index.update(complete=True, counts=totals, rawLedgerBytes=total_bytes)
        publish(stage / 'capture-index.json.gz', index)
        own_directory(stage)
        if output.exists():
            raise ValueError('Output appeared during capture')
        os.rename(stage, output)
    return index


def load_capture(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError('Symlink capture refused')
    index_path = directory / 'capture-index.json.gz'
    if index_path.is_symlink():
        raise ValueError('Symlink index refused')
    index, meta = read(index_path)
    parts = index.get('chunks', [])
    if index.get('format') != FORMAT or index.get('complete') is not True or not 1 <= len(parts) <= 16:
        raise ValueError('Incomplete or unsupported history capture')
    reports, provenance, total = [], [], 0
    left = index['requestedStartAt']
    for n, part in enumerate(parts):
        if part.get('file') != f'part-{n:02d}.json.gz' or part['startAt'] != left or part['endAt'] <= left:
            raise ValueError('Noncontiguous or invalid chunk index')
        path = directory / part['file']
        if path.is_symlink() or sha(path) != part['sha256']:
            raise ValueError('Chunk checksum mismatch')
        report, info = read(path)
        total += info['bytes']
        if total > MAX_TOTAL_BYTES:
            raise ValueError('Historical report byte cap reached')
        if (report.get('sourceIdentity') != index['sourceIdentity'] or report.get('capturedAt') != index['capturedAt']
                or report.get('windowStartAt') != left or report.get('entryWindowEndAt') != part['endAt']
                or len(report.get('signals', [])) != part['signals'] or len(report.get('probes', [])) != part['probes']):
            raise ValueError('Chunk metadata mismatch')
        for s in [*report['signals'], *(p['signal'] for p in report['probes'])]:
            if not stamp(s.get('detectedAt')) or not left <= s['detectedAt'] < part['endAt']:
                raise ValueError('Record outside its entry window')
        reports.append(report)
        provenance.append(info)
        left = part['endAt']
    if left != index['entryWindowEndAt']:
        raise ValueError('History window incomplete')
    return reports, provenance, {**index, 'indexSha256': meta['sha256']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group()
    source.add_argument('--database', type=Path)
    source.add_argument('--archive', type=Path)
    source.add_argument('--latest-backup', action='store_true')
    p.add_argument('--config', type=Path, default=Path('/etc/solana-radar-quotes.json'))
    p.add_argument('--hours', type=int, default=72)
    p.add_argument('--chunk-hours', type=int, default=6)
    p.add_argument('--end', help='Optional timezone-aware historical entry-window end')
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--list-backups', action='store_true')
    a = p.parse_args()
    if a.list_backups:
        print(json.dumps({'localQuoteBackups': backup_inventory()}, indent=2)); return
    if a.output_dir is None:
        p.error('--output-dir is required')
    end = iso_ms(a.end) if a.end else None
    archive = a.archive
    if a.latest_backup:
        rows = backup_inventory()
        if not rows:
            raise ValueError('No local quote-ledger archive with manifest found')
        archive = BACKUPS / rows[-1]['archive']
    with quote_backup.deadline(180):
        if archive:
            with restored(archive) as (database, cutoff, source):
                index = capture(database, a.output_dir, hours=a.hours, chunk_hours=a.chunk_hours,
                                end_at=end, evidence_cutoff=cutoff, source=source)
        else:
            database = a.database
            if database is None:
                config = small_json(a.config)
                database = Path(config['reports']) / 'observer.sqlite'
            index = capture(database, a.output_dir, hours=a.hours, chunk_hours=a.chunk_hours, end_at=end)
    print('Historical capture complete:', len(index['chunks']), 'chunks;', index['counts'])
    print('Source:', index['source']['kind'], '; no cloud transfer performed.')
    if index['requestedStartPrecedesEarliestRetained']:
        print('Note: requested start precedes the earliest retained row; this is not proof of full historical coverage.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Historical capture stopped (' + type(error).__name__ + '): ' + str(error))
