# Partial statistics identity index

The compact benchmark's source inventory comparison still fetches ID and timestamp
columns from scattered event-table pages when it uses only `(kind,seq)`. This
migration adds `events_statistics_identity(kind,seq,id,at)` for **only** alerts,
outcomes, research-entries and research-outcomes. Snapshots and all other kinds are
excluded. The candidate reader requires the exact reviewed index definition and
uses a covering scan for both final additions and warm identity pages. Existing
indexes remain in place. No event, candidate, outbox, journal or model record is
edited by the installer.

This is a source schema migration, unlike the earlier read-only benchmarks.
Creating an index holds SQLite's writer lock. The scanner's five-second write wait
is shorter than the allowed index build, so live online installation is refused
by the public launcher. `--apply --maintenance` explicitly permits a brief stop
and restart of the **same running scanner container**, without recreation or
rebuild. The quote observer and frozen experiment are not reconfigured. Scanner
research buffers will warm again after restart; observations during maintenance
are a real gap and must not be treated as continuous evidence.

## Bounded installation

The launcher resolves the single running radar container and writable `/app/data`
mount, checks canonical source identity, and serializes runs with a root-owned
nonblocking flock. It first inspects the index read-only. An already correct index
returns without stopping the container. A same-named different object is refused.

When installation is needed, the launcher stops that exact container, runs a fixed
root worker (Docker volume ancestors can be root-only), and attempts restart in `finally`, including after
worker failure or stop timeout. The launcher restores WAL/SHM/journal ownership
to the database owner using checked file descriptors, including after worker
timeout, so the scanner can reopen them. It never relaxes volume-directory
permissions. SIGINT/SIGTERM use the same recovery path. Abrupt
host failure or SIGKILL cannot guarantee restart; see recovery below. Other SQLite
writers can still cause a refusal. No retry loop is used.

The worker requires WAL mode, expected event columns and the sequence index,
100,000 rows or fewer per summary kind, and at least 1 GiB free disk space. Index
creation is atomic in one `BEGIN IMMEDIATE` transaction. A SQLite progress handler
checks a 30-second cooperative deadline and 64 MiB WAL-growth threshold; failure
rolls back uncommitted index work. Native I/O can delay progress callbacks; the
launcher separately limits the worker process to 45 seconds. These are migration
bounds, not increases to the statistics reader's eight-second deadline. Existing
records and derived-cache progress remain intact. No explicit checkpoint, VACUUM,
backup deletion or cloud operation is performed.

The restart report confirms container running state only. Check readiness after
restart before benchmarking. On timeout or a lost result, inspect the index rather
than assuming either success or failure. SQLite commits may have completed before
a launcher lost its result.

## Commands

Use the pinned development commit supplied in chat. Run as the regular project
user from `~/apps/solana-early-alpha-radar`:

```bash
sudo python3 -E -s ~/apps/solana-radar-dev/statistics-lab/source-index.py \
  --project "$PWD"
```

This is read-only inspection. For the explicit brief maintenance operation:

```bash
sudo python3 -E -s ~/apps/solana-radar-dev/statistics-lab/source-index.py \
  --project "$PWD" --apply --maintenance
```

Save the public JSON report with private permissions. The `--worker` argument is
internal; do not use it against the live database to bypass maintenance handling.
Successful states are `index-installed` and `already-present`; failed operations
must be reviewed, not retried automatically. Once readiness returns, run the compact
benchmark once and keep its existing cache.

If restart is unconfirmed or the launcher was killed:

```bash
cd ~/apps/solana-early-alpha-radar
sudo docker compose start radar
sudo docker compose ps
```

Then use the read-only inspection command and preserve both reports. Do not delete
or manually replace the database, index, cache or WAL files.

## Validation and remaining gate

The disposable production-schema fixture contains 160,000 relevant rows plus
1,280,000 unrelated rows (5.65 GB). The same Python installer used by the host
launcher successfully builds the partial index on this fixture. Relevant tests
cover unchanged event records, partial-index membership after inserts/deletes,
covering query plans, summary equality, WAL snapshot consistency, wrong-index
refusal, timeout rollback, busy writers, disk/schema/owner checks, identity changes,
row caps, volume access/sidecar ownership checks and restart-on-failure behavior.

A successful benchmark still does not connect the compact cache to the deployed
statistics endpoint. Host performance is the next gate; production worker
integration and its freshness/recovery behavior remain separate work. Signal
rules, admission budgets and the frozen model are unchanged.

On the development machine, the real Python installer built the 160,000-row index
in 2.294 seconds (2.292 seconds holding the writer lock), adding 16,224,256 bytes.
The subsequent initial and warm inventory validations took 0.214/0.185 seconds;
validation plus summary took 2.227/2.030 seconds. Warm historical payload reads
remained zero. These are synthetic measurements, not a promise of Kali timing.
The scale fixture invokes the same bounded installer with `--large --sparse
--covering-index` and removes only its own temporary databases afterward.

If the bounded live installation times out, use the completed-backup rehearsal
in [INDEX-REHEARSAL.md](INDEX-REHEARSAL.md) before planning further maintenance.
The rehearsal's longer copy-only deadline does not change the live installer.
