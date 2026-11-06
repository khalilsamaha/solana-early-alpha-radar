# Continuation replay consolidation — November 6, 2026

## Accepted engineering evidence

This batch follows main `c18a6eb6d99a21d3b68515774cfd3deee8275a4e` (PR #76).
It consolidates the explicit controlled continuation command, bounded failure
telemetry, exact canonical digest/text reuse, the full-size offline fixture and
consistent read-only exit snapshots. Source and authorization checks, independent
signing, durable one-send boundaries, original deadlines, holds and predecessor
history remain enforced. No fourth generation or automatic retry is introduced.

Kali report captured at 2026-11-06 04:01:51 UTC:
`radar-exit-snapshot-check-20261106T035738Z-2773785.json.gz`.
SHA-256: `9aea65abdcd050ef2cb9cc99178481e70575878445e932545b7ff2c66c5e39c8`.

All 16 integration/fault cases and 14 independent signer cases passed with the
actual 1 MiB synthetic program fixture. Continuation took 11,654.693 ms and
completed with 643 ms of positive original-deadline headroom. Twenty collection
and five sender requests included exactly one simulated send with a lost reply.
Stopped/keyless recovery observed finalized synthetic evidence without another
send; repeated recovery left the durable evidence byte-identical. Both
predecessors, source and entry accounting were preserved. There were zero real
network requests and no production-wallet/ledger access; temporary fixtures were
removed.

The prior November 6 exact-replay report failed completion by 457 ms. It is not
removed or relabelled. The new pass establishes functional host acceptance only:
643 ms is not adequate evidence of robust timing under real network and host load.

## Consolidation boundary

Local targeted tests and the full connected rehearsal passed before publication.
All twelve CI partitions must pass on the exact consolidation PR head before
merge. This consolidation does not deploy scanner code, restart services,
activate a model or execute the held devnet transaction.

No additional local replay of already-passing suites is required for these
host-acceptance documentation changes; CI validates the accumulated source batch.
The scanner, notifications, quote sampling, study registration and scheduled
availability captures keep their existing policies.

## Next engineering focus

Profile remaining collection/persistence and signing work independently. Remove
redundant exact evidence processing only where fresh source/clock/ownership
validation remains guaranteed. Demonstrate positive timing headroom in the full
real-clock offline fixture, including synthetic adapter overhead, then check Kali
under representative load. Do not relax deadlines or count profiler timing as
acceptance. Actual held-position inspection and any separately explicit devnet
continuation follow adequate operational evidence; finalized receipt accounting
and scoped closure remain outstanding.
