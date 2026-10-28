# Frozen study decision and diagnostic release — October 28

Decision: **do not promote the frozen models or activate a real-money strategy**.
The engineering path remains useful, but reliability and an economic edge require
different evidence. No profitability forecast or funded-test date is justified.

## Completed review

The supplied `radar-frozen-forward-20261028T162813Z-1068720.json.gz` matches the
original artifact identity
`016f8d0cf2b9c960e6dfa8406a4566e4473df2200e0040e95ab0480c44f50355`.
Its 12 classification metric sets and eight day-block intervals were independently
recomputed from exported predictions. Five captures report 781 admitted forward
watches after the experiment-start exclusions. Four fitted target/cohort groups
reached 200 valid labels and seven UTC dates; two availability models remain
unfitted because their original training classes were insufficient.

| Cohort | Valid 30s quotes / watches | Mean quoted change 30s | Mean quoted change 120s |
|---|---:|---:|---:|
| Baseline | 236 / 236 | -2.62% | -6.41% |
| Early activity | 218 / 281 | -8.79% | -14.02% |
| Fast30 | 254 / 264 | -4.55% | -7.13% |

These means condition on timely returned quotes. Failures remain in separate
denominators; none are assigned zero returns or invented losses. Quotes are not
fills, and this is not a failure-adjusted net-profit calculation.

The context model did not demonstrate gain-prediction improvement against the
constant benchmark and performed worse for early activity and Fast30. The
apparently positive 30s legacy Fast30 selection is fragile: seven of 44 selected
watches failed, removing its best token makes its returned-quote mean negative,
and illustrative 1%-per-side additional cost stress produces about -0.20%.

The early-activity legacy availability model is a useful lead: AUC 0.911 and,
at the unchanged 0.5 threshold, 20 excluded watches all had provider-reported
quote failures. It retained all 218 successful quotes but also 43 failures. Those
successful quotes still averaged -8.79%. This does not establish profit,
unsellability, execution success or justify activating a filter.

The initial review could not reproduce probabilities from entry features or
return summaries from raw quote exports. The diagnostic release addresses that
remaining internal-replay step on the host. Provider truth is still not independently
verified by replaying the same source data.

## New offline diagnostic

`forward-study/run-diagnostic.sh REVIEW.json.gz` reads the existing immutable
artifact, private experiment registration and preserved captures. It selects the
exact decoded index hashes listed in the reviewed report, validates existing chunk
checksums and bounded merge rules, and reproduces the full review. Counts, IDs,
cutoff and shapes must match exactly; finite floating results tolerate at most
1e-12 absolute rounding. Missing captures, changed results and unsafe inputs stop
without publishing a partial report. Extra captures are ignored, not incorporated
as a newly enlarged holdout. Existing eight-capture/512 MiB decoded-input caps remain.

The report contains:

- Failure/unknown states and entry-feature distributions by cohort and primary
  exit state, with zeros and missing values separate.
- Per-day state counts and available response timestamps relative to the signal.
  Those are receipt timings, not reconstructed market measurement times.
- Forward transformed inputs and missing fractions relative to the exact frozen
  preprocessing. The three-scale count is descriptive, not a proposed admission rule.
- Original training distributions only if ordered training IDs and count match;
  otherwise an explicit unavailable comparison. Matching IDs still relies on the
  original validated captures, not an independent external attestation.
- Selected and excluded cases at the existing 0.5 threshold for both fitted models
  and the constant comparator. No threshold search or new model is performed.

No network requests, cloud downloads, database capture, scanner restart, alert
change, new watch admission, signing or transaction submission is performed.
No prospective availability study is registered by running this tool. Outputs
are private and exclusive, outside the evidence directories; source files stay intact.

## Next decisions

1. Review the host replay and diagnostics to distinguish data/feature issues from
   a weak hypothesis. Input shift or missingness associations are not causal proof.
2. If warranted, register one separate prospective availability comparison with
   fixed weights/threshold and full failure denominators. The completed holdout
   may guide design but cannot become its fresh validation set.
3. Continue bounded exit-leg/round-trip cost engineering without enabling a sender.
4. Require both operational validation and credible future economic evidence before
   a separately authorized real-money strategy pilot. A narrowly funded mechanics
   test would answer execution questions only, not prove a profitable strategy.

Preserve the original frozen model and every capture. Do not refit this artifact,
lower its guards, reset its experiment or rerun collection just to obtain a better
result. New research versions require a new untouched forward interval.
