# Controlled devnet pool initialization — 20 October 2026

## Previous host result reviewed

The two uploaded token-pair reports passed review. The offline report named all 40 expected cases. Public raw account evidence matched two standard SPL mints with 1,000 tokens each, six decimals and no mint/freeze authority. The intent message was reconstructed and the wallet signature independently verified. The report records one send and finalized success at slot 513139810; account inventory is a separate finalized snapshot at slot 513139856. The exported report does not contain the full signed wire, so this review does not independently re-verify all five signatures or query fresh consensus.

Token setup left **4,844,520 devnet lamports**. The last observed remaining pool setup estimate is **180,779,560 lamports** including a 10,000-lamport transaction-fee allowance. A 0.2 devnet SOL faucet request is sufficient under those observations. Fresh rent, fee, deployment and account checks remain mandatory. No purchased SOL is needed.

## This release

Adds `devnet-pool`: repeatable funding inspection, deterministic pool address derivation, an independent restricted Node signer, signed simulation, durable one-send execution, finalized receipt/account reconciliation and read-only recovery. Deposits exactly 500 test tokens per mint and preserves 500 per mint for swap exercises. It has 52 offline regression cases at initial release. No production scanner rebuild is needed.

The creation fee is checked before sending and reconciled afterward. **It is not capped inside Raydium's initialize instruction**, which has no fee-ceiling argument. See the module README for this limitation and the exact verification boundary.

## Host commands

First fetch the release branch and check out the exact commit supplied in the chat. Do not overlay the scanner project or rebuild it.

Run offline checks:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-pool/pool_cli.py" \
  --output "$PWD/radar-pool-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
SH
```

Request **test** SOL once, if not already funded. A returned signature is not itself proof of finalized funding; inspection checks the finalized balance. If the faucet is rate-limited or the request times out, inspect the balance first rather than repeatedly submitting requests.

```bash
curl --silent --show-error --connect-timeout 10 --max-time 30 \
  https://api.devnet.solana.com \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"requestAirdrop","params":["FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr",200000000,{"commitment":"finalized"}]}'
```

Inspect readiness:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-pool/pool_cli.py" \
  --action inspect \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --output "$PWD/radar-pool-inspect-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
SH
```

After `offline-checks-passed` and `funding-ready`, initialize the pool once:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-pool/pool_cli.py" \
  --action execute --allow-devnet-submit \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --output "$PWD/radar-pool-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
SH
```

If execution returns an unknown/pending outcome, use the same command with `--action recover` and **without** `--allow-devnet-submit`, and use a fresh report filename. Do not repeat execute or delete state. `--action status` is a no-RPC alternative. If state is `preparation-incomplete` or `quarantined`, send the public report for review; do not attempt repairs to private files.

Upload the generated public `.json.gz` reports only. Keep the wallet directory private.

## Roadmap position

- Controlled test-token creation: host verified.
- Controlled pool initialization: engineering implemented and offline-tested; actual host execution still pending.
- Tiny controlled swap: next, after verifying pool initialization, fresh state and signed simulation.
- Swap submission/recovery and position reconciliation: still to integrate into the controlled swap workflow.
- Mainnet pilot and strategy/model promotion: separate gates; this release provides no profitability evidence or trading authorization.
