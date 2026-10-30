# Restricted admission signer — 30 October 2026

## Accepted starting point

The admission-receipt host report captured at 2026-10-30 15:51:38 UTC matched all
14 cases and safety flags exactly. It accepts the synthetic same-ledger receipt
gate, not actual RPC receipt provenance or a new transaction submission.

PR #63 remains the merged base. This is the second increment in the next batch:
receipt integration first, then the restricted signer backend. Local checks and a
pinned disposable-key host check precede the next consolidated PR/CI review.

## What is implemented

`restricted_signer.dispatch()` is an internal API with an explicit
`allow_private_key_signing=True` requirement. No scanner, observer, service or
user-facing execution command calls it. There is no transaction sender.

The existing admission dispatcher retains the cooperating source lock, recomputes
raw evidence, reads the source twice, commits all fee/principal reservations and
stores the exact request and signing-unknown boundary. The backend then runs as a
separate Node process with inherited preload/environment hooks stripped.

The Node process independently:

1. Opens only the fixed sibling admission database in read-only mode. It rejects
   unsafe paths, permissions, hard links, recovery sidecars, mixed legacy intents,
   an unexpected policy or any sequence except reserve → arm request → boundary.
2. Verifies the event hashes, request digest, policy identities, ordering and
   original deadline. It checks the entry and exit fee commitments against caps.
3. Derives the wallet, fixed pool, mint pair, vaults and authority from the recorded
   controlled-pool setup, then compares every role with the admitted forward scope.
4. Reconstructs the exact legacy message independently: one wallet signer, the
   supported standard-SPL CPMM swap, at most 1,000 input atomic units, positive
   minimum output, at most 300,000 compute units, zero priority price, at most
   10,000 lamports entry fee cap, 1–3 budgeted exits and at most 40,000 total cap.
5. Checks both message hashes, exact unsigned bytes, fee observation, receipt
   intent template, original prebalances and deadline. No uploaded summary can
   replace these private ledger bindings.
6. Reads the private key only from the existing dedicated source wallet file and
   verifies its public key. It checks STOP and clocks, saves an exclusive fsynced
   attempt record, checks again, signs once and saves a private acknowledgment.

The independent signer does not re-fetch prices or replay the entire source
history. Those remain responsibilities of the locked raw-admission caller.
Stored devnet genesis/setup metadata is not a fresh RPC genesis observation.

## Durable files and recovery

The backend adds two private files beside `entry.admission.sqlite` in
`<canonical-source-directory>-entry-handoff-v1`:

- `signer-attempt.json`: request identity, admission boundary hash and attempt time.
- `signer-ack.json`: request identity and exact signed wire/hash.

The attempt file is created exclusively **before** `crypto.sign`. An existing
attempt blocks another invocation even when the acknowledgment is missing. A
timeout, process interruption or partial write must not be solved by deleting it.

`restricted_signer.recover()` holds the same source lock and verifies the existing
attempt's boundary/deadline binding plus acknowledgment. It records the signature
through the existing admission verifier and stages the accounting outbox. It can
recover after expiry and after removal of the key, without invoking the backend.
Missing/corrupt acknowledgment files cause refusal and leave commitments unknown.
This is a write to the separate admission ledger, not a read-only ledger action.

The source wallet, setup and closed-cycle journals are unchanged by dispatch.
New files remain in the sibling ledger directory. The old fixed-cycle signer and
its layouts are not repurposed or reset. Copies of a source directory, unrelated
senders and other wallets remain outside this per-directory ownership model.
There is still no wallet-wide reservation service.

## Tests and host command

The portable check uses **two disposable test keys** in a private temporary
directory and creates **one test signature**. The second key tests key mismatch.
It makes no RPC requests, sends nothing, and cannot accept a production wallet or
directory. All temporary test files are removed before a successful report is
published. It does not export keys or signed wire.

Its 19 cases cover independent reconstruction, exact request/ledger binding,
duplicate invocation, lost acknowledgment, scope/network/deadline refusals,
missing boundary, hash/wire changes, wrong key, STOP, private-file restrictions,
SQLite recovery files, fee commitment and receipt-template mismatch.

Local integration additionally exercises the actual synthetic two-cycle source
reader, fresh raw observation, locked admission, independent key process, private
handoff and receipt gate. The resulting receipt is explicitly synthetic RPC
evidence; no transaction is submitted. Further cases cover a lost parent response
after the backend saved its acknowledgment and competing backend processes; only
one process can create the attempt and signature acknowledgment.

Local validation passed: 341 position-book regression tests, a final focused run
of all 7 restricted-signer tests, and the tracked-source policy check. These
results do not replace the pending host check or a future controlled execution.

After fetching the pinned development commit supplied in chat:

```bash
cd ~/apps/solana-early-alpha-radar
umask 077
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/restricted_signer_cli.py" \
  --output "$PWD/radar-restricted-signer-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, **19 cases**, `signaturesCreated: 1`,
`productionWalletAccessed: false`, `networkRequests: 0`, `transactionsSent: 0`.
No sudo, Docker rebuild or service restart is needed. The host report captured at
2026-10-30 18:38:34 UTC matched all 19 cases and flags exactly; this host gate is
accepted. Submission integration follows in [the next release](ADMISSION-SUBMISSION-GATE.md).

## Remaining integration gates

1. Accept the disposable-key host check. Do not run this internal backend against
   the existing devnet wallet as an unplanned third cycle.
2. Implement a durable one-send boundary and bounded, genesis-bound receipt
   collection for this new lifecycle. Preserve uncertainty after transport loss.
3. Connect authoritative entry/exit accounting and allocation ownership. Until
   then the original reservations stay held, even after a consistent receipt.
4. Include this sibling ledger and its acknowledgments in the key-excluded private
   recovery procedure before deployment; do not copy private keys into reports or
   ordinary source/backup archives.
5. Validate delayed exits, failed fees, STOP and recovery under a separately agreed
   controlled scope before considering narrow mainnet support.

This gate establishes testable signing mechanics, not trading approval, current
wallet-wide solvency or profitability. Production monitoring and the fixed study
remain unchanged. Preserve November 1, 3, 5 and 6 captures; review November 6 at
00:05 UTC / 01:05 Europe/Amsterdam.
