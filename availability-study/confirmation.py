#!/usr/bin/env python3
"""Register and review a separate, fixed-window exit-availability confirmation."""
import argparse
import collections
import datetime as dt
import json
import math
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'forward-study'))
import experiment as frozen
from audit import digest, eligibility, labels, publish
from capture_review import combine
from failure_audit import analyze, equivalent, index_hash
from model import predict, stats, outcomes, paired_interval

PROTOCOL = json.loads(Path(__file__).with_name('protocol.json').read_text())
VERSION = 'availability-confirmation-1'
REVIEW_HASH = 'bb17a7df4577b89af2b36cb2a67be5e3e8d5ae2635ad4e4c65dc82de6301e7df'
DIAGNOSTIC_HASH = '6e0d348b03a4b9d9245beb01386e3cf776f77e8764ba7c0ed2ddb03b01172b16'
DAY = 86400000


def group(model):
    matches = [g for g in model['groups'] if g['cohort'] == PROTOCOL['cohort']
               and g['target'] == PROTOCOL['target']]
    if len(matches) != 1 or not matches[0]['models']:
        raise ValueError('Required frozen availability model absent')
    predict([], PROTOCOL['cohort'], 'legacy', matches[0]['models']['legacy'])
    return matches[0]


def private_file(path):
    s = Path(path).lstat()
    if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid()
            or s.st_nlink != 1 or stat.S_IMODE(s.st_mode) != 0o600):
        raise ValueError('Unsafe private study file')


