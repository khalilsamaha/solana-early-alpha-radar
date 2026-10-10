# Solana Early Alpha Radar — v0.2.0

A single-server Solana research scanner: discover, enrich, filter, notify, and evaluate paper observations. No trade execution is implemented. **Scores are heuristic rankings, not probabilities or evidence of profit.**

## Start here

- `AUDIT-AND-ROADMAP.md`: detailed inspection of the supplied v0.1, fixes and remaining gaps.
- `DEPLOYMENT.md`: VPS setup, configuration, notification activation, monitoring, backup and restore.
- `ARCHITECTURE.md`: data flow and metric definitions.
- `HANDOFF-v0.2.md`: current state for continuing development.

## Requirements and local run

Node **24.10+** (tested here with 24.19.0). Uses native fetch, WebSocket, HTTP, test runner and SQLite; no npm runtime dependencies. Native SQLite support is tied to Node's runtime version; use the documented Node 24 image and retest before changing major versions.

```bash
cp .env.example .env
# Edit .env locally. Never commit or paste real credentials into chat.
npm test
npm run demo
npm run doctor
npm run doctor -- --live
npm start
```

Dashboard: `http://127.0.0.1:8787`. Environment variables take precedence over `.env` when loaded by Node. With a dashboard token configured, enter it in the Connect control. The browser keeps the token in memory, not localStorage or a URL; refresh requires reconnecting.

Without credentials, DEX profile discovery works, but it is not comprehensive launch discovery. Missing authority/concentration checks cap scores at 57, below the default alert threshold. Add provider keys for a meaningful trial. No private trading key or seed phrase is required.

## Included

- PumpPortal creation/migration discovery; no paid per-trade subscriptions.
- Jupiter recent/organic discovery with exact mint matching and metadata caching.
- DEX pair enrichment with base-mint validation and stable paper-pair selection.
- Helius parsed mint authorities and approximate top-10 token-account concentration.
- Fair queue across new candidates, existing candidates, and open paper entries.
- Per-provider request pacing and HTTP 429 cooldowns; configurable budgets.
- SQLite WAL persistence, transactional alert/outbox/checkpoint updates and legacy import.
- Optional Telegram signal, deterioration, service status and daily summary notifications.
- Retry/backoff, delivery status, expiration and permanent-error handling.
- Price-based 5m/15m/60m paper checkpoints, explicit gaps and missing data.
- Basic deterioration detection, provider health, search, outcome tables, cohort statistics.
- Authenticated API/metrics, liveness/readiness routes, Docker deployment and backup/export commands.

## Notifications

Notifications start **disabled**, including test sending. Configure bot token and destination yourself, then opt in:

```text
NOTIFICATIONS_ENABLED=true
OPERATIONAL_NOTIFICATIONS=true
```

`npm run notify:test` previews a message. `npm run notify:test -- --send` sends one to your configured chat. The application queues signal/deterioration alerts while sending is enabled. Operational opt-in adds service transitions and a daily lifetime-summary digest. Previously recorded alerts are not retroactively enqueued on activation.

Default lifetime is 15 minutes, with up to 8 delivery attempts; expired messages remain counted. Telegram delivery is **at least once**: a crash after remote acceptance but before the local acknowledgement can cause a duplicate. Signal IDs help identify duplicates.

## Storage and migration

`DATA_DIR/radar.sqlite` is authoritative; WAL/SHM sidecars may exist while running. The legacy JSON/JSONL import happens once transactionally. Original files remain intact. Corrupt legacy files stop migration with the filename/line; they do not silently become an empty dataset. Legacy outcomes are labeled and excluded from price-v2 statistics; incomplete legacy paper entries are not resumed as price-v2 entries.

Snapshots expire after 7 days; alerts, outcomes, outbox status and archived paper identity remain. SQLite reuses freed pages; pruning does not automatically shrink the on-disk file. Maintain backups and disk monitoring.

```bash
npm run backup -- /absolute/path/radar-backup.sqlite
npm run --silent export -- outcomes > outcomes.jsonl
npm run --silent export -- alerts > alerts.jsonl
```

Use the native backup command while live. Do not copy just an active `.sqlite` file while ignoring its WAL.

Run **one scanner writer per data directory**. Default mode includes scanner and dashboard. `npm run dashboard` may inspect the same local database and refreshes persisted candidates; it sends nothing. Do not scale Docker replicas against one SQLite volume. Do not put the database on a network share.

## Important evaluation boundaries

- Price ratios are observed quotes, not executable P&L. Fees, slippage, transfer restrictions, liquidation feasibility and MEV are not modeled.
- Horizon returns use the first fresh same-pair observation at/after the target, within the configured 90-second tolerance. Actual observation time and lateness are retained. Later observations cannot fill a missed checkpoint.
- Within-horizon peaks include only samples at/before the deadline. A rally after 60m cannot be reported as a within-60m double.
- Peaks are sampled, not true all-time highs. Poll gaps are flagged.
- Missing outcomes remain visible; an observed-only hit rate can be selection-biased. A second conservative observed-double rate includes missing outcomes in the denominator; it is a lower-bound observation metric, not expected return.
- A fetched DEX response may contain provider-cached or stale market data. Fetch time is not a verified trade timestamp.
- Account concentration is not beneficial-owner concentration. Low concentration earns no extra points. Pool/burn/treasury balances are not yet classified.
- Token extensions are conservatively capped, not fully analyzed.
- Bounded candidate storage can drop launches under load. Monitor queue age and dropped counts; this release does not promise exhaustive or sub-second coverage.

## Validation

See `VALIDATION.md` for the exact executed checks and remaining deployment gates. The supplied historical runner fixture is retained as an unverified, survivor-selected timing illustration; it must not be used as a backtest or as proof of edge.
