# Share exact public signature checks within one continuation attempt

## Observed problem

The November 6 Kali signing profile supplied useful cost evidence, but its
instrumented run was **review-required**, not an acceptance pass. It reported
12678.879 ms total continuation time, -436 ms headroom and 4561.089 ms signing.
There were no real network requests and disposable files were removed.

Aggregate signing costs included 1443.548 ms in poll waits and 233.456 ms in
SQLite. Inclusive profile totals overlap and must not be added. A local call
trace then identified seven historical public signature payloads verified in
collection and verified again in signing. The independent signer was one
separate process invocation. This trace identifies duplication; it does not
establish that every millisecond of the Kali wait category is removable.

## Correction

The enclosing `fresh_exit._run` already owns a bounded exact-wire signature
verification scope. Its continuation collection phase now explicitly joins
that owner through the existing `reuse_current` mechanism. Previously the
nested collection created an independent scope and discarded its accepted
public wire bytes before signing began.

Only the internal continuation call site changes. Direct collection, ordinary
exit, replacement and recovery continue using their previous scope behavior.
There is no new worker process, dependency, key backend, verdict service or
persistent cache. Maximum memo entries remain 64. The owner clears its set on
normal and exceptional exit. Changed bytes are reverified; failures are never
memoized, and full capacity falls back to verification.

Receipt, account, source-state, STOP, deadline, fee, reservation and instruction
checks still execute. The independent signer is unchanged. Durable transactions
and fsync are unchanged. There is no relaxation of the one-send boundary or
automatic retry. No scanner, quote observer, strategy or frozen study deployment
is part of this increment.

## Evidence to collect

The unprofiled large-fixture CLI now reports whole-attempt and per-phase public
signature counters. These contain only bounded counts and timings, not wires
or public identifiers. The expected signing reduction is from eight verifier
subprocesses to one, because the newly signed exit still requires verification.
The independent signer remains separate and is not included in those counters.

Run `position-book/continuation_exit_cli.py --large-fixture --output REPORT.json.gz`
on the pinned development checkout. Compare real host phase times and original
deadline headroom with the previous **unprofiled** report. Profiling runs must
not be used as timing acceptance evidence. A local speedup does not establish
Kali or real-network readiness.

## Validation

Focused tests cover shared scope ownership, cleanup after a lost signer response,
no retry, source changes after collection, direct-call isolation, changed wire
bytes, failures, the memo cap, nested ownership and exceptions. The full connected
rehearsal retains its 16 integration/fault cases and 14 independent signer cases,
including one lost-response send, preserved records and read-only recovery.
The connected regression also checks the phase counters so duplicate verifier
processes cannot quietly return.

Local validation completed: 8 ownership/adversarial tests and the connected
1 MiB run passed. The latter retained all 16 integration/fault and 14 independent
signer cases. It measured 4452.116 ms total and 6372 ms recorded headroom, with
signing at 1170.613 ms. There were 9 verifier launches across the complete attempt:
1 before collection, 7 during collection, 1 during signing, and 0 in submission.
The separate independent signer still ran once. Submission retained 10 preserved
generation reads. These local timings are descriptive; Kali acceptance remains
pending. Sixteen existing continuation diagnostics/digest tests also passed.
