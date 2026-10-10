# VPS deployment and operating guide

Prepared 29 September 2026. The user selected a small VPS. **No server has been provisioned or deployed from this session.** No API credentials or Telegram destination were supplied.

## Recommended starting host

Use an EU Linux VPS with 2 vCPU, 4 GB RAM and 40 GB SSD/NVMe for an initial single-process trial. This is an engineering starting estimate, not a load-test guarantee. Ubuntu 24.04 LTS or a current supported Debian image is suitable when Docker Engine and the Compose plugin are installed.

OVHcloud France's VPS-1 page currently advertises 2 vCores / 4 GB / 40 GB from **€3.81 HT (€4.57 TTC) per month** with a one-day automated backup. “From” pricing is not a final quote: check contract period, renewal, location, IP and checkout conditions. Source: https://www.ovhcloud.com/fr/vps/ (checked 2026-09-29).

Hetzner CX23 has the same headline resource size but its cost-optimized page currently marks it unavailable. Do not plan a deployment around stock that is not offered. Sources: https://www.hetzner.com/cloud/cost-optimized/ and https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/ .

Plan **€10–15/month as a provisional hosting/backup allowance**, not a purchased plan or total data budget. API plans and paid streams are separate. Start month-to-month if available so the trial can be changed or stopped.

## 1. Provision and access

Create the VPS in your own account. Use SSH-key access, OS security updates and a firewall that permits SSH from your administrative IP. Do not expose port 8787 publicly. Install Docker Engine and the Compose plugin using the distribution-specific official instructions: https://docs.docker.com/engine/install/ . This package assumes those prerequisites are present; it does not run an unreviewed root bootstrap script.

Upload/extract this project as `/opt/solana-radar`, owned by your deployment user. Keep the original v0.1 archive separately.

## 2. Configure secrets

```bash
cd /opt/solana-radar
cp .env.example .env
chmod 600 .env
```

Generate a random dashboard token (for example `openssl rand -hex 32`) and put it in `DASHBOARD_TOKEN`. Set keys directly in `.env` or your server secret manager. Do not send private keys, API credentials, a Telegram token or your SSH private key in a project archive or conversation.

| Setting | What to supply | Purpose |
|---|---|---|
| PUMPPORTAL_API_KEY | Your PumpPortal key | Launch and migration discovery |
| JUPITER_API_KEY | Jupiter developer key | Recent/organic discovery and metadata |
| HELIUS_API_KEY | Helius mainnet API key | Authority and account-concentration checks |
| TELEGRAM_BOT_TOKEN | Token for your bot | Notification output |
| TELEGRAM_CHAT_ID | Your private destination chat ID | Notification routing |
| DASHBOARD_TOKEN | Random >=24-character value | Dashboard/API access |

PumpPortal keys can have trading capability in its ecosystem. This app implements no trading endpoint and needs no wallet private key. Keep any provider-linked wallet isolated; there is no need to fund paid trade streams for this release.

Leave `NOTIFICATIONS_ENABLED=false` until the destination and message preview are reviewed. Prefer a private chat/channel you control. Start the bot/chat as required by Telegram before testing. Verify the exact chat ID locally; do not guess a recipient.

## 3. Build and run

```bash
docker compose build
docker compose run --rm radar node scripts/doctor.js
docker compose run --rm radar node scripts/doctor.js --live
docker compose up -d
docker compose ps
docker compose logs --tail=100 radar
```

The image runs as Node's unprivileged user. Root filesystem is read-only; persistent data goes into the named `radar_data` volume. The host port is bound to loopback. Node listens inside the container on all interfaces and refuses startup without a sufficiently long access token.

A failing health check marks the container unhealthy. The restart policy restarts an exited process; it does **not** automatically restart a still-running unhealthy process. Investigate queue/provider failures before adding automatic restart loops.

## 4. Open the dashboard privately

From your computer:

```bash
ssh -L 8787:127.0.0.1:8787 youruser@YOUR_VPS_IP
```

Keep the SSH session open, then visit `http://127.0.0.1:8787`. Enter `DASHBOARD_TOKEN` and click Connect. SSH encrypts the transport. For mobile/public access later, put a maintained HTTPS reverse proxy and suitable access controls in front of this service; never send the bearer token over public plain HTTP.

## 5. Enable and verify notifications

```bash
docker compose exec radar node scripts/notify-test.js
```

This previews only. After reviewing the chat destination, set both flags as desired in `.env`:

