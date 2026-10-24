# Reconcile external devnet funding before cycle 2

The October 24 host diagnostic reverified the prior round trip and found the native balance increased from 19,824,059,960 to 39,824,059,960 lamports. Both test-token balances and authorities matched. That +20 devnet SOL is consistent with the reported top-up, but the balance comparison alone did not verify incoming transactions.

This release adds `cycle_cli.py --action prepare-funded`. It verifies external native credits and writes the existing immutable cycle-2 preparation only if those credits explain the entire native difference. The ordinary `prepare` action retains its exact-balance requirement. There is no amount override or journal reset.

## What is verified

- Replay the original entry and exit receipts and current token balances/authorities, as before.
- Read at most 17 recent finalized wallet signatures, requiring the exact prior exit signature as the history anchor. At most 16 intervening credits are supported. Missing history, duplicate signatures, failed transactions and ambiguous same-slot ordering stop preparation.
- Verify each intervening transaction's actual Ed25519 signature and wire message. Support one direct System transfer from an external fee payer to this wallet, optionally accompanied by validated compute-limit/price instructions. Token operations, inner instructions, lookup tables, outgoing payments and other transaction shapes are not accepted.
- Match every transaction's complete native balance changes to its signed transfer and fee. The wallet must not sign or pay fees. Follow wallet balances from the historical closing receipt through every credit in chronological order.
- Refresh all three account balances, repeat signature discovery to detect changed history, and recheck devnet identity. The final wallet balance must match the reconciled credits exactly; both token balances and authorities must still match the close.
- Save bounded raw evidence privately in `controlled-cycle-0002/preparation.json` with its completion seal. Public reports contain credit amounts, signatures and hashes, never signed transaction bytes or private keys. Status and repeat preparation reverify saved evidence without network requests or a second allocation.

At most 27 read-only RPC requests are allowed, with no retry or pagination. One credit normally needs 12 requests. No credit with unchanged balances uses the original seven-request path. Unavailable or unsupported evidence fails before creating the cycle directory. An interruption after directory creation remains incomplete and is never automatically reset.

This relies on a single RPC provider for finalized chain metadata/history and on same-user files. Signature verification authenticates the transaction, not the completeness or honesty of the RPC history. It identifies direct incoming transfers, not the identity of a faucet or beneficial owner. Saved balances describe the preparation snapshot, not present balances.

## Spending remains fixed

External funding is recorded separately from trading performance and spending allocation. It does not erase historical fees, replenish gross input, increase the cycle count or raise the fee allowance. With the supplied historical receipts:

| Item | Value |
| --- | --- |
| Historical controlled swap fees | 10,000 lamports |
| Proposed cycle-2 fee allocation | 20,000 lamports |
| Cumulative fees plus allocation | 30,000 lamports |
| Cumulative gross original-token input | 2,000 atomic units |
| Execution permission | None |

`prepared-not-executable` remains the expected result. The next engineering step is binding this identity and cumulative allocation into the restricted sender and durable reservation flow, followed by a controlled devnet demonstration. This release cannot sign or send, and does not access the wallet private key.

## Host procedure

Fetch and detach at the exact release commit supplied in chat. Run the default offline self-check (45 cases), then `prepare-funded` with the same dedicated wallet and pool. No production rebuild or service restart is needed.

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"

python3 -E -s \
  "$HOME/apps/solana-radar-dev/devnet-pool/cycle_cli.py" \
  --output "$PWD/radar-funding-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"

python3 -E -s \
  "$HOME/apps/solana-radar-dev/devnet-pool/cycle_cli.py" \
  --action prepare-funded \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-funded-cycle-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Upload only the two public reports. If it stops, share the printed bounded reason; preserve journals and do not rerun old execution commands. A subsequent `status` action with the same scope replays the saved preparation. No new wallet funding is requested by these commands.

The scanner, quote observer, backups, entry rules and frozen study are unchanged. The study review remains October 27; engineering success does not establish a profitable strategy or approve real-money testing.

RPC history semantics: [Solana getSignaturesForAddress](https://solana.com/docs/rpc/http/getsignaturesforaddress), [getTransaction](https://solana.com/docs/rpc/http/gettransaction).
