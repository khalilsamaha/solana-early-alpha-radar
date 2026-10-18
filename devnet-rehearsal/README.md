# Dedicated devnet rehearsal

The preparation CLI (`rehearsal_cli.py`, release 1) creates a new local Ed25519 wallet, records an intent before signing, and can request a signed devnet simulation. That CLI has no broadcaster. The separate submission CLI added below can send one explicitly authorized devnet self-transfer. Neither CLI has a faucet, wallet import, mainnet option, token swap or production-ledger integration.

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

A process-wide file lock covers the session. The intent is committed using SQLite FULL synchronization before invoking the signer. The independently verified signature and signed bytes are committed before the simulation request. Preparation alone allows one plan per session. The separate submission workflow can explicitly retire an expired original plan and create at most one replacement, while preserving both records. Reopening a committed or incomplete plan provides status, not automatic re-signing, blockhash renewal, reset or resubmission.

Simulation uses signature verification, no blockhash replacement, minimum context and the wallet account response. A pass requires the simulation's own fee and pre/post balances, a wallet decrease of exactly that fee, no System Program balance change, and matching returned wallet balance. A change between the earlier account read and simulation is not itself a failure: comparisons use the simulation's own pre-state. Missing fields, errors, context regressions or contradictory balances remain incomplete. Provider support for these fields must be confirmed on the host; the tool never substitutes an earlier balance to manufacture a pass. A final genesis read must match.

The RPC receives real signed bytes for simulation. A party holding those bytes could submit them while valid, so this is deliberately a dedicated devnet self-transfer only. The tool does not call `sendTransaction` or `requestAirdrop`. A simulation is not a receipt, finality proof, historical account proof or profit result. `executionApproved` and `resubmitAllowed` always remain false.

## Recovery and next engineering gate

Abrupt-stop tests cover a committed intent surviving restart and an uncommitted intent rolling back. Signed/incomplete records remain visible without retry. The release-2 submission boundary described below is now implemented and covered by offline tests; actual host submission remains to be verified. Token lifecycle and broader independent trading stop controls remain later work.

Reference specifications reviewed for this release:

