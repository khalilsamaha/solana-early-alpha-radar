# Successor one-attempt transport — 7 November 2026

The complete Kali signing rehearsal passed all 24 checks with 1,106 ms of
original-deadline headroom. This release implements the next internal transport
component. The only public command runs disposable offline tests. It does not
connect the operational wallet, change the scanner, or expose an execution mode.

## Behavior

The private successor signature is bound to the validated candidate, retirement,
request and signing-chain head. A new `admission_successor_transport` hash chain
records the application boundary, optional transport acknowledgment and at most
eight finalized-signature observations. Original tables and backend markers are
preserved. No fee reservation or protected inventory is released.

The internal sender requires both explicit opt-in and an injected provider. It
uses the fixed devnet endpoint and existing bounded RPC client. Four preflight
reads verify genesis, blockhash, fee and context before one exact `sendTransaction`
request (`maxRetries=0`, preflight enabled). Full semantic validation repeats
inside the writer transaction immediately before the boundary is committed.
STOP, clock regression, expiry or failed validation prevents a new send.

Once the boundary commits, the generation cannot send again, including a crash
before transport, lost response, acknowledgment persistence failure, or deadline
expiry. Recovery observes only its recorded signature, with no signer or send
method. It remains available after STOP/expiry. Terminal evidence and duplicate
status checks do not issue additional RPC requests. Conflicting signatures or
receipt identities quarantine the evidence.

The read-only lifecycle and backup projection include the transport chain's state
and head, so the new records cannot be silently omitted or orphaned. The phase
continues to represent the original retired held position: successor transport
is an additional stage, not a settlement or release. Finalized RPC claims still
require exact token/fee receipt reconciliation and fresh residual balances.

## Host command

Check out the pinned release commit supplied in chat, then run:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s -W error::ResourceWarning \
  "$HOME/apps/solana-radar-dev/position-book/successor_submission_cli.py" \
  --output "$PWD/radar-successor-submission-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected state: `offline-checks-passed`, **17 cases passed**. Upload only the public report. No Docker
rebuild or restart is needed. The CLI rejects wallet, directory and execution
arguments and refuses to overwrite an existing output. Tests use disposable
Ed25519 keys, temporary journals and synthetic provider responses with socket
connections disabled.

## Local verification

- Complete offline CLI: 17 cases passed, no failures or skips.
- Existing independent signer suite: 9 cases passed.
- Existing lifecycle suite: 6 cases passed, including the portable lifecycle CLI.
- Six CLI scope/output refusals and two partition-coverage cases passed.
- Source hygiene, package manifests and whitespace checks passed.

Tests use real semantic source replay and disposable signatures. They cover the
committed boundary before transport, duplicates, lost response, acknowledgment
write failure, postcommit crash/expiry, precommit rollback, STOP, wrong cluster,
fee/context/clock rejection, changed historical evidence, finalized/failed/
unknown/conflicting receipts, capture caps, rehashed substitution, orphan tables,
writer exclusion and unchanged accounting. A falsy injected adapter is rejected
before source access so the shared RPC client cannot fall back to its default
network adapter. These tests do not qualify real network timing.

## Kali acceptance

The report `radar-successor-submission-check-20261107T222159Z-1480388.json.gz`,
captured at 2026-11-07T22:31:31.352668+00:00, passed all 17 cases with no failures
or skips. User journals, user keys, the scanner and real network were untouched.
This accepts transport semantics, not combined signing/send latency.

## Next acceptance gate

The [combined execution rehearsal](SUCCESSOR-EXECUTION-20261107.md) composes this component with fresh successor collection and independent signing
under the original deadline. Measure the complete path on Kali with the 1 MiB
fixture, including lost-response recovery. The 1.106-second signing headroom is
not sufficient evidence that real preflight and send will fit. This component's
fixed-clock fault tests establish semantics, not end-to-end timing or live
execution approval. No trading strategy or frozen-study conclusion changes.
