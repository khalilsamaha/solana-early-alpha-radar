# Scanner consumer supervision — 15 November 2026

## Published base and change

The approved capture/session package is published on
`research/r1-offline-capture-20261111` at
`c4e45f2cad2a7805b355b3e291193ecaa3ac5855`. Tree
`089a6e04c3c5d2f0d57b627f1bd973f92b147328` exactly matches the tested local
`726a938` tree. Main is unchanged.

The new local increment connects the manifest-supervised capture to the existing
Node scanner-adapter fixture through an inherited pipe. The Node process uses the
actual shared-discovery adapter and LaunchRegistry; no scanner loops or live
upstream run. The Python child still uses a fixed in-memory upstream and produces
real SQLite capture, measurement journal and retirement/shutdown evidence.

The parent consumes the durable claim and storage gate before starting Node,
verifies readiness, rechecks source/manifest/preparation and then starts capture.
Only the owned pipe write descriptor is passed into the worker. Parent descriptor
copies close after handoff. Worker and scanner collection share one parent wall
deadline, with bounded cleanup for each child. Exact scanner output, successful
capture/journal replay and reaping receipts are all required for success. No
zero-exit or disposal-only shortcut can confirm missing scanner evidence.

| Case | Node tokens / creations | Capture cleanup | Discovery after retirement |
| --- | --- | --- | --- |
| Normal | 3 / 2 | unsubscribed | Later creation delivered and counted |
| Cleanup failure | 2 / 1 | upstream-aborted | No later creation |

In the normal case, the worker waits for the delivery counter before shutdown.
The actual Node result must include creation, migration and the later creation,
plus one terminal discovery gap. Cleanup failure requires only the first two
events. These are bounded fixture outcomes, not coverage or profitability claims.

## Verification

[Retained validation](evidence/r1-scanner-supervision-development-20261115.json)
records 51 passing tests, zero failures/errors/skips and 191 source hashes. Local
Linux run: 2026-11-15 18:05:03.263035–18:05:27.534871 UTC
(19:05:03–19:05:27 CET). No parent diagnostics were captured. Child stderr is
intentionally discarded; no comprehensive child-diagnostics scan is claimed.

Twelve new scanner tests cover actual Node consumption, normal/adverse event counts,
lost scanner confirmation, lost readiness return, worker spawn failure after Node
start, missing Node, uncertain reaping, capacity rejection before actor creation,
receipt tampering, short-fixture duration admission, malformed zero-exit results,
and changed inputs after scanner readiness. The existing 39 supervision/capture
tests pass unchanged. All started test children were reaped, including fault
cases whose retained supervisor outcome correctly remains unresolved.

Historical inspection reads the retained scanner result without starting/querying
Node or repairing capture artifacts. A missing supervisor terminal does not
confirm either process history. The expanded source and result schema require
older receipts to be inspected with their exact recorded source revision.
Accepted scanner adapters, Node fixture, capture/session and native handoff sources
are unchanged; this increment integrates them through the supervisor.

## Scope and next intervention

This is a development pipe integration, ready for publication review against
`c4e45f2cad2a7805b355b3e291193ecaa3ac5855`. It is not yet published. No standalone
Kali rerun is requested. Docker is unavailable in this workspace; no Docker/native
check was attempted or claimed. This work does not establish Unix peer identity,
container isolation, an accepted scanner image or host-wide production ownership.

Manifest kernel limits apply to the Python capture child only. Node retains its
existing fixed twelve-second fixture timer and the parent's shared wall deadline;
its receipt explicitly denies image verification and manifest kernel-resource
application. This mode accepts research at most three seconds, service at most
five seconds and aggregate wall at most twelve seconds. These fixture bounds do
not approve pilot limits or demonstrate resource adequacy. Scanner kernel/resource
and parent-death containment still need integration before production readiness.

Remaining work: actual production target/configuration/ownership, native scanner/
Unix integration, scanner resource controls and phase shutdown, credentials,
variable-session delivery/retention, live resource adequacy and exact pilot terms.
The five-focused-working-day cap remains unchanged; consumed/remaining effort is
still unquantified. No new allowance or study start is asserted.

No production/main/E0 action, paid provider or remote transfer occurred. E0 remains
blocked with holds preserved; this adds no E0 closure receipt or fresh host/RPC
observation and reports no current balances. Its November 20 evidence-based
checkpoint and reopen criteria remain unchanged.
