# Fresh controlled quote observation — 27 October 2026

## Evidence accepted before this increment

Kali reported ten hours of scanner uptime, zero restarts, readiness HTTP 200, an
active quote observer and 679 statistics refresh successes with zero failures.
The supplied eight-case quote-binding report was replayed exactly. The supplied
reservation view reported closed controlled cycles, zero held native/token funds,
20,000 cumulative confirmed devnet swap-fee lamports and a 1.823-second local
read. Its report consistency was checked; private host journals were not uploaded.
These checks establish the reported operational checkpoint, not strategy returns.

## What changes

`position-book/fresh_quote_cli.py` is a standalone, explicitly invoked reader.
Under the existing wallet lock and read-only journal context it:

1. Replays existing controlled reservations and requires the two-cycle scope to
   be closed. Independently replays the finalized test-pool setup for account roles.
2. Captures one finalized pool/program batch and checks the pinned deployment.
3. Calculates an exact-input quote for 1,000 atomic units of the controlled test
   token. It deducts accrued vault fees, applies integer trade/creator fees and
   floors curve output. The instruction minimum is the ceiling of 99% of that
   output. This is an observation parameter, not a trade authorization.
4. Builds a fresh **unsigned** message, with zero priority price and the existing
   10,000-lamport total fee cap. It requests an exact-message fee and blockhash.
5. Captures a second combined program/pool/wallet batch, validates the exact
   instruction and fee, and recalculates the quote. Any change to reserves or fee
   parameters is rejected, even if rounded output is unchanged.
6. Replays current local reservations again, requires the same ledger/cycle
   binding, and checks spendable token/native funds while still holding the lock.
   Unknown reservations never become zero. Freshness is checked through completion.

The original quote request must remain within ten seconds. Network calls share
an 18-request maximum and a 30-second request-start budget; each transport timeout
is capped by its remaining budget. There is no retry. These are bounded acceptance
and request-start controls, not a hard process termination guarantee. Slow local
replay or a slow response can still yield an unavailable report. No freshness
limit is relaxed to obtain a passing result.

The public report records the calculation inputs, arithmetic, raw-capture hashes,
pinned-program review, exact-message binding and scoped reservation observation.
It exports no signed wire bytes, private key or raw historical signatures. It is
not an executable packet or an input accepted by a sender.

## Formula reference and limits

The calculation follows Raydium's primary source at commit
[`f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5`](https://github.com/raydium-io/raydium-cp-swap/tree/f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5):
`programs/cp-swap/src/curve/calculator.rs`, `constant_product.rs`, `fees.rs`, and
`states/pool.rs`. Input-side trade plus creator fees use ceiling division, with
the creator share split by floor division; output-side creator fees use ceiling
division after the curve. Protocol/fund fees are shares of the trade fee, not an
additional debit. Disabled creator fees are zero. A zero combined input fee is
refused because the referenced implementation's split denominator is zero.

Pinned deployed bytes are checked independently. This does **not** prove that
those bytes were built from the referenced source. Actual unsigned simulation
and comparison with on-chain effects remain the next engineering gate. The
calculation supports existing standard SPL accounts and the direct controlled
devnet pool only. No Token-2022 transfer extensions, native wrapping, account
creation, aggregator route, mainnet scope or economic dollar return is supported.

The wallet lock only coordinates cooperating processes. Local reservations cover
the existing controlled experiment, not all wallet activity. A consistent report
cannot grant a third cycle, reserve new funds, approve signing or guarantee a fill.

## Kali validation

Fetch the exact development revision supplied in chat into `solana-radar-dev`.
Run as `redeye`, without sudo; no Docker rebuild or service restart is needed.

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_cli="$HOME/apps/solana-radar-dev/position-book/fresh_quote_cli.py"
python3 -E -s "$radar_cli" \
  --output "$PWD/radar-fresh-quote-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
python3 -E -s "$radar_cli" --observe-devnet \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-fresh-quote-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

The offline check expects eleven arithmetic/rejection cases. The live observation
may return `fresh-quote-observation-consistent` or `unavailable` (exit 2). Upload
both public reports, including unavailable results. Do not rerun execution,
clear a STOP marker or edit journals to make this check pass. Success here is a
devnet observation; no transaction, study evaluation or service change occurs.

## Validation and rollout

Tests use integer examples, curve invariants, both fee directions, raw account
fixtures, real collectors over fake HTTP, pinned-deployment drift, changed pools,
balance shortfalls, unknown/changed reservations, request caps, deadlines and
private CLI publication. A disposable two-cycle journal test exercises the real
local readers with no key and compares source bytes before/after the complete
observation. Offline arithmetic tests do not substitute for this host RPC check.

This is the third increment in the agreed batch (declared quote binding, local
reservation integration, fresh quote production). Run full local regression and
one consolidated PR/CI cycle. Keep the frozen study unchanged until October 28
at 17:30 Europe/Amsterdam. Simulation, mainnet validation and a separately agreed
funded pilot remain subsequent gates; profitability is still unproven.
