# Recorded token-flow update — 18 October 2026

## Evidence carried forward

The host report at 15:30:42 UTC passed all twelve signed-token reconciliation cases and exactly matched local replay, apart from its capture timestamp. This is synthetic accounting validation. The earlier devnet native self-transfer and terminal recovery remain the actual submitted-transaction milestone.

## What this release adds

A separate public, read-only token transaction capture and replay tool now connects the signed-identity verifier to whole-transaction token-flow accounting. It can select exactly one recent finalized devnet transaction referencing the standard SPL Token program, or capture an explicitly supplied public signature and network. It does not search for a transaction that passes its checks.

The checker verifies every required outer-message signature, matches raw signed bytes against RPC JSON, checks cluster/finality/slot and both RPC encodings, then compares ordered transfers against every recorded token account. It accounts separately for fees, supported account creation funding, supported closure refunds and existing wrapped SOL movements. Failed transactions are checked as fee-only failures; attempted instructions are not treated as executed transfers.

This historical review has no registered prior intent. A consistent result cannot establish what the user intended, whether a router is safe, whether an output meets a trade limit, or whether anything was profitable. That distinction is explicit in every report. The earlier prior-intent auditor remains separate.

## Commands on Kali

Use the pinned development checkout supplied with the release. From there, run:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
radar_capture="$HOME/apps/solana-radar-dev/token-reconciliation/capture_cli.py"

python3 -E -s "$radar_capture" \
  --output "$PWD/radar-recorded-token-check-$radar_stamp.json.gz"

python3 -E -s "$radar_capture" --sample-devnet \
  --output "$PWD/radar-recorded-token-capture-$radar_stamp.json.gz"
SH
```

Upload both public reports. The first runs eleven synthetic cases without network access. Some intentionally return mismatch or unknown; all eleven must match their expected states. The second performs at most six public RPC reads and sends no transaction. It requires neither a wallet nor funding. No production installation, Docker rebuild or service restart is needed.

The live report may say `recorded-token-flows-consistent`, `recorded-failure-fee-only`, `unsupported`, `unknown`, `mismatch` or `invalid-input`. Upload it even when it is unsupported or unavailable; do not repeatedly sample to obtain a pass. CLI completion means a report was saved, not that accounting passed.

To replay a saved report without network access:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/token-reconciliation/capture_cli.py" \
  --input /path/to/radar-recorded-token-capture.json.gz \
  --output "$PWD/radar-recorded-token-replay-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

## Scope and remaining gates

Supported successful accounting is deliberately narrow: standard single-owner SPL Transfer/TransferChecked; System CreateAccount plus InitializeAccount3; empty non-native account closure to a recorded recipient; existing wrapped SOL with consistent implied backing. New accounts and closed accounts retain their absent raw endpoint as null in the summary.

ALT-bearing transactions retain verified signed-message identity but token accounting stays unsupported until historical address resolution is established. Token-2022, mint/burn, delegated/multisig authorities, wrap/unwrap, transient unrecorded accounts and other System operations remain unsupported. Other router programs are not semantically audited. RPC inner instructions, balances and finality remain endpoint claims, not independent consensus proofs.

The development live attempt stopped after one unsuccessful public RPC request; no new actual token capture is claimed. Tests replay public signed synthetic fixtures and keep an existing actual ALT-bearing capture blocked. Host capture is the next concrete evidence gate, followed by targeted support for the observed operation or a controlled devnet token lifecycle rehearsal. Independent spend/position/exit controls and validated strategy performance remain separate requirements before any funded pilot.

Validation: `bash scripts/check.sh` passed 837 tests (554 Python and 283 Node), including 25 new capture/accounting tests and 51 total token-reconciliation tests. These exercise ordered split transfers, lifecycle ordering, contradictory quantities/identities, missing evidence, fee-only failures, WSOL backing, bounded discovery, replay and private output. The suite does not contact RPC or submit transactions.

Scanner, research rules, quote budgets, notifications, backup settings and execution journals are unchanged. There is no new daemon or continuous workload. See the [component contract](../token-reconciliation/README.md).
