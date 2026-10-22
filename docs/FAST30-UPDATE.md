# Fast30 follow-up and quote sampling update

Historical deployment guide for commit `a55e567a11ba8baa0f308a71061ebd4892183b8a`. If that release is already installed, use [the evidence update](EVIDENCE-UPDATE.md) from the newer checkout.

The 2026-10-10 report showed 352 entries, but only 67.4% of mature entries had usable five-minute price evidence. Entries later linked to the existing early cohort had 91.3% coverage versus 32.6% without a link. This update addresses uneven observation and exposes actual timing; it does not optimize the entry rule on that sample.

## Behavior and limits

- Scanner rule thresholds remain unchanged. New Fast30 entries carry `fast-followup-1` admission metadata. At most 12 positions receive tracking priority (fewer for a small configured focus limit). Capacity exclusions remain recorded and may receive ordinary observations.
- These positions share the existing focus limit, normally 60. Existing research positions retain higher priority; fresh discovery and paper tracking retain their scheduler groups. Batch sizes, minimum revisit interval and provider rate limits remain unchanged. Ordinary focus candidates can be displaced; health reports `fastSelected`, `fastAwaitingCapacity` and `ordinaryDisplaced` as current gauges.
- Admission survives restart; interrupted paths remain gapped. Reservations expire when all checkpoints finish or become unavailable. They do not imply guaranteed provider data or market freshness. Existing Fast30 positions are not retroactively admitted.
- Reports separate follow-up policy and admission, actual endpoint delays, simultaneous versus earlier links and missing evidence. New links save comparison entry price/time. Matched returns use the same original-pool endpoint; historical missing comparison prices are not reconstructed. Fees and execution remain unmodelled.
- Observer 0.6.0 adds Fast30 and reserves two watches/hour per cohort. Each existing cohort loses one reserved watch/hour to Fast30. Total maximum remains six watches/hour and 144/day, with five requests/watch. Previous rolling admissions remain counted. No new API or paid subscription is introduced.

All reports must keep old and new policy groups separate. Eventual-link groups and complete paths are retrospective diagnostics, not eligible entry filters. Do not compare them as independent randomized cohorts.

## Deploy in the existing host directory

Use a separate Git checkout. Keep the current project at `~/apps/solana-early-alpha-radar`. The installer verifies exact installed source hashes, tests a temporary source copy, makes a source backup and modifies only three scanner files. It never edits Compose, `.env` or databases. Do not run Compose inside this repository's `scanner/` directory against production.

After reviewing the PR and confirming the checkout commit, from the checkout root:

```bash
python3 deployment/install-fast-followup.py \
  --project "$HOME/apps/solana-early-alpha-radar"
```

Only if that succeeds, rebuild from the original running directory:

```bash
cd ~/apps/solana-early-alpha-radar
sudo docker compose up -d --build --force-recreate radar
sudo docker compose ps
curl --max-time 10 --silent --show-error http://127.0.0.1:8787/readyz
```

From the checkout root, install the observer:

```bash
sudo python3 quote-observer/install.py \
  --project "$HOME/apps/solana-early-alpha-radar" --enable-service
sudo python3 -E -s /usr/local/lib/solana-radar-quotes/0.6.0/manage.py status
```

Run the quality helpers from the original host project, replacing `/path/to/checkout` with the real checkout path:

```bash
cd ~/apps/solana-early-alpha-radar
node --env-file=.env /path/to/checkout/quality-tools/verify.mjs
bash /path/to/checkout/quality-tools/run-report.sh
bash /path/to/checkout/quote-observer/export.sh --hours 1
```

Expected: `followupPolicy: fast-followup-1`, tracking limit no greater than 12; observer version 0.6.0 and `three-cohort-budgets-v3`. Counters can initially be zero. Existing legacy budget usage can delay quotes. Check the first completed five-minute paths and first admitted Fast30 quote watch before a longer research interval. Record restart count, market revisit ages and coverage displacement; increased delays are grounds to roll back this scheduling experiment.

## Rollback

Run the scanner installer with `--rollback` pointing to the exact source-backup directory printed at installation, then rebuild from the original host directory. It refuses modified sources. Stored evidence is preserved. Run `sudo python3 quote-observer/rollback.py` from the checkout to return to the installed 0.5.0 observer. Its current ledger is preserved rather than overwritten with the safety snapshot.

The quote ledger still needs its own scheduled backup/restore coverage; the installer snapshot is not a replacement for that work.
