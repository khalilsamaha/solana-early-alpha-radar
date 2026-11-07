# Connected successor signing rehearsal — 7 November 2026

## Accepted prerequisite

The Kali independent-backend report captured at 19:21:34 UTC passed all 50
cases: 41 Node backend cases and nine Python adapter/recovery cases. These
component tests used disposable keys and synthetic providers. They did not
measure complete collection-to-signing latency.

## Kali result and setup correction

The first Kali report, captured at 21:42:46 UTC on November 7, is
`review-required`: 11/11 boundary cases passed, but fixture class setup stopped
after 67,528.731 ms. No connected case ran; `integration` and fixture size were
null. Cleanup completed. No real network, user key, user journal or transaction
was involved. This is **not host acceptance** of the signing path.

The bounded trace ends at the historical entry's raw quote derivation during
its signing-boundary validation. The old diagnostic did not retain the specific
contract rejection code. Expired setup evidence on the slower host is consistent
with this trace, but the report does not establish that exact reason.

The `successor-fixture-setup-2` correction adds the existing bounded exact-content
reuse scopes around disposable history construction. Those scopes were previously
applied to later prerequisite phases but omitted from class setup. They are
checked empty before construction and after success or failure, before the
measured successor path. Wall clocks, monotonic clocks, validators and deadlines
are unchanged. Nothing is signed against an altered clock, no failure is retried,
and no validation result is substituted. The correction affects rehearsal code
only; the internal successor integration and operational modules are unchanged.

Four additional checks verify scope lifetime, real clock function identity,
cleanup without retry on failure, expired-input rejection by the actual validator,
and bounded diagnostic reporting. Known `Rejected` contract codes are now
reported through an explicit allowlist; arbitrary exception text is never copied.
The corrected host CLI reports these as `Fixture setup checks: 4`, separately
from the 11 boundary and five connected checks.

The corrected local CLI passed all four setup, 11 boundary and five connected
checks. Historical class setup completed in 20,007.059 ms (previous local run:
32,234.511 ms). The measured successor integration took 4,553.029 ms with
6,759 ms of original quote headroom. Keyless and repeat recovery, original source
preservation, held accounting and cleanup all passed. Two partition-coverage
checks and source hygiene passed. These are local measurements, not predictions
of Kali latency. Host acceptance must still pass before proceeding to successor
submission integration.

## Second Kali result and handoff cost correction

The corrected Kali report captured at 21:49:54 UTC passed four setup checks and
11 boundary checks. Historical setup completed, and the 1 MiB connected path
collected all 28 responses and recorded the disposable successor signature and
acknowledgment. It nevertheless failed the original completion deadline:
14,305.128 ms total integration, with **-193 ms** headroom at return. Collection
and persistence took 5,318.839 ms; signing handoff took 8,972.402 ms, including
2,503.126 ms in the child adapter. No transaction was sent. Recovery and final
preservation assertions were not reached, so this remains `review-required`.

A diagnostic local profile identified four full historical `handoff.load` calls
within the signing handoff. The child adapter repeated the full replay immediately
before the parent did the same post-child replay. The correction removes only
that duplicate from the internal adapter. The parent still performs full replay
before committing the unknown boundary, again before invoking the child, and
after the child returns before appending its acknowledgment. Separate source and
database locks, original freshness, STOP, protected inventory, fee reservations
and independent Node compilation remain enforced.

The child adapter still reads the committed candidate and signing chain through
a read-only connection, checks exact candidate/request identities, and validates
the saved marker, ACK hash and Ed25519 signature. Its return is a signed response,
not a position validation or send permission. Standalone keyless recovery retains
its full historical replay. No validation verdict is reused across a write or
child invocation; no new cache is introduced.

Four regression cases verify the three required full replay boundaries, refusal
to record success after old marker mutation, rejection of a corrupt new ACK, and
request-identity refusal before starting the child. They are included in the
public CLI as `Backend replay checks: 4`. The report also gives return-time
headroom on failed completions and identifies the completion check correctly.
This is a measured timing correction, not permission for live submission.

The existing independent signer regressions (9 cases) and signing handoff regressions
(15 cases) also passed with ResourceWarning treated as an error. Six CLI refusals,
two partition-coverage checks, source hygiene and package manifest checks passed.

The local corrected CLI passed all 24 checks: four setup, four backend replay,
11 boundary and five connected checks. Complete integration took 4,269.518 ms,
with 7,186 ms remaining at return. The adapter took 406.690 ms and the complete
signing handoff took 2,478.492 ms. Keyless recovery after STOP, byte-identical
repeated recovery, original source/marker preservation, held accounting and
temporary cleanup passed. The earlier local adapter measurement was 856.387 ms;
these are separate local runs, not a guaranteed host speedup. A new complete
Kali pass remains required. No live invocation or deployment command is added.

