# Solana Early Alpha Radar — detailed inspection and continuation plan

**Review date:** 29 September 2026  
**Inputs:** `solana-early-alpha-radar-chat-handoff(1).md` and `solana-early-alpha-radar-v0.1(1).zip`  
**Deliverable:** v0.2.0 reliability and deployment release  
**Status:** code and local validation completed; VPS provision, Docker execution, full keyed-provider trial and real notification receipt remain pending.

## 1. Overall assessment

The v0.1 is a real, small working prototype with a sensible discovery/enrichment/scoring separation. It is not yet a validated alpha engine. The five original tests all passed, but four concern synthetic scoring and one concerns writing/reading storage. They do not establish network correctness, notification reliability, launch coverage, crash recovery or economic edge.

The right next milestone is a reliable instrument that records what it actually observed. Shipping more signals before fixing stale observations, missed delivery and biased outcomes would make the resulting dataset difficult to trust. This continuation therefore implements reliability and measurement first, plus an initial deterioration warning and a VPS operating package.

The user selected a **small VPS** during this session. No server/account/API secret/Telegram destination was supplied. Nothing has been purchased, publicly hosted, sent to a real Telegram recipient or connected to real trading funds.

## 2. What was inspected

Every non-directory file in the ZIP was read: package/runtime/configuration, all five provider adapters, core scoring/radar/storage, HTTP server, HTML/CSS/JavaScript dashboard, tests, demo/benchmark scripts, fixtures, README and architecture document. The separate handoff was read in full. The original package had no installed npm runtime dependencies and contained no configured API keys or `.env` with credentials.

The handoff preserves the intended research-first approach well. However, several items in the feature summary are broader than the code supports. “Holder adoption” is a threshold on a single holder-count snapshot, not holder-growth measurement. The acceleration metrics compare overlapping 5-minute aggregates, not unique buyers or true individual trade velocity. Creator history has a scoring hook but no data collector. Wallet intelligence, social authenticity, beneficial-owner clustering, calibrated signal probabilities and an Exit Engine were not implemented in v0.1.

The 18-token runner fixture reproduces a median detection market cap of **$52,247**, with **13/18 <=$100k**, **16/18 <=$250k**, **17/18 <=$300k**. That confirms the arithmetic in the handoff, not the provenance of the underlying token observations. Source URLs, observation timestamps and losing/non-runner examples are absent. The PARASITE narrative and 67x timing are inherited context, not independently verified research in this review. No historical return claim is used to validate this scanner.

## 3. Findings and disposition

Severity refers to the impact on a paper-research deployment.

