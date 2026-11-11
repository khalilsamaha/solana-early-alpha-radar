#!/usr/bin/env python3
"""Bounded C1 inventory of saved identities and bytes; never evaluates a model."""
import argparse
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024
DAY = 86400000
# history.load_capture -> build.read hashes the exact decompressed index bytes,
# not the gzip transport or a canonical reserialization. Keep those accepted pins.
CAPTURE_PINS = {
    'b0-live': 'af0eadf277dab988214db0211d1f33267c7f22b3c4a05688d5c621f0d552baff',
    'b0-backup': 'c849f63950f96a49bdf1868539332ddb9b58d0e60cbd3ec954931360bc49103b',
}


class InventoryError(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise InventoryError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def literal(path, name):
    values = [ast.literal_eval(n.value) for n in ast.parse(path.read_text()).body
              if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    require(len(values) == 1, 'source-constant')
    return values[0]


ARTIFACT_PIN = literal(ROOT/'forward-study/experiment.py', 'ARTIFACT_SHA256')
REVIEW_PIN = literal(Path(__file__).with_name('confirmation.py'), 'REVIEW_HASH')
DIAGNOSTIC_PIN = literal(Path(__file__).with_name('confirmation.py'), 'DIAGNOSTIC_HASH')
FORWARD_PROTOCOL = json.loads((ROOT/'forward-study/protocol.json').read_text())
PROTOCOL = json.loads(Path(__file__).with_name('protocol.json').read_text())


def fingerprint(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode, s.st_nlink)


class Reader:
    def __init__(self):
        self.deadline = time.monotonic() + 60
        self.bytes = 0
        self.identities = {}

    def guard(self):
        require(time.monotonic() < self.deadline, 'read-deadline')
        require(self.bytes <= 512 * MIB, 'total-byte-cap')

    def track(self, path, private=False, directory=False):
        self.guard()
        path = Path(path).absolute()
        require(path.resolve() == path, 'symlink-path')
        s = path.lstat()
        require(stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink == 1,
                'input-type-or-link')
        if private:
            require(s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == (0o700 if directory else 0o600),
                    'private-permissions')
        mark = fingerprint(s)
        require(path not in self.identities or self.identities[path] == mark, 'source-changed')
        self.identities[path] = mark
        return path, s

    def read(self, path, cap, private=False, retain=True):
        path, before = self.track(path, private)
        require(before.st_size <= cap, 'file-byte-cap')
        pieces = []
        sha = hashlib.sha256()
        count = 0
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            require(fingerprint(os.fstat(stream.fileno())) == fingerprint(before), 'source-changed')
            while True:
                self.guard()
                block = stream.read(min(MIB, cap + 1 - count))
                if not block:
                    break
                count += len(block)
                self.bytes += len(block)
                require(count <= cap, 'file-byte-cap')
                sha.update(block)
                if retain:
                    pieces.append(block)
            require(fingerprint(os.fstat(stream.fileno())) == fingerprint(before), 'source-changed')
        require(fingerprint(path.lstat()) == fingerprint(before) and count == before.st_size, 'source-changed')
        self.guard()
        return b''.join(pieces), {'compressedSha256': sha.hexdigest(), 'compressedBytes': count}

    def metadata(self, path, cap, private=False):
        raw, identity = self.read(path, cap, private)
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            decoded = stream.read(cap + 1)
        require(len(decoded) <= cap, 'decoded-byte-cap')
        def pairs(items):
            out = {}
            for key, value in items:
                require(key not in out, 'duplicate-json-key')
                out[key] = value
            return out
        def constant(_):
            raise InventoryError('nonfinite-json')
        value = json.loads(decoded, object_pairs_hook=pairs, parse_constant=constant)
        require(isinstance(value, dict), 'metadata-object')
        self.guard()
        return value, {**identity, 'decodedSha256': hashlib.sha256(decoded).hexdigest()}

    def finish(self):
        for path, expected in self.identities.items():
            self.guard()
            require(path.resolve() == path and fingerprint(path.lstat()) == expected, 'source-changed')


def tokens(value):
    require(isinstance(value, list) and len(value) <= 10000
            and all(isinstance(x, str) and 1 <= len(x) <= 64 for x in value), 'token-list')
    require(value == sorted(set(value)), 'token-list-order')
    return value


def seal(value, field):
    data = {k: v for k, v in value.items() if k != field}
    require(value.get(field) == digest(data), 'metadata-seal')
    return data


def registrations(reader, original, confirmation, now):
    models = []
    files = {}
    for role, directory in (('original', original), ('confirmation', confirmation)):
        reader.track(directory, private=True, directory=True)
        sealed, info = reader.metadata(directory/'model.json.gz', 8*MIB, private=True)
        model = seal(sealed, 'artifactSha256')
        require(digest(model) == ARTIFACT_PIN and model.get('format') == 'forward-model-1'
                and model.get('protocol') == FORWARD_PROTOCOL and model.get('protocolSha256') == digest(FORWARD_PROTOCOL)
                and model.get('modelFrozen') is True and model.get('liveUseAllowed') is False, 'frozen-model-identity')
        models.append(model)
        files[role+'Model'] = info
    require(models[0] == models[1], 'model-copy-mismatch')
    model = models[0]
    old_sealed, files['originalRegistration'] = reader.metadata(original/'experiment.json.gz', 16384, private=True)
    new_sealed, files['confirmationRegistration'] = reader.metadata(confirmation/'registration.json.gz', 2*MIB, private=True)
    old = seal(old_sealed, 'registrationSha256')
    new = seal(new_sealed, 'registrationSha256')
    train = tokens(model.get('seenTrainingMints'))
    excluded = tokens(new.get('excludedMints'))
    groups = [g for g in model['groups'] if g['cohort'] == PROTOCOL['cohort'] and g['target'] == PROTOCOL['target']]
    require(len(groups) == 1 and isinstance(groups[0].get('models'), dict), 'legacy-model-absent')
    weights = groups[0]['models']['legacy']
    for value in (model['frozenAt'], model['trainingCutoffAt'], model['testNotBeforeAt'], old.get('installedAt'),
                  old.get('testNotBeforeAt'), new.get('registeredAt'), new.get('developmentCutoffAt'),
                  new.get('startAt'), new.get('endAt'), new.get('reviewNotBeforeAt')):
        require(type(value) is int and 0 < value <= now, 'registration-clock')
    require(old.get('format') == 'frozen-forward-experiment-1' and old.get('artifactSha256') == ARTIFACT_PIN
            and old.get('sourceIdentity') == model['sourceIdentity'] and old.get('liveUseAllowed') is False
            and old['installedAt'] >= model['frozenAt']
            and old['testNotBeforeAt'] == max(model['testNotBeforeAt'], old['installedAt']+FORWARD_PROTOCOL['holdout']['embargoMs']),
            'original-registration')
    require(new.get('format') == 'availability-confirmation-1' and new.get('protocol') == PROTOCOL
            and new.get('protocolSha256') == digest(PROTOCOL) and new.get('artifactSha256') == ARTIFACT_PIN
            and new.get('modelSha256') == digest(weights) and new.get('sourceIdentity') == model['sourceIdentity']
            and new.get('reviewedReportSha256') == REVIEW_PIN and new.get('diagnosticSha256') == DIAGNOSTIC_PIN
            and new.get('liveUseAllowed') is False and set(train).issubset(excluded)
            and new.get('excludedMintsSha256') == digest(excluded)
            and model['frozenAt'] <= new['developmentCutoffAt'] < new['registeredAt']
            and new['startAt'] == ((new['registeredAt']+PROTOCOL['maturityMs'])//DAY+1)*DAY
            and new['endAt'] == new['startAt']+PROTOCOL['durationDays']*DAY
            and new['reviewNotBeforeAt'] == new['endAt']+PROTOCOL['maturityMs'], 'confirmation-registration')
    summary = {'state': 'pinned-artifact-and-registration-bindings-verified', 'files': files, 'artifactSha256': ARTIFACT_PIN,
               'legacyModelSha256': digest(weights), 'originalRegistrationSha256': digest(old),
               'confirmationRegistrationSha256': digest(new), 'protocolSha256': digest(PROTOCOL),
               'sourceIdentitySha256': digest(model['sourceIdentity']), 'threshold': PROTOCOL['threshold'],
               'frozenAt': model['frozenAt'], 'trainingCutoffAt': model['trainingCutoffAt'],
               'originalEvaluationWindow': [old['testNotBeforeAt'], new['developmentCutoffAt']],
               'confirmationEntryWindow': [new['startAt'], new['endAt']],
               'confirmationReviewNotBeforeAt': new['reviewNotBeforeAt'],
               'trainingTokens': {'count': len(train), 'sha256': digest(train)},
               'trainingAndDevelopmentTokens': {'count': len(excluded), 'sha256': digest(excluded)},
               'developmentOnlyTokens': len(set(excluded)-set(train)), 'futureExclusionRegistryComplete': False}
    return summary, model['sourceIdentity']


def catalog(reader, directory, source, now, pin=None):
    reader.track(directory, directory=True)
    index, info = reader.metadata(directory/'capture-index.json.gz', 65536)
    require(pin is None or info['decodedSha256'] == pin, 'pinned-index-mismatch')
    require(index.get('format') == 'quote-history-capture-1' and index.get('complete') is True
            and index.get('windowClock') == 'observer-detected-time'
            and isinstance(index.get('sourceIdentity'), str), 'capture-index')
    require(source is None or index['sourceIdentity'] == source, 'capture-source-mismatch')
    start, end, at = (index.get(k) for k in ('requestedStartAt', 'entryWindowEndAt', 'capturedAt'))
    require(all(type(v) is int for v in (start, end, at)) and 0 < start < end <= at <= now, 'capture-clock')
    chunks = index.get('chunks')
    require(isinstance(chunks, list) and 1 <= len(chunks) <= 16, 'chunk-count')
    cursor, compressed = start, 0
    for n, chunk in enumerate(chunks):
        require(chunk.get('file') == f'part-{n:02d}.json.gz'
                and re.fullmatch(r'[0-9a-f]{64}', str(chunk.get('sha256'))) is not None
                and type(chunk.get('startAt')) is int and type(chunk.get('endAt')) is int
                and chunk['startAt'] == cursor < chunk['endAt'] <= end, 'chunk-index')
        _, part = reader.read(directory/chunk['file'], 16*MIB, retain=False)
        require(part['compressedSha256'] == chunk['sha256'], 'chunk-checksum')
        compressed += part['compressedBytes']
        cursor = chunk['endAt']
    require(cursor == end, 'capture-window-gap')
    return {**info, 'requestedWindow': [start, end], 'capturedAt': at, 'chunks': len(chunks),
            'chunkCompressedBytes': compressed, 'chunkBytesVerified': True, 'chunkPayloadsDecoded': False,
            'sourceIdentitySha256': digest(index['sourceIdentity']), 'sourceMatchedModel': source is not None,
            'fullReplayVerified': False, 'tokenMembershipExtracted': False}


def capture_directories(reader, root):
    folder = root/'captures'
    reader.track(folder, directory=True)
    names = []
    with os.scandir(folder) as entries:
        for entry in entries:
            require(len(names) < 32, 'directory-entry-cap')
            names.append(entry.name)
    captures = sorted(n for n in names if n.startswith('capture-'))
    require(1 <= len(captures) <= 8, 'capture-directory-count')
    require(all(re.fullmatch(r'capture-[A-Za-z0-9-]{1,80}', n) for n in captures), 'capture-name')
    return [folder/name for name in captures]


def window_inventory(captures, role, target):
    start, end = target
    require(start < end, 'evaluation-window')
    rows = [value for key, value in captures.items() if key.startswith(role+'-') and value is not None]
    windows = sorted([max(start, r['requestedWindow'][0]), min(end, r['requestedWindow'][1])]
                     for r in rows if r['requestedWindow'][0] < end and r['requestedWindow'][1] > start)
    gaps, cursor = [], start
    for a, b in windows:
        if a > cursor:
            gaps.append([cursor, a])
        cursor = max(cursor, b)
    if cursor < end:
        gaps.append([cursor, end])
    return {'targetRequestedWindow': target, 'uncoveredRequestedIntervals': gaps,
            'requestedWindowCovered': not gaps, 'latestEvidenceCutoffAt': max((r['capturedAt'] for r in rows), default=None),
            'continuousUptimeVerified': False, 'completeObservationsVerified': False}


def inventory(original, confirmation, live, backup):
    reader, now = Reader(), time.time_ns()//1000000
    report = {'format': 'c1-metadata-inventory-1', 'state': 'inventory-complete-readiness-blocked',
              'capturedAt': now, 'identities': None, 'captures': {}, 'errors': [],
              'networkRequests': 0, 'outcomePayloadsDecoded': False, 'modelEvaluated': False,
              'modelTrained': False, 'studyRegistered': False, 'gatePassed': False, 'liveUseAllowed': False,
              'offMachineRestoreVerified': False, 'futureExclusionRegistryComplete': False,
              'remainingGaps': ['confirmation-and-later-inspected-token-membership-not-reconciled',
                                'registration-digests-not-reconciled-with-earlier-accepted-reports',
                                'original-reviewed-capture-set-not-reconciled',
                                'new-study-off-machine-restore-and-retention-not-verified',
                                'numeric-decision-tolerances-not-agreed',
                                'untouched-window-and-dependent-sample-contract-not-agreed'],
              'limitations': ['Saved-file metadata and compressed-byte checks only; no capture payload decoding.',
                              'Catalog is not proof of reviewed membership, uptime, full replay or fresh holdout.',
                              'Existing registrations are closed historical identities, not authority for a new study.',
                              'Checksums/stat checks are not independent provenance or a locked multi-file snapshot.',
                              'Only the two known study roots and two pinned B0 captures are inventoried; no exhaustive host scan.']}
    def checked(label, fn):
        try:
            return fn()
        except (OSError, ValueError, KeyError, TypeError, EOFError) as exc:
            code = str(exc) if isinstance(exc, InventoryError) else type(exc).__name__
            report['errors'].append({'scope': label, 'code': code})
            return None
    identity = checked('registrations', lambda: registrations(reader, original, confirmation, now))
    source = None
    if identity:
        report['identities'], source = identity
    for role, root in (('original', original), ('confirmation', confirmation)):
        directories = checked(role+'-catalog', lambda root=root: capture_directories(reader, root))
        if directories:
            for n, directory in enumerate(directories):
                label = f'{role}-{n:02d}'
                report['captures'][label] = checked(label, lambda directory=directory: catalog(reader, directory, source, now))
    for label, directory in (('b0-live', live), ('b0-backup', backup)):
        report['captures'][label] = checked(label, lambda directory=directory, label=label: catalog(reader, directory, source, now, CAPTURE_PINS[label]))
    report['requestedWindowCoverage'] = None
    if identity:
        report['requestedWindowCoverage'] = checked('requested-windows', lambda: {
            'original': window_inventory(report['captures'], 'original', report['identities']['originalEvaluationWindow']),
            'confirmation': window_inventory(report['captures'], 'confirmation', report['identities']['confirmationEntryWindow'])})
    checked('final-source-stability', reader.finish)
    if report['errors']:
        report['state'] = 'inventory-partial-readiness-blocked'
    report['compressedBytesRead'] = reader.bytes
    return report


def publish(path, report):
    raw = json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    require(len(raw) <= MIB, 'output-cap')
    fd, name = tempfile.mkstemp(prefix='.c1-inventory-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(gzip.compress(raw, mtime=0))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(name, path)
    finally:
        os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('original', 'confirmation', 'live', 'backup', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    roots = [getattr(args, k).absolute() for k in ('original', 'confirmation', 'live', 'backup')]
    require(output.parent.resolve() == output.parent and output.parent.is_dir()
            and not os.path.lexists(output), 'output-must-be-new')
    require(not any(output.is_relative_to(root.resolve()) for root in roots), 'output-inside-source')
    result = inventory(*roots)
    publish(output, result)
    print('C1 inventory:', result['state'])
    print('Report JSON SHA-256:', digest(result))
    print('No predictions, new outcomes, network, registration or operational changes.')
    print('Upload:', output)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('C1 inventory stopped ('+type(exc).__name__+'); no replacement report published.')
