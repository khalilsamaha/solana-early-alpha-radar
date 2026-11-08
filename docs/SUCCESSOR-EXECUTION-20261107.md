# Combined successor execution rehearsal — 7 November 2026

The separate signing rehearsal passed all 24 Kali checks with 1,106 ms of
original-deadline headroom. The submission component then passed all 17 Kali
checks. This release joins them into a measured internal operation. Its public
CLI only creates disposable test data and synthetic RPC replies. It offers no
wallet, journal-directory, RPC-endpoint or execution arguments.

## November 8 host result — gate still blocked

The report captured at 03:47:50 UTC passed 4 setup and 11 boundary checks but
failed the complete real-clock gate. Signing finished with 2,657 ms remaining;
submission preparation then took 2,742.007 ms and refused with
`successor-signing-expired`. The full operation returned 90 ms past the original
deadline. No sender RPC or send request occurred. Seven connected recovery and
preservation checks were not reached, not passed. `originalSourceUnchanged=false`
in that report is an uncompleted assertion, not evidence of a detected mutation.
Temporary fixture cleanup succeeded; no production wallet or runtime was used.

The earlier text described one shared computational owner, but nested decorators
still created fresh scopes. The November 8 correction makes that reuse explicit
for canonical digest/text, public encoding, admission-chain exact-row replay and
signature verification. Independent callers remain isolated by default. Nested
phases do not clear their parent's cache; only the outer owner clears it. Full
source reads and semantic, clock, STOP and spending checks remain in place.

The corrected CLI includes 4 setup, 12 boundary, 5 scope-ownership and 7 connected
checks (**28 total**). Its report identifies `successor-computation-owner-1` and
labels whether preservation checks completed. Nested computational counters are
cumulative owner snapshots and must not be summed; signature phase counters keep
the existing delta semantics. No freshness limit, operation budget or cache
capacity has increased. Kali acceptance remains required.

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

The corrected command also runs four fixture-setup, twelve composition fault
checks and five scope-ownership checks. Expected total: **28 checks**.
Temporary data is removed, including on a failed phase. A failed report remains
`review-required`; it is not approval to repeat an operational signing attempt.

## Local validation

The November 8 corrected packaged CLI passed **4 setup + 12 boundary + 5 scope
ownership + 7 connected = 28 checks**. Its measured combined path took
**5,758.970 ms**, leaving **5,604 ms** on the original deadline. The first corrected
local run took 5,627.292 ms with 5,721 ms headroom; neither result substitutes for
Kali or real RPC measurements. The original November 7 package took 6,157.620 ms
with 5,109 ms headroom locally and subsequently failed the host gate above.

Regression results: 45 canonical/text/encoding replay cases, 7 admission-history
cases, 11 signing integration cases and 4 post-child historical/ACK mutation cases
passed with ResourceWarnings treated as errors. The new owner tests cover parent
identity through actual nested calls, mutation, exception cleanup, thread
isolation, strict opt-in flags and original capacity limits. Six CLI output/scope
refusals preserved files. Both partition checks, source hygiene and staged
whitespace checks passed.

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
