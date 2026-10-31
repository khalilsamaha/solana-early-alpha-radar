# Admission accounting, recovery and delayed preparation consolidation

This batch combines three host-accepted increments after PR #64:

| Increment | Host evidence | Scope |
|---|---|---|
| Entry accounting | October 31 04:57:52 UTC, 15 cases | Acquired delta and paid/held fees in the existing admission ledger |
| Combined private recovery | October 31 05:26:57 UTC, 19 actual tests | Historical source plus admission/acknowledgment snapshot and isolated replay |
| Fresh delayed exit preparation | October 31 05:40:57 UTC, 27 cases | New raw evidence bound to acquired quantity and remaining fee commitments |

The exit report was replayed locally and matched every case and boundary flag.
The recovery case-list formatter incorrectly included the non-callable attribute
`test_key` as a twentieth label; the actual runner count was 19 and no key value
was exported. Callable unittest discovery now produces the correct list, with a
CLI regression check.

The original entry reservation is retained. Receipt effects are replayed before
accounting. Snapshot replay never restores into active state. Delayed preparation
has a new deadline and blockhash, protects existing inventory, and consumes no
exit attempt. The optional exit record is included in semantic snapshot replay.

## Merge acceptance

Run `bash scripts/check.sh core` and `bash scripts/check.sh devnet-pool` locally,
then require both corresponding CI jobs at the exact PR head. Source hygiene and
package checks are part of the core group. Review the diff and merge only the
tested head. Record the actual merge SHA in the next engineering release.

This is source consolidation. No scanner rebuild, service restart, signer use,
transaction submission, private-journal migration or production deployment is
required. Existing controlled cycles remain closed. The next component will be
developed separately after this merge.

## Remaining work

1. Collect bounded fresh exit RPC evidence under the same wallet and admission
   ownership checks, and preserve collector provenance in the private record.
2. Bind restricted exit signing and a durable send boundary to that exact record;
   retain uncertain outcomes rather than retrying.
3. Reconcile successful/failed exits, actual fees and residual quantities before
   releasing any allocation or allowing another entry.
4. Complete scoped operational/devnet acceptance before mainnet-specific work.

The fixed availability study is independent: preserve captures November 1, 3, 5
and 6, and review November 6 at 00:05 UTC / 01:05 Amsterdam. No outcomes are
evaluated, refitted or promoted by this engineering batch. Profitability and a
real-money pilot remain separate, unmet gates.

## CI partitioning

The first consolidation core job exceeded the ten-minute CI limit while running
position-book tests; it reported no assertion failure before cancellation. CI now
runs core-base, three deterministic position-book partitions and devnet-pool in
parallel. Every `test_*.py` position-book module belongs to exactly one partition;
local `scripts/check.sh core` and `all` keep their complete coverage. No test is
skipped and the per-job ten-minute bound remains. This change reduces CI wall time
without changing application or research behavior.
