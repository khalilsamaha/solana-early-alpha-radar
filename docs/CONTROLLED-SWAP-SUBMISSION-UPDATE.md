# Controlled devnet swap submission — 21 October 2026

## Evidence accepted

The host report at 04:35 UTC records `signed-simulation-consistent`: 1,000 atomic input, 998 simulated output, 5,000 devnet lamports of fee and 21,405 compute units. There were 14 public RPC requests, one signature and zero sends. The public signature, reconstructed message/wire hashes and controlled scope bindings matched independent replay. The complete raw preflight/simulation evidence remained private, so full account validation was a host-side check.

That journal is retained unchanged. A successful simulation does not establish a fill or strategy profitability.

## New execution boundary

`devnet-pool/swap_submit_cli.py` provides offline self-check, explicit execute, status and read-only recover. It is a standalone host tool; no scanner rebuild, service restart, strategy/model change or production position update is involved.

Execution requires the dedicated devnet wallet, explicit controlled pool and `--allow-devnet-submit`. It replays finalized local setup and the prior successful simulation. It then requires the prior simulation's blockhash to be invalid at finalized commitment and its signature/receipt to be absent from the RPC's historical view. These are RPC observations, not a guarantee that an untrusted provider has complete history. The old signed transaction is never sent by this release.

A separate `swap-execution-v1` directory is created exclusively under the common wallet lock. Once created it is never reused, replaced or cleared, even if preparation fails. The scope remains fixed:

| Setting | Value |
| --- | --- |
| Network | Solana devnet only; fixed public RPC endpoint |
| Pool | Derived from the previously finalized controlled pair |
| Direction | Sorted mint0 to mint1 |
| Input | 1,000 atomic units / 0.001 six-decimal test token |
| Minimum output | 990 atomic units / 0.000990 test token |
| Priority fee | Zero |
| Total transaction fee cap | 10,000 devnet lamports |
| Compute cap | 300,000 units |
| Signatures | At most one new signature in this execution journal |
| Application sends | At most one sendTransaction request; maxRetries=0 |

A fresh canonical message and exact fee are collected. Current pool, holder, vault, mint, oracle and pinned program deployment checks precede signing. The separate Node signer independently derives the controlled accounts and enforces the fixed execution scope. It accepts an explicit allowlisted execution purpose, not an arbitrary journal path. The original simulation mode remains available with its existing interface.

The exact signed wire is simulated with signature verification, no blockhash replacement and exact native/token effects. A second complete preflight requires unchanged account evidence, a context at least as recent as simulation, remaining block-height margin, no already-observed signature, valid deadlines and no STOP marker. The original 15-second packet and 10-second evidence deadlines remain; slow or changing evidence stops the attempt rather than relaxing them.

Before transport, an exclusive fsynced boundary records the expected signature and wire hash. STOP and deadlines are checked again after fsync. A crash there can consume the boundary without sending. The RPC request uses preflight, finalized commitment and no node retry request. A lost or unexpected acknowledgement never causes a resend or switches recovery to an unrecognized signature.

All collectors together are capped at 64 actual HTTP attempts per execute invocation. Recovery is restricted to four read-only RPC methods and at most 12 requests, with up to three observation rounds. Requests may each take up to ten seconds. Neither action retries signing or sending.

## Receipt and recovery

Finalized success requires exact signed bytes, legacy account layout, matching status/receipt slot and error, the exact quoted fee, wallet-only native fee debit, unchanged token-account rent and exactly four standard SPL balance records. Mint, authority, decimals, indexes and amounts are checked; source input and vault input must conserve 1,000 atomic units, and destination output must equal the vault decrease and meet the 990 minimum. Actual output may differ from simulation. A failed transaction must have fee-only native effects and zero token deltas.

The bounded raw receipt fields remain private. Terminal status replays the stored receipt against the signed plan and pre-send evidence and compares the result with the saved summary. Public reports contain signature, hashes, atomic effects, fee and request counts, but no signed wire or private keys. This is RPC receipt reconciliation, not independent validator consensus verification. Account changes after the transaction are outside that receipt's claim.

| State | Meaning / action |
| --- | --- |
| finalized-success | Exact successful swap receipt reconciled; upload the report |
| finalized-failure | Transaction failed, fee-only effects reconciled; upload the report |
| submission-unknown / submission-pending | Delivery/finality not established; use recover |
| expired-outcome-unknown | Validity expired without sufficient receipt evidence; still use recover, never assume zero fill |
| preparation-incomplete | Preserve journal and upload status; no automatic replacement |
| quarantined | Contradictory receipt effects; preserve all evidence for review |

`status` makes no network requests. Recovery makes no requests for a terminal journal and cannot sign, simulate or send. A root `STOP` marker blocks execution but permits observation. Both operations verify the local dedicated wallet identity; they are not keyless filesystem readers. Same-user journal/key tampering and a separate holder broadcasting signed bytes are outside this software boundary.

## Host commands

Fetch the pinned release commit supplied in chat into `~/apps/solana-radar-dev`. Run the default `devnet-pool/swap_submit_cli.py --output ...` offline self-check first. It uses only disposable unfunded wallets and synthetic RPC, including actual local signing and injected crashes. Then execute once with the explicit directory, wallet, pool and submission flag shown in chat. Keep the prior `swap-simulation-v1`, new `swap-execution-v1`, token-pair and pool journals intact.

After interruption or any uncertain result, run `--action recover --directory ... --wallet ... --output ...`. Do not supply a pool or submission flag to recovery. Do not repeat execute to retry, delete state, or rerun pool initialization.

## Next milestone

Review the actual finalized swap receipt, then build a separately bounded reverse swap and round-trip position/fee reconciliation. This release does not authorize mainnet execution or establish that the research strategy has positive returns. Forward strategy qualification remains an independent gate.