| # | Priority | v0.1 finding | Consequence | v0.2 disposition |
|---|---|---|---|---|
| 1 | Critical | Old market values survived failed DEX fetches while observation time advanced | False freshness, stale alerts and fictitious checkpoints | Failed/mismatched market fetches cannot produce signals or fresh outcomes |
| 2 | Critical | Paper performance used market cap or FDV interchangeably | Supply/methodology changes could look like price returns | New entries use same-pair USD price ratios; FDV remains distinctly labeled |
| 3 | Critical | Any later observation could fill a missed horizon | A price much later than 5m could become the 5m result | 90s default tolerance, actual timestamp/lag, explicit missing checkpoints |
| 4 | High | All-time running maximum included the late checkpoint price | A rally after 60m could count as a within-60m success | Within-window peaks only include samples at/before the deadline |
| 5 | High | Candidate age expiry stopped paper tracking | Signals near age cutoff could lose later outcomes | Open price-v2 entries continue until their checkpoints resolve |
| 6 | High | Top-80 selection always favored high scores | New/low-scored candidates could starve | Fair rotation across new, tracked and revisited cohorts |
| 7 | High | Candidate persistence rewrote/sorted the whole registry on each discovery | Disk amplification and poor ingestion scalability | Indexed SQLite upserts; bounded candidate registry |
| 8 | High | Alert level was advanced before Telegram delivery with no retry | One transient failure permanently lost the notification | Durable outbox, attempts/backoff, expiration and delivery status |
| 9 | High | Alert file, candidate state and delivery state were separate writes | Crash inconsistency, duplicate or lost research state | Transactional candidate/alert/outbox writes and checkpoint deduplication |
| 10 | High | A malformed JSONL line caused the entire reader to return empty | Silent loss in dashboard/statistics | SQLite ledger; strict transactional legacy import that fails visibly |
| 11 | High | Dashboard bound publicly by default and had no authentication | Unintended exposure of research data and activity | Loopback default, bearer-protected API, non-loopback token requirement |
| 12 | High | Dashboard inserted some external values into HTML without escaping | Untrusted provider strings could affect the page | Dynamic provider/token strings escaped; restrictive CSP and static allowlist |
| 13 | High | Jupiter search fell back to the first returned token | A different token's organic/audit data could be attached | Exact mint match required |
| 14 | High | Highest-liquidity DEX pair selected without validating requested base mint | Potential identity/source mismatch | Exact Solana base mint required; retain tracked pair where present |
| 15 | High | Missing security data did not prevent high momentum scores | Unknown risk could look like a qualified strong signal | Incomplete checks cap at 57; fresh security required by default |
| 16 | High | A hard authority cap applied only when both authorities were active | One dangerous authority could coexist with an alert-level score | Either active authority or extreme concentration caps at 55 |
| 17 | Medium | Security enrichment was effectively one-time once fields existed | Holder concentration became outdated indefinitely | Periodic checks with TTL and explicit expired state |
| 18 | Medium | Largest token accounts were called top holders | LPs/burn/treasuries could be mistaken for owners | Clear account-based labels; remove positive low-concentration bonus; real owner analysis remains deferred |
| 19 | Medium | Missing/null metrics could be coerced to zero | Unknown organic/audit data looked measured | Explicit unknown numeric and audit values |
| 20 | Medium | Every request lacked centralized quota coordination | Quota exhaustion and repeated failures under load | Per-provider pacing, HTTP 429 cooldowns, metadata TTLs/activity filter |
| 21 | Medium | One Jupiter feed failure discarded the combined discovery batch | Avoidable loss of available discovery | Feed failures isolated |
| 22 | Medium | No structured readiness/provider/queue/delivery monitoring | A running dashboard could conceal a stalled scanner | Liveness/readiness, provider health, queue age/drops and metrics |
| 23 | Medium | Dashboard-only process loaded candidate state once | Read-only view became stale as scanner wrote updates | Dashboard reloads persisted candidates and worker health |
| 24 | Medium | Shutdown exited after a fixed 50ms | In-flight work might not settle | Loop cancellation, bounded graceful shutdown and storage close |
| 25 | Medium | No database migration, retention, backup, restore or hosting runbook | Difficult recovery and uncontrolled snapshot growth | Native backup/export, 7-day snapshot retention, Docker and deployment guide |
| 26 | Research | Success-only benchmark and completed-only statistics | Selection bias could overstate edge | Legacy exclusion, visible missing/gapped outcomes and explicit denominator limits |
| 27 | Research | No deterioration subsystem existed | No post-signal warning logic | Initial deterministic price/liquidity/sell-pressure warning; not a calibrated exit strategy |
| 28 | Research | No real buyer/wallet/creator history | Cannot support those promised intelligence claims | Explicitly remains a later workstream |

## 4. What changed technically

### Durable state

The runtime target moves from Node 22+ to Node 24.10+ and uses native `node:sqlite`. No npm runtime dependency was introduced. A SQLite WAL database replaces active JSON/JSONL storage. Legacy files are imported once and retained. A malformed import fails visibly; legacy market-cap outcomes remain separate from price-based outcomes.

Signal creation persists the candidate, alert and notification intent in one transaction. First-entry identity persists across candidate eviction/restart. Checkpoints use unique entry/horizon identities. Open tracked entries are protected from eviction, although discovery can still be dropped when the bounded registry cannot accept more candidates. Drops are observable.

