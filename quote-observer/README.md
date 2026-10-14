# Solana Radar quote observer 0.7.0

Walletless prospective quote observation for baseline, early-activity and Fast30 shadow signals. No signing, wallet access, transactions, notifications or automatic exits.

## Sampling

Policy `three-cohort-budgets-v3` reserves two admissions/hour and 48/day for each of three cohorts, with 30-minute spacing per cohort and no borrowing. Global limits remain six admissions/hour, 144/day, one active watch, five requests per admission and at least ten seconds between requests. Existing 24-hour per-mint suppression applies across cohorts. This is not paired or random sampling.

Provider cooldowns, access-denial halts and the 15-second signal-age limit remain. No queue is introduced. Previous admissions count against rolling limits after upgrade; a cohort may initially be blocked by its old budget usage.

Existing feed cursors and completed evidence are preserved during this upgrade. Fast30 fields come only from its immutable entry event; unknown security/liquidity remain unknown. Fast30 follow-up admission is recorded, but does not gate quote admission. Each probe retains its cohort, sampling policy and feature-capture version.

## Install from reviewed checkout

See `../docs/QUALIFICATION-REVIEW-UPDATE.md` for the coordinated scanner and observer procedure. The observer installer itself does not rebuild the scanner.

```bash
sudo python3 quote-observer/install.py --project "$HOME/apps/solana-early-alpha-radar" --enable-service
sudo python3 -E -s /usr/local/lib/solana-radar-quotes/0.7.0/manage.py status
```

The installer verifies the manifest, runs offline tests, checks managed configurations and snapshots the existing ledger before restarting. Modified configurations stop installation. A running watch may become interrupted; it is never reconstructed. Scanner data, source identity and cursor are retained. This update does not change the SQLite schema or sampling policy.

## Export and interpretation

Run `bash /path/to/checkout/quote-observer/export.sh --hours 24` from the host project. Report format remains `quote-observer-report-0.2.0`; runtime version is 0.7.0. `cohortCapacity` includes all three cohorts. Exit evidence groups by policy and cohort. Existing qualification shadow rules apply only to baseline and early-activity; Fast30 is evaluated through its own price/quote reports.

Offsets are relative to buy-response time; request and response timestamps are preserved. Quotes are not fills. Failed or skipped signals are not zero returns. Deduplicate exports using source identity plus sequence number. Observer retention is seven days; scanner backups do not cover this separate ledger.

## Pricing evidence in 0.7.0

Existing responses retain optional input/output/swap USD values, platform fee fields and exact route input/output atomic quantities. Missing or malformed optional values remain null; zero stays zero. The original output amounts and return calculations are unchanged. These fields describe provider quotes, not fills or independently verified valuations. Do not subtract reported price impact or fees from quoted output a second time.

Entry features also preserve qualification version, shadow mode and an entry-time timestamp when available. Old records remain explicitly unversioned. The offline `../qualification-review/run.sh` compares the existing retain/defer/unknown groups without changing eligibility or fitting new rules.

## Rollback

`sudo python3 quote-observer/rollback.py` verifies the installed 0.6.0 payload and returns the observer program/configuration to it. The current ledger and three-cohort sampling policy stay intact. New pricing fields already stored remain in historical records; the old program does not capture them for subsequent responses.

`replay-results.json` is a preserved historical 0.5.0 reporting fixture, not a current performance report.
