#!/usr/bin/env python3
"""Reproduce B1 entry coverage from the two accepted B0 derived reports only.

No outcome values, quote states, threshold fitting or registration are used.
Original capture validation remains the dataset builder's responsibility.
"""
import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'launch-study'))
from report import publish

HASHES = {
    'live': '46b1559982bf91c738e40260d7a183b24ce47e6393592ef7ef6b1269b95a0e90',
    'backup': '3180b3c524a99cb2ec662663ca7467361f35517a725dfbb626e1aad630c17234',
}
MAX_BYTES = 64 * 1024 * 1024
MAX_ROWS = 20000
DAY = 86400000
COHORTS = ('baseline', 'early-activity', 'fast30-shadow')
IDENTITY = ('id', 'seq', 'mint', 'signalAt', 'utcDay', 'cohort', 'decision',
            'samplingPolicy', 'featureCaptureVersion', 'entrySchemaVerified')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def utc_day(at):
    return dt.datetime.fromtimestamp(at / 1000, dt.timezone.utc).date().isoformat()


def read_pinned(path, role):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, 'Compressed input cap exceeded')
    require(hashlib.sha256(raw).hexdigest() == HASHES[role], 'Accepted input hash mismatch')
    # Decode the checked bytes, not a second potentially changed path read.
    import io
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        decoded = stream.read(MAX_BYTES + 1)
    require(len(decoded) <= MAX_BYTES, 'Decompressed input cap exceeded')
    return json.loads(decoded)


def entry(row, source):
    out = {key: row[key] for key in IDENTITY}
    require(type(out['seq']) is int and out['seq'] > 0, 'Invalid sequence')
    require(out['id'] == source + ':' + str(out['seq']), 'Invalid row identity')
    require(isinstance(out['mint'], str) and bool(out['mint']), 'Absent token identity')
    require(type(out['signalAt']) is int and out['signalAt'] > 0, 'Invalid entry clock')
    require(out['utcDay'] == utc_day(out['signalAt']), 'Inconsistent UTC day')
    require(out['cohort'] in COHORTS, 'Unknown cohort')
    require(isinstance(out['decision'], str), 'Invalid decision')
    p = row['predictors']
    c = row['supplementalEntryContext']
    out.update(legacyLiquidity=p.get('liquidityUsd'), legacyMarketAge=p.get('marketObservedAtAgeMs'),
               contextState=c.get('state'), contextVersion=c.get('version'),
               liquidity=c.get('predictors', {}).get('liquidityUsd'),
               marketAge=c.get('predictors', {}).get('marketObservedAtAgeMs'),
               liquidityState=c.get('valueStates', {}).get('liquidityUsd'),
               marketClockState=c.get('clockStates', {}).get('marketObservedAt'))
    return out


def exclusion(row):
    if (row['entrySchemaVerified'] is not True or row['featureCaptureVersion'] != 'entry-features-1'
            or row['samplingPolicy'] != 'three-cohort-budgets-v3'):
        return 'incompatible-entry-contract'
    if row['contextState'] != 'recorded' or row['contextVersion'] != 'entry-context-1':
        return 'missing-or-invalid-context'
    if row['liquidityState'] != 'recorded' or not number(row['liquidity']) or row['liquidity'] == 0:
        return 'missing-invalid-or-zero-liquidity'
    if row['liquidity'] != row['legacyLiquidity']:
        return 'liquidity-contract-disagreement'
    if (row['marketClockState'] != 'within-ttl' or not number(row['marketAge'])
            or row['marketAge'] != row['legacyMarketAge']):
        return 'market-clock-unusable'
    return None


