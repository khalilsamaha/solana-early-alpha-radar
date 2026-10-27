# Declared quote to instruction and account evidence — 27 October 2026

This development increment binds one declared direct **devnet** CPMM quote to
the existing unsigned instruction policy and raw account capture. It closes a
specific integration gap: independently valid quote, message and account objects
could previously refer to different amounts, accounts or times.

`swap-state/quote_binding.py::review(bundle, now_ms=...)` recomputes the existing
instruction and state validators, checks exact wallet/source/destination/pool/mint
identity, input quantity and minimum output, then checks source-token and native
funding after caller-declared reservations. Priority is already inside the total
network fee cap and is not added twice.

Scope is deliberately the existing controlled devnet program. This is **not** the
mainnet route adapter or a connection to the live scanner. Mainnet, routers,
multiple pools, lookup tables, Token-2022, native wrapping, account creation and
closure remain unsupported. Standard token accounts must already exist and have
the correct mint, owner and initialized/unfrozen state, with no delegate or close
authority. Active mint authorities and existing pool eligibility blockers reject
the bundle. The three allowed instructions cannot debit new-account rent; this
does not mean a future route has zero rent or no other costs.

## Input and timing

The bundle has exactly `format: devnet-quote-state-binding-1`, `quote`, `capture`,
`reservations`, and `maxSlippageBps` (integer 0–9999).

The quote has exactly:

- `network`, `program`, `pool`, `wallet`, `source`, `destination`, `inputMint`, `outputMint`;
- `inAmount`, `outAmount`, `minimumOutAmount`: positive canonical u64 decimal strings;
- `requestedAtMs`, `receivedAtMs`, `contextSlot`: integer clocks and positive slot.

The capture is the existing raw `cpmm-state-capture-1` with `selection: prior-packet`.
A precomputed successful summary cannot replace it. The quote must arrive before
policy issuance, and the policy before capture begins. The original quote request,
capture start and reservation observation must each be at most ten seconds old.
Review also revalidates the original message policy at the current clock. Account
snapshot slot must be at least the quote context slot. Sequential RPC reads are
not atomic, and these checks cannot prove that the RPC node is caught up.

Minimum output must match the instruction exactly and be between
`ceil(outAmount * (10000 - maxSlippageBps) / 10000)` and `outAmount`. Ceiling is
intentional: truncation must not weaken the caller's maximum slippage. Quoted
output is also checked against effective output reserves and destination u64
space. **No AMM price is recomputed and no quoted price is authenticated.**

Reservations have exactly `wallet`, `source`, `inputMint`, `otherTokenAtomic`,
`otherNativeLamports`, and `asOfMs`. They must bind the same accounts and predate
capture. Unknown values produce `unavailable`; they do not become zero. This is
arithmetic against declared other reservations, **not authoritative ledger
integration** or protection from a concurrent spend.

The successful state is `declared-quote-state-consistent`. Hashes bind the original
quote, message, policy, capture and reservation inputs. Signing/execution approval,
quote authenticity, reservation verification, program deployment verification and
simulation flags stay false. There is no economic result or profitability claim.

## Host check and runtime boundary

No installer, scanner rebuild, service restart, wallet access, cloud transfer,
frozen-study evaluation or transaction replay is needed. The optional command
below runs eight deterministic **synthetic** cases on Kali and writes a private
report. It establishes local interpreter/import compatibility, not live chain
correctness or host service health.

```bash
cd ~/apps/solana-early-alpha-radar
umask 077
python3 -E -s \
  ~/apps/solana-radar-dev/swap-state/quote_cli.py \
  --output "$PWD/radar-quote-binding-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Run this only after checking out the development revision supplied in chat. To
review a genuinely fresh public bundle, the CLI additionally accepts `--input`;
it checks the **current** clock and returns exit code 2 for unavailable evidence.
Old completed journal messages must not be rewritten or recycled as fresh input.
No live bundle producer is included in this increment.

## Validation and next integration

Local validation: 25 new binding/CLI tests; all 64 swap-state tests pass. Related
30 instruction-contract, 29 combined-preflight and 67 execution-cost tests also
pass. The normal core test discovery already includes this new suite. This is a
development checkpoint, not a claim of a new full-CI release or host acceptance.

Next: connect a fresh quote producer and authoritative reservation view, then
exercise the combined result through the existing read-only pinned-program and
simulation gates. A separately scoped mainnet route adapter remains necessary
before the mainnet cost module can claim quote/message semantic consistency.
The completed devnet cycles stay closed. The frozen review remains October 28 at
17:30 Europe/Amsterdam, under its original guards.