- [simulateTransaction](https://solana.com/docs/rpc/http/simulatetransaction)
- [getFeeForMessage](https://solana.com/docs/rpc/http/getfeeformessage)
- [getLatestBlockhash](https://solana.com/docs/rpc/http/getlatestblockhash)
- [Transaction structure](https://solana.com/docs/core/transactions/transaction-structure)

## Release 2: explicit submission and read-only recovery

`submission_cli.py` defaults to a nine-case offline check with temporary keys and synthetic RPC responses. It does not send a real transaction unless invoked with both `--action execute` and `--allow-devnet-submit`, plus the exact `--wallet` address. No install, Docker rebuild or production restart is required.

Execution holds the existing session lock, revalidates the saved signed bytes and simulation identity, checks the official devnet genesis, queries block height and signature history, and requires at least five blocks of remaining validity. Preflight remains enabled with finalized commitment. The tool commits a FULL-sync `submission-unknown` boundary before the single `sendTransaction` call. HTTP retries are absent and RPC `maxRetries` is zero. This guarantees at most one application send call per session, not exactly-once network delivery. A crash between the commit and transport is deliberately indistinguishable from uncertain delivery.

The optional `--allow-expired-plan-replacement` flag permits one replacement only when the original is expired according to finalized block height, no tool submission boundary exists, and both signature-history and finalized transaction queries return no record. The old state becomes `expired-unsubmitted` (meaning not submitted by this tool); its signed bytes, intent and simulation report remain intact. The absence of RPC records is not proof that nobody else ever submitted the bytes. This workflow depends on the dedicated private devnet wallet and RPC evidence. The replacement is prepared and simulated under the same lock before submission. No third plan is allowed. Once a boundary exists, replacement is prohibited regardless of timeout, error, expiry, or final result. An expired state cannot regress into send eligibility if block height later moves backward.

The journal gains two additive tables, `submission` and `submission_events`. The original preparation records are preserved. New status supports at most two plans; older release-1 tools should not be used after replacement. The source checks refuse keys in git. The session remains private and outside the scanner backup system.

### Host commands

After checking out the pinned release, first run:

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/devnet-rehearsal/submission_cli.py \
  --output "$PWD/radar-devnet-submission-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

The following action can submit **one 1-lamport self-transfer on devnet**, with a maximum fee of **10,000 test lamports (0.00001 devnet SOL)**. It uses the existing wallet and may create one replacement for the expired simulation plan:

```bash
python3 -E -s ~/apps/solana-radar-dev/devnet-rehearsal/submission_cli.py \
  --action execute \
  --allow-devnet-submit \
  --allow-expired-plan-replacement \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --output "$PWD/radar-devnet-submission-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Upload only the public `.json.gz` reports. The tool does not export the key or signed transaction bytes. `executionApproved: false` means no general trading or further execution approval; the explicit CLI authorization applies only to this one rehearsal. `submissionAttempts` counts durable send boundaries, not proved delivery. `requests` describes this invocation; `preparationRequests` describes its optional replacement preparation.

The bounded observer makes at most three observations, with ten seconds between rounds. Each round checks cluster identity, signature status and either a finalized receipt or block height. A final state requires the exact locally verified signed transaction bytes, matching slot and status, the expected fee within the cap, and wallet/System balances consistent with this self-transfer. Failed finalized transactions retain fee-only accounting. Missing evidence stays unknown. Contradictory receipts or an unexpected acknowledgement signature cause sticky quarantine.

The execution client permits at most 30 calls, plus at most six replacement preparation calls; recovery permits at most 12 calls. Every request uses the existing ten-second socket timeout and 4 MiB response cap. These caps do not promise a ten-second total run. No requests use a custom endpoint or inherited environment proxy.

If execution ends pending/unknown, or the process stops before publishing its report, use **recover**, not another execute command:

```bash
python3 -E -s ~/apps/solana-radar-dev/devnet-rehearsal/submission_cli.py \
  --action recover \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --output "$PWD/radar-devnet-recovery-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Recovery uses a separate RPC allowlist that cannot send, simulate or request a new blockhash. It queries only the already recorded signature. Expiry after a boundary produces `expired-outcome-unknown`, never permission to resend. Final and quarantined states are preserved without further network calls. Repeated execute also returns the existing state without network calls. No reset/retry/unquarantine command exists.

A persistent independent stop marker can be written even while the session lock is held:

```bash
python3 -E -s ~/apps/solana-radar-dev/devnet-rehearsal/submission_cli.py \
  --action stop --directory "$HOME/solana-radar-devnet-rehearsal" \
  --output "$PWD/radar-devnet-stop-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

The marker is checked before recording the boundary and again immediately before transport. It cannot recall a transaction already in flight or remove the narrow race after the final check. Recovery remains allowed while stopped. There is no automated removal of the stop marker. This is a devnet rehearsal control, not a complete live trading kill switch.

`--action status --directory ... --output ...` makes no network calls and exports the durable state. Status uses the current schema and may initialize the additive control tables; it never resets a plan. Preserve the session on any failure. Do not roll back its database, delete it, copy it into another working wallet, or reinitialize to work around an unknown outcome. State protections assume a single intact session on the host and do not protect against an owner copying private keys/journals.

Additional specifications reviewed:

- [sendTransaction](https://solana.com/docs/rpc/http/sendtransaction): acknowledgement is not confirmation.
- [getSignatureStatuses](https://solana.com/docs/rpc/http/getsignaturestatuses): history search must be explicit.
- [getBlockHeight](https://solana.com/docs/rpc/http/getblockheight): block height and commitment are used for expiry.


## Release 3: atomic WSOL lifecycle rehearsal

The separate `token_lifecycle_cli.py` now exercises a fixed seven-instruction devnet contract: create and initialize two fresh WSOL accounts, transfer exactly 1,000 test lamports, then close both to the dedicated wallet. It has a separate narrow signer and private `token-lifecycle-v1/lifecycle.sqlite` journal; the original native self-transfer signer, plans and submission boundary are not changed. The shared parent lock and STOP marker apply to both workflows.

Default invocation is a ten-case offline self-check. Live execution requires `--action execute --allow-devnet-token-submit`, the existing private directory and exact public wallet. Signed simulation precedes at most one application send. Intent and signed data are committed before their respective external boundaries. A durable unknown state precedes transport. There is no automatic replacement or repeat execution; recovery has a read-only RPC allowlist. Partial setup and incomplete plans are preserved rather than recreated.

The narrow fee cap is 20,000 test lamports, rent cap 2,500,000 per account, fixed amount 1,000. Actual final wallet change must equal the fee; temporary accounts must have zero native balances at both endpoints. WSOL closure returns the wrapped test lamports. Intermediate balances are not observed because the accounts exist only inside the atomic transaction. Exact signed instructions and RPC-reported successful execution are the lifecycle evidence; this is not generic transient-account support or a swap.

See [commands, recovery and evidence limits](../docs/DEVNET-TOKEN-LIFECYCLE-UPDATE.md). No production deployment or new background service is involved. Actual host lifecycle receipt remains the next gate.
