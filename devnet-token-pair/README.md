# Controlled devnet test-token pair

A separate one-shot provisioner for the existing dedicated devnet wallet. It creates **two new standard SPL mints and two holder accounts in one atomic transaction**. Each mint has six decimals and exactly 1,000,000,000 atomic units (1,000 test tokens), all initially held by the wallet. Freeze authority is absent from initialization; mint authority is revoked after minting. It does not acquire the reference pool's tokens or create a pool.

## Policy and cost

- Fixed public devnet RPC endpoint and before/after genesis checks. No endpoint/network override, credentials, automatic airdrop or mainnet action.
- Exactly 12 instructions: for each token, create mint, InitializeMint2, create holder, InitializeAccount3, MintToChecked, SetAuthority(MintTokens, None).
- Five writable signers (wallet and four newly generated account keys), two readonly programs, legacy transaction, no lookup tables, compute-budget/priority-price instructions, delegates or close-authority changes. Signed wire is 1,012 bytes.
- Fresh rent/fee queries. Per-mint rent cap 2,000,000 lamports; per-holder cap 2,500,000; fee cap 50,000; **combined rent plus the full fee allowance must fit within 6,000,000 lamports (0.006 devnet SOL)**. Neither CLI nor provider can increase these constants.
- The reviewed host costs at 20 October 10:43 UTC imply 5,110,480 lamports of rent plus a 25,000-lamport five-signature fee if the fresh RPC quote agrees. The expected debit would be 5,135,480 and the wallet would retain 4,844,520 lamports. These are estimates, not a submitted transaction or guaranteed fee.
- Rent remains in the created accounts; this tool does not close them or promise refund of mint rent. Test tokens have no established economic value. Pool creation needs additional devnet SOL; the prior full estimate was 185,980,040 lamports against a 9,980,000-lamport wallet.

## Durable boundaries

The existing wallet directory stays private. New state is in `test-token-pair-v1` under that directory. Four account keypairs are generated locally with exclusive writes, owner-only permissions and fsync. Public reports contain their addresses, never private keys or signed transaction bytes.

The Python controller uses the existing wallet session lock. It records immutable intent before invoking a separate Node signer. That signer reconstructs the exact fixed message from the local keys and intent, independently enforces amounts/rents/fee/total/time limits, checks STOP and wallet identity, and records an exclusive durable signing-attempt marker before signing. A partial initialization, interrupted signature or existing plan is never silently replaced.

Simulation verifies signatures, disables blockhash replacement, requires exact native rent/fee deltas, exact token output balances and raw mint/holder account states, including removed mint/freeze authorities. The intent must still be within its 30-second signing/submission window and its blockhash must have sufficient height headroom. A pre-send signature check and durable one-time send boundary precede one `sendTransaction` call with `maxRetries: 0` and preflight enabled. There is no application retry or fresh transaction replacement.

Recovery only observes the recorded signature and account state. It cannot sign or send. A finalized receipt is bound to the exact signed bytes, status, fees, native deltas and token endpoints. Successful setup additionally requires a finalized raw snapshot of both mints and holder accounts. Its slot is retained separately; it is not claimed to be the transaction's historical account snapshot. Missing snapshot evidence remains unverified; contradictions are quarantined. Finalized failure is fee-only. Unknown/expired outcomes never count as success or permission to resend.

At most 32 immutable observation records are kept. Terminal results are preserved. A terminal `status` is a stored as-of result, not a fresh inventory. The local guarantee assumes the owner does not copy/delete/edit private setup state. The local signer is not an OS sandbox or hardware wallet; signed simulation bytes could be submitted by a holder while valid.

## Commands

Default `pair_cli.py --output PUBLIC_REPORT.json.gz` runs 40 offline cases using disposable unfunded wallets and synthetic RPC. No existing wallet or public endpoint is accessed.

Execute requires all of:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-token-pair/pair_cli.py" \
  --action execute --allow-devnet-submit \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --output "$PWD/radar-token-pair-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

This command **spends devnet test SOL** to create the accounts if all checks pass. No real SOL is required. `finalized-success` and `setupPairVerified: true` identify the complete receipt-plus-account result. Upload only the public report.

For unknown/pending state, use the same wallet/directory with `--action recover` and **omit** `--allow-devnet-submit`. `--action status` reads durable local state without RPC. A STOP marker in the parent wallet directory blocks preparation/submission but not recovery. Do not repeat execute to retry and never delete or move state to force another attempt. A preparation failure before submission needs review; recovery reports no boundary rather than inventing a new transaction.

## Validation and source

The suite tests exact instruction bytes/account privileges, real Ed25519 signatures from the separate signer, caps, missing/changed authorities, stale intent/blockhash, simulation failure, STOP, timeout and crash boundaries, duplicate invocation, failed receipts and read-only recovery. All transport is synthetic; host execution is a separate gate.

Authoritative SPL interface reference: [instruction.rs](https://github.com/solana-program/token/blob/main/interface/src/instruction.rs), observed blob `deab7afefd1ffb4de12e4e7eae1e5f1ec222d861`. The fixed encoding uses InitializeMint2 (20), InitializeAccount3 (18), MintToChecked (14) and SetAuthority (6, MintTokens=0, None=0). This source reference is not a deployed-binary equivalence proof.

No scanner, research policy, quote budget, existing signer, production ledger or backup job is modified. Next: separately scoped controlled pool initialization and an actual-wallet swap simulation. Real-money and strategy qualification remain independent.
