# Exact signature reuse within one entry attempt — November 3, 2026

## Evidence and scope

The accepted Kali entry profile recorded six passing connected checks, nineteen
complete spans and unchanged historical source evidence at 05:04:56 UTC. Three
source replay spans took 1,196.250 ms, about 79% of the 1,519 ms post-collection
interval. Sender replay took 876.113 ms. These are synthetic timings, not live
submission latency. The earlier unsigned live check had 2,454 ms remaining and
did not include durable signing or sending.

Signing and submission previously created separate exact-signature memo scopes.
This second increment after PR #72 gives the connected entry operation one fresh
owner scope and explicitly joins it in those two phases. An unrelated nested
scope is still isolated by default. Standalone signing, observation, exit and
recovery retain their existing independent scope behavior.

Only successful Ed25519 authentication of identical canonical wire bytes is
reused, with at most 64 entries. Parsing, journal rereads, receipt interpretation,
source identity, STOP, original deadlines, fee/blockhash/genesis checks, durable
boundaries and the independent signer still run. Changed wire bytes require a
new cryptographic verification; failed verification is never cached. A full memo
falls back to verification. No file, receipt, authorization or freshness result
is cached. The owner clears its set on normal return and exceptions; a later
attempt or recovery starts independently. There is no persistent/global cache.

## Result and interpretation

The connected local comparison used the actual collector, disposable-key backend,
admission and sender against synthetic replies. Verifier subprocesses fell from
**16 to 8** while preserving **6 source rereads and 25 request attempts**, including
one intentionally lost send response. Signing and submission outcomes, request
order and deadline checks matched. This reduces redundant local work; it does not
prove a fixed millisecond gain, a successful live round trip or profitable trades.

The report now includes `signatureVerification` with `attempt`, `signing` and
`submission` counters. Phase counters are deltas; the attempt counters are their
total, so do not add the total again. `memoEntries` is a shared occupancy gauge,
not a sum. `verifierProcesses` counts the wire-authentication subprocesses, not
all subprocesses or private signing. In the fixed successful exercise, submission
reuses authenticated bytes and launches zero new wire verifier processes.

Ten new tests cover counter accounting, default isolation, exception cleanup,
subsequent attempts, capacity, signature/message tampering, independent recovery,
source identity changes, historical receipt tampering after signing, STOP and
expiry after a durable send boundary. Existing profile, signature replay,
signing, entry, exit and journal regressions are also checked. The host acceptance
is pending; local timings are not substituted for Kali measurements.

## Kali acceptance

Use the pinned development checkout supplied in chat, then run:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/entry_profile_cli.py" \
  --output "$PWD/radar-entry-attempt-profile-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-entry-profile-passed`, seven connected checks, nineteen complete
spans, valid original-deadline checks and reconciled verification counts. The test
uses temporary disposable keys and synthetic replies, blocks Python sockets,
cleans up its temporary journals and performs no real transaction. Upload only
the resulting public report. Preserve a failed/partial report rather than retrying
operational execution.

No Docker rebuild, service restart, airdrop or access to the existing private
rehearsal directory is needed. Scanner, observer, Telegram, studies and backups
are unchanged. This is a development commit, not a deployment or live approval.

## Next gates

1. Review the new Kali phase/counter report against the accepted original profile.
2. If headroom improves, prepare the separate controlled devnet acceptance path
   with original deadlines and one-send recovery intact; do not infer authorization
   from a synthetic pass.
3. Consolidate around the agreed three-increment checkpoint with full CI.
4. Preserve the November 3, 5 and 6 availability-study captures; review November 6
   at 00:05 UTC / 01:05 Amsterdam. Economic qualification remains independent of
   execution engineering. No real-money date or profitable strategy is established.
