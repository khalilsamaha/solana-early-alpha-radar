# Same-simulation post-entry collector — 29 October 2026

The host's 19:39 UTC nine-case offline report reproduced exactly. This increment
connects the accepted pure post-entry reviewer to a distinct opt-in live devnet
collector. Local fake-HTTP integration passes; actual host observation is pending.

## Behavior and bounds

The command reads the existing closed controlled-cycle ledger under its wallet
lock, derives the fixed direct-pool entry quote, checks the observed deployment,
builds an unsigned message and verifies current accounts and local reservations.
Its single simulation requests nine accounts: the original eight plus PoolState.

The exact armed request includes wire bytes, zero-signature flags, finalized
commitment, minimum context slot and ordered accounts. It cannot send a
transaction, airdrop, simulate twice, redirect or retry. The ninth account has
the ordinary bounded account size; only the existing program-data position gets
the larger deployment-byte allowance. Provider logs and arbitrary text are
discarded. The original eight-account collector still rejects nine-account data.

The operation keeps the existing limits: **at most 20 public requests, one
unsigned entry simulation, a 30-second shared transport budget and the original
ten-second quote deadline**. A final devnet genesis check, read-only ledger replay,
stop-marker check, pure post-entry review and final clock check are required.
Pool/collection success flags are published only after all checks pass.

The post-entry review checks pool fee counters and immutable bytes, then computes
reverse arithmetic from the same response's vault balances and accrued fees.
It uses the exact acquired quantity. No independent second pool read is relabelled
as post-entry evidence. Full-response and exact-request hashes bind the collector
and reviewer; the original eight-account effect hash remains separately visible.

The observer neither executes an entry nor builds/simulates an exit. Returned
state is hypothetical. Creator-enabled pools are unsupported; epoch is checked
only for non-regression; oracle effects and deployed-source equivalence are not
proved. Funding, fees and simulated prices do not establish economic profitability.

## Kali command

After fetching and selecting the published `feature/post-entry-collector-20261029`
commit, run the following once. No scanner rebuild or service restart is needed.

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/post_entry_live_cli.py" \
  --simulate-devnet --deployment-observation-20261027 \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-post-entry-live-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected success state: `controlled-post-entry-observation-consistent`.
`liveCollectorVerified` and `postEntryObservedInSimulation` should be true;
`exitSimulationVerified`, execution approval, signature count and send count
remain false/zero. The projected output depends on current simulated reserves;
there is no fixed profit or required output value.

If unavailable, upload the public report. Do not reset journals, relax deadlines,
alter the deployment baseline or invoke an execution command. The command has no
signing/submission option. The earlier offline CLI remains offline-only; this
new CLI also defaults to the same nine-case self-check unless explicitly enabled.

## Validation and next gate

Tests cover actual collectors/parsers over fake HTTP, exact one-request binding,
both response contracts, absent/null/extra/oversized/altered pool data, bad fee
counters, wrong cluster, stale simulation and post-review expiry, stop/ledger
changes, missing reservations, sanitized provider errors and exclusive output.
The full position/accounting suite passed **198 tests**, including 11 new
collector integration tests. Source hygiene, whitespace checks and the exact
`python3 -E -s` offline CLI also passed. No scanner or study behavior is modified.

After host acceptance, validate an exact reverse message against the projected
state and its acquired inventory. Public RPC does not make an uncommitted entry
simulation persist for a second simulation: sequential exit proof requires a
separate supported stateful rehearsal or explicitly scoped controlled cycle.
Mainnet, signed execution and a funded pilot remain separate gates. The frozen
availability confirmation and November 6 review are unchanged.
