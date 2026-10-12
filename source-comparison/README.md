# Prospective exact-pool source comparison (version 1)

This finite experiment investigates disagreements between original-pool paper prices
and fixed-quantity walletless quote changes. It reads the installed quote observer's
ledger and requests public DEXScreener and GeckoTerminal prices for the exact original
Solana pool. It never changes a paper outcome, chooses a replacement feed, sends a
quote request, signs a transaction, or changes the scanner or Backblaze configuration.

## Why this follows the latest report

The 2026-10-12 11:27:08 UTC joined report contains 735 entries and 33 admitted watches.
Its analysis reproduces exactly with the current joined-report builder. Of those
watches, 31 overlap the preceding 11:11 report and only two are new.
At 30 seconds, eleven large disagreements survive the strict original-pool,
on-time, close-receipt comparison; all eleven have sub-second local processing
pipelines. Eight pairs report cache MISS on both receipts; three report positive
HTTP Age. These are audit results, not evidence of a profitable trading strategy
or proof that either price source is correct. A cache MISS is not proof of fresh
underlying price data.

## Protocol fixed before collection

- Register at the current quote-ledger tail. Ignore all existing watches.
- Take the first new valid watch while idle, regardless of later returns.
  Record busy, invalid, oversized and untimely exclusions. This is a small
  convenience sample, not random or cohort-balanced.
- Observe its buy receipt and 30/60/120-second sell receipts. These offsets belong
  to the quote observer and are relative to its buy response. The zero-offset sell
  is deliberately excluded from this experiment's request budget.
- For each validated quote receipt no older than five seconds, start one price
  request to each provider concurrently. Record request, header and body clocks,
  quote-to-request delay, HTTP Age, Date, cache status and explicit orientation.
  Do not turn HTTP receipt or Date into a provider price timestamp.
- At most three watches, four paired points per watch, 24 public HTTP requests
  per invocation. At least ten seconds between pairs. No delayed request queue,
  retry, credential, redirect, paid endpoint or cache-busting parameter.
- Stop after 30 minutes (an in-flight request has a four-second timeout), three
  completed watches, provider access denial/rate limiting, or source error.
  Missing points remain explicit. No suitable new watch is a valid empty result.
- Open the ledger read-only with short bounded queries; release each query before
  HTTP work. Refuse source/ledger replacement and sequence rewind. A separate
  flock prevents concurrent invocations of the provided runner.

Limits are per invocation, not a new global quota for the scanner or other users
of the same public IP. Do not schedule repeated runs yet. No service is installed.

## What the result can establish

`summary` reports coverage and contemporaneous cross-provider price disagreements.
Each point retains the original quote amounts, token-touching route pools, quote
clocks and each price response. `changeFromBuyPricePct` compares that provider's
sampled buy-time and later prices; `quoteMinusPriceChangePp` compares this change
with the fixed-quantity quoted USDC change. It is not net profit or an executable
return. Missing entry prices produce null comparisons, never a zero return.

Prices arrive *after* quote receipts and can change between them. USD market prices
also differ in basis from USDC route quotes. Fees, liquidity/size effects, route
changes, caches and upstream calculation differences remain possible explanations.
DEX prices require the requested mint to be the pool's base token. Gecko prices
may use explicitly verified base or quote orientation. Neither silently switches
pools. Failure to find the pool is a coverage result, not a failed trade.

GeckoTerminal's public documentation states a one-minute endpoint cache. It is
included for independent provider corroboration; this experiment does not establish
that it is faster or suitable for sub-minute trading. Provider implementations may
share underlying market events and are not statistically independent observations.

## Run on Kali

Use the pinned source commit supplied with the PR. No install, rebuild or scanner
restart is needed. Keep the terminal open until the collector finishes:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/source-comparison/run.sh
```

The runner requests sudo only to read the installed observer configuration and
ledger. HTTP requests contain only the public pool address and an Accept header.
The final private JSON report is owned by your normal user in the project directory.
Upload the path printed at completion. A source error or provider halt is still
published with its actual state and collected evidence. Abrupt host/process death
can prevent final report publication; this is not a persistent service.

## Next decision and project position

Hosting, backups, notifications, paper collection and bounded quote observation
are in place. The current gate is **measurement integrity and route feasibility**,
before strategy qualification or any funded test.

1. Inspect this small capture for exact pool/mint matches, new-pool coverage,
   response delays, cache behaviour and price/quote differences.
2. If coverage/timing cannot support the question, select a different documented
   source or investigate route/size effects. Do not promote a provider by agreement
   alone. Keep unknowns and failures visible.
3. Only after measurement is reliable, evaluate fixed entry/exit rules prospectively
   with costs and failed exits represented. A successful engineering check is not
   a real-money go-ahead.

No new overnight collection gate is required to try this finite engineering check.

## Tests and primary references

```bash
node --test source-comparison/*.test.mjs
bash scripts/check.sh
```

- https://docs.dexscreener.com/api/reference
- https://api.geckoterminal.com/docs/index.html
- https://api.geckoterminal.com/docs/v2/swagger.json

Documentation checked on 2026-10-12. Public Gecko documentation lists approximately
10 calls/minute, while other official pages have described 30. The experiment's
ten-second spacing is conservative for either; any HTTP 429 stops it immediately.
