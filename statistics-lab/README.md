# Standalone projected statistics benchmark

The production reader parses full event JSON before keeping the small subset used
by statistics. This candidate projects that same subset inside SQLite, then uses
the existing summary implementation. It is experimental and is not installed in
the running scanner.

Run once from the live project directory using a reviewed, pinned development
checkout:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/statistics-lab/run-projected.sh
```

Upload the printed `radar-statistics-projected-*.json.gz` report. It contains the
reader identifier, phase timings, row counts, original byte counts, returned byte
counts and a sanitized completion/failure state. It contains no summary outcomes,
raw events, tokens, credentials or model evaluation.

The command starts one separate worker through the existing container, checks
installed source hashes, and opens the scanner database read-only. It neither
rebuilds nor restarts the scanner, changes its statistics cache, updates signal
rules, nor evaluates the frozen study. It makes no network requests. There can
still be brief additional CPU and disk contention while the benchmark runs.

## Meaning of the result

`completed` proves that this standalone replay finished within the existing
bounds for that run. Compare elapsed time and per-kind counts with the original
profiler, allowing for new rows and local contention. A smaller returned payload
alone is not proof of faster computation. `stopped` remains useful evidence; do
not automatically rerun or increase limits.

Original limits remain: eight-second read deadline, ten-second worker watchdog,
96 MiB old-generation heap, 100,000 rows per kind, 256 KiB per original row,
1 GiB cumulative original JSON, and 64 MiB WAL growth. No partial statistics are
accepted. The outer command has a 20-second timeout.

## Equality and integrity

Projection retains the exact fields consumed by `compactSummaryRow`. JSON text
extraction preserves types and numeric precision; duplicate selected keys fall
back to full JSON so last-key-wins behavior is unchanged. Invalid JSON, JSON5 and
oversized original records cannot become valid projected summaries. Recent
research-event reads remain unchanged.

Tests compare the complete original and candidate summaries across versions,
missing/null/zero fields, gaps and alternate pools, and verify unchanged database
bytes. Runtime integration tests cover bounded reports and malformed/oversized
rows. No runtime release is authorized by a successful benchmark alone; a runtime
patch still needs review, integration checks and deployment verification.

## Subsequent experiment

The projected reader did not meet the runtime target on the host. The next
standalone candidate is documented in [COMPACT-STORE.md](COMPACT-STORE.md): a
resumable compact row cache with source-inventory reconciliation. Neither
candidate is connected to the production statistics worker.

The optional partial source index and its explicit maintenance installer are
covered in [SOURCE-INDEX.md](SOURCE-INDEX.md). This schema migration is separate
from the read-only benchmark and does not deploy the compact statistics service.

For host index-build timing without scanner downtime, see the disposable local
backup [INDEX-REHEARSAL.md](INDEX-REHEARSAL.md).
