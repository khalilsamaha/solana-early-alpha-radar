# Fresh entry sender integration — November 2, 2026

The November 2 signing host report passed all 17 cases and exactly matched the
portable contract. This increment connects that accepted collection/signing path
to the existing bounded entry sender. It is an internal controlled-devnet API;
the new CLI exposes synthetic checks only. No scanner, observer, study, service
or dedicated wallet is changed by running the host check.

## Integrated behavior

`position-book/fresh_entry.py` requires both private-key signing and devnet-submit
opt-ins before collecting anything. It collects its own raw evidence, uses the
fixed vacant operational admission slot, and invokes the existing independent
signer once. An isolated rehearsal, saved report, or recovered signature cannot
be supplied to restart this fresh entry operation.

After a valid on-time signer acknowledgment, it reacquires the source lock. It
checks the exact signed message, wire, policy, request, accounting handoff,
historical source head and cycle identity. A read-only replay verifies that the
closed historical source still matches before any sender RPC request.

The existing sender verifies devnet genesis before and after blockhash/fee
preflight. It commits its uncertainty boundary before one exact-wire
`sendTransaction` call, with `maxRetries=0`. The original wall-clock deadline and
a shared 30-second monotonic budget cover collection, signing and submission.
They are checked before every sender request and before the durable send boundary.
STOP and clock regression block the next request. No phase refreshes the deadline.

The collection cap remains 20 requests and the sender cap five. An in-flight
request can finish after expiry; a late acknowledgment is retained with
`completedWithinOriginalDeadline=false`. The budget limits starting further work,
not the duration of an already issued request. RPC acknowledgment is not finalized
receipt evidence, guaranteed delivery or proof of a fill.

`networkRequests` counts collection plus sender request attempts. Separate
`collectionRequests`, `senderRequests` and `sendRequestsThisRun` show the split.
`transactionsSent` is unknown once a send is invoked: only receipt recovery can
establish supported observed effects. If inspection fails after entering the
sender, `applicationSendBoundaryRecorded` remains unknown in that run's report;
the private journal must be inspected, not reset. Signing and submission signature
verification counters have separate scopes.

## Failures and recovery

- An existing operational slot refuses repeated entry before collection or signing.
- Late or unknown signing never automatically proceeds to submission.
- Invalid genesis, expired blockhash, fee cap, changed source or STOP blocks sending.
- Expiry or failure after the durable send boundary preserves an unresolved attempt.
- A lost response never causes an automatic resend, new signature or new quote.
- `fresh_entry.recover` collects at most four receipt RPC responses for the existing
  signature. It works after expiry and STOP, with no signing key or signer
  acknowledgment file, because the committed sender already binds the exact wire.
- Recovery of a signed but unattempted entry returns `not-attempted` without RPC.
  It never resumes submission. Incomplete signing uses the separate signer recovery.
- Terminal receipt recovery is idempotent and needs no additional RPC. Unknown and
  quarantined outcomes retain reservations. This integration does not release
  allocation, apply final accounting, or authorize another cycle.

The source lock coordinates these local components; it cannot prevent unrelated
external wallet activity. There is no wallet-wide spending guarantee or mainnet
path in this increment.

## Validation and host command

The portable CLI runs 21 cases using public signed fixtures and temporary journals.
It reads no private key, creates no signature and makes no real network request.
Local validation passed 43 targeted tests: 11 new integration tests, 23 existing
sender tests and nine signing tests. Two CI partition tests also passed.
Additional local integration tests use disposable generated keys and the actual
independent signer through the real collector/parser, with fake RPC responses and
sockets blocked. They cover exact one-send behavior, stopped/expired keyless
receipt recovery and a lost send response. Existing sender and signing suites are
run as regressions. Synthetic elapsed times are not provider latency benchmarks.

Run the pinned command supplied in chat:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/position-book/fresh_entry_cli.py" \
  --output "$PWD/radar-fresh-entry-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expect `offline-checks-passed` and 21 cases. Upload only that compressed public
report. This command has no execute, wallet, directory or submission options.
No install, rebuild, restart or real-wallet action is needed.

## Next gate

After host acceptance, complete the connected receipt/accounting and separately
collected delayed-exit lifecycle before exposing a narrowly scoped devnet execution
command. Full-path host latency and uncertainty recovery remain acceptance gates.
No mainnet pilot or profitable strategy follows from these synthetic checks.

The November 3, 5 and 6 evidence captures and November 6 00:05 UTC review are
unchanged. This is the second development increment after PR #70; consolidate
with CI at the agreed batch boundary, rather than opening a PR for each change.
