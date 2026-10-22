# Historical research capture

This offline extension reads retained quote observations in bounded windows. It also accepts a verified local quote-ledger backup. It does not install anything, restart the scanner, alter collection, request market quotes, train a model or access Backblaze.

## First run: retained live history

After checking out the pinned commit in the release message, run:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/research-dataset/history-run.sh --hours 72
```

Upload the `research-dataset.json.gz` at the **final** path printed by the wrapper. Keep its adjacent `capture/` directory, which contains the original window exports and their checksum index. A successful run publishes both together in a new `radar-history-TIMESTAMP-PID/` directory. On any capture or analysis failure, the wrapper removes its staging directory and publishes neither. Reports are private and refuse overwrite.

Unlike repeatedly exporting the latest 24 hours, this queries distinct historical intervals in one pinned SQLite read transaction. The default is twelve six-hour chunks covering 72 hours. Every chunk uses the same evidence cutoff. A watch admitted near the end of a chunk keeps its later recorded outcomes; entry selection and outcome availability use separate clocks.

The scanner keeps running. This adds temporary host CPU, disk reads and memory use during capture/analysis. It does not change scanner scheduling or observer request budgets. The read transaction lasts at most 60 seconds and stops on more than 32 MiB WAL growth. Shorter windows are available if host load or a cap prevents completion:

```bash
bash ~/apps/solana-radar-dev/research-dataset/history-run.sh --hours 48 --chunk-hours 3
```

This explicitly changes the requested window. There is no automatic narrowing. A smaller chunk helps a per-chunk limit; it does not bypass the total limits.

## Can Backblaze backups supply ML data?

Yes, if the relevant evidence was recorded and retained in the snapshot. Two different backups have different uses:

| Backup | Evidence | Appropriate research use |
| --- | --- | --- |
| Scanner database, `daily/` | Scanner events, launch context, paper entries and sampled prices | Detection/launch studies and paper-price targets; not a substitute for quote exits |
| Separate observer ledger, `quote-ledger/` | Recorded entry features, admitted/skipped decisions, buy/sell quote responses, failures and policy registrations | Entry-time features with later quoted outcomes and quote-availability labels |

The repository contains the separate quote-ledger backup implementation. Its expected local copies are in `/var/backups/solana-radar-quotes`. Check the actual inventory before assuming historical archives exist:

```bash
sudo python3 -E -s ~/apps/solana-radar-dev/research-dataset/history.py --list-backups
```

This lists only local archive/manifest pairs; listing alone does not verify their contents. To analyse the latest local copy:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/research-dataset/history-run.sh --latest-backup --hours 72
```

Or select one exact local archive from that list:

```bash
bash ~/apps/solana-radar-dev/research-dataset/history-run.sh \
  --archive /absolute/path/to/quote-TIMESTAMP-ID.sqlite.gz --hours 72
```

The archive must have its adjacent `.sqlite.gz.json` manifest. This tool checks compressed SHA-256, format/identity, restored size, SQLite integrity, all table hashes and recorded metadata. It decompresses into a temporary isolated directory and removes that copy afterwards. It never restores over the live database or launches an observer. No cloud operation is implemented here. If only the cloud copy exists, stop at the local inventory; cloud retrieval remains a separate decision.

The old manifest records backup **completion**, not the exact snapshot-start time. Reports retain that distinction and use completion as an upper bound on evidence availability. They do not invent observations between the snapshot and completion. A backup ending yesterday cannot establish today's performance.

For a prior entry window within the chosen source, an explicit timezone-aware end is supported:

```bash
bash ~/apps/solana-radar-dev/research-dataset/history-run.sh \
  --hours 24 --end 2026-10-13T00:00:00Z
```

That timestamp is an example, not a forward-test registration. `--end` filters observer detection times; it does **not** roll back the database to that historical instant. Later outcomes present in the source remain available, with their actual clocks. Entry windows are half-open `[start,end)`. Never present these retrospective results as prospective validation.

## Evidence limits and joining

- Source identity plus signal sequence identifies the same observation across overlapping snapshots. The existing dataset builder deduplicates these; never add backup counts together as independent examples.
- Missing and failed quotes remain explicit. Unrecorded features cannot be reconstructed from today's token data. Older versions and sampling policies remain separate.
- The live observer retains seven days. Earlier retained bounds are reported, but neither an empty interval nor an absence of gaps in queried windows proves uninterrupted collection.
- A stored row is capped at 1 MiB; each chunk at 5,000 rows per table and 16 MiB combined raw JSON; the complete capture at 20,000 rows per table and 96 MiB raw JSON. At most 16 chunks, 1..72 hours and 1..12 hours per chunk are allowed. Ledger/restore size is capped at 512 MiB. Rebuilt inputs retain the existing 128 MiB total and final-report publication caps.
- The capture command has a 180-second overall deadline, including local restore verification. This is a bounded offline tool, not a permanently running collector.
- The capture index validates contiguous windows, checksums, record counts, clocks and source identity when rebuilding. A requested window preceding the first retained row is flagged, not silently accepted as complete historical coverage.

To rebuild a saved capture without database access or sudo:

```bash
python3 -E -s ~/apps/solana-radar-dev/research-dataset/build.py \
  --history-dir /absolute/path/to/radar-history-TIMESTAMP-PID/capture \
  --output /absolute/path/to/new-dataset.json.gz
```

For overlapping captures, the existing repeated `--input` option accepts individual `part-NN.json.gz` files, subject to the total 16-input/byte/unique-row limits. Use only the needed windows. Distinct source identities cannot be combined by this release. The default wrapper handles one source/capture at a time.

## Next ML milestone

The immediate purpose is to inspect more historical days without waiting for all of them to be collected again. First establish feature availability, failures, policy/version boundaries and usable labels by cohort and day. Then freeze a small baseline model and chronological evaluation protocol. Fit preprocessing on training rows only; keep tokens out of both train and test, and compare against constant and existing-rule baselines. Old evidence may support an exploratory model, but new pricing fields exist only from their deployment onwards.

No model is trained or enabled by this change. A promising retrospective result still needs a later untouched evaluation period. Quotes do not demonstrate executable fills or net profitability.

## Verification for this release

The October 15 02:33 UTC source export was replayed through a temporary ledger and twelve historical chunks. The resulting dataset rows, targets, summary and pricing audit exactly match the direct builder: 3,635 raw signal records, 3,270 eligible signals and 131 watches. The capture correctly warns that this one-day upload cannot establish three-day coverage. This is a replay check, not a capture from the user's running machine.

Regression checks cover half-open boundaries, outcome clocks after an entry-window end, concurrent writes during a pinned snapshot, row/byte failures with no partial publication, index/identity mismatches, tampered captures, isolated local archive verification, wrapper cleanup and legitimate progress of incomplete watches. Scanner and observer source files are unchanged.
