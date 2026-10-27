# Controlled single-leg cost readiness — October 27, 2026

## Accepted preceding checkpoint

The host unsigned simulation at 18:46 UTC reported one successful simulation on
the refreshed observed deployment. Input 1,000 atomic units, calculated and
simulated output 998, minimum 989, and exact-message/simulated fee 5,000 devnet
lamports agreed. It consumed 21,719 compute units and finished its final ledger
read 7.557 seconds after the original quote request. The two closed cycles and
20,000 historical fee lamports remained unchanged; no signature or send occurred.

The offline report exactly replayed all 13 cases. The live summary's hashes,
amounts, price arithmetic, deployment identity and clocks were cross-checked.
Raw live RPC responses were not included in that report, so independent live
response replay was not possible. This is historical, pointwise devnet evidence,
not source/build equivalence, future fill certainty or trading approval.

## This increment

`position-book/cost_cli.py` adds an explicit cost-observation mode to the existing
fresh unsigned simulation pipeline. The default simulation and read-only quote
commands retain their existing behavior. No scanner service is changed.

The assessment receives the bounded, projected raw simulation item internally,
only after the simulation and final cluster check pass. After the final locked
local ledger replay it independently recomputes the raw deployment preflight,
quote/message/account binding, and simulation effect checks. It checks the final
reservation scope and clocks and binds message, quote, capture, simulation,
deployment baseline and local ledger hashes. It never accepts an uploaded public
summary as sufficient raw evidence and has no report-input CLI.

The module loads the existing pure execution-cost contract by its fixed file path
under a distinct module name, avoiding collision with the instruction validator's
`contract.py`. It reuses canonical integer/amount validation. It does not feed
these devnet test tokens into the USDC round-trip calculator.

The result separates:

- **Single-leg evidence:** exact input, output/minimum, network fee, priority
  already included, fee cap, current local reservations and available funding.
- **Economics:** unavailable. There is no validated exit leg, real USDC principal,
  native valuation, exit fee budget or failed-attempt budget. Unknowns remain null.
- **Execution:** unapproved. No signing, send, new cycle, durable spending
  reservation, or wallet-wide coordination is introduced.

Native funding uses the full network fee cap, not merely the lower observed fee.
Priority is not added twice. Embedded pool fees are already reflected in output.
Previously paid historical fees are not new reservations. Zero separate tips and
new rent apply only because the exact validated message has CU-limit, CU-price
and swap instructions, and its simulation shows only the fee's native debit.
They are not assumptions for future routes. An input token unit cannot be directly
compared with a different output token unit to claim profit.

The successful state is `controlled-cost-observation-consistent`, with nested
`costReadiness.state = single-leg-cost-evidence-consistent`. All acceptance
remains within the original ten-second quote window, including the added cost
computation. The final check rejects a result that expires during computation.
There are still at most 20 public devnet requests, one unsigned simulation, no
retries and no increase to byte limits. Raw simulation data stays in memory and
is not added to the public report. It is not a persistent recovery artifact.

The pure cost assessment assumes reservation data came from the locked reader;
its output cannot independently authenticate a caller's ledger. The live observer
provides that read, verifies its head against the earlier reads and checks STOP.
Sequential RPC observations are not an atomic snapshot or protection against
external wallet activity. An old report cannot authorize a future transaction.

## Kali check

Fetch the exact development revision supplied in chat. No sudo, Docker rebuild,
restart, key preparation or funds transfer is required.

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_cli="$HOME/apps/solana-radar-dev/position-book/cost_cli.py"
python3 -E -s "$radar_cli" \
  --output "$PWD/radar-cost-readiness-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
python3 -E -s "$radar_cli" --simulate-devnet \
  --deployment-observation-20261027 \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-cost-readiness-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Upload both reports, including an `unavailable` result (exit 2). Do not repeat an
execution command or modify journals to resolve an observation failure.

## Next boundary

The 18:58 UTC host cost observation passed review on October 27. The offline
13-case report matched exactly; the live report bound 1,000 atomic input to 998
output (minimum 989), a 5,000-lamport simulated fee within the 10,000-lamport cap,
and unchanged closed reservations. The full observation took 7.337 seconds within
the original ten-second window. Report arithmetic, hashes and clock relationships
were checked; the uploaded summary did not include raw simulation responses for
independent replay. No signing or submission occurred.

This simulation/diagnostic/cost batch is now at consolidated regression and PR
review under the agreed local-first workflow. No additional Kali command is
required for documentation consolidation. A later
adapter needs a fresh validated exit leg and total-round-trip funding/cost evidence;
this result does not make either available. No mainnet pilot is enabled.
The frozen study stays unchanged until October 28, 17:30 Europe/Amsterdam.
