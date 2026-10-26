# Execution cost contract

This standalone module answers a narrow question: **do caller-declared quote
amounts cover explicit cost caps, an additional exit haircut, and a specified
minimum surplus?** It also checks the separate spendable native-fee reserve.
It does not predict a profitable trade or approve signing/submission.

The motivation is practical: a positive returned quote can become negative after
fees, tips, account funding and adverse execution. Unknown costs cannot silently
be zero. No existing research, scanner, quote observer, wallet or frozen-study
code imports this module. There are no network calls or new scheduled services.

## Arithmetic and assumptions

Amounts are canonical unsigned decimal **strings**, with no floats or scientific
notation. Each input atomic amount must fit u64. USDC uses six decimal places;
native amounts use nine. Only a USDC → asset → USDC sequence is supported. Sell
input must equal the complete quantity in the buy quote; dust-route checks cannot
stand in for that quantity. Mint identifiers must decode to 32 bytes.

For principal `P`, quoted exit `Q`, haircut `h` in basis points, native reserve
`L`, and upper-bound valuation `V` in USDC atomic units per SOL:

```text
stressed proceeds = floor(Q × (10000 − h) / 10000)
native cost       = ceil(L × V / 1000000000)
modeled surplus   = stressed proceeds − P − native cost − other USDC debit
```

Required quoted exit is the smallest integer output that would cover these
costs and the caller's minimum surplus after the same haircut. A 100% haircut
has no finite break-even quote. Required outputs beyond u64 are explicitly
marked outside the amount domain. Input hashes bind the complete assumptions;
they are not evidence of prospective registration or authentic provider data.

`costs` fields:

| Field | Meaning |
| --- | --- |
| `coverage` | `declared-complete` or `unknown`; completeness is a caller assertion |
| `entryNetworkFeeCapLamports`, `exitNetworkFeeCapLamports` | Total network-fee caps, **including** priority fees |
| `entryPriorityIncludedLamports`, `exitPriorityIncludedLamports` | Included portions, checked against totals and never added again |
| `entryTipCapLamports`, `exitTipCapLamports` | Separate tips not already in network-fee totals |
| `failedAttemptBudgetLamports` | Extra failed-attempt allowance, beyond the two planned legs; not retry permission |
| `rentDebitLamports` | Fully reserved and treated as unrecovered; no speculative refund offset |
| `otherUsdcDebitAtomic` | Additional USDC debit not already embedded in quoted amounts |

Native reserve is the sum of total network fees, separate tips, failed-attempt
allowance and rent. `nativeSpendableLamports` must be supplied **after** other
reservations. The module cannot verify balances or enforce wallet-wide limits.
Native valuation is an explicit upper-bound assumption; it is not fetched or
independently verified. Rent is capital tied up, not necessarily a permanent
expense; charging it here is deliberately conservative until recovery is proven.

Quote outputs are treated as provider-reported amounts with embedded route fees
and price impact already reflected. Those must not be added as separate costs.
This assumption needs independent provider/message validation in any future
adapter. `additionalExitHaircutBps` is additional adverse execution, not measured
slippage or an on-chain minimum output. New sell routes or different bought
quantities require fresh evidence; the calculation does not guarantee an exit.

Quote freshness is measured from request time, so a late response cannot refresh
an old request. Both request and response clocks must be ordered, not in the
future, and the reverse request must follow the buy response. Quote/rate age
policies are bounded to 60 seconds. No default policy is selected for trading.

## Results

| State | Meaning |
| --- | --- |
| `invalid` | Schema, units, quantity, time ordering or amount bounds rejected |
| `unavailable` | Missing/failed/stale quote, unknown cost coverage, value, rate or reserve; no modeled return |
| `modeled-constraints-not-met` | Explicit margin requirement or native reserve is insufficient |
| `modeled-constraints-met` | Arithmetic meets caller assumptions only; execution remains unapproved |

Every result has `executionApproved: false`, `measuredNetProfit: false` and
`inputAuthenticityVerified: false`. No failed quote becomes a zero return, a
loss, or a success. Returned quote amounts alone do not measure total P&L.

## Local use

Run the deterministic regression tests (no host data needed):

```bash
cd ~/apps/solana-radar-dev/execution-cost
python3 -E -s -m unittest discover -p 'test_*.py'
```

Optional demonstration report, with five synthetic scenarios:

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/execution-cost/run.py \
  --output "$PWD/radar-cost-examples-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

The example's 10 USDC size, 200 USDC/SOL valuation and other values are test
fixtures, not prices, recommended fees or approved budgets. They show a positive
modeled margin, rent erasing that margin, missing costs, a missing exit quote and
insufficient native reserve. The report is not a test of production performance.

`--input /absolute/path/scenario.json` accepts a plain JSON packet matching
`examples.fixture()` and uses the current system time. Input is capped at 64 KiB;
symlinks, duplicate keys and nonfinite JSON are refused. Output is exclusively
created at mode 0600; existing files are never replaced. Reports expose amount
calculations and hashes, but not raw input quotes or arbitrary errors. Scenario
CLI exit 2 means constraints are not met, evidence is unavailable or the packet
is invalid; it is not a transaction failure. No production exports are accepted
by an adapter in this release. Do not feed frozen-study data into exploratory
cost analysis before its agreed review.

## Next integration gate

A future fixed-scope execution adapter must supply independently validated
quote/message identities, pre-signing fee evidence, route fee treatment, account
funding needs and spendable balances; bind the input digest to the approved
intent; and recheck fresh evidence and reservations before the durable send
boundary. Current mainnet routes, signing, fee measurements and fill reconciliation
are not implemented here. Cost caps and modeled margins are not on-chain loss
limits. The existing completed devnet cycles remain closed.
