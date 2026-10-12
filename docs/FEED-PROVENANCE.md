# Feed timing and backup cap investigation — 12 October 2026

## Why this update

The supplied 12 October joined report contains 876 matched decisions and 34 admitted quote watches. Entry history matches all 876 recorded entry prices, but 15 of 33 paired 30-second observations still have large disagreements despite close local receipts, original-pool routes and timely quotes. This makes transport and application timing the next measurement task. It does not establish a provider defect or a profitable rule.

## What changes

The scanner labels each successful DEX market response with `feed-provenance-1`: request queue/start, headers/body receipt and scanner application clocks; endpoint category; pool and price binding; numeric HTTP Age/Date when supplied; and an allowlisted Cloudflare cache status. Unknown fields remain null. No URL, authorization header, cookie or arbitrary error text is stored.

Each candidate retains one bounded record, with separate counts for repeated price and repeated selected values (price, liquidity, five-minute volume and buy/sell counts). Comparison resets on a pool change, backwards clocks or a gap above 45 seconds. The counts describe observations and never establish price freshness. State may survive a scanner restart when the persisted record is still within the comparison window; the clocks remain explicit.

New baseline, early-activity and Fast30 research entries and observed checkpoints preserve the record that supplied their price. No new event stream or snapshot payload is introduced. Existing historical entries are not backfilled. The joined report exports these records and summarizes available/absent/invalid evidence separately. HTTP Date and Age describe a response; the upstream price timestamp is still unknown.

| Area | Impact |
| --- | --- |
| Monitoring scope | Same Solana candidates, pools and cohorts |
| Request frequency | Same requests, batching, polling and rate limits; no additional provider calls |
| Rules and notifications | Same scoring, admission, paper rules and notification settings |
| Performance | Small fixed metadata/hash work per accepted market observation; extra bytes in candidate state and research entry/checkpoint records. Production overhead must be measured, not assumed zero |
| Reliability | Diagnostic callback failure does not fail the market fetch; installer stages tests and backs up only changed source |
| Visibility | Separates local queue/network/body/application delays from unknown upstream price age |
| Deployment | One scanner rebuild/restart; observer and research timer stay as installed |

## Backblaze cap

Backblaze documents separate cap categories and 75%/100% alerts: [official cap documentation](https://www.backblaze.com/docs/cloud-storage-data-caps-and-alerts). The user reported a 100% daily-cap alert. The cap category, usage, limit and current backup outcome are not yet known. The scanner and separate quote-ledger cloud jobs perform download-based verification, which may contribute to download usage. Storage accumulation and API transaction categories are other possibilities; no cause is confirmed.

Run the new diagnostic before starting any manual cloud backup:

```bash
cd ~/apps/solana-early-alpha-radar
umask 077
radar_backup_report="radar-backup-status-$(date -u +%Y%m%dT%H%M%SZ).json"
sudo python3 -E -s ~/apps/solana-radar-dev/operations-tools/backup-status.py > "$radar_backup_report" &&
printf 'Upload: %s/%s\n' "$PWD" "$radar_backup_report"
```

This reads local status files, systemd result fields and bounded directory sizes. It performs zero cloud requests and does not read rclone credentials or healthcheck URLs. Old successful files keep their dates and must be assessed alongside service results. A service's last result also does not prove the next run will succeed. Supply the exact cap label, current usage and configured limit from the B2 console, hiding account and credential details.

No caps, backup timers, retention, deletion, retries or verification policies are changed in this release. The scanner cloud script is installed on Kali and is not available in this repository; changing it without inspection would be unsafe. After the cap type is established, address the actual cause and retain explicit distinction between uploaded and restored/verified copies. Do not assume a reset solves accumulating storage or that an object visible in the bucket has passed verification.

## Install and verify

Fetch this branch into the development checkout and detach at the published tested commit shown in the accompanying instructions. Do not copy the whole development tree over production.

```bash
python3 ~/apps/solana-radar-dev/deployment/install-feed-provenance.py \
  --project "$HOME/apps/solana-early-alpha-radar" &&
cd ~/apps/solana-early-alpha-radar &&
sudo docker compose up -d --build --force-recreate radar
```

The installer accepts only the known deployed source/dependency hashes or its already-installed state. An unexpected hash stops before changing production; report that output instead of bypassing the guard. It prints the source backup directory. It does not alter `.env`, Compose, database contents, cloud settings or quote-observer source. A short scanner collection interruption occurs during restart.

```bash
cd ~/apps/solana-early-alpha-radar
node --env-file=.env ~/apps/solana-radar-dev/deployment/verify-feed-provenance.mjs
sudo docker compose ps
sudo docker inspect --format 'RestartCount={{.RestartCount}} Status={{.State.Status}}' "$(sudo docker compose ps -q radar)"
sudo docker stats --no-stream "$(sudo docker compose ps -q radar)"
```

Expect `ready: true`, scanner `0.2.9`, and `feedEvidenceVersion: feed-provenance-1`. `withFeedEvidence` can start at zero while observations warm up. New records should have ordered clocks and a nonnegative application delay; unknown cache headers are normal. Rerun after a few minutes if necessary. This verifies deployment, not profitability or price accuracy.

After some new quote watches finish, collect the next report without waiting another day:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/launch-study/run-joined.sh --hours 1
```

Upload the report alongside the backup diagnostic. Older entries in that hour remain `not-recorded`; new observed outcomes may carry timing even for older entries. Pair-level assessment must respect those distinctions and observer sampling policy. No strategy or execution promotion follows from a successful install.

To roll back, use the exact backup directory printed by the installer with `--rollback PATH`, then rebuild the original scanner project. This restores source only; stored diagnostic evidence remains. Rollback refuses to overwrite source edited after installation.

## Decision after capture

Use entry and checkpoint transport records for the discrepant watches to separate queue/application delay from request duration and HTTP cache metadata. If local delay is small while discrepancies persist, upstream market timestamp quality and aggregation remain hypotheses, not solved problems. Any feed replacement or trading rule change should be a separately specified prospective comparison. Keep rate budgets and existing cohort rules fixed during this investigation.
