# Read-only canonical digest reuse — November 4, 2026

The November 5 host observation passed. See the subsequent
[continuation integration](CONTINUATION-DIGEST-INTEGRATION.md) for the current
scope and acceptance status; the sections below record the observation-only release.

The 19:54 UTC host reports confirm that the exact expired original/replacement
pair remains eligible for the separately controlled continuation. Inspection made
no RPC request. Observation completed all twenty fixed requests without modifying
journals, signing, submitting, releasing holds or consuming another preparation.

Collection took 7,737 ms, preserved validation another 1,405 ms, leaving **858 ms**
of the original deadline. The four RPC-containing stages totalled 5,810.323 ms;
this includes their local work, not just network latency. Final binding and
preserved validation, which make no RPC requests, totalled **3,319.221 ms**.
The 11,677.616 ms overall phase timer additionally includes admission checks before
the freshness window. Observation success does not prove that persistence,
private signing and transport fit. The earlier failed operational attempt's
underlying cause remains unproven. Do not repeat execution based on this report.

## Implementation

Only `preserved_exit_observation.observe` opens the new operation-local scope.
The common contract digest function retains its original canonical JSON and SHA-256
behavior everywhere else. The actual fresh-exit/continuation execution path does
not open this scope. There is no new execution option or runtime deployment.

Within observation, a digest may be reused only after rebuilding an exact typed
immutable key from the **complete current input content**. Dictionary order is
canonicalized; list order, booleans versus integers and all string contents remain
significant. Object identity and a caller-supplied hash are never sufficient.
On a miss the original serializer hashes a materialized copy of that immutable
key, so later mutation cannot poison the stored result. Only exact built-in JSON
containers/primitives qualify. Floats, subclasses, cycles, excessive depth/size
and unsupported inputs follow the original serializer and error behavior without
reuse. Errors are not retained.

Every SQLite reread, source/ownership validation, balance check, lineage replay,
STOP check, expiry check and collection deadline remains in place. No permission,
validation verdict, current balance or ledger-read result is substituted. Hash
calculation is a pure conversion, not evidence acceptance. Changed records remain
subject to full validation even when their hashes were recomputed by an attacker.

The scope retains at most 128 entries with a conservative 32 MiB retained-content
budget and a 16 MiB per-entry limit, using least-recently-used eviction. Keys have
at most 8,192 nodes and depth 48. These are cache limits, not a process RSS limit:
normal parsing, transient key construction and serialization use additional memory.
All retained content is discarded on return or exception; nested scopes are
isolated. Reports expose only counters under `canonicalDigestReplay`, never the
retained content or transaction bytes. There is no disk cache.

## Measurement and acceptance

The broader full-JSON-text cache was not shipped: its connected large-fixture
comparison did not improve overall observation time. This change retains only
canonical digests. Small records can incur extra traversal overhead, so the large
connected benchmark and the actual host timings both matter. Synthetic RPC replies
cannot establish network latency or operational execution readiness.

The fixed connected benchmark can be reproduced locally with
`python3 -E -s position-book/canonical_digest_benchmark.py`. It builds disposable
ledgers with a 1 MiB synthetic program account and compares disabled/enabled/
enabled/disabled scopes. The final implementation measured 1,228.032 and
1,184.896 ms disabled versus 1,062.665 and 1,029.716 ms enabled (about 13% lower
mean elapsed time in this local comparison). Both enabled runs reported 829 reuse
hits across 1,032 calls and 31,936,476 conservative retained bytes. This is a small
sample, not a host latency prediction or general performance guarantee. A second
run of the saved benchmark measured 1,147.210 / 976.754 ms disabled and
945.002 / 1,075.436 ms enabled, only about 5% lower mean elapsed time; individual
runs overlap. Treat this as a modest experimental gain requiring host evidence.

Local verification covers canonical hash equality, mutations, input type
boundaries, exceptions, scope cleanup, memory limits and eviction, concurrent
context isolation, unchanged private files and RPC order, and rejection of a
rehashed ownership change. The preserved-exit fault matrix additionally exercises
STOP/expiry, cluster/deployment drift, balance shortfall, source locks and final
validation. The final revision passed 83 local unit/integration tests across chain-reader,
swap-contract, the new connected equivalence/tampering tests, the preserved-exit
fault matrix, collection diagnostics and CI partition checks. Compilation and
source/package hygiene also passed. The reproducible benchmark completed without
network requests. Host performance acceptance and the next batched PR CI remain
pending.

## Host step

Use the exact development commit supplied in chat. First run the zero-RPC local
inspection bound to the original and replacement SHA-256 identities; only if it
passes run one preserved-exit observation. It uses at most twenty fixed devnet
RPC calls, including unsigned simulation. Upload the two public reports. Compare
`observationTiming` headroom, the final-binding and preserved-validation stages,
and `canonicalDigestReplay` hits/budget with the 19:54 UTC baseline.

No Docker rebuild, service restart, new preparation, signature or transaction is
part of this step. Scanner rules, notifications, quote sampling, studies and
Backblaze are unchanged. Keep the November 5 and 6 availability captures. Actual
exit execution, receipt reconciliation and scoped closure remain unresolved.
