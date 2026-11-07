# Offline continuation timing review

This increment adds `position-book/timing_review.py`. It reads two existing gzip
rehearsal reports and writes an exclusive, private gzip summary. It performs no
RPC, key access, signing, submission, database access, or runtime deployment.
The scanner, study, deadlines, and execution rules are unchanged.

The latest supplied Kali snapshot report passed its offline checks with only
643 ms of recorded headroom. The newer canonical comparison optimization still
needs its own Kali report. A local execution time is not a substitute for that
host check.

## Use

Generate the newer offline `continuation_exit_cli.py --large-fixture` report on
Kali first. Then compare it with the earlier snapshot report:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/timing_review.py" \
  --before "$HOME/apps/solana-early-alpha-radar/radar-exit-snapshot-check-20261106T035738Z-2773785.json.gz" \
  --after /absolute/path/to/the/new-comparison-report.json.gz \
  --output "$HOME/apps/solana-early-alpha-radar/radar-timing-review-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Only add `--same-host-and-load` when both runs were on the same host under
comparable load. Without that attestation, the tool retains both summaries but
suppresses numerical comparison. The tool cannot verify the attestation.
Even with it, a pair is descriptive evidence, not a controlled benchmark.

## Interpretation

- A complete offline pass requires the known integration and signer check names,
  successful outcomes, cleanup, actual matching fixture size, complete phase
  clocks and positive recorded headroom. These are source report claims, not
  independently replayed or authenticated proofs.
- Failed or incomplete runs remain visible as `review-required`; they do not
  produce a speedup delta. Malformed, oversized, duplicate-key, nonfinite or
  non-offline reports are rejected without publishing a new report.
- Comparison requires matching fixture sizes and diagnostic clock versions.
- Deltas are **after minus before**. Lower duration and higher headroom are
  favorable observations; neither proves real-network readiness.
- Collection, signing and submission are separate timed phases. Synthetic sender
  setup is nested in submission. Parent phases overlap children. The reviewer
  never adds setup twice or subtracts it to manufacture headroom.
- No new arbitrary timing threshold or mandatory execution gate is introduced.
  `executionApproved` is always false. Source inputs are never modified.

## Validation

Nine focused tests cover failure retention, fixture/clock mismatch, environment
attestation, nested timings, sanitized output, strict types, bounded gzip/JSON
reads, exclusive publication, and a network-disabled CLI. Existing saved Kali
pass/failure reports and the newer local report are also replayed as inputs.
No new full connected rehearsal is needed for this reporting-only increment.

This remains a locally validated increment for the next batched consolidation;
no standalone PR or CI run is required by this change.

## November 6 host result and next diagnostic

The subsequently supplied comparison report passed all 16 integration/fault and
14 signer checks with a 1 MiB fixture. Total continuation time was 11652.658 ms,
headroom 459 ms, collection 3447.872 ms, signing 3814.053 ms and submission
3595.384 ms. The prior host run was 11654.693 ms with 643 ms headroom. These two
runs show no meaningful end-to-end gain; comparable host load was not measured.
A useful primitive optimization does not establish a system-level improvement.

`position-book/continuation_profile_cli.py --phase signing --output REPORT.json.gz`
now profiles exactly the selected function during the continuation stage of the
disposable 1 MiB connected rehearsal. Other choices are `collection` and
`submission`. Fixture calls are outside the profiling scope. The connected
path retains real deadlines and cleanup; the standalone fault suite is omitted
from this diagnostic. This never counts as an acceptance run. Profiling may
cause expiry; partial cost evidence is deliberately preserved.

The report contains fixed aggregate categories, with exclusive/self and
inclusive function costs and call counts. Inclusive values overlap. SQLite
self-time may include blocking; it is not necessarily CPU time. Child process
internals are not measured. Raw profiles, input arguments and arbitrary
function names/paths are not published. No production wrapper is modified.

Four focused profiler tests cover sanitization, result/exception preservation,
fixture scope exclusion, and unsupported phase rejection. A full disposable
signing-profile run validates the integration before publication.