def audit(reports):
    require(len(reports) == 2, 'Exactly two accepted reports required')
    source = reports[0].get('sourceIdentity')
    require(isinstance(source, str) and bool(source), 'Missing source identity')
    rows, windows, duplicate_count = {}, [], 0
    for report in reports:
        require(report.get('format') == 'research-dataset-1', 'Unsupported dataset')
        require(report.get('sourceIdentity') == source, 'Source identity mismatch')
        require(isinstance(report.get('rows'), list) and len(report['rows']) <= MAX_ROWS, 'Row cap exceeded')
        capture = report['historyCapture']
        require(capture.get('complete') is True and capture.get('sourceIdentity') == source,
                'Incomplete or mismatched history metadata')
        require(capture.get('requestedStartPrecedesEarliestRetained') is False, 'Retained start gap')
        require(capture.get('windowClock') == 'observer-detected-time', 'Unknown window clock')
        start, end = capture['requestedStartAt'], capture['entryWindowEndAt']
        require(type(start) is int and type(end) is int and 0 < start < end, 'Invalid window')
        require(report['merge']['coveredIntervals'] == [[start, end]], 'Non-contiguous capture')
        windows.append([start, end])
        for raw in report['rows']:
            row = entry(raw, source)
            if row['id'] in rows:
                require(rows[row['id']] == row, 'Conflicting entry projection')
                duplicate_count += 1
            rows[row['id']] = row
            require(len(rows) <= MAX_ROWS, 'Union row cap exceeded')
    intervals = []
    for start, end in sorted(windows):
        if intervals and start <= intervals[-1][1]:
            intervals[-1][1] = max(end, intervals[-1][1])
        else:
            intervals.append([start, end])
    complete_days = []
    for start, end in intervals:
        day = ((start + DAY - 1) // DAY) * DAY
        while day + DAY <= end:
            complete_days.append(utc_day(day))
            day += DAY
    ordered = sorted(rows.values(), key=lambda row: (row['signalAt'], row['seq']))
    cohorts = {}
    for cohort in COHORTS:
        eligible = [r for r in ordered if r['cohort'] == cohort]
        admitted = [r for r in eligible if r['decision'] == 'admitted']
        cohorts[cohort] = {
            'eligibleRecords': len(eligible), 'admissions': len(admitted),
            'uniqueAdmittedTokens': len({r['mint'] for r in admitted}),
            'decisions': dict(sorted(collections.Counter(r['decision'] for r in eligible).items())),
            'admissionsBySignalUtcDay': dict(sorted(collections.Counter(r['utcDay'] for r in admitted).items())),
        }
    baseline = [r for r in ordered if r['cohort'] == 'baseline' and r['decision'] == 'admitted']
    first, seen, exclusions = [], set(), collections.Counter()
    for row in baseline:
        # First admission is chosen before checking feature usability. No replacement by a later success.
        if row['mint'] in seen:
            continue
        seen.add(row['mint'])
        reason = exclusion(row)
        if reason:
            exclusions[reason] += 1
        else:
            first.append(row)
    projection = json.dumps(ordered, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return {
        'format': 'b1-entry-coverage-1', 'state': 'design-input-audited',
        'uniqueEligibleRecords': len(rows), 'duplicateEntryProjectionsRemoved': duplicate_count,
        'entryProjectionSha256': hashlib.sha256(projection).hexdigest(),
        'requestedDetectionIntervals': intervals, 'completeRequestedUtcDays': complete_days,
        'cohorts': cohorts,
        'baselineCandidate': {
            'admissions': len(baseline), 'firstAdmissionsPerToken': len(seen),
            'repeatAdmissionsExcluded': len(baseline) - len(seen),
            'featureUsableFirstAdmissions': len(first), 'firstAdmissionExclusions': dict(sorted(exclusions.items())),
            'featureUsableBySignalUtcDay': dict(sorted(collections.Counter(r['utcDay'] for r in first).items())),
        },
        'outcomesAnalyzed': False, 'thresholdFitted': False, 'modelTrained': False,
        'studyRegistered': False, 'gatePassed': False, 'liveUseAllowed': False,
        'limitations': [
            'Pinned derived evidence only; original capture hashes and quote contracts are not revalidated here.',
            'Duplicate equality covers the entry projection only, not outcomes or entire source reports.',
            'Complete requested detection days do not prove continuous operation or full signal-time coverage.',
            'Unique tokens are a concentration count, not an effective independent sample size.',
            'Existing outcomes were already inspected; these files cannot supply an untouched holdout.',
            'Admission was nonrandom. Skipped opportunities have no inferred outcome.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reports = [read_pinned(args.live, 'live'), read_pinned(args.backup, 'backup')]
    result = audit(reports)
    result['inputCompressedSha256'] = HASHES
    publish(args.output, result)
    print(json.dumps(result['baselineCandidate'], sort_keys=True))
    print('B1 entry coverage audited; B1/G1 acceptance and trial registration remain false.')
    print('Upload: ' + str(args.output.absolute()))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('B1 design audit stopped (' + type(exc).__name__ + '); no replacement report published.')
