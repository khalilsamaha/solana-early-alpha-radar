# Public chain evidence reader 1

This component reads two public Solana RPC methods and reconciles their reported transaction identity, finality, native balances and token-account balances. It does not construct transactions, access private keys, sign, simulate, send, retry a submission or mutate any ledger. It is separate from `execution-lab` and the production scanner.

By default it runs synthetic offline cases and writes a private report:

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/chain-reader/run.py \
  --output "$PWD/radar-chain-self-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

For an **existing public transaction**, explicit `--network devnet` or `--network mainnet-beta`, `--signature`, `--wallet` (public address) and `--mint` enable two read-only requests. A quote-observer sequence or quote response is not a transaction signature. There is no funded transaction to inspect merely because a quote succeeded. Never supply a seed phrase or private key. The release commands deliberately use the offline mode.

The transport allows only `getSignatureStatuses` (with historical search) and `getTransaction` (finalized, JSON, maximum supported transaction version 0). Each request has a ten-second timeout, four-MiB response cap and no retries, credentials, redirects or environment proxies. Only fixed official public endpoints are accepted. Reports omit instructions, logs, arbitrary provider error text and raw RPC responses. Endpoint responses are trusted RPC evidence, not independently verified proofs.

The reader checks the first signature, slot agreement, explicit finalization, status-error agreement, required wallet signer, version, account-key order including v0 loaded addresses, balance array lengths, integer native amounts, token ownership, mint, decimals and atomic token amounts. Native delta includes rent and transfers; transaction fee is separately identified and assigned to the wallet only when it is the first account. These are transaction balance deltas, not realized P&L or spendable balances.

Missing owner/recording or an account present on only one token-balance side stays unknown. Account creation/closure is not reconstructed by assuming zero. Null history never proves transaction failure, expiry or safe resubmission. Confirmed/processed evidence remains provisional. A successful transaction need not be a swap or match an intended order. A failed transaction can still pay fees.

Before using any such evidence in an execution state machine, implement and independently test expected-intent/instruction checks, native/token account lifecycle handling, mint-program and extension checks, current spendability, trusted RPC/finality policy, blockhash expiry and reconciliation after uncertain submissions. This release does not implement those gates or enable live execution. Its automated tests use synthetic legacy/v0 responses and mock transport; no live RPC observation is claimed.

Reference semantics: [getSignatureStatuses](https://solana.com/docs/rpc/http/getsignaturestatuses), [getTransaction](https://solana.com/docs/rpc/http/gettransaction), [JSON structures](https://solana.com/docs/rpc/json-structures).

The [offline intent lab](../intent-lab/README.md) adds message/balance expectations and a narrow standard SPL account lifecycle evidence path. It requires full original RPC evidence, not this reader's summarized report, and never updates a ledger.
