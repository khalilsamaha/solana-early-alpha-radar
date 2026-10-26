# Incremental compact statistics experiment

This is a standalone diagnostic, not a deployed statistics service. It leaves the
scanner database read-only and writes a separate private derived cache. It does
not change scanner code, signals, polling, notifications, the quote observer or
the frozen experiment. It does not export outcomes or evaluate the model.

## Run once

From the live project, with the reviewed development checkout pinned:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/statistics-lab/run-compact.sh
```

Allow approximately two minutes. Upload only the printed
`radar-statistics-compact-*.json.gz` report. Keep the private cache on the host;
it contains compact historical event data and must not be uploaded or committed.
It lives under the configured scanner data directory in
`statistics-cache-lab-1/compact.sqlite`. It persists through container recreation
when that data directory is mounted persistently. No service/timer is installed.

`completed` means both an initial/resumed pass and a warm pass completed. The
report distinguishes total reconciliation time from final inventory validation
plus summary time. Original JSON is fetched only for records not already matched
in the cache. Cached compact rows are still read during summary computation; this
is not an incremental aggregate engine and does not guarantee constant runtime.

`paused` means the total work budget or changing-source limit was reached. Durable
completed batches are retained, but no complete statistics are published for the
unfinished round. Preserve the report before deciding on another bounded run.
`stopped`/`unavailable` reports a sanitized error. Do not increase limits, delete
journals, or retry in a loop. A stale `active.lock` after a parent-process crash
requires checking that no benchmark is active before operator cleanup; the tool
never guesses that a lock is stale.

## Consistency contract

The reviewed `Storage.append` inserts events and `Storage.prune` deletes them.
It does not update existing event payloads. The derived cache relies on that
immutability contract; arbitrary in-place database edits retaining the same
sequence, kind, ID and timestamp are not detectable without rereading payloads.
Such edits require invalidating/rebuilding the derived cache. This is not an
independent tamper detector.

Each batch reconciles at most 128 source identities, reads missing payloads and
removes cached rows absent from that sequence range. Source reads use a read-only
transaction; cache rows and progress commit together in a separate transaction.
A restart resumes the committed cursor. Source replacement is rejected using file
identity. Reader provenance is persisted. Unknown reader changes cannot reuse a cache; the
explicit reviewed compatibility transition described below is the sole exception.

After a pass, a fresh read transaction compares all retained source identities to
the cache using native SQLite joins and existence checks. Up to 512 new arrivals, deletions or reused sequence numbers with different
identities are reconciled inside that same read snapshot before calculation.
Larger changes prevent completion and restart bounded reconciliation. Both difference queries finish before applying the collected delta. Only the resulting matching
inventory can feed the unchanged statistics functions; the latest 30
research events are read in that same source snapshot. Pending/overdue calculations
use its current timestamp. Source retention is respected rather than inferred
from a guessed cutoff.

This experiment discards computed summaries and exports only diagnostic counts
and timings. A production adapter, publication/cache freshness policy and runtime
integration tests are still required before deployment.

## Bounds and recovery

- Each batch and final validation/summary keeps the eight-second read deadline,
  ten-second parent watchdog, 96 MiB worker old-generation limit, and 64 MiB WAL
  growth limit. Read transactions close between batches with a brief pause.
- Original JSON limits remain 256 KiB per row, 100,000 rows per summary kind and
  1 GiB total retained original JSON. Compacting does not bypass these limits.
- The whole benchmark has a 120-second cooperative budget; one last bounded step
  can extend that. The host command has a 145-second outer timeout.
- Malformed/oversized records or step failures roll back the current batch;
  completed earlier batches remain resumable. Failed validation never publishes
  partial statistics.
- The cache is disposable derived data, not a replacement for scanner backups or
  frozen captures. Permissions and exclusive run lock are checked. No cloud
  transfers are made. Extra local CPU, reads and cache writes may cause contention.

## Validation

Tests cover full-summary equality, bootstrap and warm reuse, restart recovery,
new events, retention/empty kinds, sequence reuse, changes before validation,
malformed/oversized input rollback, timeout/summary failure, source replacement,
source/cache alias rejection, provenance changes, bounded reports, privacy and
launcher behavior. Host timing remains a release gate, not a test-suite inference.

An optional reproducible scale exercise creates 65,000 synthetic events and runs
both benchmark rounds, then removes its temporary databases:

```bash
node statistics-lab/scale-check.mjs
```

It checks completion and zero historical payload reads in the warm round. It is
not run against production data and its timings are not predictions for Kali.

## Phase diagnostics and local-first development

Reports retain `diagnostic.failedPhase` on a caught failure and `activePhase` for
an externally terminated worker. `inventory-validation` includes the source/cache
identity comparison and bounded catch-up. `summary-calculation` includes compact
row reads and the unchanged summary functions. `summary-finalization` includes
post-calculation guards and committing completion metadata. Timings are elapsed
wall time, not CPU attribution; an incomplete phase has only the last progress
message if the parent watchdog terminates the worker.

`cursor` identifies the committed cursor before the current batch. `readRows` and
`reusedRows` count completed batches; unfinished work is not reported as committed.
Phase instrumentation does not change summary semantics or relax timeout, memory,
row or WAL limits. The native reader uses the explicit cache compatibility
transition described below.

For a larger local exercise (160,000 rows, with longer synthetic identifiers):

```bash
node statistics-lab/scale-check.mjs --large
```

This fixture is not a production disk, writer workload or complete reproduction
of private event shapes. Passing it does not establish readiness for deployment.

## Native inventory comparison

The `sqlite-delta-1` experiment attaches the source with SQLite URI `mode=ro` to
the cache connection. All final inventory, catch-up and recent-event reads use
that attachment in the same transaction. The summary is computed before that
transaction commits. Tests exercise a concurrent WAL writer and verify that later
arrivals do not leak into the final snapshot.

Only differences cross into JavaScript, with the existing 512-change limit. The
source's existing `events_kind_seq` index supports deletion checks without reading
source payload pages. The new `rows_inventory` covering index exists only in the
private derived cache; no source index is created. SQLite statements remain under
the cooperative eight-second transaction deadline and ten-second worker watchdog.
An individual statement cannot be interrupted by a JavaScript guard while running;
the parent watchdog bounds an unresponsive worker. Limits are not increased.

A single compatibility transition permits reuse of the earlier cache from commit
`9693b44726d670a05b0ea015ca214153a0236986`. Both its exact old provenance and the
unchanged scanner-file manifest fingerprint must match. Compact row semantics and
schema remain compatible; the upgrade adds the private covering index and records
previous provenance atomically while preserving rows and the committed cursor.
Unknown provenance, changed scanner files, source identity changes and version
mismatches still refuse reuse. Keep the existing cache; do not delete it to bypass
a mismatch. The older reader will refuse the upgraded cache.

The sparse local exercise adds 1.28 million unrelated rows to the large fixture,
creating approximately 5.5 GB of source data:

```bash
node statistics-lab/scale-check.mjs --large --sparse
```

It needs temporary disk space and deletes only its own temporary directory when
finished. `--store /absolute/path/to/reader.mjs` permits a local before/after
comparison. This option is for trusted local development code only, not the host
launcher. Disk caching and concurrent workload still prevent treating synthetic
timings as a prediction for the host.

A paired local sparse-fixture run (160,000 relevant events, 1,280,000 unrelated
rows, 5,546,942,464 source bytes) completed both rounds for both readers. The old
inventory phase took 1.56/1.11 seconds; the native phase took 0.54/0.82 seconds.
Final validation plus summary took 4.55/3.50 seconds before and 2.51/2.87 seconds
after. Both warm passes reread zero historical payloads. The covering index grew
the derived cache from about 54.8 MB to 73.0 MB. These single-run measurements
vary with disk caching and other load; the host benchmark remains necessary.
