# R1 local measurement evidence — accepted on Kali

Date: 2026-11-11. This is collector instrumentation and replay preparation
within the existing R1 phase. It does not start another gate, reset the five-
working-day effort cap, authorize a provider connection or establish a study.

## Measurement Kali acceptance

The report for `ccf8085860deb3fc0a508f540e5ff41cf447c921` passed review:
259 tests, zero failures/errors/skips, all 35 source hashes matched. Python
3.14.6 / SQLite 3.53.4 / websockets 17.4; 9.625006 seconds overall. Capture and
measurement replay succeeded with the expected three sends and one selected
creation. Report SHA-256:
`81a3135241cf1f3f39d37155193f04659e098d4af581cfd2cfb78e5c7855be2c`.
This is offline-scope acceptance; no raw fixture was retained in that run.
Current complete-session packaging work is in `R1-SESSION-BUNDLE-20261111.md`.
The following records the completed measurement increment.

## Preceding supervisor acceptance

The uploaded `radar-r1-supervisor-offline-20261111T143934Z-1091449.json` passed
review against commit `1e8bed1aa3158db93ee0000c3f0af78733208236`, tree
`c37e1470cbd652d8abda459797d68075957a0062`:

- Report SHA-256: `877bc3d819d59e567cb5682bd5d075a56c4276503080b33a486774fbfe26765f`.
- All 33 source hashes match; 241 tests, zero failures/errors/skips.
- Python 3.14.6 / SQLite 3.53.4 / websockets 17.4; 7.623608 seconds overall.
- One synthetic worker completed and was reaped in 0.314780 seconds.
- Source preservation and local restore/replay passed; manifest hashes agree.
- No credentials, network, provider connection or paid collection. No automatic
  restart/repair. The temporary fixture was removed as documented.

This accepts the supervisor's offline scope. Review used the uploaded report,
not direct access to Kali or its removed temporary database. The reported local
restore is not a new independently transferred artifact or B2 round trip.

## Why this implementation is needed

The capture database records deterministic selection decisions, but a planned
watch is not proof that the controller sent a subscription. The earlier session
result contained aggregate command counts without durable per-command timing.
A pilot needs to distinguish selected-but-unsent tokens, incomplete sends and
completed local sends before calculating any collection-delay metric.

`measurement.py` adds a private append-only JSONL sidecar. `run_session` accepts
an optional journal for compatibility with previously accepted component tests;
the supervised rehearsal now always supplies one. This does not make an
unaudited live entry point acceptable. The existing supervisor still has only
its fixed synthetic worker, and no live CLI or credential reader is added.

## Recorded facts and definitions

| Evidence | Exact meaning |
| --- | --- |
| Session start | Binds capture start and limits; persisted before opening the supplied wire |
| Selected creation | Binds the validated database row and hash to its mint and local receive-return clock readings |
| Send intent | Validated allowlisted command persisted before the send call; an intent alone does not prove that the call occurred |
| Local send completion | Written after the awaited wire send returns; does not prove provider processing or acknowledgement |
| Abandoned intent | The post-flush capture check found a terminal limit, so the command was not sent |
| Session finish | Binds final capture hash, rows/messages/gaps, stop reason and controller outcome |

Creation timing starts immediately after the application receives the frame
and before capture validation/storage. It ends at the observation of the local
subscription send returning, before the completion-record flush. Differences
use the same process's monotonic nanosecond clock. They include intervening
local validation and durable logging work. They do not measure block creation,
provider emission, subscription installation or first complete trade coverage.
Only selected creations with a completed local trade-subscription send contribute
to delay count/min/max/sum; missing sends stay in a separate denominator.
Forward wall-clock changes cannot inflate this monotonic delay. Clock regressions
or invalid clock values fail the journal instead of inventing a timing result.

Observed creation-record count includes duplicates. Unique creation mints and
selection/exclusion counts are independently recomputed from the verified DB.
Selected creations stopped by a terminal message cap remain selected-but-unsent.
A send exception/cancellation leaves a durable unresolved intent; it is unknown
whether the provider received the command. It is not silently treated as a
zero-cost or successfully installed subscription.

