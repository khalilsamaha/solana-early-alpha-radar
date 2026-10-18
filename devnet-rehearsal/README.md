# Dedicated devnet preparation — release 1

This standalone tool creates a new local Ed25519 wallet, records an intent before signing, and can request a signed devnet simulation. There is no broadcaster, faucet, wallet import, mainnet option, token swap or production-ledger integration.

The default action is a nine-case **offline** self-check. It creates temporary keys and journals, uses synthetic RPC responses, and removes those files on completion. Passing this check is not a live devnet simulation result.

## First host check

Use the pinned release checkout given in the chat. From the production project's directory, run without sudo:

```bash
python3 -E -s ~/apps/solana-radar-dev/devnet-rehearsal/rehearsal_cli.py \
  --output "$PWD/radar-devnet-self-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"

python3 -E -s ~/apps/solana-radar-dev/devnet-rehearsal/rehearsal_cli.py \
  --action initialize \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --output "$PWD/radar-devnet-wallet-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Upload only these two public reports. Keep `signer.pk8`, `rehearsal.sqlite`, and the wallet directory private. The wallet report contains its public address, not a seed or private key. Neither command makes network requests. No Docker rebuild or service restart is needed. Nothing is added to scanner backups or timers.

Initialization refuses an existing directory, including an incomplete prior initialization. If interrupted, inspect rather than delete or recreate:

```bash
python3 -E -s ~/apps/solana-radar-dev/devnet-rehearsal/rehearsal_cli.py \
  --action status \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --output "$PWD/radar-devnet-status-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

If status also fails, preserve the directory and report the error. Existing report files are never overwritten. A report-publication failure after an operation does not undo its journal state.

## Signing policy and storage

The signer is a separate Node process, with inherited preload environment removed. It accepts one exact 118-byte legacy message layout: the wallet as payer and signer, System Program, and one 1-lamport transfer from the wallet to itself. It rejects other recipients, amounts, programs, instruction layouts and network labels. The blockhash is supplied by the devnet preparation flow. This tests signing and fee accounting; it does not test a token trade.

The private directory must be owned by the invoking user and mode 0700. The PKCS8 Ed25519 key, metadata, lock and SQLite file are mode 0600. Symlink paths and hard-linked private files are rejected. The private key is created locally and never included in reports. SQLite contains signed bytes and must remain private as well. Git ignore/source checks reject PKCS8 files; those checks are not a complete secret detector.

Process separation and a narrow signing policy are **not an OS sandbox, hardware wallet or protection from compromise of the same user account**. The local owner can read the key. Solana message signatures do not cryptographically bind a network: use this dedicated wallet only for devnet test SOL and never fund it with real assets.

## Optional signed simulation, after reviewing initialization

The first host steps above do not request funding or simulation. After the public address is reviewed and the dedicated wallet has devnet test SOL, this explicit action is available:

```bash
python3 -E -s ~/apps/solana-radar-dev/devnet-rehearsal/rehearsal_cli.py \
  --action prepare \
  --allow-signed-devnet-simulation \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --output "$PWD/radar-devnet-preparation-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

It makes at most six sequential requests to `https://api.devnet.solana.com`, with no retries, environment proxies or redirects. Each request has a ten-second socket timeout and a 4 MiB response cap. Before signing, it checks genesis identity, a plain System-owned wallet, finalized blockhash context and a positive quoted fee at most 10,000 lamports. An absent or insufficiently funded account stops before intent creation or signing.

A process-wide file lock covers the session. The intent is committed using SQLite FULL synchronization before invoking the signer. The independently verified signature and signed bytes are committed before the simulation request. Only one plan is allowed per session. Reopening a committed or incomplete plan provides status, not automatic re-signing, blockhash renewal, reset or resubmission.

Simulation uses signature verification, no blockhash replacement, minimum context and the wallet account response. A pass requires the simulation's own fee and pre/post balances, a wallet decrease of exactly that fee, no System Program balance change, and matching returned wallet balance. A change between the earlier account read and simulation is not itself a failure: comparisons use the simulation's own pre-state. Missing fields, errors, context regressions or contradictory balances remain incomplete. Provider support for these fields must be confirmed on the host; the tool never substitutes an earlier balance to manufacture a pass. A final genesis read must match.

The RPC receives real signed bytes for simulation. A party holding those bytes could submit them while valid, so this is deliberately a dedicated devnet self-transfer only. The tool does not call `sendTransaction` or `requestAirdrop`. A simulation is not a receipt, finality proof, historical account proof or profit result. `executionApproved` and `resubmitAllowed` always remain false.

## Recovery and next engineering gate

Abrupt-stop tests cover a committed intent surviving restart and an uncommitted intent rolling back. Signed/incomplete records remain visible without retry. No live submission boundary is wired into this component yet; it must be implemented and independently tested before any sender is added. Next work is explicit devnet submission, bounded status/finality reconciliation, expiration and unknown-outcome recovery, followed by token lifecycle and independent stop controls.

Reference specifications reviewed for this release:

- [simulateTransaction](https://solana.com/docs/rpc/http/simulatetransaction)
- [getFeeForMessage](https://solana.com/docs/rpc/http/getfeeformessage)
- [getLatestBlockhash](https://solana.com/docs/rpc/http/getlatestblockhash)
- [Transaction structure](https://solana.com/docs/core/transactions/transaction-structure)
