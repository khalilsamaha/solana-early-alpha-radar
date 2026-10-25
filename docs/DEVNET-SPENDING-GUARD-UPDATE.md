# Durable controlled-devnet spending reservations

This release connects a persistent spending guard to the existing controlled swap sender. Previously, the sender checked individual amounts and fees, while the separate position book accounted for completed receipts. Now it reserves the controlled entry principal and a round-trip fee allowance before invoking the signer, and records a durable submission boundary before the send request.

## Scope and policy

- One controlled devnet entry, exactly 1,000 atomic test-token units, followed by at most one receipt-bound reverse.
- Reserve 20,000 native lamports before entry signing: at most 10,000 for each leg. These are different units from the token principal.
- An unresolved entry retains both the principal and fee reservations. An unresolved exit retains the acquired token exposure and exit fee reservation. Timeout, process restart and blockhash expiry do not release them.
- Only replayed, verified finalized receipts settle reservations. A failed transaction charges its verified fee; a failed reverse leaves the position open and consumes the only permitted reverse attempt.
- Mismatched receipt effects quarantine the accounting. A missing or inconsistent required journal prevents further action.
- The guard does not control other software using the wallet, prevent same-user file modification, or enforce an on-chain wallet-wide limit. It has no mainnet path.

The private `controlled.spending.sqlite` file belongs with the existing devnet wallet journals. Keep them together; do not delete, replace, reset or edit them to obtain another attempt. The event chain detects accidental inconsistency but is not an independent attestation against its owner. This release does not add those private files to cloud backups.

## Compatibility

Completed historical swaps remain readable and are explicitly reported as not prospectively budget-enforced. The guard cannot retroactively approve them. A new guarded reverse requires a guarded forward entry. Existing completed swaps must not be replayed.

No scanner rebuild, observer restart, model refit, research threshold change, additional market request, or notification change is required. This branch includes the frozen-forward-study tooling so its collection command remains available.

## Run on Kali

First fetch and check out the exact commit supplied with the release. Then run only the offline check:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/devnet-pool/spending_cli.py" \
  --output "$PWD/radar-spending-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected: `offline-checks-passed`, 19 cases, no existing wallet access, public RPC requests or live transactions. Upload only the named public report. Tests use temporary unfunded keys and synthetic RPC responses, exercising the real restricted signer and sender orchestration. One test kills a child process after the durable budget boundary and then verifies recovery cannot resend.

This check neither starts a new devnet cycle nor authorizes spending. Network verification of the guard is a later milestone requiring a separately prepared, explicit controlled cycle; it must not be obtained by clearing the completed cycle's journals.

## Research and next gates

The frozen study continues unchanged. Run `bash "$HOME/apps/solana-radar-dev/forward-study/collect-review.sh"` for the next planned capture. More elapsed time alone does not pass its label-count, date-coverage and model-quality gates. Do not refit or activate a model based on interim results.

After the host offline check, the next engineering task is to prepare an explicitly identified subsequent controlled cycle while preserving all prior journals and spending history. That needs cumulative-budget and receipt-continuity tests before any new submission instructions. Actual-money testing remains a separate decision: operational correctness and devnet success do not establish a profitable strategy or mainnet execution quality.