### Data qualification

Market data must match the requested token and have a positive price. Security requires a parsed mint with explicit authority state and supply/account data. Unsupported token extensions are conservatively capped rather than declared harmless. Security data expires; old organic metadata is withheld from scoring after its TTL.

A successful response is marked with local fetch time. It is not proof that the upstream quote was just produced. DEX caching and missing venue data remain material limits. The first release still depends on DEX market coverage and may miss the earliest bonding-curve window even when PumpPortal announces a creation promptly.

### Notifications

The queue sends through Telegram only when enabled. It handles API-level `ok:false` as failure, permanent errors, HTTP 429 retry windows and bounded exponential retry. The default 15-minute expiry prevents old “early” signals arriving much later as if current. Alert messages include identity and observation time.

At-least-once delivery is the honest guarantee: Telegram has no transaction with the local database. A crash between acceptance and local acknowledgement can duplicate a message. An accepted message also does not mean the user read it. The application does not currently expose a manual failed-message replay control.

Signal/deterioration alerts, service transitions and a daily lifetime-status digest are implemented. Operating notifications need separate opt-in. No live message was sent during this work; all send-path tests used controlled fixtures.

### Dashboard and monitoring

The UI now displays provider state, candidate queue age, notification pending/failed/expired counts, security freshness, stale candidate labels, search, price checkpoints and score/market-cap cohort summaries. Token/provider fields are escaped. A bearer token is kept only in browser memory. API values are bounded and static files are allowlisted.

HTTP-level routes/authentication/headers were tested. Browser rendering and desktop/mobile interaction remain unverified in this environment because the browser binary was absent and the download returned an invalid/truncated archive. This is an explicit release gate on the VPS; no screenshot evidence is claimed.

## 5. What this release still cannot establish

1. **Profitability:** the weights remain hand-written and uncalibrated. A score of 88 is not an 88% chance of a double.
2. **Sellability or safety:** authority checks do not simulate executable sell transactions or fully inspect every token extension, transfer hook, LP-control mechanism or economic attack.
3. **Beneficial ownership:** largest token accounts are not distinct owners; classifications and multi-account wallet aggregation are absent.
4. **Unique buyers:** transaction counts can include many actions by one participant. Wallet quality, Sybil behavior and trade distribution require richer data.
5. **Exhaustive launch coverage:** source limits, queue capacity, polling and API quotas can drop or delay discovery.
6. **Exact highs/lows:** sampled quote prices miss activity between polls. Pair migration/change can create missing coverage.
7. **Tradable P&L:** fees, latency, slippage, liquidity, MEV, order failures and position sizing are not modeled.
8. **Full uptime monitoring:** internal alerts cannot report a completely dead host; an external monitor must be activated.
9. **Production readiness:** no Docker daemon/server credentials were available for a real container deployment; no paid/keyed integration soak has run.
10. **Complete false-negative analysis:** snapshots are retained for research, but rejected candidates do not yet receive the same long-term outcome labeling as alerts. The next dataset design must include a representative rejected/control cohort.

## 6. Hosting decision

The scanner opens a long-lived socket and runs continuous loops. A small always-on VPS with persistent local disk fits this implementation. Static hosting alone cannot run it. A redesign could split the dashboard onto another platform, but that is not necessary for the first trial.

Start with 2 vCPU, 4 GB RAM and 40 GB storage in Europe. OVHcloud VPS-1 is a practical option to compare at checkout. Its official France page lists these resources from €4.57 TTC/month as of this review; final terms/location/renewal must be checked. Hetzner CX23 is comparable on paper, but the official cost-optimized page currently marks it unavailable. The guide therefore does not assume it can be provisioned.

The prepared Compose service uses an unprivileged user, private host port, persistent volume, restart policy, limited memory, log rotation and liveness check. A local SSH tunnel avoids needing a public domain in the first stage. HTTPS/mobile access is a follow-up once a domain and access policy are selected.

## 7. Capacity is the next important engineering constraint

