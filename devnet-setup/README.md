# Devnet setup costs and fresh packet builder

This release closes the manual short-lived packet gap and measures the cost of a controlled test-token pool. It does not yet create that pool or mint its tokens. Scanner, research, quote observer and Backblaze jobs are unchanged.

## Actions

`setup_cli.py --action setup-costs --pool PUBLIC_POOL --wallet PUBLIC_WALLET --output report.json.gz`

Read-only; no wallet directory is accepted. Up to 13 fixed-endpoint public devnet requests: six for the existing pinned program/pool capture and seven for wallet, four rent sizes and cluster checks. The reference pool identifies an existing config to reuse; its tokens are not acquired or minted. The observed creation fee is decoded from that config's raw 236-byte AmmConfig at offset 36. Disabling new pool creation is reported explicitly.

The modeled new setup creates two standard SPL mint accounts and two holder accounts, then an LP mint, two pool vaults, an LP holder, a 637-byte pool account and a 4,075-byte observation account. Each rent amount is read from devnet. The 100,000-lamport transaction-fee reserve is an explicit planning allowance, not a measured fee, maximum spend authorization, or promise the setup will fit. All quantities are integer lamports. No WSOL principal or Token-2022 extensions are modeled. Missing/invalid observations produce no partial cost total. `setupReady` is always false until an actual provisioner and its account/receipt checks exist.

`setup_cli.py --action build-packet --scope prior-scope.json --output packet-report.json.gz`

Read-only, four public requests. Requires an independently chosen `devnet-swap-scope-1` file (schema in `swap-rehearsal`). Produces a canonical legacy message with exactly two compute-budget instructions and one devnet CPMM swap. Uses the supplied compute-unit cap and zero priority price. Preserves accounts, input amount, minimum output and fee caps. Fetches a finalized blockhash and the fee for the exact serialized message, checking context ordering and cluster identity. Final validation uses the existing independent contract decoder and rehearsal hard caps. No scope is selected from a route response. The output wrapper contains the packet under `packet`; it expires within 15 seconds of starting the build and is primarily diagnostic.

`setup_cli.py --action prepare-fresh --scope prior-scope.json --wallet PUBLIC_WALLET --directory PRIVATE_REHEARSAL_DIRECTORY --allow-devnet-sign --output report.json.gz`

Future controlled-wallet simulation action, not the command needed for the current unfunded token inventory. Builds and passes the packet immediately to the existing one-shot rehearsal, which independently recollects current pinned program, pool, account, blockhash and exact fee evidence before signing. Existing plans return status without rebuilding; STOP blocks a new attempt; no state is reset. The simulation itself verifies signatures and requests no blockhash replacement. There is no transaction sender. A blocked or failed existing plan must be investigated, never deleted to force another signature. Missing token accounts cannot be repaired by this command.

## Evidence and scope

The latest supplied inventory (20 October 04:17 UTC) showed 9,980,000 lamports in the dedicated wallet and no supported accounts for either reference-pool mint. The preceding host self-check used disposable keys and synthetic RPC; it was not a live pool swap. These observations motivated the controlled setup work.

Tests include independent wire encoding comparison, exact fee-message binding, malformed/expired/stale/over-cap responses, cluster and context drift, immutable scope, STOP and existing-plan behavior, and the real restricted Node signer with a disposable unfunded wallet and synthetic simulation transport. No public RPC or transaction is used in the suite.

Next implementation: narrowly scoped standard-SPL mint/holder provisioning with durable intent, capped rents/fees, restricted signing and exact receipt reconciliation; then controlled pool initialization and fresh account inventory. The config fee and wallet shortfall must be known first. This is execution infrastructure, not evidence of a profitable strategy.

## Source references

Observed upstream source blobs (layout references, not a binary/source equivalence proof):

- [AmmConfig](https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/states/config.rs), blob `eaa966e7977315c4a5d3361c6b9bde0ce973515e`.
- [Initialize](https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/instructions/initialize.rs), blob `36f4301e186240eeedc1e829edf32b95b8fb2a2e`.
- [ObservationState](https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/states/oracle.rs), blob `6f46cc1cf66b3d80bbef844587b62ed5042d9ca8`.
- [Rent RPC](https://solana.com/docs/rpc/http/getminimumbalanceforrentexemption), [blockhash RPC](https://solana.com/docs/rpc/http/getlatestblockhash), [message-fee RPC](https://solana.com/docs/rpc/http/getfeeformessage).

Run tests from the repository root: `python3 -m unittest discover -s devnet-setup -p 'test_*.py'`.
