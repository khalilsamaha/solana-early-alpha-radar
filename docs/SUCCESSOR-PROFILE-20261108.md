# Offline successor phase-cost diagnosis — November 8

Current acceptance: the full Kali CLI passed all 42 checks at 08:07:13 UTC on
November 8, with 1,343 ms remaining. Recovery, preservation and cleanup passed.
The [consolidation record](SUCCESSOR-CONSOLIDATION-20261108.md) preserves the
failed run, diagnostic result and current phase status. Earlier pending states
below are historical. Real-provider execution and settlement remain separate.

Current status: the 05:38:36 UTC Kali profile supplied valid diagnostic evidence
but missed timing by 827 ms before sending. Its findings and the next bounded
correction are recorded in [lifecycle snapshot replay](LIFECYCLE-SNAPSHOT-REPLAY-20261108.md).
The current uninstrumented acceptance gate has 42 checks. Counts and local
measurements below describe the earlier diagnostic package, not current acceptance.

## Why this is the next gate

The 04:21:39 UTC Kali report for the pinned-snapshot correction passed all 27
preliminary checks but missed the connected completion deadline by 216 ms.
Signing left 3,894 ms; submission took 4,104.592 ms. One synthetic send occurred.
The final guard retained the unknown outcome and refused acceptance. Recovery
and preservation assertions were not reached. No real transaction occurred.

The identical base commit passed the uninstrumented 34-check command locally in
4,881.511 ms with 6,448 ms headroom. A local pass does not explain the host's
performance or satisfy Kali acceptance. Before another optimization, collect
comparable phase data on the actual host.

## Diagnostic boundary

`position-book/successor_profile_cli.py` accepts only `--output`. It invokes the
existing disposable, synthetic-network, real-clock 1 MiB connected rehearsal.
There are no wallet, execution directory, provider, signing or submission flags.
The existing fixture blocks sockets, owns its temporary ledgers and disposable
keys, and removes them on completion or phase failure. Original application
clocks, deadlines, STOP checks, validators, request limits, signing markers and
one-send rules are unchanged. No operational execution code was modified.

Only the first collection/signing/submission phase is instrumented. Setup,
predecessor expiry, recovery and preservation run normally outside those spans.
Patches are removed on exceptions as well as success. The command does not run
the separate 27 preliminary tests and never substitutes for the 34-check CLI.

At most 4,096 spans record fixed stage names, parent indexes, wall timestamps,
elapsed time, current-thread CPU time and completion flags. Stages cover:

- Collection/persistence, signing handoff and independent signer invocation.
- Lifecycle, retirement, preparation, successor and current-binding replay.
- Transport load/replay/append and individual preflight/send requests.
- Journal open and transaction enter/commit/rollback context-manager work.

Transaction stages include read-only and writable Journal contexts; they do not
claim to measure disk flushes alone. Direct SQLite snapshot operations outside
Journal.transaction remain in their containing stages. The synthetic RPC spans
include the request helper's guards and response handling, not real network latency.

The report includes Python/Node versions, logical CPU count, Git HEAD and a dirty
worktree flag before and after the exercise. These are local observations, not
independent source attestation. No hostnames, source paths, SQL, call arguments,
transaction bytes, private keys or arbitrary exception text are exported.

## Interpretation

`diagnostic-collected` means one measured phase produced valid span data. The
underlying rehearsal may still be `review-required`, including because the
instrumentation itself consumed its deadline. Partial spans remain useful.
`timingAcceptance`, `fullAcceptanceSuiteRun` and `executionApproved` are always
false. A missing measured phase, bad diagnostic clocks or span-cap overflow
produces `diagnostic-incomplete` and a nonzero CLI exit after publishing the report.

Inclusive times overlap. Exclusive values subtract directly recorded child
spans, not all uninstrumented work. Thread CPU excludes the independent Node
process. Wall time minus thread CPU includes child waits, I/O, scheduling and
measurement effects; it cannot identify any one of these as the cause by itself.
The original deadline is applied to each span's end timestamp after the run;
it is never reset, extended or supplied to the application's clocks.

## Local validation

Ten diagnostic tests and four existing continuation-profile tests passed with
ResourceWarnings treated as errors. They cover nested timing accounting, partial
failure, instrumentation restoration, scoped activation, bounded output, bad
diagnostic clocks, transaction suppression/rollback/entry failure, runtime-value
sanitization and CLI rejection of operational flags or existing/symlink outputs.

The complete diagnostic CLI reported 347 valid spans, seven connected checks,
successful recovery/preservation/cleanup, 4,930.227 ms total and 6,349 ms headroom.
These are instrumented local observations, not a new timing acceptance result.
The local worktree was marked dirty because the diagnostic was under development.
The largest exclusive groups in that sample were 46 preparation replays
(1,984.378 ms), other lifecycle work (1,343.210 ms), signer-backend work
(542.300 ms) and successor-binding work (446.783 ms). This locates costs on the
local machine; Kali profiling must establish its own distribution.

A separate fresh run of the unchanged uninstrumented acceptance CLI passed all
34 checks with this diagnostic addition present: 5,016.996 ms and 6,326 ms
headroom, including recovery, preservation and cleanup. Source hygiene/package
manifests passed for 940 tracked files, both partition-coverage tests passed and
the staged diff passed whitespace checks. The full repository suite and hosted
CI were not run for this development diagnostic; this is not a merge or release
candidate approval.

## Kali command

Use the immutable development commit supplied in chat, then run from the existing
project directory:

```bash
python3 -B -E -s -W error::ResourceWarning \
  "$HOME/apps/solana-radar-dev/position-book/successor_profile_cli.py" \
  --output "$PWD/radar-successor-cost-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Upload the resulting public report even if its underlying rehearsal is late.
No Docker restart, service installation or operational wallet action is needed.
Compare the host's span counts and stage costs, runtime metadata and location of
deadline crossing before designing a bounded correction. After a correction,
the full uninstrumented Kali gate (now 42 checks), including recovery and
preservation, remains required. Real-provider timing and exact successor receipt
reconciliation remain later separately authorized gates.