def load(directory, now=None):
    now = frozen.clock() if now is None else now
    directory = frozen.private_directory(directory)
    for name in ('model.json.gz', 'registration.json.gz'):
        private_file(directory/name)
    _, model = frozen.artifact(directory/'model.json.gz')
    sealed = frozen.read_json(directory/'registration.json.gz', 2*1024*1024)
    r = {k: v for k, v in sealed.items() if k != 'registrationSha256'}
    g = group(model)
    if (sealed.get('registrationSha256') != digest(r) or r.get('format') != VERSION
            or r.get('protocol') != PROTOCOL or r.get('protocolSha256') != digest(PROTOCOL)
            or r.get('artifactSha256') != frozen.ARTIFACT_SHA256
            or r.get('modelSha256') != digest(g['models']['legacy'])
            or r.get('sourceIdentity') != model['sourceIdentity']
            or r.get('reviewedReportSha256') != REVIEW_HASH
            or r.get('diagnosticSha256') != DIAGNOSTIC_HASH
            or r.get('liveUseAllowed') is not False
            or type(r.get('registeredAt')) is not int or r['registeredAt'] > now
            or type(r.get('developmentCutoffAt')) is not int
            or not model['frozenAt'] <= r['developmentCutoffAt'] < r['registeredAt']
            or r.get('startAt') != ((r['registeredAt']+PROTOCOL['maturityMs'])//DAY+1)*DAY
            or r.get('endAt') != r['startAt']+PROTOCOL['durationDays']*DAY
            or r.get('reviewNotBeforeAt') != r['endAt']+PROTOCOL['maturityMs']):
        raise ValueError('Study registration or clock mismatch')
    mints = r.get('excludedMints')
    if (not isinstance(mints, list) or len(mints) > 10000
            or any(not isinstance(m, str) or not 1 <= len(m) <= 64 for m in mints)
            or mints != sorted(set(mints)) or digest(mints) != r.get('excludedMintsSha256')
            or not set(model['seenTrainingMints']).issubset(mints)):
        raise ValueError('Development token exclusion mismatch')
    return model, r


def status(directory, now=None):
    now = frozen.clock() if now is None else now
    _, r = load(directory, now)
    return dict(format=VERSION, state='registered-observation-only',
                registrationSha256=digest(r), protocolSha256=digest(PROTOCOL),
                sourceIdentity=r['sourceIdentity'], artifactSha256=r['artifactSha256'],
                registeredAt=r['registeredAt'], startAt=r['startAt'], endAt=r['endAt'],
                reviewNotBeforeAt=r['reviewNotBeforeAt'], excludedDevelopmentTokens=len(r['excludedMints']),
                captureBy=[r['startAt']+i*DAY for i in (2, 4, 6)]+[r['reviewNotBeforeAt']],
                reviewOpen=now >= r['reviewNotBeforeAt'], modelRefitted=False,
                liveUseAllowed=False, changesAdmissions=False, networkRequests=0)


def register(old_directory, captures, review_path, diagnostic_path, directory, now=None):
    now = frozen.clock() if now is None else now
    directory = Path(directory).absolute()
    if os.path.lexists(directory):
        return status(directory, now)  # Existing identity and dates never reset.
    if directory.parent.resolve() != directory.parent or not directory.parent.is_dir():
        raise ValueError('Unsafe study parent')
    if any(directory.is_relative_to(Path(p).resolve()) for p in [old_directory, *captures]):
        raise ValueError('Study must be separate from original evidence')
    model, old_reg = frozen.load(old_directory, now)
    reviewed = frozen.read_json(review_path, 16*1024*1024)
    diagnostic = frozen.read_json(diagnostic_path, 8*1024*1024)
    if digest(reviewed) != REVIEW_HASH or digest(diagnostic) != DIAGNOSTIC_HASH:
        raise ValueError('Use the accepted completed review and diagnostic')
    expected = [i['indexSha256'] for i in reviewed['evidenceMerge']['inputs']]
    if not 1 <= len(captures) <= 8 or len(expected) != len(set(expected)):
        raise ValueError('Capture count or identity mismatch')
    selected = [p for p in captures if index_hash(p) in expected]
    data, evidence = combine(selected)
    if sorted(i['indexSha256'] for i in evidence['inputs']) != sorted(expected):
        raise ValueError('Completed study captures missing or duplicated')
    if not equivalent(diagnostic, analyze(data, model, old_reg, evidence, reviewed)):
        raise ValueError('Accepted diagnostic does not replay')
    if type(now) is not int or not model['frozenAt'] <= data['capturedAt'] < now:
        raise ValueError('Registration must follow completed development evidence')
    mints = sorted(set(model['seenTrainingMints']) | {r['mint'] for r in data['rows']})
    if len(mints) > 10000:
        raise ValueError('Development token cap')
    start = ((now+PROTOCOL['maturityMs'])//DAY+1)*DAY
    end = start+PROTOCOL['durationDays']*DAY
    g = group(model)
    r = dict(format=VERSION, protocol=PROTOCOL, protocolSha256=digest(PROTOCOL),
             artifactSha256=frozen.ARTIFACT_SHA256, modelSha256=digest(g['models']['legacy']),
             sourceIdentity=model['sourceIdentity'], registeredAt=now, startAt=start, endAt=end,
             reviewNotBeforeAt=end+PROTOCOL['maturityMs'], developmentCutoffAt=data['capturedAt'],
             reviewedReportSha256=REVIEW_HASH, diagnosticSha256=DIAGNOSTIC_HASH,
             excludedMints=mints, excludedMintsSha256=digest(mints), liveUseAllowed=False)
    directory.mkdir(mode=0o700)
    # Exclusive writes; a partial installation is preserved and never repaired by re-registering.
    publish(directory/'model.json.gz', {**model, 'artifactSha256': digest(model)})
    publish(directory/'registration.json.gz', {**r, 'registrationSha256': digest(r)})
    for p in (directory, directory.parent):
        fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return status(directory, now)


def rate(n, total):
    if not total:
        return dict(numerator=n, denominator=total, fraction=None, wilson95=None)
    p = n/total; z = 1.959963984540054; den = 1+z*z/total
    mid = (p+z*z/(2*total))/den
    half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return dict(numerator=n, denominator=total, fraction=p,
                wilson95=[max(0, mid-half), min(1, mid+half)])


def evaluate(data, evidence, model, r):
    if data['sourceIdentity'] != r['sourceIdentity']:
        raise ValueError('Observer source changed')
    rows = []; reasons = collections.Counter(); seen = set(r['excludedMints'])
    for row in sorted(data['rows'], key=lambda x: (x['signalAt'], x['seq'])):
        if row['cohort'] != PROTOCOL['cohort'] or row['decision'] != 'admitted':
            continue
        if not r['startAt'] <= row['signalAt'] < r['endAt']:
            reasons['outside-fixed-window'] += 1; continue
        why = eligibility(row)
        if why != 'compatible':
            reasons[why] += 1; continue
        if row['mint'] in seen:
            reasons['development-or-repeat-token'] += 1; continue
        seen.add(row['mint']); rows.append(row)
    g = group(model)
    prob = predict(rows, PROTOCOL['cohort'], 'legacy', g['models']['legacy'])
    partitions = {'all': rows,
                  'selected': [row for row, p in zip(rows, prob) if p >= PROTOCOL['threshold']],
                  'excluded': [row for row, p in zip(rows, prob) if p < PROTOCOL['threshold']]}
    ys = [labels(row)[PROTOCOL['target']] for row in rows]
    known = sum(y is not None for y in ys); successes = ys.count(1); failures = ys.count(0)
    excluded_y = [labels(row)[PROTOCOL['target']] for row in partitions['excluded']]
    retained_y = [labels(row)[PROTOCOL['target']] for row in partitions['selected']]
    days = sorted({row['utcDay'] for row in rows if labels(row)[PROTOCOL['target']] is not None})
    coverage = any(a <= r['startAt'] and b >= r['endAt']+15000 for a, b in evidence['coveredIntervals'])
    blockers = []
    for bad, why in [(known < PROTOCOL['minimumKnownLabels'], 'too-few-known-labels'),
                     (len(days) < PROTOCOL['minimumUtcDays'], 'too-few-utc-days'),
                     (failures < PROTOCOL['minimumProviderFailures'], 'too-few-provider-failures'),
                     (sum(y is not None for y in excluded_y) < PROTOCOL['minimumExcludedKnownLabels'], 'too-few-excluded-known-labels'),
                     (not coverage, 'query-window-coverage-incomplete'),
                     (data['capturedAt'] < r['reviewNotBeforeAt'], 'evidence-cutoff-before-maturity')]:
        if bad: blockers.append(why)
    interval = paired_interval(rows, prob, [g['constantProbability']]*len(rows), PROTOCOL['target'])
    interval.pop('negativeFavorsContext', None)
    interval['negativeFavorsFrozenLegacy'] = True
    return dict(format=VERSION, state='fixed-window-reviewed-not-promotion' if not blockers else 'insufficient-fixed-window-evidence',
                registrationSha256=digest(r), protocolSha256=digest(PROTOCOL), artifactSha256=digest(model),
                startAt=r['startAt'], endAt=r['endAt'], capturedAt=data['capturedAt'],
                evidenceMerge=evidence, excluded=dict(reasons), watches=len(rows), blockingReasons=blockers,
                knownLabels=known, unknownLabels=len(rows)-known, labelledUtcDays=days,
                providerFailuresExcluded=rate(excluded_y.count(0), failures),
                successfulQuotesRetained=rate(retained_y.count(1), successes),
                excludedKnownFailureFraction=rate(excluded_y.count(0), sum(y is not None for y in excluded_y)),
                metrics={'frozenLegacy': stats(rows, prob, PROTOCOL['target']),
                         'originalTrainingConstant': stats(rows, [g['constantProbability']]*len(rows), PROTOCOL['target'])},
                pairedBrierDifference=interval,
                outcomes={name: {str(h): outcomes(rr, h) for h in (30000, 120000)} for name, rr in partitions.items()},
                byUtcDay={day: {name: dict(collections.Counter(row['exitAvailability']['30000'] for row in rr if row['utcDay'] == day))
                               for name, rr in partitions.items()} for day in sorted({row['utcDay'] for row in rows})},
                predictions=[dict(id=row['id'], signalAt=row['signalAt'], probability=float(p), selected=bool(p >= PROTOCOL['threshold']),
                                  label=labels(row)[PROTOCOL['target']], exitState=row['exitAvailability']['30000']) for row, p in zip(rows, prob)],
                modelRefitted=False, thresholdChanged=False, liveUseAllowed=False, networkRequests=0,
                limitations=[
                    'Availability confirmation only; no automatic promotion or claim of profit, fills or token sellability.',
                    'All outcomes are conditional on the existing nonrandom admitted sample; skipped signals have no invented labels.',
                    'Unknown, transport and late outcomes are not provider failures or zero returns.',
                    'Wilson intervals assume independent Bernoulli outcomes; market/day dependence and admission bias limit interpretation. Day-block intervals are descriptive.',
                    'Capture query coverage does not establish continuous uptime or recover pruned observations.',
                    'Development exclusions cover original training and supplied admitted study tokens, not all tokens ever observed.',
                    'Fixed-window evidence remains insufficient when guards fail; do not extend or change rules to force a pass.'])


def review(directory, captures, now=None):
    now = frozen.clock() if now is None else now
    model, r = load(directory, now)
    if now < r['reviewNotBeforeAt']:
        raise ValueError('Fixed review window not complete; preserve captures without evaluating')
    data, evidence = combine(captures)
    if data['capturedAt'] > now:
        raise ValueError('Future evidence cutoff')
    return evaluate(data, evidence, model, r)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('register', 'status', 'review'))
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--original-directory', type=Path)
    p.add_argument('--capture-dir', type=Path, action='append')
    p.add_argument('--review', type=Path)
    p.add_argument('--diagnostic', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    roots = [a.directory, * (a.capture_dir or [])]
    if a.original_directory: roots.append(a.original_directory)
    if (a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir()
            or any(a.output.resolve().is_relative_to(x.resolve()) for x in roots)):
        p.error('Report must be a new file outside all evidence directories')
    if a.action == 'register':
        if not all((a.original_directory, a.capture_dir, a.review, a.diagnostic)):
            p.error('register requires original directory, captures, review and diagnostic')
        result = register(a.original_directory, a.capture_dir, a.review, a.diagnostic, a.directory)
    elif a.action == 'review':
        if not a.capture_dir or any((a.original_directory, a.review, a.diagnostic)):
            p.error('review requires only study directory and captures')
        result = review(a.directory, a.capture_dir)
    else:
        if any((a.capture_dir, a.original_directory, a.review, a.diagnostic)):
            p.error('status requires only study directory')
        result = status(a.directory)
    publish(a.output, result)
    print('State:', result['state'])
    for key in ('startAt', 'endAt', 'reviewNotBeforeAt'):
        if key in result: print(key+':', dt.datetime.fromtimestamp(result[key]/1000, dt.timezone.utc).isoformat())
    for when in result.get('captureBy', []):
        print('Preserve capture at:', dt.datetime.fromtimestamp(when/1000, dt.timezone.utc).isoformat())
    print('No refitting, admission change, signing or submission. Upload:', a.output.absolute())


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        raise SystemExit('Availability study stopped ('+type(e).__name__+'). Preserve all evidence; no automatic retry.')
