# Consistent exit reads — November 6, 2026

## Host evidence and next gate

The November 6 Kali large-fixture run remains `review-required`. Eleven preliminary
fault checks passed. Both predecessors were prepared and the continuation made
one synthetic send with the expected lost response, but completion missed its
original deadline by 457 ms (12,710.988 ms elapsed). Independent signer-contract
and recovery acceptance were not reached. No real RPC, production wallet or
production ledger was used.

Compressed host report SHA-256:
`b1b8f26f8361a6657da165b68660dfc4b725afeff83df925a1211f98ccac98f6`.

A local submission-only cProfile run found 14 preserved-generation reads in one
submission, including 11 signing replays and nine transport signing reads. Three
transport signing reads came from one status result. The synthetic adapter added
two preserved-generation reads; its measured cost remains included in the gate.
Profiling overhead means these timings are diagnostic, not acceptance results.

## Correction

An exit status now reads the signing chain once in a consistent SQLite snapshot,
then checks the send boundary, acknowledgment and receipt captures against that
same state. Initial sender inspection and precommit inspection each share their
own signing read with their boundary check. Source validation, backend
acknowledgment, the independent signer and the fresh precommit checks remain.

The snapshot sets `query_only` for its duration. It rolls back only the read
transaction it opened, restores the prior query-only setting, and preserves a
caller's existing transaction. Two pure read helpers (private entry-accounting
handoff and receipt status) join an enclosing transaction rather than attempting
a nested BEGIN. Their standalone behavior is unchanged. No general write
transaction semantics were modified.

No validated state is cached on the object, across calls, across RPC requests, or
across writes. A subsequent call reads the database and revalidates its evidence.
Every existing record schema, bounded read, hash, signature, raw receipt,
preflight, clock and ownership check remains. A competing writer cannot commit
halfway through the snapshot; exceptions release the read lock. No new cache or
memory budget is added.

The offline report counts preserved-generation reads during submission and
separately times `synthetic-sender-adapter-setup`. This is a
nested diagnostic phase only: it is not subtracted from the full elapsed time,
and no deadline, real clock, simulated reply or fixture size is changed.

## Scope and acceptance

The changes affect the engineering exit transport and read-only recovery, plus
the two entry evidence readers they call. They do not modify scanner polling,
Telegram alerts, provider budgets, research labels, study registration, backups
or production services. There is no scanner rebuild or service restart.

Required validation includes transaction ownership and read-only enforcement,
competing writers, source changes during preflight, corrupt signing after send,
corrupt stored boundary/captures, crash and expiry no-retry behavior, unchanged
public results and stopped/keyless recovery. The real-clock 1 MiB connected
rehearsal must pass all 16 integration/fault checks and 14 independent signer
checks before prescribing a pinned Kali offline run.

Host acceptance remains separate from local verification and actual devnet
execution. The pending batch stays unmerged until the Kali report is reviewed.
No new actual held-position attempt, additional generation or mainnet permission
is part of this release.

## Targeted local regressions

78 targeted regression tests passed: 18 exit transport/snapshot/restore tests,
58 entry-handoff, receipt, continuation-scope and diagnostic tests (including the
sixth new query-only snapshot test), plus two partition checks. The portable exit
suite exercised all 24 existing fault/recovery cases. New tests verify that two
separate status calls perform two full signing replays, not a retained verdict;
mutations between calls are rejected and restored evidence is re-read normally.
A competing writer cannot commit during the snapshot, and a signer-row mutation
after the simulated send is detected before acknowledgment persistence. The
send boundary remains recorded and no retry is introduced.

Source hygiene and immutable package manifests passed for 863 tracked files;
changed Python modules compile and whitespace checks pass. The real-clock full
large-fixture result and Kali acceptance are separate gates.

## Final-source connected result

The complete real-clock 1 MiB synthetic rehearsal passed 16 integration/fault
checks and 14 independent signer checks. Continuation elapsed time was
**5,099.893 ms**, with **5,885 ms** completion headroom. Collection/persistence
was 1,598.219 ms, signing handoff 1,529.583 ms, and submission 1,675.846 ms.
Synthetic sender setup was 265.094 ms, included within submission and the full
gate. Preserved-generation reads during submission decreased from the profiled
14 to **10**, with all ten still running their normal validators. The original
profile is instrumented, so its wall time is not a like-for-like benchmark.

One fake lost-response send was followed by stopped/keyless recovery and repeated
read-only recovery without another send. Both predecessors, source and entry
accounting were preserved. The run used zero real network requests and no user
wallet or production ledger; disposable test files were removed.

Compressed public report SHA-256:
`57fe2c81710405c1562f1b312daf0785b4e58afc77603bce77acf2849e4fe5b3`.

This local result does not establish Kali or real-network timing. Run the pinned
offline large-fixture CLI on Kali next and review both timing and recovery checks.
Keep the branch unmerged and the held operational position untouched meanwhile.
