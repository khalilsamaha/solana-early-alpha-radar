# R1 session, evidence and measurement increment — 13 November 2026

The owner requested continued engineering with chained local validation and a
consolidated Kali handoff. This increment addresses three connected gaps:

1. A reusable one-attempt session coordinator replaces delayed-first-frame and
   fixed-fixture coordination assumptions. Journal readiness gates upstream reads;
   capture deadline wake-up precedes the ordinary polling interval; stop/failed
   startup/failed sends/failed cleanup preserve their evidence and do not retry.
2. A bounded portable archive binds arbitrary candidate-session captures,
   measurement journals, admission, stop receipts and exact source identities.
   Isolated restore recomputes data and command relationships. Active, incomplete
   or rollback-bearing sources cannot acquire a complete archive marker.
3. The draft evaluator now distinguishes completed subscriptions from all completed
   commands, so a watch-expiry unsubscribe does not inflate the subscription
   completion fraction or invalidate latency denominators. All approval flags
   and numeric acceptance criteria remain unchanged.

## Local validation

Final status: `candidate-session-development-passed-unix-pending`.
Python 3.12.14, hash-pinned websockets 17.4. **157 tests**, zero failures/errors/
skips, zero captured ResourceWarning/unraisable/task diagnostics; **19.476246 s**
for tests plus retained scenarios. All **156 source fingerprints** agree before
and after the run. Syntax, shell syntax and source hygiene are checked separately.

Eight end-to-end scenarios each produced and restored its own archive: normal,
different-size, idle deadline, watch expiry, operator stop, send failure, provider
failure and cleanup failure. Failures remain failures after successful evidence
restore. Test coverage includes first-frame retention, cancellation/worker join,
failed startup, no rearm, wrong source/hash/limits, receipt mutation, unrelated
cleanup, source mutation, live locks, rollback evidence, ZIP metadata bounds,
path aliases, output reuse, low disk and failed final receipt writes.

| Final local evidence | SHA-256 |
| --- | --- |
| report.json | `26c6b8b7f6def1ce66aee5a3b9e415f5e476142a4b3dc63ceeef31679bc07b87` |
| validation.log | `7be79210a7d679aac24d6406083c6d12db2ac4c1fada8eb3d5d97bdfe464ce3e` |

The first local native-socket attempt failed because this environment denies Unix
socket creation. Development uses an explicit simulated endpoint and records
`unix_peer_uid_verified=false`. It is not native IPC acceptance. Earlier failed
development checks also exposed the deadline/poll ordering bug; the final batch
above includes its correction. No repeat timing rehearsal or E0 action occurred.

## Kali handoff

Use a fresh private directory whose checkout is named `source`, fetch the exact
published development commit, verify HEAD and invoke `scripts/r1-session-kali.sh`.
The script checks clean source, creates an isolated virtual environment, installs
only the existing hash-pinned wire dependency, checks source hygiene, then runs
the batch within a 180-second process budget with a 10-second kill grace.

The default batch requires real Unix IPC in all eight retained scenarios. The
existing Node scanner adapter is used for normal, different-size, watch-expiry
and failed-cleanup cases. No production container is read or changed, and no
provider, B2, credential, wallet or RPC is used. There is no silent simulated
fallback. Upload **results/acceptance.zip**; it contains report.json,
validation.log and eight archives for independent review. If interrupted or
failed, preserve the complete directory and supply the available report/log.

## Limits and remaining work

This is a library candidate and local preservation implementation, not a live
launcher. Actual process containment, private credential provision, global
connection ownership, production handoff/rollback, provider/TLS validation,
approved live retention/capacity and numeric exposure authority remain open.
The fixed B2 adapter remains restricted to its previously accepted synthetic
packages. An available-space check is not a reservation or continuous disk quota.
No source adequacy, billing cutoff, historical completeness or profitability is
inferred. Incomplete run bytes stay in place; there is no repair/resume/delete.

The evaluator correction deliberately changes source fingerprints. Previous
fixed B2 artifacts retain their original accepted revision
`04209213b38fdc29a37e0b830bc10cc09ed3f294`; review them there, not against this new
source set. No historical artifacts or operational journals were rewritten.

Kali acceptance precedes full-phase consolidation/PR/CI and a separate merge
decision. Main, production and E0 remain unchanged. This increment neither resets
nor extends the five-working-day R1 engineering cap. See
[agenda status](R1-STATUS-20261113.md) for the remaining study dependencies.
