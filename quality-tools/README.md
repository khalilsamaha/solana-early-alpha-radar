# Research quality helpers

Report 3 preserves `shadowSummary` and `evidenceAnalysis`, and adds:

- `joinedEvidence`: exact Fast30 entry/quote joins, validated atomic quantities, separate clocks, routes and unavailable cases. Quote changes are not fills or net profit. Legacy exports without source identity are provisional.
- `entryShadows`: independent known-liquidity and capped-prior-rise comparisons, with selected/excluded/unknown groups. Persisted registration separates forward observations from exploratory history. No entry rules or notification behavior change.
- `missingDiagnostics`: recorded checkpoint attempt evidence; missing historical details remain unknown.

From the running project directory use `bash ~/apps/solana-radar-dev/quality-tools/run-evidence.sh --hours 12`. It exports the existing observer 0.6.0 ledger and a bounded scanner snapshot into two private reports, without requesting quotes. See `docs/EVIDENCE-UPDATE.md` for installation, provenance, limitations and rollback.

`run-report.sh [QUOTE_REPORT.json.gz]` remains supported. `quality_report.py --shadow-report OLD_REPORT --quotes QUOTE_REPORT --output NEW_REPORT` performs an offline replay. The output must not exist. Original summary fields remain compatible, but consumers should accept `research-quality-report-3`.

Reports are not independent samples: deduplicate overlapping exports. Eventual-link and complete-path groups are hindsight diagnostics, not entry filters. Keep sampling policies and forward/exploratory periods separate. Unknown data, missing observations and quote failures remain explicit.

Tests: `python3 -m unittest discover -p 'test_*.py'`.

## Report format 4: pool and fixed-exit evidence

See `../docs/POOL-EXIT-UPDATE.md`. `pathEvidence` retains legacy-unavailable states, separate alternate-pool prices, and backward-only original-pool response comparisons with explicit ages. `fixedExits` evaluates the persisted 30-second primary / 60- and 120-second comparator protocol; historical observations stay exploratory. Failures, pending, missing and late exits remain explicit. Additional proceeds haircuts are stress scenarios, not measured net profit. Existing entry-shadow registration is independent of this new exit registration.
