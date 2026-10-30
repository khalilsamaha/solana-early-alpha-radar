# Ordered atomic rehearsal contract — 30 October 2026

The 18-case host check passed at 06:46 UTC on October 30. This document records
the contract increment; the subsequent [live collector](ATOMIC-LIVE-REHEARSAL.md)
adds explicit parsed-CPI normalization, raw final effects and bounded transport.
Its live host gate remains separate.

## Purpose and scope

The corrected projected-fee host check passed: 11 offline cases, 22 requests,
9.419 seconds within the original deadline, and unchanged closed journal identity.
PR #61 merged that accepted fee work after exact-head CI passed. The clean
GitHub main base is `d9e13ee01319006db220d176083f92dd9e6b943a`. This increment starts the next gate:
an entry and an exit applied in order within one unsigned atomic transaction.

An ordinary independent exit simulation reads chain state that does not contain
the preceding unsigned entry's changes. An atomic message can exercise ordered
state changes without broadcasting a trade. However, it is **one transaction**,
with a shared compute budget and its own fee; it does not reproduce two separately
submitted transactions, a holding interval, market movement or an exposed failed
exit. We retain these as separate engineering gates.

This release builds and independently decodes the message and validates a narrow
ordered token-transfer trace. **It does not collect a live combined simulation.**
No current observer, scanner, quote budget, signer, journal or frozen study changes.

## Implemented

`position-book/atomic_rehearsal.py` accepts the existing internal raw parent
evidence and revalidates it through the post-entry contract. A public success
summary cannot substitute for that raw evidence. It makes a private copied
snapshot and a separate `atomic-roundtrip-rehearsal-1-draft` format, which the
existing executable-message validator rejects.

The draft has exactly four instructions:

1. One shared compute-unit limit, unchanged from the controlled entry scope.
2. Zero priority price.
3. The exact original entry swap, including minimum output and account roles.
4. The reverse swap using exactly the prior simulated acquisition and its
   independently calculated minimum output.

The reverse accounts are re-indexed against the entry account list. Concatenating
the separately compiled reverse instruction would silently select wrong accounts;
the tests explicitly reject that error. One legacy signature slot stays all zero.
The legacy packet must fit 1,232 bytes; current synthetic packets are 650 bytes.
No extra instruction, privilege, fee assertion or account is accepted. The entry
blockhash remains a reference only, with no renewed expiry or submission permit.

The trace checker requires exactly two outer groups (entry index 2, exit index 3)
and exactly two standard SPL `TransferChecked` instructions per group. It verifies
program, source, destination, mint, authority, decimals, depth, order and quantity,
then replays all four amounts against validated original token balances. Unknown
or additional CPI shapes are unavailable; there is no permissive fallback.

The reported entry output must equal the entire reverse input. Pre-existing output
tokens cannot conceal an entry shortfall. The report separates before-entry,
after-entry and after-exit balances, original-token change and acquired-token
residual. These are **trace-derived balances**, not verified final chain accounts.
No native fee or net-profit value is invented from them.

## Validation and limits

Twelve new regression tests exercise both directions, independent wire decoding,
instruction reordering/duplication, wrong account re-indexing, weakened quantities
and minimums, signatures/privileges, fee borrowing, inventory masking, residuals,
unexpected CPI programs/roles/decimals/depth, parent changes, malformed/oversized
evidence, snapshot isolation and private exclusive report output. The portable
self-check contains **18 cases** and makes no network requests. The full
position/accounting suite passed **233 tests**; all 12 new tests also passed after
adding explicit malformed-base58 rejection. Source hygiene and whitespace checks
passed. No actual combined simulation was performed by this release.

Reports keep `simulationVerified`, `exitSimulationVerified`, `feeVerified`,
`liveCollectorVerified`, `roundTripFundingEstablished`, `executionApproved` and
`twoTransactionExecutionVerified` false. Draft wire is not exported. There is no
live-report input CLI and no execution flag. Synthetic trace success is not a live
RPC result, an actual fill or validation of all pool/program behavior.

## Kali self-check

After selecting the published development commit:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/atomic_rehearsal_cli.py" \
  --output "$PWD/radar-atomic-rehearsal-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected `offline-checks-passed`, 18 cases. Upload only that public report. No sudo,
wallet directory, restart or container rebuild is needed.

## Next integration gate

- Arm the exact combined message in a bounded devnet simulation transport; keep
  the original quote deadline, fail closed on timeout and never retry or send.
- Collect compiled inner instructions for both swaps, with bounded response
  fields. If the actual program emits a different shape, retain an unavailable
  result and review the evidence rather than relaxing checks silently.
- Bind the trace to that request/response, reconcile its effects with raw final
  token, pool, config, deployment, oracle and native-account evidence. A trace
  alone is insufficient and cannot authenticate a caller-supplied response.
- Price the exact combined message independently. Never copy the separate entry
  fee, reverse fee or their sum as its actual fee.
- Reread local reservations and preserve stop, cluster and final freshness gates.
  Failures must withhold the complete success result.

Only after that gate should we claim live atomic rehearsal evidence. Separate
transaction execution, failed-exit exposure, complete funding, mainnet routing and
prospective strategy economics remain separate tasks.

References checked October 30: [Solana transaction semantics](https://solana.com/docs/core/transactions)
and [simulation RPC parameters](https://solana.com/docs/rpc/http/simulatetransaction).
