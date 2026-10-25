#!/usr/bin/env python3
"""Install one private frozen artifact; evaluate later captures without refitting."""
import argparse
import collections
import gzip
import json
import os
from pathlib import Path
import stat
import time
from audit import PROTOCOL, digest, publish

VERSION = 'frozen-forward-experiment-1'
ARTIFACT_SHA256 = '016f8d0cf2b9c960e6dfa8406a4566e4473df2200e0040e95ab0480c44f50355'
MODEL_NAME = 'model.json.gz'
REGISTRATION_NAME = 'experiment.json.gz'


def clock():
    return time.time_ns() // 1000000


def read_json(path, cap):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > cap:
        raise ValueError('Unsafe or oversized input')
    with gzip.open(path, 'rb') as f:
        raw = f.read(cap + 1)
    if len(raw) > cap:
        raise ValueError('Decoded input cap exceeded')
    return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def artifact(path):
    sealed = read_json(path, 8 * 1024 * 1024)
    data = {k: v for k, v in sealed.items() if k != 'artifactSha256'}
    if (sealed.get('artifactSha256') != ARTIFACT_SHA256 or digest(data) != ARTIFACT_SHA256
            or data.get('format') != 'forward-model-1' or data.get('protocol') != PROTOCOL
            or data.get('protocolSha256') != digest(PROTOCOL) or data.get('liveUseAllowed') is not False
            or data.get('modelFrozen') is not True):
        raise ValueError('Frozen artifact mismatch; do not refit or replace it')
    return sealed, data


def private_directory(path):
    path = Path(path).absolute()
    s = path.stat()
    if (path.resolve() != path or not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid()
            or stat.S_IMODE(s.st_mode) != 0o700):
        raise ValueError('Experiment directory must be owned and private 0700')
    return path


def load(directory, now=None):
    directory = private_directory(directory)
    for name in (MODEL_NAME, REGISTRATION_NAME):
        p = directory / name
        s = p.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1 or stat.S_IMODE(s.st_mode) != 0o600:
            raise ValueError('Unsafe experiment file')
    _, model = artifact(directory / MODEL_NAME)
    sealed = read_json(directory / REGISTRATION_NAME, 16384)
    reg = {k: v for k, v in sealed.items() if k != 'registrationSha256'}
    if (sealed.get('registrationSha256') != digest(reg) or reg.get('format') != VERSION
            or reg.get('liveUseAllowed') is not False or reg.get('artifactSha256') != ARTIFACT_SHA256 or reg.get('sourceIdentity') != model['sourceIdentity']
            or type(reg.get('installedAt')) is not int or reg['installedAt'] < model['frozenAt']
            or reg.get('testNotBeforeAt') != max(model['testNotBeforeAt'], reg['installedAt'] + PROTOCOL['holdout']['embargoMs'])
            or reg['installedAt'] > (clock() if now is None else now)):
        raise ValueError('Experiment registration mismatch or clock regression')
    return model, reg


def inspect(directory, now=None):
    model, reg = load(directory, now)
    return {'format': VERSION, 'state': 'installed-research-only', 'registration': reg,
            'frozenAt': model['frozenAt'], 'trainingCutoffAt': model['trainingCutoffAt'],
            'models': [{k: g.get(k) for k in ('cohort', 'target', 'trainingRows', 'classes', 'utcDays', 'blockingReasons')}
                       | {'fitted': g['models'] is not None} for g in model['groups']],
            'modelRefitted': False, 'liveUseAllowed': False, 'networkRequests': 0,
            'limitations': ['Installation records a later conservative evaluation start; reinstalling does not reset it.',
                            'Local timestamps and checksums do not independently prove an untouched holdout.',
                            'No predictions are connected to alerts, admissions, signing or trading.']}


def install(source, directory, now=None):
    sealed, model = artifact(source)
    now = clock() if now is None else now
    if type(now) is not int or now < model['frozenAt']:
        raise ValueError('Clock precedes model freeze')
    directory = Path(directory).absolute()
    if os.path.lexists(directory):
        return inspect(directory, now)
    if directory.parent.resolve() != directory.parent or not directory.parent.is_dir():
        raise ValueError('Unsafe experiment parent')
    # Exclusive creation. Incomplete installations are never silently replaced.
    directory.mkdir(mode=0o700)
    parent_fd = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    publish(directory / MODEL_NAME, sealed)
    reg = {'format': VERSION, 'artifactSha256': ARTIFACT_SHA256, 'sourceIdentity': model['sourceIdentity'],
           'installedAt': now, 'testNotBeforeAt': max(model['testNotBeforeAt'], now + PROTOCOL['holdout']['embargoMs']),
           'liveUseAllowed': False}
    publish(directory / REGISTRATION_NAME, {**reg, 'registrationSha256': digest(reg)})
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return inspect(directory, now)


def review(directory, captures, now=None):
    now = clock() if now is None else now
    model, reg = load(directory, now)
    from capture_review import combine
    from model import evaluate
    data, evidence = combine(captures)
    if data['capturedAt'] > now:
        raise ValueError('Evidence cutoff is in the future')
    # Use a later local installation boundary without changing the frozen artifact.
    excluded = collections.Counter(r['cohort'] for r in data['rows'] if r['signalAt'] < reg['testNotBeforeAt'])
    data['rows'] = [r for r in data['rows'] if r['signalAt'] >= reg['testNotBeforeAt']]
    result = evaluate(data, model)
    result.update(experiment=reg, evidenceMerge=evidence,
                  beforeExperimentStartExcluded=dict(excluded), networkRequests=0)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('install', 'inspect', 'evaluate'))
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--artifact', type=Path)
    p.add_argument('--capture-dir', type=Path, action='append')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        p.error('Output must be a new file in an existing directory')
    if a.action == 'install':
        if not a.artifact or a.capture_dir:
            p.error('install requires only --artifact')
        result = install(a.artifact, a.directory)
    elif a.action == 'evaluate':
        if not a.capture_dir or a.artifact:
            p.error('evaluate requires --capture-dir and the already installed artifact')
        result = review(a.directory, a.capture_dir)
    else:
        if a.artifact or a.capture_dir:
            p.error('inspect uses installed files only')
        result = inspect(a.directory)
    publish(a.output, result)
    print('State:', result.get('state', 'forward-review-complete'))
    if 'registration' in result:
        from datetime import datetime, timezone
        print('Evaluate signals from:', datetime.fromtimestamp(result['registration']['testNotBeforeAt'] / 1000, timezone.utc).isoformat())
    for g in result.get('groups', []):
        print(g['cohort'], g['target'], g['state'], 'watches:', g['forwardWatches'])
    print('No refitting or live activation. Upload:', a.output.absolute())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Frozen study stopped: ' + type(exc).__name__ + ': ' + str(exc))
