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
identity. Reader provenance is persisted and mismatched code cannot reuse a cache.

After a pass, a fresh read transaction compares all retained source identities to
the cache in sequence order. New arrivals, deletions or reused sequence numbers
with different identities prevent completion and restart reconciliation. Only a
matching inventory can feed the unchanged statistics functions; the latest 30
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