```text
NOTIFICATIONS_ENABLED=true
OPERATIONAL_NOTIFICATIONS=true
```

Recreate, because changing `.env` is not applied by a plain container restart:

```bash
docker compose up -d --force-recreate
docker compose exec radar node scripts/notify-test.js --send
```

Confirm receipt on your phone. Then observe an actual paper-signal event and its outbox status. Sent means Telegram accepted the request, not that a person read it. Operational notifications add readiness transitions after startup warmup and a daily digest of lifetime totals. Provider issues and expired/failed sends are visible in the dashboard.

## 6. Monitoring and thresholds

| Check | Target / starting policy | What it detects |
|---|---|---|
| Liveness | `/healthz` responds 200 | HTTP process available |
| Readiness | `/readyz` responds 200 after warmup | Worker loop and recent market response |
| Provider status | Expected keyed providers show success | Individual feed failures |
| Oldest candidate attempt | Investigate >90s for intended fast coverage | Backlog and API bottlenecks |
| Notification queue | Investigate pending growth, failed or expired >0 | Delivery issues |
| Missing/gapped 60m outcomes | Investigate >5% after trial warmup | Measurement quality |
| Disk | Alert below 20% free; daily trend | Snapshot/ledger growth |
| Backups | Successful daily backup; restore verified | Recoverability |

These are proposed operating targets, not demonstrated production SLOs. `/metrics` exposes core counters with bearer authentication; `/api/health` gives more detail. Optional example Prometheus rules are in `deploy/`. Add a monitor from outside the VPS before treating it as unattended. In SSH-only mode, use your monitor's private network access or add an HTTPS route for liveness/readiness only. Do not expose the whole API just to make uptime monitoring convenient.

The scanner cannot message you if the entire VPS is dead. Its internal operations alerts do not replace an independent uptime monitor.

## 7. API budget and capacity

| Provider | Default local request ceiling | Theoretical daily maximum |
|---|---:|---:|
| DEX | 120/min, shared by market/profile requests | 172,800 |
| Jupiter | 30/min | 43,200 |
| Helius | 60/min | 86,400 |

These are local upper bounds, not free-tier entitlements or predicted usage. A mint security refresh uses two Helius requests; provider plans may count methods/credits differently. Metadata caching and activity filtering lower actual usage. Confirm the quota of your own API plan and set budgets accordingly. Pacing honors 429 cooldowns, but sustained demand can still overwhelm coverage capacity.

The 15-second enrichment setting is a **pause after a batch**, not a guaranteed 15-second revisit for every token. At 1,000 candidates and 120 market requests/minute, even the impossible best case with no other work is about 8.3 minutes per full sweep. Track only a manageable cohort during validation. If launch load grows, the next engineering step is batch requests and a deadline-based priority worker, then selective trade streams. Do not merely raise rate limits or buy a larger VPS to fix API-side throughput.

## 8. Backup and restore

Live backup inside the persistent volume, then copy it off-host:

```bash
docker compose exec radar node scripts/backup.js /app/data/backup-2026-09-29.sqlite
docker compose cp radar:/app/data/backup-2026-09-29.sqlite ./backup-2026-09-29.sqlite
```

Use a new filename each day. Copy backups to a separate protected location and maintain a retention schedule. A backup in the same volume alone does not protect against host/volume loss. Server snapshots do not replace a tested application restore.

Restore into a **new data directory or new named volume** while the scanner is stopped. Place the backup there as `radar.sqlite`, set ownership to the container's Node user (UID 1000 in the supplied image), and start one instance using that directory/volume. Do not combine a restored database with WAL/SHM files from a different database. Keep the previous volume intact until the restored dashboard, candidate counts and outcomes have been checked. `PRAGMA integrity_check` should return `ok` before resuming live collection.

## 9. Upgrade / rollback

Back up first, stop the scanner, replace application files, rebuild and restart using the same data volume. Never run two scanners against one database. Preserve the old image/tag and database backup. Rolling back from v0.2 to v0.1 requires the original legacy data backup; v0.1 cannot read the SQLite database. Do not use `docker compose down -v` unless you intentionally want to destroy the named data volume.

## 10. Acceptance before unattended use

Confirm live discovery with the configured keys, no unintended paid trade subscriptions, a received test message, a persisted signal surviving restart, resolved/missing checkpoint behavior, provider outage visibility, off-host backup/restore, and external monitoring. Docker build/run and full keyed integration remain to be executed on the selected VPS.