Provider-acknowledged subscriptions, the external creation denominator, initial-
trade coverage, billed events and actual data fees are **null/unknown**. Finality,
ledger-order verification and profitability remain false/unverified. No fraction
of local observations is relabelled as complete market coverage. These definitions
are an implementation contract; numeric pilot quality thresholds and the owner-
approved measurement/exposure registration still need to be finalized before use.

## Bounds and stop behavior

The journal allows at most 4,096 records, 4,096 bytes per record and 8 MiB total.
It admits only fixed event schemas and the controller's four subscription methods;
it records validated mint identifiers, counters and hashes, not raw upstream
error messages, arbitrary commands, URLs or credentials. New files are exclusive
and private. It will not append to or repair an existing journal.

Every record is sequence/hash chained and fsynced. A write/flush/cap error causes
the controller to abort/close and return measurement failure. If logging the
intent takes time, the controller rechecks the capture deadline **after** the
flush and before sending. Expired intents are marked abandoned without sending.
A terminal journal failure can leave partial bytes; these are retained as failed
or incomplete evidence. Completed local sends cannot be retroactively proved
from an absent record.

Replay validates the chain, schemas, increasing clocks and capture row positions,
intent/completion ordering, selected mint identity, terminal capture binding and
presence of all selected-creation observations. A missing terminal record,
tampered/truncated input, false selection or inconsistent snapshot is rejected.
Hash chains and receipts bind reviewed bytes; they are not third-party signatures
or independent proof of the truth of locally recorded timestamps.

## Preservation integration

The worker retains `session.jsonl`, copies it into both its export and restore
folders, and replays it against the restored capture. Its receipt contains the
journal hash/size and full derived measurement report. The supervisor checks
all three journal copies, recalculates the original and restored projections,
and rejects a changed copy or an invented provider-acknowledgement count.

The existing `capture.zip` format remains the accepted two-member capture package;
it does **not** embed the new sidecar. The local pair is bound by the supervisor
manifest/receipt. Future live off-machine preservation must transfer and verify
both the capture package and measurement sidecar with their receipt. The earlier
fixed synthetic B2 receipt does not cover this new sidecar. Do not rerun that
old fixed-input cloud probe as evidence of new coverage.

## Validation and next action

Development checks include 17 new measurement tests and one new supervisor
receipt-tampering test, for **259 tests** in the full suite. They cover actual
controller integration, monotonic delay, terminal-limit missingness, duplicate/
capacity denominators, failed/cancelled sends, failed writes and flushes, slow-
flush deadline expiry, tampering, malformed/incomplete journals, source binding,
copy/replay equality and private-file enforcement. The supervisor's Linux
process/resource controls and existing capture/wire regressions remain exercised.

The complete development runner passed in 4.213540 seconds on Python 3.12.14 /
SQLite 3.53.1 / websockets 17.4 with ResourceWarning treated as an error.

The Kali runner now pins 35 sources. Run the supplied exact commit/tree command
with the existing pinned portable websockets 17.4 setup. Expected:
`offline-measurement-passed-live-blocked`, 259 tests and
`supervision.worker_receipt.measurement_restore_replayed: true`.
The synthetic measurement should show three completed local sends and one
selected creation with one measured subscription delay. The delay value itself
is host-dependent and is not a trading latency or performance gate.

Upload the single offline JSON report. There is no additional cloud call,
provider connection, wallet funding, key input or scanner restart in this step.

## Remaining critical path

Resolve explicit provider permission for the exact existing-scanner/collector
coexistence arrangement, or separately approve and validate a shared connection
that preserves scanner discovery when R1 stops. Complete private credential and
exposure controls, the fixed measurement registration, actual-capture-and-journal
preservation/retention, and real host TLS/session validation under that connection
model. Obtain the owner's numeric funding decision before paid activation.

No provider message was sent by this work. A different key or host does not
establish permission. Full-gate Kali acceptance still precedes PR/CI consolidation
and the owner's merge decision. ML fitting stays outside this measurement phase.
If blockers persist through the existing effort cap, record the blocked/
insufficient verdict and reassess scope; do not extend the phase by adding more
historical probes or automatically continuing collection.
