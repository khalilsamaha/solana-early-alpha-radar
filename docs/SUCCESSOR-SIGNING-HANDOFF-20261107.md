# Separate successor signing handoff — 7 November 2026

## Accepted host evidence

Kali's collection check at 18:20:22 UTC passed all 13 offline cases. The live
read-only observation at 18:21:10 UTC returned
`successor-observation-consistent-held` after all 28 fixed requests.

- Local replay: 38,729 ms; expiry reads: 2,153 ms; quote collection: 3,517 ms.
- Successor validation: 3,237 ms; original freshness remaining at return: 3,245 ms.
- The twenty-request quote phase used one HTTPS connection and zero retries.
- Quantity 998, protected inventory 500,000,000, fee hold 25,000 lamports,
  retired fee exposure 10,000, successor fee cap 10,000; no additional reservation.
- No saved successor, key access, signature, transaction, reservation release or
  runtime change. The old attempt remains retired.

This accepts bounded collection. It does not establish commit, independent
signer or sender timing. The observed 3.245 seconds cannot be treated as a proven
execution budget. No freshness deadline is extended by this release.

## Implemented boundary

`successor_signing_handoff.py` adds an internal injected-adapter contract and a
separate `admission_successor_signing` journal. There is no default private-key
backend, RPC client, sender, operator evidence importer or live CLI action.

The request binds the exact successor, retirement, retired preparation, source
context, entry accounting, collection, message, original deadline, quantity,
protected inventory and fee exposures. Its attempt number is two; the retired
attempt remains charged. Existing preparation/signing/backend files are not
rewritten or adopted as the new generation.

A hash-chained `successor-signing-unknown` boundary is committed before entering
the adapter. A second writer is excluded during current validation and adapter
use, and the wallet source lock is held. Any later dispatch sees the existing
boundary and makes zero adapter calls, including after a crash, lost response,
STOP, expiry or failure before adapter entry. No attempt is reset or refunded.

Recovery verifies the exact Ed25519 signature and message before recording the
reply. A valid late reply remains inspectable after STOP or expiry without
resigning. Invalid or conflicting responses quarantine the generation. A missing
verifier is an infrastructure failure that preserves the unknown boundary.
Neither a signed reply nor a quarantine releases any hold or authorizes a send.

Lifecycle and snapshot projections semantically replay the new journal and bind
its head. An orphan, rehashed changed request or corrupted signature fails replay.
The old sender continues to deny the retired generation.

## Validation and limits

The portable suite has 15 cases using actual semantic source replay, disposable
Ed25519 keys and synthetic provider evidence. It covers durable visibility before
adapter entry, writer exclusion, exact signing, lost and late replies, duplicate
recovery, precommit rollback, lost acknowledgment writes/completion output, postcommit STOP/expiry, old-wire rejection,
rehashed request/signature attacks, orphan/oversized rows, clock regression,
verifier outage, original sender denial and snapshot projection.

Local release validation passed all 15 portable cases and 37 affected regressions
(unsigned successor, bounded collection, lifecycle and retirement snapshots) with
`ResourceWarning` treated as an error. Two test-partition checks, five CLI
scope/output refusal checks, source hygiene and package manifests also passed.

The suite does not exercise an independent successor key process or live
submission. Historical fixture clocks make it a functional check, not a benchmark
of completion under real freshness deadlines. Full live preparation/commit/signing
headroom remains unmeasured. Do not run any previous execution command to retry
the retired attempt.

## Kali check

Use the pinned commit supplied in chat, then run from the live project directory:

```bash
python3 -E -s -W error::ResourceWarning \
  "$HOME/apps/solana-radar-dev/position-book/successor_signing_handoff_cli.py" \
  --output "$PWD/radar-successor-signing-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 15 cases. Upload only the generated public
report. Test keys and journals are disposable; no user wallet or RPC is used.
No Docker rebuild, observer restart, scanner deployment or study change is needed.

## Host acceptance

Kali passed all 15 cases at 18:55:10 UTC on November 7. The next
[independent key backend](SUCCESSOR-KEY-BACKEND-20261107.md) builds on this accepted handoff.

## Next gate

Implement the independently validating, generation-specific restricted signing
backend and its durable attempt/acknowledgment files. Then integrate fresh
collection, persistence, signing and one controlled devnet send in a single
measured path. Preserve the original deadline; stop if it expires. Exact receipt
reconciliation and scoped closure follow. These are execution milestones, not
approval for a trading strategy or a real-money pilot.
