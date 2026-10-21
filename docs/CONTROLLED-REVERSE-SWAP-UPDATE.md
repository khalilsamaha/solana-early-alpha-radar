# Controlled reverse devnet swap and round-trip receipts — 21 October 2026

## Accepted evidence

The host's forward execution at 09:48 UTC reported finalized success, one send, 1,000 atomic test-token input, 998 atomic output and a 5,000-lamport native fee. The reconstructed message/signature and public receipt arithmetic matched. Its 09:53 UTC recovery reproduced the same terminal evidence with zero requests, signatures or sends. That recovery is local receipt replay, not a second fresh chain observation. Full raw receipt validation is performed on the host because private transaction evidence is not exported.

## This release

`devnet-pool/reverse_cli.py` adds one explicit reverse in a separate immutable `swap-reverse-v1` journal. It derives the entire acquired quantity from the validated original receipt, reverses only the original holder/mint/vault roles, and does not accept user-supplied quantities or destinations. The current controlled test permits entry output between 990 and 1,000 atomic units. It does not support arbitrary-sized positions.

For the accepted host receipt, input is **998 atomic** and minimum output **988 atomic**, calculated as `floor(received × 99 / 100)`. This is a fixed nominal test policy for this equal-seeded-reserve pair, not a current route quote or a 1% bound from an executable market price. Fresh simulation must satisfy it. Actual returned output can differ above the minimum.

The independent Node signer reconstructs and verifies the original Ed25519-signed message and its four-token receipt effects, then independently derives the reverse scope. Execution also re-fetches the finalized original signature/receipt, validates current deployment and accounts, builds a fresh 15-second message, simulates that exact signature, and repeats the pre-send checks. The fee cap remains 10,000 devnet lamports per message with zero priority fee. The existing shared wallet lock, STOP checks, request caps, durable signing attempt and durable one-send boundary remain in force.

Both holder balances and the wallet's native balance must exactly continue from the forward receipt. An unrelated transfer, airdrop or spend therefore blocks this test instead of contaminating its accounting. Vaults may have changed between legs, but each actual receipt must conserve its own token effects. No attempt resets the original simulation or forward journal.

The public round-trip record reports:

- Original token input, acquired quantity, reverse input, returned original quantity and original-token net change, all as integer atomic strings.
- Acquired-token residual, which must be zero for a successfully reconciled reverse.
- Each native transaction fee and their sum in lamports, separately from token amounts.
- Both signatures and exact holder/native continuity.

A finalized failed reverse reports `exit-failed-position-open`: it spends no test tokens, retains the acquired quantity and reconciles the additional fee. Pending or unavailable receipts produce no synthetic round-trip result. Contradictory evidence is quarantined. Terminal status revalidates raw private receipts; it does not merely trust a saved success label.

## Host steps

Use the exact release commit supplied in chat in `~/apps/solana-radar-dev`. No production scanner rebuild is needed. These commands run inside Bash and are safe to paste from a zsh terminal.

First run offline checks and local inspection:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_reverse="$HOME/apps/solana-radar-dev/devnet-pool/reverse_cli.py"
python3 -E -s "$radar_reverse" \
  --output "$PWD/radar-reverse-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
python3 -E -s "$radar_reverse" \
  --action inspect \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-reverse-inspect-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
SH
```

Expected first-time inspection: `reverse-scope-ready`, input `998`, minimum `988`, no network/signing/sending. If an existing reverse journal or STOP is reported, preserve it and use status/recovery for review.

Execute once, only following the expected inspection:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-pool/reverse_cli.py" \
  --action execute --allow-devnet-submit \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-reverse-execution-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
SH
```

Expected success: `finalized-success`, `round-trip-reconciled`, zero acquired-token residual, and one application send. Amount returned is determined by the actual receipt; success does not require a token profit. Unknown or interrupted output is not permission to retry execute, remove files, replace a plan or sign again.

Use this read-only recovery after execution, including on interruption:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-pool/reverse_cli.py" \
  --action recover \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --output "$PWD/radar-reverse-recovery-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
SH
```

Recovery sends and signs nothing. A terminal recovery can complete with zero network requests by replaying local evidence. Upload only the public `.json.gz` reports printed by the CLI; retain private journals locally.

## Verification and next gate

27 new offline cases use disposable unfunded wallets, synthetic RPC and the real packet compiler, restricted signer and receipt validators. They cover exact acquired quantity, independent entry signature checks, changed actual output, oversell rejection, holder/native continuity, successful and failed reverse accounting, missing/corrupt evidence, STOP, drift, crashes on either side of the send boundary, lost acknowledgements, read-only recovery and immutable prior journals. Existing forward submission cases remain regression gates.

Actual host reverse execution is pending. A controlled test-token round trip establishes execution/accounting behavior; it does not establish a profitable strategy or mainnet execution quality. Next, after accepted host reports, integrate verified receipts into the isolated position/budget state machine and exercise reconciliation and stop controls. Production scanner signals, ML gates, observer sampling, backups and money permissions are unchanged.
