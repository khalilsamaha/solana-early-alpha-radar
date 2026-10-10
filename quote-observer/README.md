# Solana Radar quote observer 0.5.0

For the existing scanner 0.2.9, research tools 1.1.0 and observer 0.4.0. No scanner rebuild is needed. Statistics memory/worker patches are untouched.

## Purpose

Expose the actual clocks behind paper and quote comparisons, distinguish returned sell quotes from failed or absent checks, and preserve more entry-time evidence for forward research. This update does not implement trading, automatic exits or new Telegram alerts.

## Install

```bash
python3 -m zipfile -e \
  ~/Downloads/solana-radar-quote-observer-0.5.0.zip \
  ~/Downloads && \
sudo python3 \
  ~/Downloads/solana-radar-quote-observer-0.5.0/install.py \
  --project "$HOME/apps/solana-early-alpha-radar" \
  --enable-service
```

The installer verifies files, Node 24 and read-only scanner schema access, then runs 56 JavaScript and 27 Python tests before stopping the observer. It accepts matching generated configurations from 0.2.0–0.4.0 or this version. Edited configurations are preserved and installation stops. Only the quote observer restarts. An active watch may be marked interrupted, and fresh signals can be skipped during its short restart.

Its existing ledger, scanner event cursor, source identity, rolling admission history, provider halt/cooldown and cohort-budgets-v2 registration remain. There is no SQLite schema change. The new feature-capture registration is created once on startup and persists across restarts. No historic signals are resampled to fill missing features.

A private, integrity-checked upgrade snapshot is created at `/var/lib/solana-radar-quotes/pre-0.5.0-TIMESTAMP.sqlite`. This is a local upgrade safety copy, not a scheduled or cloud backup. The separate quote ledger is still not covered by the scanner's daily backup; closing that gap remains a separate task. These upgrade copies are not automatically pruned.

## Verify now

```bash
sudo systemctl status solana-radar-quotes.service --no-pager -l
sudo python3 -E -s \
  /usr/local/lib/solana-radar-quotes/0.5.0/manage.py status
cd ~/apps/solana-early-alpha-radar
bash ~/Downloads/solana-radar-quote-observer-0.5.0/export.sh --hours 24
```

Upload the report path printed by export.sh and paste the status output. Expected status markers:

- `observerVersion`: `quote-observer-0.5.0`
- `samplingRegistration.id`: `cohort-budgets-v2` with the original registration date
- `featureCaptureRegistration.id`: `entry-features-1` with a new installation-time registration
- The compatible report format remains `quote-observer-report-0.2.0`.

The first export immediately analyzes existing quote records. New feature data appears only as fresh signals are received. No wait is required for installation verification. A quiet or budget-limited period can legitimately contain no new probes. lastPollAt is persisted every ten seconds although the feed is polled every two seconds; it is not a per-request timestamp.

## What changes

### Entry-time evidence

For new signal records, `features` additionally captures available market cap, holder count, average reported trade size, five-minute transaction count and volume, unchanged-market duration, drawdown, liquidity change, interval return, venue identifier and Jupiter observation time. Existing liquidity, security and short-window returns remain.

The values come solely from the immutable event being consumed. `featureCapture.sources` identifies numeric fields as recorded, absent or invalid and gives the exact event field used. Observation ages are measured at the signal. Future/invalid timestamps become unknown. A security description without a recorded check timestamp is not upgraded into evidence of freshness.

Early-activity events do not currently include all provider fields. Their missing holder counts, organic scores and timestamps stay unknown. No later candidate snapshots, token lookups or current provider data are substituted. Recorded timestamps are receipt/check times, not proof of fresh exchange trades.

### Exit evidence and timing

`manage.py export` now adds `exitEvidence`. The original signals, probes, quoted returns and report format are preserved.

Each probe has a buy status and four exit states, including:

- `sell-quote-returned`: provider returned a quote; execution remains unverified.
- `sell-quote-failed`: request did not yield an accepted quote; category is a provider hint, not a verified cause.
- `not-sampled-buy-failed`: no sells attempted after the failed buy quote.
- `not-sampled`: explicit skipped checkpoint, with its reason retained.
- `pending` / `overdue-unrecorded`: a running watch has not recorded the checkpoint; overdue uses a conservative scheduling/timeout allowance.
- `incomplete-unrecorded` / `interrupted`: incomplete evidence remains explicit.

