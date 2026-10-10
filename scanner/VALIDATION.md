# Validation record — 29 September 2026

## Environment

Node 24.19.0 on the managed Linux workspace. Zero npm runtime dependencies. Live HTTP fetches in this environment use `NODE_USE_ENV_PROXY=1`; a normal VPS generally does not need this setting. API credentials and Telegram recipient were absent.

## Executed checks

- Original v0.1: 5/5 tests passed; demo reproduced breakout 100, manipulated 0, ordinary 50.
- v0.2: 35/35 automated tests passed in the final regression pass, including native backup integrity, real database reopen and archived-entry rediscovery.
- Syntax: Node checked all source, scripts and test JavaScript before packaging.
- Original benchmark arithmetic reproduced: median detection MC $52,247; 13/18 <=$100k, 16/18 <=$250k, 17/18 <=$300k. Provenance and economic performance were not verified.
- Live doctor: 23 Solana profile rows, exact base-mint market enrichment with a positive price.
- Integrated scanner smoke: 22 candidates collected, 4 successful DEX HTTP calls at observation, readiness true after ~22 seconds, incomplete-security candidate capped at 57, shutdown code 0.
- No actual Telegram message, paid trade subscription or trading action was performed.

## Meaningful regression coverage

Configuration guards; single-authority/extreme-concentration/unknown-security caps; null-value normalization; exact token and pair matching; malformed mint rejection; integer concentration calculation; transaction rollback; unique checkpoint deduplication; corrupt legacy import failure; exclusion of legacy results; price-versus-MC accounting; late/stale/wrong-pair/missing checkpoint behavior; post-horizon peak exclusion; peak-to-trough drawdown; retry persistence; expiration; global Telegram flood cooldown; HTTP-success/API-failure handling; scheduler fairness; stale-market suppression; restart deduplication; continuing paper tracking past candidate-age expiry; deterioration heuristics; HTTP bearer auth, method restriction, readiness and static allowlist/CSP.

## Dashboard QA

Flow intended for browser verification: app loads → authenticate → candidates/provider health render → search/active filter updates → paper checkpoints remain visible.

Browser plugin was not available, so the frontend-testing workflow used the installed Playwright package (1.62.1). No browser executable was installed. The attempted Chromium headless-shell download failed repeatedly with an invalid/truncated ZIP; it could not launch. No rendered screenshot, mobile layout, console-health or DOM interaction pass is claimed.

| Check | Result |
|---|---|
| HTTP root/static delivery | Passed in server integration test |
| API authenticated/unauthenticated behavior | Passed |
| Methods, protected paths and headers | Passed |
| Page identity / meaningful rendered content | Not executed: browser unavailable |
| Framework/runtime overlay and console health | Not executed |
| Screenshot / desktop-mobile visual inspection | Not executed |
| Connect / search / active-filter browser interactions | Not executed |

The UI changes are small plain-JavaScript additions, but browser validation is still a real release gate. On the VPS or development computer, use a working browser/Playwright installation to complete that flow at desktop and phone viewport sizes.

## Remaining integration checks

- Docker build/run, healthcheck, container user/volume permissions and restart behavior: not executed (Docker unavailable here).
- PumpPortal live subscription/reconnect and message schema: documented and implemented, not exercised with a real key.
- Jupiter and Helius live credentials, plan quotas and complete security coverage: not exercised.
- Telegram real recipient, acceptance/receipt, operational digest and outage recovery: no real sends; mocked transport paths tested.
- 72-hour stability, throughput under launch floods, long-running disk growth and real backup/restore on the chosen VPS: pending.
- Predictive performance, creator history, unique buyers, wallets, trades and sell execution: not validated or claimed.
