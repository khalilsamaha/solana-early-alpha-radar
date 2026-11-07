# Exact comparison loops — November 6, 2026

## Purpose and scope

The full-size continuation profile identified nested canonical comparisons as a
material contributor to collection and signing work. Both canonical digest reuse
and canonical text reuse check every current input against a bounded immutable
snapshot. The old implementation constructed generators and invoked `all` for
every nested list and dictionary.

This change uses explicit loops for those same comparisons. It preserves exact
built-in type checks, every list index and dictionary key/value comparison, and
both initial and final container lengths. Indexed list access remains deliberate:
a shrinking list must not silently match a prefix through `zip`. Unsupported
input, mutation, cycles, scope isolation, eviction and fallback behavior retain
their existing contracts. The digest diagnostic version is
`exact-canonical-digest-4`; text serialization bytes and digest outputs are
unchanged.

No new cache or retained evidence is introduced. The 32 MiB digest and 48 MiB text
limits are unchanged. No validation result, source read, authorization decision,
clock, ownership check, durable commit or independent signer step is removed.

## Validation and limits

The chain-reader suite includes late differences in wide/deep nested values,
integer versus boolean/float changes, and dictionary mutation during comparison.
The full 1 MiB connected rehearsal uses real clocks and disposable keys, with
synthetic provider replies and no actual network or user-wallet access.

A local comparison benchmark is diagnostic only. A local connected pass also
cannot establish Kali or real-network timing headroom. The last accepted Kali
snapshot run had just 643 ms headroom; a new pinned host rehearsal remains required
before considering a separate real devnet attempt. Do not widen the original
deadline or reset the held position to obtain a pass.

No scanner rebuild, runtime service restart, study change, notification change,
mainnet activation or actual devnet submission is part of this source increment.

## Local results

The full 1 MiB rehearsal passed all 16 integration/fault cases and 14 independent
signer contract cases. Measured continuation: 4,589.837 ms; original-deadline
headroom: 6,294 ms. Collection/persistence: 1,385.238 ms; signing handoff:
1,403.264 ms; submission: 1,492.948 ms. Synthetic sender setup (228.851 ms)
remains included, not subtracted. Preserved-generation submission reads remain
ten. Lost-response recovery, repeated recovery and preserved source records all
passed; zero real RPC and no production-wallet access occurred.

The 59-test chain-reader suite and two exit canonical/ownership regressions passed. A nine-round alternating before/after
microbenchmark (600 comparisons per round, nested synthetic account/event
values) had median times 206.301 ms before and 120.506 ms after. This measures only
the comparison primitive; it is not an execution or network benchmark. The prior
local full-size snapshot run was 5,099.893 ms, but these separate single runs are
not a controlled end-to-end speedup estimate.

Local connected report SHA-256: `c3cb9223954e0380ce8194d0822299e16bac089677012f19db53ff363d279479`.
