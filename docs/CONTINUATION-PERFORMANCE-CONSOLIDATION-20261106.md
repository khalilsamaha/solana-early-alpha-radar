# Continuation performance batch — November 6, 2026

Base: main `ce3656eb747ab88f74f75f48a24bf1b7bdae80bf` (PR #77).
Three completed increments are consolidated together under the agreed local-test,
batched-PR workflow:

1. Exact canonical comparison loops preserve full content/type checks with less
   generator overhead. They did not establish a meaningful Kali total-time gain.
2. Offline timing review and scoped cost profiling distinguish failures, unknown
   comparability and profiling overhead from acceptance evidence.
3. Trusted nested continuation collection shares its owner's bounded exact-wire
   signature verification scope. Direct calls and recovery remain isolated.

## Latest host evidence

`radar-shared-verification-check-20261106T061957Z-3111183.json.gz` passed all
16 integration/fault and 14 independent signer cases using the actual 1 MiB
synthetic program. Total continuation time was 10864.153 ms and original-deadline
headroom 1351 ms. The previous unprofiled run was 11652.658 ms with 459 ms headroom.
This pair shows improvement, not a controlled benchmark or a live-network
readiness guarantee.

Collection took 3331.723 ms, signing 2977.638 ms, and submission 3602.121 ms.
The independent signer still ran once. Signing public-verifier processes fell
from eight to one; submission used zero. Nine public verifier processes covered
746 checks in the complete attempt, with 737 exact-wire hits and no capacity
bypass. The memo cap remains 64 and clears on scope exit.

One simulated lost-response send, preserved predecessors/source/entry accounting,
read-only finalized recovery and repeated recovery all passed. Recovery did not
release reservations. There were zero real network requests, no production wallet
access and temporary fixtures were removed.

The profiled Kali run with -436 ms headroom remains a failure of its instrumented
completion check. It is diagnostic evidence only and is not relabelled a pass.

## Consolidation and limits

The exact PR head must pass all twelve existing CI jobs before merge. No test,
workflow timeout or execution deadline is weakened. This merge is source
consolidation; it does not rebuild or restart scanner services, activate a model,
change alerts or quote sampling, submit a transaction, or evaluate frozen data.

The next operational evidence is a fresh local inspection of the preserved
original/replacement pair, followed only on eligibility by a bounded read-only
RPC observation. These existing commands make no preparation, key invocation,
transaction submission or release. Observation may issue up to twenty devnet
requests, including unsigned simulation. Its remaining time excludes persistence,
signing and send; do not add different runs' clocks to claim an execution budget.

A one-shot controlled devnet continuation remains a separate decision based on
that fresh evidence. If a prior attempt has consumed the continuation slot or
created a signing/send marker, use the existing recovery path; do not reset or
create a fourth generation. Then reconcile finalized receipts and fresh balances
before scoped closure. Mainnet and economic qualification remain separate.

## Local validation

The previous increments passed 59 chain-reader tests, 2 exit ownership/canonical
tests, 13 new review/profile tests, and full connected rehearsals. Signature
sharing passed 8 ownership/adversarial tests, 16 continuation diagnostic/digest
tests, the full 16/14 connected run, partition coverage and source hygiene.
The new test modules retain deterministic existing CI partition assignment.
