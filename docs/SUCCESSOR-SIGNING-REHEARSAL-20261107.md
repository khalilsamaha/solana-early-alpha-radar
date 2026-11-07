# Connected successor signing rehearsal — 7 November 2026

## Accepted prerequisite

The Kali independent-backend report captured at 19:21:34 UTC passed all 50
cases: 41 Node backend cases and nine Python adapter/recovery cases. These
component tests used disposable keys and synthetic providers. They did not
measure complete collection-to-signing latency.

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

Expected success is `offline-integration-passed`, 11 boundary checks and five
connected checks. The report must show positive original-deadline headroom,
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
