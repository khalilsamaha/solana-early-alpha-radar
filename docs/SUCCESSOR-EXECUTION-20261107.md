# Combined successor execution rehearsal — 7 November 2026

The separate signing rehearsal passed all 24 Kali checks with 1,106 ms of
original-deadline headroom. The submission component then passed all 17 Kali
checks. This release joins them into a measured internal operation. Its public
CLI only creates disposable test data and synthetic RPC replies. It offers no
wallet, journal-directory, RPC-endpoint or execution arguments.

## What is connected

The existing eight expiry/account reads and twenty quote/simulation reads feed
atomic successor preparation, the independent Node key process and durable parent
acknowledgment. The existing four preflight reads precede one `sendTransaction`
request. The original ten-second collection deadline is never reset between
stages. The outer 120-second operation budget also reaches every sender request,
so starting submission does not restart that budget.

Exact-content hashing, serialization, public encoding and signature-verification
reuse have one bounded owner across the call. They do not cache authorization,
source reads, expiry decisions or validation outcomes. Full semantic replay still
occurs at the existing persistence, signing and transport boundaries. The owner
ends before the caller records final deadline headroom; cleanup cannot hide a
late completion. Shared scopes start cold in the measured rehearsal.

A transport call is uncertainty, not proof of delivery. A committed application
boundary consumes the generation even if transport never begins or its reply is
lost. The public result retains request counts and an unknown boundary state if
an exception prevents inspection. A late response remains recorded but cannot
pass the timing gate. Repeating the composition never refreshes or automatically
signs an existing successor.

## Connected acceptance

The 1 MiB real-clock fixture deliberately loses the single synthetic send reply.
Expected nested integration state is `successor-submission-unknown`, while the
complete report is `offline-integration-passed` only after all of these pass:

1. Full collection, persistence, independent signing and send return before the
   original deadline: 28 collection plus 5 transport requests, exactly one send.
2. The durable send boundary and unknown response are retained.
3. Repeated composition makes no new collection, signature or send and changes
   no saved bytes.
4. Remove the disposable key, set STOP and observe only the recorded signature.
5. Terminal recovery makes no new RPC request or database write.
6. Original retired tables, backend markers and historical source remain intact.
7. All held accounting remains conservative; no receipt settlement or closure is
   inferred from a finalized RPC claim.

The command also runs four fixture-setup checks and eleven composition fault
checks. Expected counts: **4 setup + 11 boundary + 7 connected = 22 checks**.
Temporary data is removed, including on a failed phase. A failed report remains
`review-required`; it is not approval to repeat an operational signing attempt.

## Local validation

The packaged CLI passed 4 setup, 11 boundary and 7 connected checks. Its
combined path took **6,157.620 ms**, leaving **5,109 ms** on the original
deadline. These are local synthetic-provider measurements, not Kali or live RPC
results. Six output/scope refusal checks preserved existing files, and both test
partition checks passed. The existing submission suite passed 17 tests and
the signing integration suite passed 11 tests with ResourceWarnings treated as
errors. Source hygiene and staged whitespace checks also passed.

## Kali command

After checking out the pinned release supplied in chat:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s -W error::ResourceWarning \
  "$HOME/apps/solana-radar-dev/position-book/successor_execution_cli.py" \
  --output "$PWD/radar-successor-execution-rehearsal-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Upload only the resulting public report. No Docker rebuild or restart is needed.
This test is offline and sends no real transaction. Synthetic request counters
inside the report describe the exercised transport, not real network activity.

## Remaining gates

Kali must pass the complete real-clock gate with positive headroom. Synthetic
replies do not include real provider latency or finality. The earlier 1.106-second
signing-only host margin is narrow, so no live timing success is assumed.

After acceptance: controlled devnet operation and exact successor token/fee
receipt reconciliation, followed by fresh residual balances and durable scoped
closure. The closed research results are unchanged; this engineering evidence
neither establishes profitability nor authorizes a funded trading pilot.