Default pacing permits at most 120 DEX, 30 Jupiter and 60 Helius requests/minute; actual throughput is lower because requests/metadata work are sequential and networks add delay. These are configuration ceilings, not provider-plan entitlements.

With 1,000 candidates, 120 DEX requests/minute means at least 8.3 minutes for a complete market sweep, even before discovery/metadata overhead. A 15-second loop setting does not change that arithmetic. This is acceptable only as a bounded first research cohort, not the end-state alpha radar. Upgrade to batch market and Jupiter calls, deadline-aware paper checkpoint scheduling, bounded parallel enrichment and candidate admission metrics before attempting broad coverage. DEX/Jupiter batching must still preserve exact mint/source/time semantics.

## 8. Staged continuation

| Stage | Deliverable | Proposed acceptance evidence |
|---|---|---|
| A — Connect and deploy | User-owned EU VPS, actual keys, private dashboard, Telegram, backup, independent monitor | Container boots; all intended providers succeed; test received; restart preserves entries; restore works |
| B — Reliability trial | 72-hour unattended paper collection | No silent worker death; quota/queue metrics reviewed; missing/gapped checkpoint rate understood; delivery failures investigated |
| C — Measurement trial | 2–4 weeks of signals plus rejected/control cohort | At least a few hundred distinct entries as an initial diagnostic sample; report uncertainty and correlated launches, not a promise of statistical sufficiency |
| D — Throughput | Batching, deadline-aware scheduling and load replay | Measured latency percentiles, backpressure, event/drop accounting, provider-budget compliance under replayed launch load |
| E — Selective trades | Candidate-only PumpPortal subscriptions, reconnect replay handling, event idempotency and budget cap | Unique-buyer velocity, sell-size distribution and event coverage validated; spending explicitly bounded |
| F — Wallet intelligence | Point-in-time wallet/deployer history, owner concentration, cluster indicators | Historical features contain no future leakage; outcomes tested chronologically on held-out tokens |
| G — Exit research | Replayable warning/partial-exit policies with simulated friction | Compare to fixed-horizon and simple trailing baselines using realistic missing/liquidity assumptions |

Do not calibrate using only winners. Preserve raw inputs, provider provenance, feature timestamps, code/score version and admission decisions. Report performance by token cohort, time period, market-cap band, score band, provider completeness and sampling quality. Repeated watch/strong alerts for one mint should not be counted as independent experiments. A paper double is not a filled profitable trade.

## 9. Required user-side inputs for the next deployment step

Choose/provision the VPS in your own account and identify its OS, IP and SSH username. Supply access through a secure server/session mechanism, not by pasting a private key. Create provider/API credentials directly on that server. Create a private Telegram destination and configure its exact ID locally. No private trading key or wallet seed is needed.

Once access is available, the next concrete work is running the included build, live doctor, authentication checks, real test notification and backup/restore exercise on that VPS. The first trial should record actual API consumption before choosing paid plans or trade-stream spending.

## 10. Primary references checked

- PumpPortal creation/migration and trade stream interface: https://pumpportal.fun/data-api/real-time/
- PumpPortal fee distinction: https://pumpportal.fun/fees/
- Jupiter Tokens V2 schemas/first-pool recency/exact-mint batching: https://developers.jup.ag/docs/tokens/token-information
- DEX Screener API reference: https://docs.dexscreener.com/api/reference
- Solana largest token accounts: https://solana.com/docs/rpc/http/gettokenlargestaccounts
- Telegram API success/error/retry parameters: https://core.telegram.org/bots/api
- Node native SQLite API: https://nodejs.org/api/sqlite.html
- Docker Compose production: https://docs.docker.com/compose/how-tos/production/
- OVHcloud France VPS resources/pricing: https://www.ovhcloud.com/fr/vps/
- Hetzner cost-optimized availability: https://www.hetzner.com/cloud/cost-optimized/

The release's factual provider descriptions are grounded in these primary documents. The engineering targets, host sizing allowance and roadmap are proposed design choices, not externally validated service guarantees.
