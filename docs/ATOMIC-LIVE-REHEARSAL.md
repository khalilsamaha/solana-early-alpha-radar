# Bounded unsigned atomic rehearsal — 30 October 2026

## Accepted evidence and scope

The supplied `radar-atomic-rehearsal-check-20261030T064621Z-1864971.json.gz`
matched all 18 expected portable contract cases. It was synthetic and made no
network requests, signatures or sends. It proves the host can run that contract;
it does not prove a live combined simulation.

This next increment adds an opt-in collector in `position-book/atomic_live_cli.py`.
It is a standalone development tool. No scanner rebuild, observer service update,
new cycle, signing or transaction submission is included. The availability study
continues unchanged: preserve November 1, 3, 5 and 6; review November 6 at 00:05 UTC
/ 01:05 Europe/Amsterdam. No premature outcome evaluation is part of this work.

## What the collector checks

1. Run the existing fixed devnet account/program/quote checks and unsigned entry
   simulation. Keep the ninth returned pool account and the exact acquired amount.
2. Build one separate unsigned legacy message containing compute limit, zero
   priority price, entry swap and reverse swap. The reverse consumes the exact
   simulated acquisition; it does not use the wallet's prior destination inventory.
3. Request a fee for **that combined message**, then simulate those exact bytes
   once with `sigVerify=false`, `replaceRecentBlockhash=false`, finalized commitment,
   a non-regressing minimum slot and inner instructions requested.
4. Reconcile all four token transfers, the token pre/post metadata and returned
   token accounts, native fee debit, both directions' pool fee counters, unchanged
   config/program/deployment, oracle bytes, and the bank's returned Clock sysvar.
5. Check the final cluster and re-read closed local reservations under the existing
   source lock. Revalidate raw parent evidence at the final reservation timestamp.
   Withhold success if any evidence fails or the original deadline has expired.

The limit is **23 requests total**, including two unsigned simulations (entry,
then combined entry+exit). No request is retried. There is a shared 30-second
request-start budget and the stricter **original ten-second quote deadline** still
applies through final validation. A slower response cannot refresh that deadline.
The prior fee observation had only 582 ms remaining; a host timing failure is
possible and must remain an unavailable result, not a partially accepted pass.

## Inner instructions and oracle accounting

The internal trace contract uses compiled `TransferChecked` instructions. Solana
simulation commonly returns parsed inner instructions. The new adapter explicitly
normalizes only standard SPL `transferChecked` with one authority, exact known
accounts, atomic integer quantity and decimals, and stack height 2. It accepts a
fully compiled trace as well; mixed, unknown or extra CPI shapes fail. UI amounts,
provider logs and arbitrary error text are not used or exported.

Oracle replay follows the pinned `raydium-cp-swap` source reference
`f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5`, `states/oracle.rs`, `states/pool.rs`
and `instructions/swap_base_input.rs`. It checks the full 4,075-byte observation
account, Q32 cumulative prices from fee-excluded pre-swap reserves, initialization,
legacy last-update timestamps, the 15-second observation boundary, circular index,
checked multiplication, wrapping accumulation and unchanged padding. Two swaps
in the same simulation bank use one Clock timestamp. The pool's resulting epoch
must equal the returned Clock epoch and cannot regress.

This is reference-model agreement for one observation, **not proof that deployed
program bytes were built from that source**. Missing Clock data or a different
oracle/trace behavior remains unavailable. The collector never silently substitutes
a more permissive model.

## Evidence and limitations

A complete report has `controlled-atomic-rehearsal-observation-consistent`, exact
combined-message hashes, its own matching observed/simulated fee, ordered flow
balances, zero acquired residual, final effect flags, sanitized trace encoding,
reservation identities and completion timing. Wire bytes, keys for signing and
raw arbitrary provider output are not exported. On failure the report retains
stage, bounded diagnostic and request count, withholds `atomicRehearsal`, and
keeps overall simulation/live-collector verification false.

One atomic transaction has one fee and reverts both swaps together if an instruction
fails. It does **not** model two independent submissions, delayed market exposure,
a failed exit after a successful entry, separate blockhash lifetimes or two-trade
funding. `twoTransactionExecutionVerified`, `roundTripFundingEstablished`,
`sourceEquivalenceVerified`, `validForSubmission` and `executionApproved` remain
false. Controlled test-token changes are not a monetary return or profitability
estimate. No real-money pilot is enabled.

## Local validation

The portable self-check has **21 cases**, including both mint directions and both
supported trace encodings. Ten new regression tests exercise the complete fake-HTTP
collection path, exact message fee binding, parser limits and sanitization,
partial/inventory-masked transfers, account drift, independent oracle numeric
cases, transport arming, failure/late-response rejection, final reservation/stop
checks, CLI scope and exclusive private output. The existing 12 atomic contract
tests are also retained. All **243 position/accounting regression tests passed**, as did the targeted
22-test atomic suite, source hygiene and whitespace checks. Live devnet success
is a separate host gate and is not claimed by these tests.

## Host sequence

Fetch and detach the published commit first, using the exact SHA supplied in chat.
Then run these commands once. No sudo, service restart or Docker rebuild is needed.

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_cli="$HOME/apps/solana-radar-dev/position-book/atomic_live_cli.py"

python3 -E -s "$radar_cli" \
  --output "$PWD/radar-atomic-live-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"

python3 -E -s "$radar_cli" \
  --simulate-devnet \
  --deployment-observation-20261027 \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-atomic-live-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Upload both public reports. If the live observation is unavailable, preserve that
report for diagnosis; do not loop retries, widen freshness or change the study.
After an accepted host result, consolidate the batch and continue the separate
transaction funding/failure-state work. Mainnet route validation and explicit
pilot controls remain later gates.

References: [Solana JSON structures](https://solana.com/docs/rpc/json-structures),
[simulation RPC](https://solana.com/docs/rpc/http/simulatetransaction),
[pinned oracle source](https://github.com/raydium-io/raydium-cp-swap/blob/f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5/programs/cp-swap/src/states/oracle.rs),
[pinned pool price source](https://github.com/raydium-io/raydium-cp-swap/blob/f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5/programs/cp-swap/src/states/pool.rs).
