# Bounded canonical content sharing — November 5, 2026

Host follow-up: Kali stopped before this optimization could be measured, during
legacy disposable replacement construction. See the
[prerequisite correction](CONTINUATION-FIXTURE-SETUP.md). The local results below
remain valid; host acceptance is not established by the failed setup run.

## Problem and change

The verified 1 MiB continuation rehearsal previously failed its completion timing
gate at 12,813.567 ms, with −1,463 ms headroom. It made 9,067 digest requests,
performed 1,482 serializations/hashes and evicted 1,431 cache entries. Many keys
contained equal large immutable account-data strings stored as separate objects.
Repeated eviction made the same full records expensive to hash again.

`exact-canonical-digest-2` shares equal **builtin immutable strings** of at least
4,096 characters across frozen cache keys. Equality uses the entire string,
including type and content; an object identity or a digest alone never substitutes
for equality. Distinct records retain distinct typed structural keys and hashes.
The original canonical JSON serializer and SHA-256 calculation are unchanged.

Only the existing opt-in scopes use the cache: preserved-exit observation and the
explicit continuation integration. Ordinary entry, ordinary fresh-exit,
replacement and recovery wrappers do not open a new scope. The independent Node
signer, validators, SQL/source rereads, current ownership/balance checks, STOP,
fees, expiry and durable one-send boundary are unchanged.

## Bounds and lifetime

- Existing limits remain 128 retained keys, 32 MiB retained-byte accounting,
  16 MiB original per-input accounting, 8,192 nodes and depth 48.
- The full original per-input limit is checked **before** deduplication. Sharing
  does not make an otherwise ineligible input eligible for reuse.
- Structural storage is charged per entry, including a separate 512-byte entry
  bookkeeping allowance. Each shared string is charged once at its Python object
  size plus 512 bytes for its pool entry/refcount. This is conservative cache
  accounting, not a whole-process RSS cap; transient serialization remains.
- Each retained key owns one reference per unique large string, even if that
  string appears in multiple fields. Eviction releases those references. The
  last user removes the pooled string. Admission recomputes memory cost after
  eviction so it cannot forget the cost of a newly unshared string.
- Sharing is operation-local, never `sys.intern` or a global pool. Normal exit and
  failure both discard all keys and pooled strings. Nested scopes are isolated.
- Unsupported values still use the original serializer. Failed computation is
  never retained. Mutable caller inputs and authorization decisions are not
  cached; a fresh immutable content snapshot determines each key.
- Public reports add only bounded counts: shared strings, their accounted bytes
  and retained references. No string content or private evidence is exported.

## Verification

The targeted suite covers exact canonical bytes, type distinctions, changed
content, unsupported values/errors, traversal limits, LRU eviction, shared
reference lifetime, byte-cap churn, last-user eviction during admission, Unicode
and escaping, nested scopes, exceptions, threading and safe diagnostic projection.
It also verifies observation equivalence, unchanged source files and rejection
of rehashed ownership changes after warming the cache.

The expanded rehearsal constructs a real 1 MiB captured program-account fixture
with disposable keys, an isolated signer and synthetic provider replies. Its
captured-size assertion prevents a small fixture from masquerading as a large
one. All sixteen fault/integration cases and fourteen independent signer cases
must pass, including lost-response recovery with no repeat signing or send.
The original freshness deadline and shared thirty-second limit remain in force.

The first corrected local run passed at 9,052.757 ms with 2,183 ms headroom.
The same 9,067 digest requests required 107 computations, with 8,960 hits and no
evictions. Two shared strings served 54 retained references. This first result
preceded the additional fixed entry-bookkeeping allowance; final release
verification is recorded below.

## Deployment boundary

This is an unmerged development candidate pending Kali acceptance. Use the pinned
offline `continuation_exit_cli.py --large-fixture` command supplied with the
release and upload only its public report. It accepts no user wallet, directory,
endpoint or execution permission. It uses disposable temporary journals and
does not restart the scanner or any host service.

A synthetic pass does not include real RPC latency or chain finality. It is not
an instruction to retry the held devnet exit. Host acceptance and a separately
reviewed operational timing assessment remain necessary before prescribing a
controlled action. The actual held position, frozen study, notifications,
Backblaze and scheduled availability captures remain untouched.

## Final release verification

The final isolated expanded run passed all sixteen fault/integration cases and
fourteen independent signer cases, with the full bookkeeping allowance:

| Measurement | Previous candidate | Final content-sharing candidate |
| --- | ---: | ---: |
| Complete continuation operation | 12,813.567 ms | 8,529.428 ms |
| Completion headroom | −1,463 ms | +2,603 ms |
| Collection and persistence | 2,981.702 ms | 2,070.878 ms |
| Signing handoff | 3,267.270 ms | 2,178.627 ms |
| Submission including bookkeeping | 6,160.194 ms | 3,934.413 ms |
| Digest requests | 9,067 | 9,067 |
| Digest computations | 1,482 | 107 |
| Cache evictions | 1,431 | 0 |
| Accounted retained cache bytes | 32,038,790 | 9,193,707 |

The complete operation was about 33% shorter in this pair of isolated local
samples. The preceding corrected run also passed at 9,052.757 ms; this variation
shows why neither sample is a latency guarantee. Both used fixed synthetic
provider replies, not real network latency. Nested phase timings must not be
added to the complete-operation timing.

All 34 targeted Python tests passed: 17 canonical-cache tests, six continuation
scope/projection/fixture tests, seven diagnostic tests, two observation/source
integrity tests and two test-partition checks. Source hygiene, package manifests,
changed Python syntax and whitespace checks passed. No actual devnet execution
or host deployment was performed.

The connected result verifies preserved predecessors and entry accounting,
independent signer rejection of tampered lineage/ownership, repeated-attempt
refusal, read-only stopped recovery without another send, byte-identical repeated
recovery and removal of temporary fixture ledgers. It reports zero real network
requests and no user-wallet access; its one send uses a synthetic transport.

Kali acceptance remains pending. Keep the branch unmerged until its pinned host
rehearsal is reviewed; any later actual devnet continuation needs separate current
state and live timing evidence.

Final local public report SHA-256: `56c4c856af886fc5738934825c59f831147ceb1bc50f310199c54a0e7151416f`.