## This increment

An internal composition now connects the actual eight expiry/account reads and
twenty quote/simulation reads to atomic successor preparation, the durable
unknown signing boundary, the independent Node key process, parent acknowledgment
validation and ledger commit. Its explicit private-key and preparation opt-ins
precede source access. It preserves the retired generation and cumulative holds.

The original ten-second quote deadline is checked through the final return,
including cleanup of the operation's exact-content replay scopes. Preliminary
source and expiry reads have their existing separate bounded budgets; the quote
clock begins at quote collection, not at operation entry. Therefore total
operation time and remaining quote headroom are not complements of ten seconds.
No deadline or request budget is increased.

The existing exact-content text, hash, encoding, signature and admission-history
reuse scopes now span this combined operation. They are empty at its start and
cleared at its end. Full input comparisons and source, state, expiry and STOP
checks still run. No authorization decision is cached across operations. The
separate key process independently reconstructs and signs the exact message.

An existing candidate is returned as held without any collection or signing,
including after a lost creation or signing reply. Orphan successor backend files
block collection. STOP, expiration and failed persistence prevent key invocation.
A backend failure after invocation leaves signature effects unknown. A valid
late acknowledgment is retained but cannot produce a timing-pass result.
Recovery validates saved evidence without opening a key or making RPC requests;
it does not create a replacement or release reservations.

## Offline host command

`position-book/successor_signing_rehearsal_cli.py` accepts only `--output`.
It offers no wallet, private-directory, execute or network options. Run the
pinned checkout and exact command supplied in chat; upload only the generated
`radar-successor-signing-rehearsal-*.json.gz` public report. No Docker rebuild,
scanner deployment or service restart is needed.

The command creates a complete temporary source with a 1 MiB program-account
fixture and real clocks. It uses actual collectors with synthetic responses and
an actual independent key process with a disposable key. Historical setup and
retirement are separately measured; their exact-content reuse scopes are closed
before the measured successor operation. Keyless recovery and original ledger,
marker and cumulative-hold preservation are then checked. All temporary material
is removed. The fixture's amounts are synthetic, not a current host balance audit.

Expected success is `offline-integration-passed`, four fixture setup checks,
four backend replay checks, 11 boundary checks and five connected checks. The report must show positive original-deadline headroom,
unchanged original source, preserved holds and completed cleanup. A failed phase
or expired deadline requires investigation; it is not permission to retry an
operational signing attempt or relax freshness.

## Local evidence

- All 11 boundary cases passed: opt-ins, successful composition, repeat refusal,
  uncertain backend response, STOP, collection expiry, orphan markers,
  post-persistence expiry, disk rollback, cleanup deadline and late acknowledgment.
- All five connected checks passed with real clocks and the 1 MiB fixture.
- Complete integration: **4,609.436 ms**; original-deadline headroom at return:
  **6,711 ms**. Collection and persistence took 1,640.449 ms; signing handoff took
  2,961.398 ms, including 856.387 ms in the independent backend adapter.
- Recovery passed after removing the disposable key and setting STOP. Repeated
  recovery left the ledger bytes unchanged. Old tables, old markers and all
  original private source files were preserved; no holds were released.
- Six CLI scope/output refusals and two CI partition-coverage checks passed.
  Source hygiene and package manifest checks passed.

Earlier local runs stopped in prerequisite retirement and final accounting
verification because an uncached history replay exceeded its existing read
limit. Those rehearsal-only reads now use the existing exact-content replay
scope. The measured signing path already met its deadline in the second run;
only the final complete pass above is accepted. No timeouts were enlarged and
no failed check was omitted.

These timings exclude real RPC and finality latency. They do not establish host
performance, live submission headroom, or successful devnet settlement. The
primary connected run includes normal parent acknowledgment persistence; lost
child responses are covered by the accepted component tests and the integration
fault cases, not presented as an additional live result.

## Finite next gate

After Kali accepts this complete rehearsal, bind a single controlled devnet send
and read-only signature recovery to this exact successor generation, with exact
receipt reconciliation and scoped closure. Retired wire denial, cumulative fee
exposure and original deadlines remain mandatory. No live sender, execution
command, scanner change or trading-policy change is included here.

The frozen gain and availability study decisions remain unchanged. This gate
measures mechanical reliability, not an economic edge or real-money approval.
