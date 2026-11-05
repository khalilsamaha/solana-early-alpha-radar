# Canonical digest continuation integration — November 5, 2026

## Host observation accepted; actual exit remains open

The 04:58 CET inspection and observation reports passed their respective read-only
checks. The original and replacement identities are unchanged. Quantity 998,
protected inventory 500,000,000 and fee commitment 25,000 lamports remain held.
No preparation, private-key access, signature, send or release occurred.

| Measurement | Nov 4 baseline | Nov 5 observation |
| --- | ---: | ---: |
| Collection | 7,737 ms | 7,114 ms |
| Preserved validation | 1,405 ms | 1,067 ms |
| Headroom after validation | 858 ms | 1,819 ms |
| Final binding + preserved validation | 3,319.221 ms | 2,721.535 ms |
| RPC-containing stages, including their local work | 5,810.323 ms | 5,448.283 ms |

The final local stages were about 18% shorter in these two observations. Network
stages also improved, so this is not a controlled causal estimate of the cache's
contribution. The 1,819 ms excludes persistence, signing and submission. It does
not authorize an execution retry or establish operational timing reliability.

The cache reported 740 hits in 1,047 calls, 57 unsupported-input bypasses, no
computation failures, and 28,091,947 retained bytes within its 32 MiB budget.
Unsupported input follows the original hash calculation; bypass is not a failed
validation. All SQL reads and current-state checks still ran.

Compressed public report SHA-256 values:

- Inspection: `df478938c47877a940682f2cc53c553006086ffb6c949823e032f1c39c22eee5`
- Observation: `b6651943ae14487a23e293f3eccd09d40491c290cd2ad74742eee787f4a29c6b`

## Engineering change

The existing exact-content digest scope now surrounds the explicitly authorized
`continue_sign_submit` operation. It covers fresh collection, preparation,
Python signer handoff and one-send checks, then clears on success or exception.
The ordinary fresh-exit, replacement and recovery wrappers do not open the scope.
The independent Node signer still reconstructs and validates its own inputs;
Python cache contents and verdicts are never passed to it as authority.

The original three explicit opt-ins, exact predecessor identities, one
continuation limit, ownership and protected inventory, fee holds, STOP markers,
freshness deadline, thirty-second budget and durable one-send boundary remain
mandatory. The scope stores only an exact-content-derived digest, not a permission
or source read. Changed records and timestamps obtain different keys. Existing
source validators still run. Failed or unknown attempts retain reservations and
never automatically repeat signing or sending.

The controlled report exports only a bounded allowlist of digest counters.
Malformed counters are omitted as diagnostics, never used to accept an operation.
The cache's retained-byte cap is not a process RSS limit.

## Rehearsal and host gate

The existing offline continuation CLI adds `--large-fixture`, a fixed 1 MiB
synthetic program-account workload. It has no wallet, endpoint, execution or
permission arguments. The test builds historical fixtures with that account data
and verifies the actual captured size before claiming the expanded workload ran.
It does not rewrite user journals, relax record caps or change the devnet
baseline. Temporary fixture globals are restored on exit.

The fault matrix uses the public continuation wrapper, including its digest
scope. The connected fixture uses a real isolated disposable-key signer,
synthetic provider replies, a deliberately lost send response, read-only recovery
and repeat refusal. It checks predecessor and entry-accounting preservation and
runs fourteen independent signer tampering cases. Its original deadlines remain
in force. All measurements exclude real provider latency and chain finality.

## Local acceptance result: timing gate remains blocked

Thirty-eight targeted Python tests passed: six new integration/fixture tests,
ten canonical-digest tests, seven diagnostic tests, ten controlled command tests,
three existing connected continuation/CLI tests, and two test-partition checks.
The small connected fixture passed sixteen fault/integration cases and fourteen
independent signer checks. Source hygiene, package manifests and changed-source
syntax checks also passed. These are correctness results, not large-workload
latency acceptance.

The first **verified** 1 MiB connected run stopped before a synthetic send with
`exit-signing-expired`, taking 12,352.497 ms. It ran alongside another heavy test.
An isolated unprofiled rerun also failed the full completion gate:

| Isolated large-fixture stage | Elapsed |
| --- | ---: |
| Collection and persistence | 2,981.702 ms |
| Signing handoff | 3,267.270 ms |
| Submission including local bookkeeping | 6,160.194 ms |
| Complete continuation operation, including eligibility | 12,813.567 ms |
| Remaining headroom at completion | −1,463 ms |

The isolated run reached one guarded **synthetic** send and the deliberate lost
response; final completion was late. It therefore remains `review-required`,
with `rehearsal-original-expiry`. Eleven preliminary fault cases passed; the
large run did **not** reach the subsequent preservation, signer-contract and
recovery assertions. It made no real network request, used no user wallet and
removed its temporary journals. A late report after a guarded send is distinct
from an attempted send after expiry; the original send-time checks were retained.
Neither failure is reclassified as successful acceptance.

The digest counters show 7,585 hits in 9,067 calls, 1,482 computations and 1,431
evictions within 32 MiB. This suggests repeated large-evidence serialization and
cache churn deserve focused profiling; it does not justify increasing resource
caps or caching authorization. Instrumented profiling also identifies repeated
source/signing reads inside the submission phase. Profiling overhead is excluded
from the table above.

An initial fixture-hook experiment affected a different fixture generator and
left the connected account small. That run is excluded from expanded-workload
evidence. The new actual captured-size assertion and regression test prevent
that mislabelling from recurring.

This branch remains an unmerged integration candidate. The next engineering
focus is bounded exact evidence-processing reuse in the signer handoff/submission
path, keeping SQL rereads, source integrity, STOP, current balances and deadline
checks. Rerun the fixed large workload locally before another host acceptance
request. No additional Kali command or operational retry is prescribed for this
candidate. Actual exit receipt reconciliation and scoped closure remain pending.
Scanner deployment, quote observer, alerts, Backblaze and the November 5/6
availability captures are unchanged.


Local isolated public report SHA-256: `3d3cd0e78de22f8d0571e9973667f59da16ccfcb19932326bb86ec1d7275ea26`.
