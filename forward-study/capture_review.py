"""Combine validated captures for forward evaluation without raising exporter caps.

Retain full admitted watches; retain only identity hashes and decision counts for
other signals. The original capture directories remain the detailed evidence.
"""
import collections
from pathlib import Path
from audit import build, digest, eligibility, load_capture
from build import identity, merge, read

MAX_COMBINED_BYTES = 512 * 1024 * 1024  # Sequential decoded input, not retained raw payloads.
MAX_CAPTURES = 8
MAX_SIGNALS = 100000
MAX_WATCHES = 5000


def combine(directories):
    if not 1 <= len(directories) <= MAX_CAPTURES:
        raise ValueError('Provide 1..8 capture directories')
    ordered = []
    for directory in directories:
        directory = Path(directory)
        path = directory / 'capture-index.json.gz'
        if directory.is_symlink() or path.is_symlink() or path.stat().st_size > 65536:
            raise ValueError('Unsafe or oversized capture index')
        index, _ = read(path)
        ordered.append((index['capturedAt'], str(directory), directory))
    known, eligible, watches = {}, {}, {}
    source = None; total = 0; duplicate_signals = 0; duplicate_watches = 0
    inputs, intervals = [], []
    cutoff = 0
    for _, _, directory in sorted(ordered):
        reports, provenance, index = load_capture(directory)
        total += sum(p['bytes'] for p in provenance)
        if total > MAX_COMBINED_BYTES:
            raise ValueError('Combined capture byte cap exceeded')
        if source is not None and source != index['sourceIdentity']:
            raise ValueError('Different source identities')
        source = index['sourceIdentity']; cutoff = max(cutoff, index['capturedAt'])
        # Every complete source is validated before any projection or filtering.
        data = build(reports)
        raw, _ = merge(reports)
        signals = {s['seq']: s for s in raw['signals']}
        probes = {p['signal']['seq']: p for p in raw['probes']}
        for seq, p in probes.items():
            signals.setdefault(seq, {**p['signal'], 'decision': 'admitted'})
        for seq, s in signals.items():
            fingerprint = digest({'identity': identity(s), 'decision': s.get('decision'),
                                  'detectedAt': s.get('detectedAt')})
            if seq in known:
                if known[seq] != fingerprint:
                    raise ValueError('Conflicting immutable signal across captures')
                duplicate_signals += 1
            known[seq] = fingerprint
        if len(known) > MAX_SIGNALS:
            raise ValueError('Unique signal audit cap exceeded')
        for row in data['rows']:
            seq = row['seq']
            classification = (row['cohort'], row['decision'], eligibility(row))
            if seq in eligible and eligible[seq] != classification:
                raise ValueError('Conflicting eligibility across captures')
            eligible[seq] = classification
            if row['decision'] != 'admitted':
                continue
            single = {**raw, 'signals': [signals[seq]],
                      'probes': [probes[seq]] if seq in probes else []}
            if seq in watches:
                prior = watches[seq][1]
                if prior['probes'] and not single['probes']:
                    raise ValueError('Probe disappeared from later capture')
                # Existing validator enforces immutable contracts and append-only
                # observations, including terminal receipt immutability.
                merge([prior, single])
                duplicate_watches += 1
            watches[seq] = (row, single)
            if len(watches) > MAX_WATCHES:
                raise ValueError('Admitted watch cap exceeded')
        inputs.append({'indexSha256': index['indexSha256'], 'capturedAt': index['capturedAt'],
                       'startAt': index['requestedStartAt'], 'endAt': index['entryWindowEndAt'],
                       'chunks': provenance})
        intervals.append([index['requestedStartAt'], index['entryWindowEndAt']])
        del reports, data, raw, signals, probes  # Release each full capture before reading the next.
    coverage = []
    for start, end in sorted(intervals):
        if coverage and start <= coverage[-1][1]:
            coverage[-1][1] = max(end, coverage[-1][1])
        else:
            coverage.append([start, end])
    decisions = collections.Counter(eligible.values())
    evidence = {'format': 'forward-capture-merge-1', 'captureCount': len(inputs),
                'sourceIdentity': source, 'inputDecodedBytes': total,
                'uniqueRawSignals': len(known), 'uniqueEligibleSignals': len(eligible),
                'uniqueAdmittedWatches': len(watches), 'duplicateSignalsRemoved': duplicate_signals,
                'duplicateWatchesRemoved': duplicate_watches,
                'decisionCounts': [dict(cohort=c, decision=d, eligibility=e, count=n)
                                   for (c, d, e), n in sorted(decisions.items())],
                'coveredIntervals': coverage, 'gapBetweenCaptures': len(coverage) > 1,
                'inputs': inputs,
                'limitations': ['Query coverage does not prove continuous observer uptime.',
                                'Only admitted rows enter model evaluation; all eligible decision counts are retained.',
                                'Original capture directories retain skipped-signal details; never delete them after this projection.',
                                'Existing per-capture exporter and dataset limits are unchanged.']}
    return {'sourceIdentity': source, 'capturedAt': cutoff,
            'rows': sorted((x[0] for x in watches.values()), key=lambda r: (r['signalAt'], r['seq']))}, evidence
