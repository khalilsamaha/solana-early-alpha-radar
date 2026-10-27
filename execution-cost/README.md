# Execution cost contract

This standalone module answers a narrow question: **do caller-declared quote
amounts cover explicit cost caps, an additional exit haircut, and a specified
minimum surplus?** It also checks the separate spendable native-fee reserve.
It does not predict a profitable trade or approve signing/submission.

The motivation is practical: a positive returned quote can become negative after
fees, tips, account funding and adverse execution. Unknown costs cannot silently
be zero. No existing research, scanner, quote observer, wallet or frozen-study
code imports this module. The calculator makes no network calls. The optional
evidence bridge below makes bounded public reads only when explicitly invoked;
no new scheduled service is installed.

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
by the scenario runner. Do not feed frozen-study data into exploratory
cost analysis before its agreed review.

## Read-only fee and native balance integration

`evidence.py` connects exact unsigned message envelopes, fresh RPC fee responses
and a raw native account balance to the arithmetic component. It does **not**
validate swap instructions or establish that a message implements its associated
quote. Even a system transfer can have a valid fee envelope: regression tests
explicitly demonstrate why this must never be execution approval.

The optional `evidence_run.py` takes a private plain JSON input (64 KiB maximum):

| Field | Required value |
| --- | --- |
| `format` | `execution-cost-evidence-1` |
| `network` | Explicit `devnet` or `mainnet-beta` |
| `wallet` | Public fee payer address; no key material |
| `scenario` | Original cost packet, but `nativeSpendableLamports` and both `*PriorityIncludedLamports` must be `null` because they are derived |
| `entryTransactionBase64`, `exitTransactionBase64` | Exact unsigned transactions; one all-zero signature, legacy/v0 with no lookups; explicit CU-limit then CU-price instructions |
| `reservations` | `{ "otherNativeLamports": "…", "asOfMs": … }`, or both fields `null` when unknown; this remains a caller assertion |

The reader performs at most five requests, with no retries: genesis, entry fee,
exit fee, wallet account, genesis again. Only fixed public HTTPS RPC endpoints
are allowed; redirects and proxies are disabled. It uses finalized commitment
and nondecreasing `minContextSlot`. Each request has a five-second timeout and
64 KiB response cap. Collection stops starting requests after ten seconds; a
request already in flight can finish later, but an aged capture is refused.
The review checks original request/receipt clocks and never refreshes an old
observation by replaying it. Sequential observations are not an atomic snapshot.
Request-age checks and nondecreasing slots do not prove that the RPC node is
caught up with the chain; they are not independent chain-head freshness evidence.

Fees are obtained for the decoded message bytes, with payer and hashes checked.
Explicit compute instructions determine the included priority fee, rounded up;
the observed total must cover it and remain within the caller's total-fee cap.
The economic calculation continues using the **cap**, not the lower observed
fee, and does not add priority a second time. The wallet must be a nonexecutable,
empty system account. Declared other reservations are subtracted exactly; an
unknown reservation remains unknown. Negative spendable balances are refused.

Quote identities, full reverse quantity and freshness are checked by the original
contract, but their association with message hashes is not semantic route proof.
There is no token-account/USDC principal check, reservation-ledger lock, route-fee
coverage proof, automatic rent discovery, simulation or signer. Devnet captures
report fee evidence only: devnet assets cannot be interpreted as actual USDC
economics. Mainnet reads do not authorize mainnet execution.

Reports retain projected RPC fee/account observations and request/input hashes,
not raw messages, arbitrary provider errors or input wallet/quote objects. Keep
the private input for exact local replay. Provider observations are not independent
cryptographic proof; an uploaded capture alone cannot authenticate its source.
The result separates `feeAndNativeEvidence` from assumption-based `economics`.
CLI success means evidence collection/review succeeded, **not** that economics
passed, a route was validated, or trading was approved.

No host action or restart is needed for this integration. A future route adapter
must construct an independently validated input before an actual live fee review
is useful. Once such an input is available, the explicit read command is:

```bash
python3 -E -s ~/apps/solana-radar-dev/execution-cost/evidence_run.py \
  --input /absolute/path/to/private-evidence-input.json \
  --allow-public-read \
  --output /absolute/path/to/new-fee-evidence.json.gz
```

Do not substitute old completed devnet transactions, change their blockhashes,
or reopen existing journals to make this input. The new module neither creates
messages nor signs or submits them.

RPC and priority-fee semantics were checked against the official Solana docs:
[getFeeForMessage](https://solana.com/docs/rpc/http/getfeeformessage),
[getAccountInfo](https://solana.com/docs/rpc/http/getaccountinfo), and
[fees](https://solana.com/docs/core/fees).

## Remaining integration gate

A future fixed-scope execution adapter must supply independently validated
quote/message semantics, route fee treatment, account funding needs, token
spendability and ledger-backed reservations; bind the input digest to the approved
intent; and recheck fresh evidence and reservations before the durable send
boundary. Mainnet route validation, signing, actual paid-fee measurement and fill
reconciliation are not implemented here. Cost caps and modeled margins are not on-chain loss
limits. The existing completed devnet cycles remain closed.

## Controlled devnet single-leg adapter

The separate [controlled cost observation](../docs/CONTROLLED-COST-READINESS.md)
now connects raw validated direct-pool quote/message/account/simulation evidence
and final local reservation reads to a single-leg funding assessment. It reuses
this module's canonical amount validation, but deliberately does not evaluate
USDC round-trip economics for the controlled devnet token pair. No validated exit
leg is present. This is an explicit standalone command with no scheduler or
scanner integration and no signing/submission authority.
