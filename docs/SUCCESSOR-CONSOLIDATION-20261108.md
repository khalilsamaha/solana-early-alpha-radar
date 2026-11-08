# Successor execution consolidation — November 8, 2026

## Accepted host gate

The full uninstrumented Kali rehearsal captured at 08:07:13 UTC passed all
42 checks: 4 setup, 12 boundary, 5 scope ownership, 6 retirement snapshot,
8 lifecycle snapshot and 7 connected cases. No case failed or was skipped.
The measured collection/signing/submission path took 11,889.065 ms and returned
with 1,343 ms of positive headroom on its original deadline. Earlier work before
fresh collection is included in the path total; the ten-second freshness limit
was not enlarged.

Twenty-eight collection requests and five transport requests included exactly
one synthetic send with a deliberately lost response. The durable unknown
outcome was preserved. Repeated composition did not recollect, resign or resend.
Stopped, keyless observation recovered the same signature; terminal recovery
made no new request or write. Source, retired history, inventory and fee holds
remained preserved. No receipt accounting or scoped closure was inferred from
the finalized claim. Cleanup completed, with zero real network requests or
transactions and no production-wallet, ledger or scanner-runtime changes.

The provided host command pinned development commit
`82595a9b3cf556b5960b97b59af591478e2480da`, tree
`c607a550ab61093773fc35db211fe48113459221`. The preceding profile independently
reports that commit and a clean checkout before and after its run. The full
rehearsal reports version markers, not its own Git SHA; source attribution is
based on the pinned command and adjacent profile, not a claimed attestation.

## Evidence retained

| Report | Captured UTC | Outcome |
|---|---|---|
| `radar-successor-execution-rehearsal-20261108T055852Z-2540047.json.gz` | 06:02:26 | 35 preliminary checks passed; connected phase failed 53 ms late before sending; cleanup passed, preservation not reached |
| `radar-successor-cost-20261108T075900Z-2827636.json.gz` | 08:00:23 | Valid profile; 7 connected cases passed; 12,573.094 ms total, 853 ms headroom; not full-suite acceptance |
| `radar-successor-execution-rehearsal-20261108T080236Z-2837810.json.gz` | 08:07:13 | Full 42-check acceptance; 11,889.065 ms total, 1,343 ms headroom; recovery, preservation and cleanup passed |

SHA-256 of the original compressed report bytes, in table order:

```text
b8b4baaa4c67bceac65fce5f0c3cd686020ad650f12fed310a14314a6a0ade41
a3016f05efc431e78c2054b5502dcc6e61b7461998c2300f234432d727b9f4e1
8cdd7843980c71309230892feabe0bdff45e494d71b3691a558046bfaebbb374
```

The pass meets the registered offline gate; it does not erase the previous
failure or establish robust latency under host load and real RPC providers.
No additional runs were discarded or combined into a synthetic 42-check pass.

## Batch and consolidation boundary

Base: main `d1153636db104295b9a8812565a1db17b1e47738` (PR #78).
The accumulated batch adds a separate unsigned successor contract and bounded
collection, generation-specific durable signing and independent key backend,
one-attempt submission with exact-signature recovery, connected real-clock
offline rehearsal, bounded profiling and scoped replay reductions. It preserves
retired generations, cumulative holds, fresh source checks, locks, STOP rules,
original clocks/deadlines and conservative unknown outcomes. Computational reuse
ends at its explicit owner; semantic evidence reuse stays inside its snapshot.
No operational successor execution CLI or default network adapter is added.

The consolidation review checked the three explicit execution opt-ins, exact
generation/request/ACK binding in both parent and independent child, the durable
signing marker before signature creation, source replay after the child and after RPC,
pre-send transaction and original-deadline guards, no resend after an unknown
boundary, keyless same-signature recovery, conservative accounting projections,
and bounded computational/snapshot ownership. Existing original-generation
validation remains the default; the successor uses its separate schema.

Host acceptance allows the agreed full-check/PR/CI/merge cycle to begin. Local
consolidation checks passed through the repository's twelve CI groups
(`core-base`, `devnet-pool`, and all ten position-book partitions), covering the
same suites as `scripts/check.sh all` with position-book modules isolated as in
CI. Test-partition coverage validates that every module is selected exactly once.
Required checks must pass on the final PR head before merge; post-merge checks
must also be verified. No tests, deadlines or required checks may be skipped to
clear consolidation. All twelve local groups passed, including the complete
partition-2 recheck described below. Source hygiene/package manifests passed
for 944 tracked files, both partition-coverage tests passed and the staged diff
passed whitespace checks. Hosted CI and merge verification remain the next gate.

The first local partition-2 run failed one assertion in
`test_unresolved_exit_retains_real_journal_reservations`: the unscoped read hit
`reservation-read-deadline` before the expected `closed-history-required`
rejection. This assertion tests a semantic historical-mode refusal, not host
timing. It now uses a fixed fixture clock, matching the adjacent closed-history
test. Its preceding normal inspection and preservation assertions remain, as do
the separate clock-regression/deadline/future-ledger tests. No production clock,
deadline or acceptance-rehearsal code changed. The complete affected partition
was rerun and passed all 17 modules, including all 19 reservation-view tests;
the first failure is retained rather than counted as a pass.

This phase does not deploy the scanner, restart Docker, activate a model, sign
with an operational key or submit a real transaction. Next work addresses a
separately scoped operational command and provider timing, followed by exact
successor receipt effects, residual balances and durable closure. The research
decisions remain unchanged; see the [conditional timeline](PROJECT-TIMELINE-20261108.md).

## CI partition correction

The initial PR run `42463521461` cancelled partition 3 at its ten-minute runner
limit, while it was still running signed-exit timing tests. Completed tests in
that job reported no assertion failure, but the unfinished run is not accepted.
The read-snapshot module took 77.714 seconds and the retired-successor module
took 31.410 seconds there. Partition 0 completed in 414 seconds. Both modules
move from partition 3 to partition 0, balancing the measured work without
changing test contents, the twelve-job matrix or any runner/application deadline.

All modules had already passed locally in isolated per-module processes. The
assignment change is checked with the two partition-coverage tests and an exact
before/after module-union comparison; nothing is omitted or duplicated. The full
twelve-job CI run must pass again on the updated PR head before merge.

## Hosted runner budget correction

The rebalanced run `42464398047` passed partition 3 but cancelled partitions
0, 2 and 4 at the ten-minute runner cutoff. Their available logs show no failed
assertions. Partition 2 printed successful completion of every module immediately
before cancellation; that cancelled job still does not satisfy acceptance.
Unchanged partition 2 had completed in 507 seconds and partition 4 in 502 seconds
on the prior run, showing that the earlier remaining margin was insufficient
under observed runner variation.

Keep the measured reassignment and all twelve jobs. Give position-book jobs a
15-minute runner budget, with 20 minutes for partition 1, whose complete local
run took 988.279 seconds. Core and devnet-pool jobs retain ten minutes. This
changes only how long GitHub permits each entire regression job to run: every
test, per-test timeout, application clock, freshness limit, STOP guard and
acceptance assertion remains unchanged. No cancelled run is treated as a pass.
The updated full PR run and post-merge run must both complete successfully.
