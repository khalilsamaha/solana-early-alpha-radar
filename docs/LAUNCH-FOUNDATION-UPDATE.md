# Launch evidence and quote backup release — 11 October 2026

This implements sequence A of [EDGE-RESEARCH-PLAN.md](EDGE-RESEARCH-PLAN.md). It does not introduce a profitable strategy, creator risk score, paid feed, wallet or trading action.

## Release contents

- First retained PumpPortal creation per mint, captured before candidate admission/eviction in an indexed `launch_registry` table in the existing scanner database. Bounded fields; creator and trader kept distinct; URI hash only; no metadata fetch.
- Local receipt/availability timestamps explicitly separated from unknown on-chain time. Unknown fields stay null; reported numeric fields retain reported units.
- Hard limit of 100,000 rows, maximum 4 KiB per row and 30-day retention. At most 500 expired rows removed per minute while creations arrive. Cap drops, duplicates, rejects and errors appear in `launchRegistry.sinceRestart` in health. These counters reset at restart; the existing health snapshot preserves the latest sampled counters, not a lifetime loss ledger.
- A bounded read-only feature-availability report. It does not analyze returns or claim complete Solana coverage.
- Independent daily quote-ledger backups, restored in an isolated temporary directory and compared across all four tables, including metadata/cursors/registrations. Optional B2 upload, download and verification of both archive and manifest. Restored copies never start the observer.
- The pool/exit evidence from PR #4 is included by the installer, so there is a single scanner rebuild from either known source state.

The scanner stays version 0.2.9; quote observer stays 0.6.0. Entry rules, market polling, quote limits, subscriptions and Telegram settings remain unchanged. The registry adds SQL work per received creation, not per market poll. Extra database bytes are bounded by row count and row size; actual I/O and backup growth must be measured. Existing whole-scanner backups include the new table automatically.

## Prerequisites

Use the exact release commit supplied in the conversation. The installer accepts the known deployed source at `fdf7199e3391f04ae7b179aef46f2236b511ec20`, or that source with the prepared pool/exit update at `c7f2994d7697d6c263273dbe650415f12209eaf1`. It rejects unexpected edits before mutation. No git merge or database replacement is required.

The production root remains `~/apps/solana-early-alpha-radar`. The development checkout remains `~/apps/solana-radar-dev`. Never run Compose from the checkout's nested scanner directory. Preserve the current `.env` and data volume.

## 1. Protect the separate quote ledger

Run from the pinned checkout:

```bash
sudo python3 -E -s ~/apps/solana-radar-dev/operations-tools/install-backup.py
sudo systemctl start solana-radar-quotes-backup.service
sudo cat /var/backups/solana-radar-quotes/last-run.json
systemctl list-timers solana-radar-quotes-backup.timer --all --no-pager
```

Require `success: true`, `localVerified: true` and `cloudVerified: true`. This may take a few minutes depending on ledger size and upload speed. The timer runs at 04:10–04:15 in the host timezone, with missed-run catch-up, 192 MiB service memory cap and a five-minute service timeout. It does not restart the observer.

Transfers use one worker, an 8 MiB B2 chunk and one multipart chunk at a time to limit backup memory. These controls follow the [rclone B2 documentation](https://rclone.org/b2/).

The B2 destination is the existing bucket's dedicated `quote-ledger/` prefix, using `/etc/solana-radar/rclone.conf`. The snapshot has a 512 MiB database size cap, a 45-second SQLite copy deadline and a WAL-growth budget; the entire tool has a four-minute deadline. Exceeding a limit is a visible failure rather than publishing a partial success.

Local retention keeps the 14 newest complete named archives after a successful run. Cloud objects are not deleted by this release: review storage growth and configure retention for this dedicated prefix separately. This new service has a failure exit status, journal and last-run file, but does not yet send an independent external failure notification. Existing scanner backup/monitor units are untouched.

Recheck any named archive without the live observer or network:

```bash
sudo python3 -E -s /usr/local/lib/solana-radar-operations/1.0.0/quote_backup.py \
  --verify /var/backups/solana-radar-quotes/EXACT_ARCHIVE_NAME.sqlite.gz
```

Replace the example archive path with `archive` from last-run.json. This only restores into a temporary folder. For a real disaster recovery, reconcile the scanner source identity and cursor before restarting the observer; copying a ledger onto a different source is not an automatic recovery procedure.

## 2. Apply the combined scanner source update

```bash
python3 ~/apps/solana-radar-dev/deployment/install-launch-foundation.py \
  --project "$HOME/apps/solana-early-alpha-radar" && \
cd ~/apps/solana-early-alpha-radar && \
sudo docker compose up -d --build --force-recreate radar
```

The installer stages and tests the combined scanner, backs up existing changed source and supports rollback. It changes six scanner files (one new). It never copies Compose, secrets or databases. Restarting the scanner can interrupt current short research paths; existing handling keeps interruptions explicit.

## 3. Verify and capture a short audit

```bash
cd ~/apps/solana-early-alpha-radar
node --env-file=.env \
  ~/apps/solana-radar-dev/deployment/verify-launch-foundation.mjs
sudo docker inspect \
  --format 'StartedAt={{.State.StartedAt}} RestartCount={{.RestartCount}} Status={{.State.Status}}' \
  "$(sudo docker compose ps -q radar)"
sudo docker stats --no-stream "$(sudo docker compose ps -q radar)"
bash ~/apps/solana-radar-dev/operations-tools/run-launch-audit.sh --hours 1
```

Require readiness and `launchRegistry.version: launch-registry-1`; the pool-path version must also be `pool-timing-evidence-1`. At least one new creation is needed before launch registration exists. No restart is needed to wait for this. In early audits a zero count is not an error if no creation has arrived yet. Upload the audit JSON and paste the verification and backup status output. Do not upload databases, .env or rclone credentials.

The audit's window is received launches only. Do not expect all features to exist. Its purpose is to decide which features merit an as-of study; it contains no new return claims. Continue the existing evidence report after new five-minute paths complete:

```bash
bash ~/apps/solana-radar-dev/quality-tools/run-evidence.sh --hours 12
```

## Rollback

Use the source-backup directory printed by this release's installer:

```bash
python3 ~/apps/solana-radar-dev/deployment/install-launch-foundation.py \
  --project "$HOME/apps/solana-early-alpha-radar" \
  --rollback /absolute/source-backup/path/printed/by/installer
cd ~/apps/solana-early-alpha-radar
sudo docker compose up -d --build --force-recreate radar
```

The rollback path above is a placeholder. Guards require unchanged post-install source and matching backup hashes. Existing launch data are not deleted. To stop only the new backup schedule: `sudo systemctl disable --now solana-radar-quotes-backup.timer`. A currently running backup may finish; no scanner or quote observer is stopped.

## Next decision

Use availability and resource evidence to choose a small launch-quality study. Do not change momentum thresholds, increase provider budgets or move to real money based on this installation. The consolidated plan specifies the separate feature, validation and execution gates.
