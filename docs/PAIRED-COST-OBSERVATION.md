# Independent paired cost observation — 29 October 2026

The host's 18:59 UTC reverse observation passed its intended gate: reference entry
1,000 → 998 atomic units; reverse quote and simulation 998 → 996, minimum 987;
5,000-lamport observed/simulated fee within the 10,000 cap; 7.671 seconds from
original quote request to completion; unchanged closed local ledger; 20 requests,
one simulation, zero signatures/sends. Ten offline cases were reproduced. Public
quote arithmetic, hashes, baseline identity and clocks matched. Raw RPC responses
and private journal replay were not present in the uploaded summary, so those
checks remain host-side evidence, not independently replayed chain proof.

## New scope

`position-book/paired_cost_cli.py` runs the existing raw-validated entry observation
and then the raw-validated reverse observation. Each keeps its original ten-second
freshness limit, at most 20 requests and one unsigned simulation. The combined
operation has a 60-second elapsed/clock window, at most 40 requests and two
simulations, with no retries. If entry evidence fails, the reverse is not attempted.

Raw evidence is handed directly between modules in process after successful local
checks. There is no report-input CLI. The paired evaluator repeats message, fee,
account, simulation and reservation validation at each leg's recorded completion
clock; it never re-dates evidence. Public reports exclude raw RPC account payloads
and unsigned wire bytes. Report summaries cannot replace that handoff.

The pair must have the same fixed entry scope, wallet, pool, closed ledger identity
and reservations. It requires unchanged entry economic inputs across the two pool
observations, increasing evidence slots and chronological observations. Reverse
accounts/mints/vaults must match exactly, and its entire input must equal the
fresh entry's simulated output. A changed pool is not accepted merely because
integer rounding preserves the quoted output.

## Fee scenario, not spending authority

The user must explicitly provide `--failed-exit-attempts 0`, `1` or `2` for a live
observation. The host sequence below models one additional failed exit. This adds
one reverse network-fee cap to the two leg caps. Priority is already included; it
is not added again. No additional failed-entry attempts are modelled. No retry is
authorized and no spending reservation is created.

With both caps at 10,000 lamports and one additional failed exit, the modelled
fee-cap budget is 30,000 lamports. The sum of observed message fees is reported
separately. Known local reservations are already deducted; the calculation uses
the lower of the two independently observed native spendable balances and shows
any shortfall. Historical paid fees are not subtracted again.

Both simulations use existing actual inventory. No entry is executed, and the
reverse pool is not a proven post-entry pool. The two observations are not atomic.
The entry quote may already be expired at the end; this is labelled explicitly,
not made current by report generation. Consequently `currentFundingVerified`,
`roundTripFundingEstablished`, `completeExecutionCostBudget`, and execution
approval remain false. No gross round-trip return, native valuation or net profit
is computed. Missing post-entry transition evidence remains a distinct next gate.

## Kali sequence

After fetching the published development commit:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_cli="$HOME/apps/solana-radar-dev/position-book/paired_cost_cli.py"
python3 -E -s "$radar_cli" \
  --output "$PWD/radar-paired-cost-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
python3 -E -s "$radar_cli" \
  --simulate-devnet --deployment-observation-20261027 \
  --failed-exit-attempts 1 \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-paired-cost-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected states: `offline-checks-passed` (ten cases) and
`independent-paired-cost-observation-consistent`. An `unavailable` report is also
useful: upload it instead of changing caps, resetting journals or retrying
execution. There is no signing/submission flag. Upload only these public reports.

No scanner rebuild, service restart, new cycle, private key access or cloud
transfer is required. The standalone command briefly uses local CPU and network;
it does not change discovery, polling, notifications or sampling rules. The
availability confirmation and November 6 review time remain unchanged.

## Validation and next boundary

Local tests cover real collector integration over fake HTTP, raw-evidence-only
handoff, exact full exit quantity, independently valid but incompatible pool
observations, reservations, fee caps versus observed fees, failure-count bounds,
explicit shortfalls, stale-entry labelling, no-send transport, exclusive private
outputs and early termination. Existing entry, reverse, simulation and single-leg
cost regressions pass: 53 focused tests across the five affected suites, including
12 paired-cost tests, plus the ten-case offline CLI self-check. Source hygiene and
whitespace checks pass. The host paired observation is still pending.

Next: verify the paired host report and consolidate the development batch. Then
implement explicit post-entry pool/state provenance before claiming sequential
entry/exit readiness. Mainnet route validation, independently qualified strategy
results and a separately scoped funded pilot remain separate gates.
