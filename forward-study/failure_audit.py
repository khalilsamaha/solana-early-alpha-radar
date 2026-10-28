#!/usr/bin/env python3
"""Replay a frozen review and describe failures/features; no refit or activation."""
import argparse
import collections
import gzip
import hashlib
import math
from pathlib import Path

import numpy as np
from audit import PROTOCOL, digest, eligibility, features, labels, publish
from capture_review import combine
from experiment import load, read_json, clock
from model import evaluate, matrix, LEGACY

VERSION = 'frozen-failure-feature-audit-1'


def index_hash(directory):
    directory = Path(directory)
    path = directory/'capture-index.json.gz'
    if directory.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('Unsafe capture index')
    with gzip.open(path, 'rb') as f:
        raw = f.read(65537)
    if len(raw) > 65536:
        raise ValueError('Capture index cap exceeded')
    return hashlib.sha256(raw).hexdigest()


def equivalent(expected, actual):
    """Only finite floats tolerate rounding; identities, counts and shape are exact."""
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return expected.keys() == actual.keys() and all(equivalent(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(equivalent(a, b) for a, b in zip(expected, actual))
    if type(expected) is float:
        return math.isfinite(expected) and math.isfinite(actual) and math.isclose(expected, actual, rel_tol=0, abs_tol=1e-12)
    return expected == actual


def summary(values):
    known = [v for v in values if v is not None]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in known):
        raise ValueError('Invalid diagnostic feature')
    return dict(rows=len(values), known=len(known), missing=len(values)-len(known),
                zero=sum(v == 0 for v in known),
                median=float(np.median(known)) if known else None,
                p10=float(np.quantile(known, .1)) if known else None,
                p90=float(np.quantile(known, .9)) if known else None)


def feature_summary(rows):
    data = [features(r) for r in rows]
    return {k: summary([f[k] for f in data]) for k in PROTOCOL['features']}


def inputs_against_frozen_transform(rows, cohort, variant, weights):
    """Descriptive input shift, not feature importance or a causal explanation."""
    names = PROTOCOL['features'] if variant == 'context' else LEGACY[cohort]
    x = matrix(rows, cohort, variant)
    missing = np.isnan(x)
    filled = np.where(missing, weights['medians'], x)
    result = {}
    for i, name in enumerate(names):
        z = (filled[:, i]-weights['center'][i])/weights['scale'][i]
        result[name] = dict(rows=len(rows), missing=int(missing[:, i].sum()),
            frozenTrainingMissingFraction=weights['center'][len(names)+i],
            forwardMissingFraction=float(missing[:, i].mean()) if len(rows) else None,
            meanStandardizedInput=float(z.mean()) if len(rows) else None,
            outsideThreeTrainingScales=int((np.abs(z) > 3).sum()),
            basis='frozen log/imputation/scale; diagnostic only; not causal or a filter')
    return result


def training_reconstruction(data, artifact, group):
    rows = [r for r in data['rows'] if r['cohort'] == group['cohort'] and r['decision'] == 'admitted'
            and eligibility(r) == 'compatible' and r['signalAt'] < artifact['trainingCutoffAt']
            and labels(r)[group['target']] is not None
            and type(r['targets']['30000']['availableAt']) is int
            and r['targets']['30000']['availableAt'] <= artifact['trainingCutoffAt']]
    matched = len(rows) == group['trainingRows'] and digest([r['id'] for r in rows]) == group['trainIdsSha256']
    return dict(state='matched-frozen-training-ids' if matched else 'training-capture-not-exact',
                candidateRows=len(rows), frozenTrainingRows=group['trainingRows'],
                features=feature_summary(rows) if matched else None)


def analyze(data, artifact, registration, evidence, reviewed):
    if data['capturedAt'] != reviewed.get('capturedAt'):
        raise ValueError('Use exactly the capture set from the reviewed cutoff')
    before = collections.Counter(r['cohort'] for r in data['rows'] if r['signalAt'] < registration['testNotBeforeAt'])
    forward = {**data, 'rows': [r for r in data['rows'] if r['signalAt'] >= registration['testNotBeforeAt']]}
    replay = evaluate(forward, artifact)
    replay.update(experiment=registration, evidenceMerge=evidence,
                  beforeExperimentStartExcluded=dict(before), networkRequests=0)
    if not equivalent(reviewed, replay):
        raise ValueError('Frozen review does not replay from these captures and artifact')
    by_id = {r['id']: r for r in forward['rows']}
    if len(by_id) != len(forward['rows']):
        raise ValueError('Duplicate dataset identity')
    groups = []
    for g, original in zip(replay['groups'], artifact['groups']):
        out = dict(cohort=g['cohort'], target=g['target'], frozenState=g['state'],
                   fitted=bool(original['models']))
        if not original['models']:
            groups.append(out)
            continue
        predictions = g['predictions']
        rows = [by_id[p['id']] for p in predictions]
        states = sorted({r['exitAvailability']['30000'] for r in rows})
        out.update(watches=len(rows),
            trainingReconstruction=training_reconstruction(data, artifact, original),
            byPrimaryExitState={state: dict(
                watches=sum(r['exitAvailability']['30000'] == state for r in rows),
                responseAfterSignalMs=summary([
                    r['targets']['30000']['availableAt']-r['signalAt']
                    if type(r['targets']['30000']['availableAt']) is int else None
                    for r in rows if r['exitAvailability']['30000'] == state]),
                features=feature_summary([r for r in rows if r['exitAvailability']['30000'] == state])) for state in states},
            byUtcDay={day: dict(watches=len(rr),
                states=dict(collections.Counter(r['exitAvailability']['30000'] for r in rr)))
                for day in sorted({r['utcDay'] for r in rows})
                for rr in [[r for r in rows if r['utcDay'] == day]]},
            frozenInputShift={v: inputs_against_frozen_transform(rows, g['cohort'], v, original['models'][v])
                              for v in ('legacy', 'context')},
            fixedThresholdPartitions={})
        for variant in ('legacy', 'context', 'constant'):
            partitions = {}
            for name, selected in (('selected', True), ('excluded', False)):
                rr = [by_id[p['id']] for p in predictions if (p['probabilities'][variant] >= .5) == selected]
                partitions[name] = dict(watches=len(rr),
                    primaryStates=dict(collections.Counter(r['exitAvailability']['30000'] for r in rr)),
                    positiveReturnedQuotes=sum(labels(r)['positiveReturnedQuote'] == 1 for r in rr),
                    unknownReturnLabels=sum(labels(r)['positiveReturnedQuote'] is None for r in rr))
            out['fixedThresholdPartitions'][variant] = partitions
        groups.append(out)
    return dict(format=VERSION, state='review-replayed-diagnostics-only',
        reviewedReportSha256=digest(reviewed), artifactSha256=replay['artifactSha256'],
        capturedAt=data['capturedAt'], sourceIdentity=data['sourceIdentity'],
        evidenceMerge=evidence, groups=groups, decision='not-promoted',
        modelRefitted=False, thresholdChanged=False, liveUseAllowed=False, networkRequests=0,
        limitations=[
            'Retrospective diagnostics of the completed experiment; not a new holdout or prospective validation.',
            'Only original admitted forward watches, with frozen exclusions and threshold 0.5; skipped signals have no invented outcomes.',
            'Provider quote failure is not proof of token unsellability; unknown and transport outcomes remain separate.',
            'Input shift and conditional feature summaries do not establish causation or justify a new threshold.',
            'Training features are reported only when ordered training IDs and count match the frozen artifact.',
            'Same-source replay checks internal consistency, not independent provider truth or actual fills.',
            'No new availability protocol is registered or activated by this diagnostic.'])


def run(directory, capture_dirs, review_path, output):
    output = Path(output)
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError('Output unavailable')
    if output.resolve().is_relative_to(Path(directory).resolve()) or any(
            output.resolve().is_relative_to(Path(p).resolve()) for p in capture_dirs):
        raise ValueError('Output must be outside evidence directories')
    artifact, registration = load(directory)
    reviewed = read_json(review_path, 16 * 1024 * 1024)
    # Match the exact indexes named in the reviewed report. Extra later captures
    # must not silently enlarge the already examined experiment.
    expected = [i['indexSha256'] for i in reviewed['evidenceMerge']['inputs']]
    if len(expected) != len(set(expected)) or not 1 <= len(expected) <= 8:
        raise ValueError('Invalid reviewed capture set')
    if not 1 <= len(capture_dirs) <= 8:
        raise ValueError('Capture cap exceeded')
    selected = []
    for path in capture_dirs:
        if index_hash(path) in expected:
            selected.append(path)
    data, evidence = combine(selected)
    if sorted(i['indexSha256'] for i in evidence['inputs']) != sorted(expected):
        raise ValueError('Reviewed capture set missing or duplicated')
    if data['capturedAt'] > clock():
        raise ValueError('Future capture cutoff')
    result = analyze(data, artifact, registration, evidence, reviewed)
    publish(output, result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--capture-dir', type=Path, action='append', required=True)
    p.add_argument('--review', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    r = run(a.directory, a.capture_dir, a.review, a.output)
    print('State:', r['state'])
    print('No refit, threshold change, network request or runtime change.')
    print('Upload:', a.output.absolute())


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        raise SystemExit('Frozen diagnostic stopped ('+type(e).__name__+'). Preserve all captures; no partial report published.')
