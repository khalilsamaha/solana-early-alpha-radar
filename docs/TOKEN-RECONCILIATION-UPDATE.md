# Token reconciliation update — 18 October 2026

## Verified before this release

The dedicated devnet self-transfer finalized with a 5,000-lamport fee. The follow-up fresh-process recovery report preserved the same signature, slot, transaction hash and fee, with one submission attempt and zero new network requests. Expired plan history was preserved. This satisfies the narrow host terminal-recovery gate. It does not independently re-query finality or prove crash/power-loss behavior on the user's hardware.

## Engineering change

Added a separate offline signed-token receipt auditor. It connects the existing signature verifier and prior-intent balance checks, adds decoded transfer-flow validation, tightens creation/closure accounting and introduces existing-WSOL backing consistency. This helps prevent a future execution ledger from treating an incomplete receipt, unexplained debit, rent movement or failed transaction as a successful swap.

The tool is a validation component, not a new signal or execution service. Scanner frequency, candidate scope, Telegram alerts, quote limits, forward-study registration, Backblaze and the production database are unchanged. There is no new background resource use; the command performs bounded local work when invoked.

Run the pinned checkout commands supplied with the release, then:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/token-reconciliation/cli.py" \
  --output "$PWD/radar-token-reconciliation-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
SH
```

Expected: `token-reconciliation-self-check-1`, twelve cases passed, zero network requests/transactions/production-ledger updates. The cases include successful supported accounting, fee-only failure, missing or contradictory transfers, inconsistent WSOL backing and unavailable receipt. Some cases must intentionally report unknown/mismatch for the self-check to pass. Upload only this public report. No wallet directory, private key, rebuild or service restart is needed.

## Where this puts the project

- Hosting and evidence collection continue; current strategy has not demonstrated a validated edge.
- Controlled devnet native submission and local finalized-state recovery passed host checks.
- Signed token accounting is implemented offline with a host self-check next.
- Remaining execution work includes captured/devnet token evidence, wrap/unwrap and supported router validation, independent spend/position/exit limits, and a separately authorized funded pilot.
- ML/strategy forward validation remains independent. This release does not establish expected profits or a real-money testing date.

See [component contract and limitations](../token-reconciliation/README.md).
