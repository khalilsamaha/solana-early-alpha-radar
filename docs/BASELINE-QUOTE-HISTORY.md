# Baseline quote history and local restore verification

After scanner launch preservation, reuse `research-dataset/history-run.sh` for
multi-day observer evidence. Capture one 72-hour live window and one 72-hour
window from the latest local quote-ledger backup with `--latest-backup`.
These are overlapping retrospective windows, not independent samples or a newly
registered experiment. Preserve their source identities, policy versions,
capture cutoffs and unknown/failed outcomes separately.

The existing local-backup path verifies the archive hash, decompressed size,
SQLite integrity, table hashes and metadata in an isolated temporary restore.
It does not restore over the running ledger, start an observer or contact cloud
storage. The historical capture retains its 60-second read, 180-second overall,
row, byte, chunk and WAL-growth budgets. Failure does not silently shorten the
requested window or publish a partial successful capture.

Database connections in the historical reader and quote-backup snapshot/summary
helpers now close explicitly on success and failure, after the existing transaction
context finishes. This fixes connection lifetime without changing archive format,
table hashing, query windows, report contents, retention or service configuration.
The operations package manifest advances to `radar-operations-1.0.4`; no installer
or installed backup job is changed by invoking tools from the development checkout.

Local validation passed all 40 research-dataset tests and 28 operations tests.
The lifecycle regression checks all opened connections across backup, restore,
capture and capture failure. Kali acceptance remains required.

Review usable labels and missingness by cohort and day before deriving a sample
forecast. Do not add overlapping live/backup totals, use current lookups to fill
historical features, or reinterpret old closed studies as fresh validation.
Neither capture authorizes model promotion, collection-policy changes, trading,
or consolidation before the agreed baseline engineering phase is complete.
