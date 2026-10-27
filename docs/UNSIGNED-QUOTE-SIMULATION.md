# Unsigned quote simulation — 27 October 2026

## Purpose and accepted input gate

The host fresh-quote report at 04:28 UTC passed the previous observation gate:
1,000 atomic input, 998 calculated output, 989 minimum, exact-message fee 5,000
devnet lamports, unchanged pinned deployment, and closed local reservations.
The full path took 4.904 seconds within the original ten-second quote window.
Those report calculations and internal bindings were checked; raw RPC captures
were not included in the uploaded summary, so independent raw-response replay
was not possible. The report and its quote are now historical, not reusable authority.

This increment builds a new quote and checks one **unsigned** simulation against
it. It is a standalone development command, not a scanner deployment. The earlier
read-only command remains read-only; simulation requires the separate CLI flag.

## Exact boundary

`position-book/simulation_cli.py --simulate-devnet` uses the fixed controlled
wallet/pool, holds the existing cooperating wallet lock, and opens source journals
read-only. It performs the complete prior 18-request fresh quote/account/program/
reservation pipeline before allowing one `simulateTransaction` request and one
final genesis check. There are at most 20 public requests, no retries, no redirects,
and a shared 30-second request-start budget. Acceptance still requires the original
quote to be at most ten seconds old through simulation and final journal replay.
These are request/acceptance bounds, not a hard process termination guarantee.

The simulation uses the exact validated zero-signature legacy message. Options
are fixed: devnet, finalized commitment, base64, `sigVerify=false`,
`replaceRecentBlockhash=false`, and the account batch slot as `minContextSlot`.
The transport compares the entire wire and options to the bound request; changed
flags, accounts, amount, message or repeat simulation are rejected.

A successful comparison requires:

- The simulation's own fee, compute use, full native pre/post arrays, four SPL
  token pre/post balance rows and requested post-account data. Missing data is
  unavailable; earlier account reads cannot replace it.
- Exactly the quoted input debit and calculated output credit, with corresponding
  vault conservation. Output merely exceeding the minimum is insufficient.
- Only the fee payer losing the exact quoted network fee; other native balances
  unchanged; compute use within the instruction cap; no account creation or rent.
- Correct token mint, owner, decimals, program, raw account state and unchanged
  authority/layout fields. Simulation pre-balances must agree with preflight.
  A changed prestate is unavailable, not a fabricated return or automatic reprice.
- Returned config, executable program and full ProgramData rows matching the
  pinned preflight observations. The exact-message quote is rederived from raw
  preflight pool bytes during effect review.
- A final devnet genesis check and unchanged closed-cycle ledger/head after
  simulation, with STOP and clocks checked through completion.

There is no private-key read, signing, `sendTransaction`, spending reservation,
new cycle, source journal write, scanner/observer change, or study evaluation.
Unsigned bytes are not exported. The public result contains safe summaries,
amounts, clocks and hashes; arbitrary provider logs/errors are withheld. A
consistent summary is not accepted as an execution permit by any sender.

## Limits

Simulation is a pointwise comparison against one RPC bank, not a fill or a proof
of profitability, signature validity, source/binary equivalence, or behavior for
all possible inputs. `minContextSlot` is a lower bound, not a guarantee of the
same bank as the preceding account read. The checks reject observed drift; they
do not turn several RPC calls into an atomic snapshot or freeze external wallet
activity. Pool configuration/deployment identity and sampled token effects are
checked, but this is not a complete proof of all program-state side effects.

The scope remains existing standard SPL accounts in the controlled devnet pool.
No mainnet, aggregator, native wrapping, Token-2022 extension or account creation
support is implied. A returned fee is a simulation fee, not a charge incurred.
Source journals cover only the controlled cycles, not all wallet activity.

Primary API references reviewed for this implementation:
[Solana simulateTransaction](https://solana.com/docs/rpc/http/simulatetransaction)
and its linked [Agave v3.1.8 RPC implementation](https://github.com/anza-xyz/agave/blob/v3.1.8/rpc/src/rpc.rs).
They support unsigned simulation, explicit no-blockhash-replacement, optional
own pre/post balance metadata, and requested account data. Provider omissions
remain a failed evidence gate, not a reason to weaken validation.

## Kali commands

Fetch the exact development revision supplied in chat first. Run as `redeye`,
without sudo. No Docker rebuild, restart, wallet reset or funds transfer is needed.

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_cli="$HOME/apps/solana-radar-dev/position-book/simulation_cli.py"
python3 -E -s "$radar_cli" \
  --output "$PWD/radar-unsigned-simulation-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
python3 -E -s "$radar_cli" --simulate-devnet \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-unsigned-simulation-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Upload both public reports. The offline check expects 13 cases. The live state
may be `unsigned-quote-simulation-consistent` or `unavailable` (exit 2, with report).
Do not edit journals, clear STOP, or repeat an execution command in response to
an unavailable observation. The current host simulation is still pending until
its report is reviewed.

## Validation and next gate

Focused local tests cover exact request arming, real collectors over fake HTTP,
missing evidence, unsupported shapes, quote/effect mismatch, prestate changes,
program errors, deployment changes, fees/compute, stale clocks, final cluster,
STOP, changed reservations and private CLI publication. A disposable actual
two-cycle journal integration runs without the signing key and compares every
source file before and after. No public RPC is used in the automated tests.

This is the first increment in a new batch: local tests and a development commit,
with consolidated regression/PR/CI at the batch boundary. Production and the
frozen protocol stay fixed. Review remains October 28 at 17:30 Europe/Amsterdam.
Next: accept host simulation evidence, then connect validated execution evidence
to the cost/readiness contract without opening another cycle or enabling a sender.

## Reviewed deployment refresh — 27 October, 18:38 UTC

The 18:19 UTC host run stopped before simulation because the deployment no longer
matched the October 19 observation. The four-read diagnostic at 18:30 UTC and
complete five-read program observation at 18:38 UTC identify the same new bytes.
The complete report was independently replayed from its raw accounts; its review
matched exactly. The old raw observation also replayed successfully. Payloads
differ within the old allocation, not merely in newly allocated trailing bytes.

The complete observation is bound to capture hash
`8fd7e3437cd2fc4641a5e121267d52138e3e47e656daf7d38f91201c288e6294`,
slot 515785731, deployment slot 515685818, and payload hash
`30a9273dda17d7b3513889af1dab1185d9facc4756a6edf36c42f30ba228d8d1`.
Program address, ProgramData address and upgrade authority are unchanged.
This is a single-provider observation repeated at two times, not independent
consensus, audited behavior, or verified source/build equivalence.

`--deployment-observation-20261027` explicitly selects the new fixed observation
**only together with `--simulate-devnet`**. No arbitrary pin, report, address or
hash can be supplied through the CLI. The original preflight pin remains intact
for every other path, including the default simulation command. Both account
captures, diagnostic summaries and quote preflight reviews use the selected pin;
subsequent drift still stops the run. No module-global pin is overwritten.

Add this flag to the live simulation command above after fetching the supplied
revision. The offline self-check remains unchanged (13 cases). The normal
20-request ceiling, ten-second original quote validity, exact economic/effect
checks, read-only journals and no-sign/no-send boundary all remain in effect.
A fixture with the actual new account allocation size (1,766,685 bytes) passed
through both collectors and the simulation response under existing byte limits.

The next host result must establish compatibility for this one quoted input.
It may still be unavailable if the upgraded program differs in behavior, required
RPC fields are absent, or clocks/state change. Do not clear journals or use an
execution command to resolve such a result. No scanner deployment is required.
