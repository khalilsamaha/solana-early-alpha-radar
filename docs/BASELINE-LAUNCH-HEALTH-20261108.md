# Launch registry visibility in the operational baseline

The scanner health endpoint already exposes launch-registry capacity and
cumulative counters. The operational review omitted those fields, so a ready
scanner could appear healthy while its bounded registry was unable to retain
new launches.

The review now projects only the supported registry version, retained row count,
row capacity, retention days, and six counters since restart. It emits:

- An error when retained rows reach or exceed the configured capacity.
- Warnings for recorded capacity drops or storage errors. These cumulative
  counters do not establish a current rate or an incident timestamp.
- Warnings when registry evidence or counters are unavailable or invalid.
  Unknown values are never interpreted as zero.

Scanner readiness remains a separate observation. This change only affects the
diagnostic report; it does not change storage, pruning, capacity, runtime health
endpoints, collection policy, or services. Arbitrary health payload fields are
excluded from the report.

## Validation

All 14 operational-review JavaScript tests and 23 Python tests pass locally.
Coverage includes a full registry with a ready scanner, historical drops below
capacity, missing counters, invalid counts and versions, and allowlisted output.
These local results do not replace Kali acceptance or close the baseline gate.

For the pinned development revision, run both operational-review test suites on
Kali, then run `operational-review/run.sh` from the live project directory. Use
the existing `operations-tools/run-launch-audit.sh --hours 720` to inspect the
30-day retained window. That audit retains its existing read-only connection,
time, row, byte, and WAL-growth limits and refuses partial success.

A capacity finding requires a preservation and retention decision based on host
evidence. This increment does not authorize deletion, a larger cap, shortened
retention, deployment, or a restart. Keep raw host evidence outside the repository.
Development publication precedes host acceptance; PR, CI, and consolidation wait
for completion of the agreed phase.
