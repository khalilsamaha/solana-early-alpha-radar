# Exit collection diagnostics — November 4, 2026

The controlled host attempt at 19:46:40 UTC stopped in collection after 20 RPC
requests, before a signer call or send. Its public code was
`fresh-exit-evidence-unavailable`, with no preparation returned. Subsequent local
reinspection at 19:48:02 UTC confirmed that the continuation table remained absent,
both exact expired predecessors remained eligible, and all inventory and fee holds
were preserved. No execution retry or fourth generation follows these reports.

The read-only observation at 19:48:14 UTC passed. Collection took 7,868 ms, full
preserved validation another 1,395 ms, leaving 737 ms of the original deadline.
That remaining time excludes preparation persistence, private signing and transport.
It does not establish sufficient execution headroom or explain the failed attempt.
The previous failure's underlying cause remains unknown.

Public report SHA-256 identities:

- Failed attempt: `7eaf3ae374178d886c94de3c5dbbf5a855a0f07324ca7d2dd32497e387610220`
- Reinspection: `079f2bbc6b233961318c994001e869fe07f6acb1d0f69fbeabad7871e40ac0a4`
- Observation: `4c7f1ba410217195cc7d4f3c140d2b30e46a1866c40c98e4af83cc74919d3be2`

## Change

The existing collector records bounded local monotonic elapsed times for admission,
pool read and pricing, packet build, account recheck, simulation, final binding,
preserved validation when used, and successful cleanup. Each phase includes both
RPC and local work within it; it is not pure network latency. The `complete` row
measures successful cleanup, not additional validation. Failure retains the last
stage and its elapsed duration, including cleanup. At most eight rows are exported.

`collectionTiming.elapsedMs` starts before local admission checks, earlier than the
RPC freshness window. Compare the existing `observationTiming` separately for
actual collection/validation deadline headroom. Timings use an independent
performance counter and never supply deadlines or an authorization decision.
Unavailable, regressing or invalid telemetry yields null, not zero or a fabricated
measurement. The safety clocks, request order, caps, freshness and STOP checks are
unchanged; telemetry adds small measurement/serialization overhead only.

Fresh exit integration preserves a bounded `collectionDiagnostic` even when the
collector returns failure. The controlled continuation report exports only its
allowlisted state, stage, error code, request count and timing rows. Raw provider
errors, request parameters, evidence, transaction bytes and private paths are not
copied. Unknown fields and values are withheld. This corrects error visibility;
it does not repair an unproven cause of the previous host failure.

## Host acceptance and next decision

Use the pinned revision provided in chat. First inspect the exact original and
replacement identities with `controlled_continuation_cli.py --action inspect`.
Only if still eligible, run the existing `preserved_exit_observation_cli.py --action
observe --allow-devnet-observation` once. It performs at most 20 fixed devnet RPC
requests, including unsigned simulation, without writing a preparation or signing,
sending, consuming capacity or releasing holds. Upload both public reports.

There is no scanner rebuild or restart. Research, quote observer, Telegram,
Backblaze and availability-study captures are unchanged. Review stage costs before
choosing an optimization. Do not lengthen deadlines, remove checks or repeat the
operational execution merely because one read-only observation passed.

## Verification

Local verification passed: seven new diagnostic tests, five existing collector
regressions, twelve existing fresh-exit tests, and two CI partition checks (26
unit/integration checks total). Coverage includes preserved journal bytes, absent
telemetry without authorization changes, simulated collection failure propagated
through both wrappers without signing, deadline enforcement, actual isolated
signer integration over synthetic replies, lost-response recovery and no resend.
Source hygiene/package manifests and compilation also passed. No live wallet or
RPC was used for local testing. This increment is published as a tested development
commit for host observation; it has not yet undergone the next batched PR CI run.