Every recorded check shows signal time, buy request/response, scheduled quote time and sell request/response, plus elapsed milliseconds for each clock. The nominal zero-second sell has request spacing; its actual timing is always shown. Negative timing differences are flagged. Summaries retain all admitted probes in the denominator and report missing quote returns separately. They never assign a missing quote a zero return or loss.

A price can repeat while exit quote requests fail. These are different evidence dimensions. Quotes, price snapshots and hypothetical paper exits are never substituted for one another.

### Prospective activity comparison

The upgrade registers one observational comparison using the existing $5 small-average-trade threshold: below $5, at least $5 and unknown, evaluated primarily at the 120-second quote checkpoint. Results are split by cohort, sampling policy and prospective status; legacy records are not backfilled or counted as newly captured evidence. The primary horizon is fixed before new outcomes arrive. Other existing horizons remain visible.

This comparison changes no signal or quote admission decision. A minimum average trade size is not a validated profitability or safety filter. The small-trade threshold was already an observational flag; this release preserves the data needed to evaluate it prospectively. Unknown and failed observations remain in reports.

## Compare quote and paper clocks offline

Use an exported quote report and research-tools 1.1.0 report. They may cover different windows; unmatched entries remain explicitly outside the matching research export.

```bash
bash ~/Downloads/solana-radar-quote-observer-0.5.0/compare.sh \
  /full/path/to/quote-report.json.gz \
  /full/path/to/research-report.json.gz
```

This requires no sudo, host configuration, network or running scanner. A new `radar-clock-comparison-*.json.gz` appears in the current directory. It includes:

- `clockComparisons`: paper entry/exit and quote request/response clocks for fixed 60/120-second policies, including each model delay scenario.
- `quoteExitEvidence`: the same exit-evidence summary as the export.
- Prior original-pool alignment, model evidence and registered qualification comparisons.

`modelExitMinusQuoteSellRequestMs` makes timing differences explicit. The model's delayed entry and sampled exit remain unchanged. No interpolated prices, new hypothetical trades or claims of equal execution are introduced.

## Performance, scope and reliability

- Scanner discovery, signal thresholds, market polling, research evidence retention and notifications are unchanged.
- Quote requests stay capped at five per watch, six admissions/hour globally, three/hour per cohort, 72/day per cohort, no borrowing and 20-minute cohort spacing.
- New fields add modest per-signal storage. The existing seven-day ledger retention and 256-MiB observer storage cap remain. Larger exports may require a shorter window if the existing 32-MiB raw-export cap is reached.
- Report aggregation runs in the separate export process after releasing the read-only SQLite transaction. It is not added to the scanner or its statistics worker.
- The transport, endpoint, request spacing, amount, retry policy and failure cooldowns are unchanged. No new API traffic or paid subscriptions are introduced.
- Inputs are bounded; duplicate quote offsets fail analysis explicitly. No partial export is promoted by export.sh.

## Roll back the observer program if necessary

If the old 0.4.0 installation is intact and the managed configuration has not been edited:

```bash
sudo python3 ~/Downloads/solana-radar-quote-observer-0.5.0/rollback.py
```

This verifies the installed 0.4.0 payload, restores its service/configuration and restarts it if it was running. The current ledger, observations, cursor and budgets stay intact; the ledger safety snapshot is not restored over newer evidence. Use the 0.4.0 status/export commands after rollback. No scanner rollback or rebuild is needed. Service/configuration changes are reverted automatically if installation/restart raises an error; a later runtime failure still requires the explicit status check.

## Verification included

The package contains tests for immutable feature extraction, absent/invalid values, legacy evidence, missing and failed quote denominators, explicit clocks, duplicate evidence, registration persistence, source-read-only behavior, unchanged budgets, controlled installer upgrades, restart-failure restoration and program rollback. Systemd/Docker calls in installer tests are mocked; actual host service operation is checked using the commands above.

`replay-results.json` records an offline regression against the user's 101-probe report: 57/57 baseline and 40/44 early-activity final quotes, nine exact matches, and a 28,999-ms nox model/quote exit-clock difference. Inputs and original returns were preserved. This is validation of reporting, not strategy profitability.
