# Simulated post-entry evidence contract — 29 October 2026

Independent entry and reverse observations do not include the effect of entry on
the reverse pool. This increment adds a pure reviewer for a pool account returned
in the **same entry simulation response** as the wallet, token accounts and
vaults. A reverse amount can then be projected from those simulated reserves.

## Implemented boundary

`position-book/post_entry.py` defines a distinct nine-account request contract.
The pool is appended to the existing eight-account response. This does not alter
the existing transport, observer, scanner or paired-cost command. There is no live
collector for this new contract yet, and no report-input interface.

The pure reviewer checks the exact declared request parameters and recomputes the
existing raw entry checks: unsigned message, pinned deployment observation, fee,
pre/post balances, token quantities, reservations and freshness. It then checks:

- Pool owner, 637-byte layout, account lamports and identity.
- Exact protocol/fund counter increments on the input side, with integer floor
  rounding and overflow checks; creator-enabled pools remain unsupported.
- Unchanged pool bytes except those counters and a non-regressing recent epoch.
- Effective reserves from the same response's validated vault amounts minus
  accrued fees, in either token direction.
- The reverse calculation uses exactly the acquired entry quantity, excluding
  any pre-existing destination inventory, within the 1,000-atomic-unit scope.

The full simulation, request, pre/post pool accounts, message, baseline, capture
and projection have separate hashes. Public output contains no raw account data
or transaction bytes. No input evidence is mutated. Rejection publishes no
partial projection and only a fixed diagnostic reason.

The counter transitions follow the already referenced upstream commit
`f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5`:
[swap instruction](https://github.com/raydium-io/raydium-cp-swap/blob/f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5/programs/cp-swap/src/instructions/swap_base_input.rs),
[pool layout and fee updates](https://github.com/raydium-io/raydium-cp-swap/blob/f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5/programs/cp-swap/src/states/pool.rs),
[calculator](https://github.com/raydium-io/raydium-cp-swap/blob/f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5/programs/cp-swap/src/curve/calculator.rs)
and [fee rounding](https://github.com/raydium-io/raydium-cp-swap/blob/f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5/programs/cp-swap/src/curve/fees.rs).
Matching that source does not prove deployed binary equivalence.

## What this does not establish

The pure function cannot authenticate a caller-supplied request/response pair.
The next collector must bind its single response to the exact armed request,
retain the existing read deadline and request cap, sanitize bounded rows and
recheck the closed source ledger. `liveCollectorVerified` stays false here.

A simulation-returned state is hypothetical, not committed chain state. The epoch
has only a monotonicity check. Oracle effects are not reviewed. The projection
does not build an exit message, simulate an exit, value assets in USDC or account
for complete round-trip funding. All execution, signing, mainnet and profit gates
remain false. No current quote or expiry extension is manufactured.

## Validation

Thirteen regression tests cover nonzero fee sharing with hand-calculated results,
both directions, immutable byte/owner/lamport changes, wrong fee splits, request
ordering and types, missing/mixed responses, stale evidence, inherited deployment
and balance guards, existing inventory, unsupported creator-enabled pools, output
exclusivity and a network-disabled self-check. Nine portable offline cases are
available through the CLI. Existing entry, reverse, unsigned simulation, paired
cost and single-leg cost suites passed 53 compatibility tests; with the 13 new
tests, 66 focused regression tests passed. Source hygiene and whitespace checks
also passed. The preceding consolidated base passed 1,830 release tests.

## Kali check

After selecting the published development commit, run:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/post_entry_cli.py" \
  --output "$PWD/radar-post-entry-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected: `offline-checks-passed`, nine cases. This is only a portability check;
it makes no RPC request and does not read the wallet or journals. No rebuild,
service restart, live simulation or additional data-collection wait is needed.
The next increment is the opt-in bounded live collector. The availability study,
its sampling, weights and November 6 review stay unchanged.
