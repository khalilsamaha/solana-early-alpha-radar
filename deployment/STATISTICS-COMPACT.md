# Compact statistics runtime

This release connects the host-tested compact reader to `/api/stats` and
`/metrics`. Historical summaries refresh in a worker in the background, even
without dashboard requests. The scanner's market polling, scoring, research,
quote admissions and frozen study rules are unchanged.

## Behavior and bounds

One refresh at a time reconciles the existing private cache in 128-row batches,
pausing 10 ms between batches. The final inventory comparison and summary use
one consistent source snapshot. Only a complete result from a successfully
exited worker replaces the published summary. The timestamp belongs to that
source snapshot, not the start or end of reconciliation.

Each transaction retains its eight-second deadline and 64 MiB WAL-growth guard.
The worker retains its 96 MiB old-generation heap limit and original row/byte
limits. Progress resets a ten-second inactivity watchdog, while an independent
130-second job watchdog prevents endless progress from extending a job forever.
The worker also checks a 120-second total work budget between transactions.
Cold HTTP requests wait at most five seconds, then return 503 while the same job
continues. Existing summaries remain available for at most 120 seconds; those
older than 60 seconds are labelled stale. Failed refreshes wait 30 seconds before
retrying. There is no synchronous full-history fallback.

`statisticsWorker` health reports the runtime version, current phase, complete
snapshot age, reconciliation counters, final computation time and full refresh
time separately. Current candidates and provider health remain live fields.
The existing dashboard already renders summary freshness and updating/error labels.

## Cache and recovery

Keep `/app/data/statistics-cache-lab-1/compact.sqlite`. The worker explicitly
accepts the reviewed benchmark provenance, including the covering-index reader,
and preserves committed rows, source identity and progress. Semantic source
hashes and the compact-store hash are checked; unknown provenance is refused.
The runtime store is the same code as the validated laboratory candidate.
The partial source index must already exist; there is no automatic schema change
or fallback to the slow unindexed path.

A separate SQLite lease file holds an OS-managed lock for the refresh. A matching
`active.lock` marker prevents legacy benchmarks from overlapping. Worker exit,
timeout and graceful shutdown release both. Process death releases the SQLite
lock, allowing a later runtime to recover its own leftover marker. An active
legacy benchmark PID is refused; unknown lock contents are preserved/refused.
The lease and compact files are private and never alias the source database.

The published summary is intentionally memory-only. Restart keeps compact rows
but starts a new verified refresh before publishing; cold requests may return
503 during this interval. Source replacement, malformed rows, incompatible cache,
missing index or deadline violations cannot produce partial or fabricated statistics.

## Installation and acceptance

From the pinned development checkout supplied in chat:

```bash
python3 ~/apps/solana-radar-dev/deployment/install-statistics-compact.py \
  --project "$HOME/apps/solana-early-alpha-radar"
cd ~/apps/solana-early-alpha-radar
sudo docker compose up -d --build --force-recreate radar
node --env-file=.env \
  ~/apps/solana-radar-dev/deployment/verify-statistics-compact.mjs
```

The installer checks payload and dependency hashes, stages the complete scanner
regression suite, and backs up source before replacing six statistics/server
files. It does not copy configuration or databases. A build/restart is necessary
and creates a genuine observation gap. Preserve all frozen-study captures.
The acceptance command observes only local endpoints and exports safe diagnostics,
not statistics, token data, credentials or model outcomes. It requires two
distinct successfully served summary snapshots and records readiness throughout.
Allow roughly three minutes. Upload its JSON even for `needs-review`.

No repeat source-index installation or standalone compact benchmark is needed.
Do not run legacy benchmark tools while this runtime owns the cache.

For a source rollback, use the exact source-backup directory printed by installation:

```bash
python3 ~/apps/solana-radar-dev/deployment/install-statistics-compact.py \
  --project "$HOME/apps/solana-early-alpha-radar" \
  --rollback "$HOME/apps/solana-early-alpha-radar/source-backups/EXACT_BACKUP_NAME"
```

Then rebuild/restart radar. Rollback preserves the index and private cache; the
previous full-history statistics reader may still time out. Do not delete evidence
to make an older reader appear healthy. Final host acceptance remains necessary
before calling the production statistics issue resolved.
