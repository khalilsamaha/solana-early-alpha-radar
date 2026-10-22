# Controlled devnet token lifecycle — 18 October 2026

## What passed before this release

The host recorded-token self-check at 20:40 UTC matched all eleven expected cases. Its six-request actual devnet capture replayed exactly: two verified signatures, legacy transaction, slot 512559524, one standard token transfer of ten atomic units, and a 10,000-lamport fee. Both existing token endpoints reconciled. This transaction did not create or close accounts, use wrapped SOL, or establish a swap. Its public capture is now a permanent offline regression fixture.

## New engineering step

The new standalone `devnet-rehearsal/token_lifecycle_cli.py` implements one narrowly specified atomic transaction using the existing dedicated devnet wallet. The original self-transfer signer and its journal are preserved.

The seven instructions are:

1. Create a fresh standard token account with its minimum storage balance plus 1,000 test lamports.
2. Initialize it for the native WSOL mint, owned by the dedicated wallet.
3. Create a second fresh account with its minimum storage balance.
4. Initialize it for the same mint and owner.
5. TransferChecked exactly 1,000 atomic WSOL units from the first account to the second.
6. Close the now-empty source account, refunding the dedicated wallet.
7. Close the destination WSOL account, returning its storage balance and the 1,000 test lamports to the same wallet.

Three local signatures are required: wallet, source account and destination account. The independent Node signer reconstructs the exact message from those local keys and rejects changes to recipients, programs, amount, instruction order or account layout. Funding is capped at 2,500,000 test lamports per account plus the fixed 1,000-lamport transfer. The fee cap is 20,000 test lamports. Maximum upfront balance requirement under these caps is 5,021,000 lamports (0.005021 devnet SOL); only the actual transaction fee remains spent after successful closure. The RPC-quoted rent and fee are checked before signing. No airdrop is requested.

## Host commands

Use the pinned development checkout supplied with this release. The first command below is an offline self-check with ten expected cases and temporary synthetic wallets. The second explicitly authorizes one devnet transaction using the wallet already initialized for this project. It makes bounded public RPC requests, signs locally, simulates with signature verification, and sends only after all preparation checks pass.

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
radar_tool="$HOME/apps/solana-radar-dev/devnet-rehearsal/token_lifecycle_cli.py"

python3 -E -s "$radar_tool" \
  --output "$PWD/radar-token-lifecycle-check-$radar_stamp.json.gz"

python3 -E -s "$radar_tool" \
  --action execute \
  --allow-devnet-token-submit \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --output "$PWD/radar-token-lifecycle-$radar_stamp.json.gz"
SH
```

Upload both public reports. Do not upload `signer.pk8`, `source.pk8`, `destination.pk8`, either SQLite journal, or the wallet directory. Reports contain public intent/signature details, from which the public signed message can be reconstructed; they contain no private keys. No Docker rebuild, installation, service restart or scanner configuration change is needed.

A saved report is not necessarily a passed rehearsal. If the state is pending, unknown, preparation-incomplete, failed or quarantined, preserve everything and upload the report. Do not repeat execute to try a new transaction. Once a plan exists, execute returns its existing state without network calls; no automatic blockhash replacement, reset or retry exists.

For a pending/unknown submitted outcome, or interrupted execution, use read-only recovery:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/devnet-rehearsal/token_lifecycle_cli.py" \
  --action recover \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --output "$PWD/radar-token-lifecycle-recovery-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

`--action status` with the same directory/wallet makes no network calls. The existing `--action stop` command writes the shared persistent STOP marker without waiting for the session lock. It affects both native and token rehearsals; recovery remains allowed. Stop cannot recall an in-flight transaction. There is no automated unstop.

## Durability, limits and evidence

A new private `token-lifecycle-v1` directory is created inside the original dedicated devnet wallet directory. It contains the two temporary account keys, public identity metadata and a separate SQLite journal. The parent session lock prevents concurrent rehearsals; all private files are owned by the invoking user and mode 0600, directories mode 0700. Partial setup is not silently repaired or replaced. Original native self-transfer plans remain intact.

The full intent is committed with SQLite FULL synchronization before the signer runs. Verified signatures are committed before simulation. A single `submission-unknown` boundary is committed before the sole application send call. A crash immediately before transport remains uncertain. Recovery cannot sign, simulate, replace the blockhash or send. Finalized and quarantined states are sticky. The guarantees assume the intact local journal; copying/deleting private state is outside them.

Execution permits at most 30 public RPC calls; recovery at most 12. There are no HTTP retries or provider retry instructions (`maxRetries: 0`). Three bounded observation rounds can pause ten seconds between rounds. Each RPC response is limited to 4 MiB and each call uses a ten-second socket timeout, fixed devnet endpoint, no redirects and no environment proxies. These are request bounds, not a short total-runtime guarantee.

Simulation accepts each closed temporary account as either null or an explicitly zero-lamport, empty, non-executable System account; the report retains which representation was returned. It never treats a missing entire accounts array as closure evidence.

Receipt validation binds the exact signed bytes and finalized status/slot, the quoted capped fee, all six native balance endpoints, absence of persistent token balance rows and zero final lamports in both temporary accounts. Success is checked against the exact seven-instruction contract. Failed atomic execution must be fee-only and cannot claim completed lifecycle operations.

Because accounts are created and closed in one transaction, intermediate token balances are not recorded as pre/post token rows. The report explicitly labels `intermediateTokenBalancesObserved: false`. Instruction quantities are locally specified; execution success and balances are RPC claims. This does not relax the general recorded-token auditor's rejection of unsupported transient accounts. It is not a router/swap, slippage test, proof of sellability, retained-position recovery or a profitability result.

## Next gate

All development execution and failure tests use synthetic transport; no new transaction was sent by the development environment. Actual host lifecycle success and recovery remain to be verified. After that, independent position/exit and spend controls, supported router semantics and strategy forward-validation gates remain. The scanner, research/model protocol, quote budgets, notifications and Backblaze are unchanged.

Primary references:
- https://solana.com/docs/tokens/basics/create-token-account
- https://solana.com/docs/tokens/basics/close-account
- https://solana.com/docs/tokens/basics/sync-native
- https://github.com/solana-program/token/blob/main/interface/src/instruction.rs
- https://solana.com/docs/rpc/http/sendtransaction

Validation: the full local regression suite passed 863 tests (580 Python and 283 Node). The 25 new lifecycle tests cover signer policy, durable boundaries, abrupt process exit, receipt contradictions, missing evidence, stop behavior, private files, original-plan preservation and CLI authorization. A separate new test replays the actual host token capture offline. The lifecycle suite is also rerun after the closed-account snapshot representation check. CI runs the complete suite on the final published source.
