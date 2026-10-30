# Projected reverse-message validation — 29 October 2026

The accepted same-simulation collector produces a reverse amount from simulated
post-entry reserves. This increment binds that amount into a separate unsigned
message draft and independently decodes its instruction/account semantics.
It does not simulate or execute the exit.

## Exact scope

The validator repeats the raw post-entry evidence checks. It reverses the source
and destination token accounts, mints and vaults; retains wallet, pool, authority,
configuration and oracle accounts; and uses exactly the acquired quantity and
the recomputed 1% minimum output. Existing inventory is not added to the input.
Projected source sufficiency and destination overflow are checked.

The wire reviewer checks legacy format, exactly one zero signature, fee payer,
account set, writable permissions and exactly three instructions: compute limit,
zero compute price and the expected direct-pool exact-input swap. Amounts,
minimum output, discriminator, program and ordered roles must match. Extra
instructions, changed accounts/permissions, signatures and partial exits fail.

The draft has its own format and cannot pass the existing executable packet
schema. It contains no fee assertion and no claimed expiry. The entry blockhash
is used only as a reference to construct the draft, never as proof of current
exit validity. The draft bytes remain in memory; the public report contains
hashes, accounts and checked amounts, not transaction bytes.

## Integrated observation

`position-book/projected_exit_cli.py` is a separate opt-in command. It runs the
existing single unsigned entry simulation and builds/reviews the draft under the
same wallet lock. The raw simulation and projection identities are retained.
Its final timing and stop checks must pass before the exit binding is published.

The limits remain **20 RPC requests, one unsigned entry simulation, the original
ten-second quote deadline and the 30-second shared transport budget**. No exit
request, retry, new key access, signature, send or journal update is introduced.
The existing post-entry-only and independent paired observers keep their behavior.

Public RPC does not commit a simulated entry. This draft therefore is not a
transaction validated against actual acquired inventory. Exit fees, blockhash
validity, complete funding, exit simulation and execution approval remain false
or unavailable. The source/binary equivalence and oracle-effect limitations also
remain. No economic edge or net profit is inferred from these devnet token units.

## Local validation

The full position/accounting suite passed: **207 tests**. This includes nine new
tests covering wire/account mutations, parent evidence, both orientations,
deadline/stop failures, the bounded fake-RPC collector and CLI output handling.
The portable offline command passed all ten cases. Source hygiene and whitespace
checks passed. The October 30 host reports also passed: ten offline cases and the live
observation in 8.015 seconds, with entry 1,000 → 998 and reverse draft
998 → 997/minimum 988. Public summary bindings were checked; raw RPC replay
remains host-side. Neither test layer establishes exit execution or profitability.

## Kali check

After selecting the published `feature/projected-exit-message-20261029` commit:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_cli="$HOME/apps/solana-radar-dev/position-book/projected_exit_cli.py"
python3 -E -s "$radar_cli" \
  --output "$PWD/radar-projected-exit-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
python3 -E -s "$radar_cli" \
  --simulate-devnet --deployment-observation-20261027 \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-projected-exit-live-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected: `offline-checks-passed` (ten cases), then
`controlled-projected-exit-observation-consistent`. The nested
`projectedExitMessage` should be `projected-reverse-message-consistent`, with
`draftOnly: true`, `exitFeeLamports: null` and execution approval false.

If unavailable, upload the report without resetting journals, widening deadlines
or invoking an execution command. No rebuild or service restart is needed.

## Next gates

The host message gate passed. The [next fee increment](PROJECTED-EXIT-FEE.md)
separately observes the exact exit-message fee and assesses
conditional funding without borrowing the entry fee or claiming a real round
trip. Actual sequential exit evidence requires a supported stateful rehearsal
or an explicitly scoped controlled cycle. Mainnet route validation and strategy
qualification remain independent. The availability study and November 6 review
are unchanged.
