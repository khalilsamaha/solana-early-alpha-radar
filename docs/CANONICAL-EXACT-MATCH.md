# Exact canonical hit comparison — November 5, 2026

## Host blocker

The latest Kali large-fixture report reached the measured continuation after
successful predecessor setup. It stopped during submission validation with
`fresh-signing-expired`: 12,480.238 ms overall, no sender requests. Collection and
persistence took 4,515.600 ms; signing handoff 4,533.525 ms; submission validation
2,581.363 ms before stopping. Eleven preliminary fault checks passed, but the
connected timing and recovery gate did not. No real network or user wallet was
accessed; temporary ledgers were removed.

Compressed report SHA-256:
`175722826ae2c7d3b0b3f2aa5cd2e13603b825358bfa217dbc0a1e4827a9298a`.

## Correction

The existing canonical digest scope rebuilt a deeply nested immutable snapshot
before every lookup, even for identical evidence already present. A diagnostic
local cProfile run counted 1,347,269 recursive freezer calls for 9,067 digest
requests. It also identified repeated JSON serialization. A separate bounded
serialization-cache experiment did not show a dependable end-to-end improvement
while it still rebuilt every lookup snapshot. Direct exact comparison removes
that cost and makes the combined approach useful, as measured below.

The digest cache now keeps a small candidate index for built-in dictionary roots
with at most 32 short string keys. The index groups root keys and a short `format`
label. **It never establishes equality.** Each candidate must match every current
nested value and its exact built-in type against its retained immutable snapshot.
Dictionary order is irrelevant; list order is preserved; booleans and integers
remain distinct. Any mutation or unsupported type prevents that hit. There is no
mutable-object-identity shortcut, digest-only comparison or validation cache.

On an exact hit, the stored SHA-256 is returned without allocating and sorting a
new full snapshot. Misses, wide/unsupported roots and unsupported values retain
the existing bounded freezer and original canonical serializer behavior. The
stored snapshot bounds recursive comparison even against a cyclic current input.
Candidate indexes disappear with their entries and are cleared on scope exit.

The retained limits remain 128 entries and 32 MiB. Entry bookkeeping charges rise
from 512 to 2,048 bytes to conservatively include the small index and references;
this can reduce retention capacity rather than exceed the limit. No mutable input
is retained. The limit is retained cache accounting, not a whole-process RSS cap.

The same exact-comparison lookup supports a separate canonical JSON text cache.
It uses the original `json.dumps` with unchanged arguments on misses; there is no
custom encoder. Mutable results are not returned. The text cache adds a maximum
of 48 MiB / 128 entries, including serialized output and snapshot bookkeeping.
The measured working set was about 45.3 MB; the earlier 32 MiB experiment evicted
frequently. Increasing capacity without the exact-comparison change was not
sufficient. The existing digest limit remains 32 MiB, so the two configured
retention caps sum to 80 MiB; this is not a process RSS limit. Both clear on exit.

Only the explicit continuation opens the text scope in operational code. The
offline predecessor helper opens independent disposable scopes; the harness
requires all five contexts to be absent before and after the measured operation.
Ordinary entry, original preparation, replacement and recovery wrappers continue
to use the original uncached JSON serializer. Public reports include only bounded
`canonicalTextReplay` counters, never retained text or raw evidence.

Existing digest opt-in locations are unchanged: the preserved observation path, explicit
continuation, and separate disposable predecessor scopes. Journal/source reads,
ownership, balances, lineage, STOP, clock and freshness checks still run. The
independent Node signer, original ten-second freshness window, shared thirty-second
budget, single-send boundary and retained predecessor records are unchanged.
Scanner deployment, study registration, admission/sampling and notifications are
not modified. No real devnet/mainnet attempt is authorized by this release.

## Verification

Regression coverage includes equal copies without another snapshot allocation,
mutations of the same mutable object (including list growth/shrinkage during a
comparison), differing values inside the same candidate
bucket, exact boolean/integer types, unsupported subclasses, cycles, eviction and
index cleanup, and wide roots falling back to the existing lookup. Existing
canonical-byte equivalence, mutation, size, input-type, exception, shared-string
and scope-isolation tests remain required. The shared-allocation budget regression
accounts for the additional bookkeeping while preserving its original failure
condition.

Additional text-cache tests cover original JSON bytes and exception behavior,
Unicode and lone surrogates, randomized nested values, fresh mutable inputs,
mutation detection without repeated snapshots, output-memory accounting, eviction,
thread/nested/disabled scope isolation, failure cleanup and private report filtering.

The fixed 1 MiB connected rehearsal must still pass all sixteen fault/integration
cases and fourteen independent signer cases, including lost-response recovery,
preserved records, repeated-attempt refusal and no recovery resend. Local timing
is not host or real-network acceptance; the branch remains unmerged until the
pinned Kali offline report is reviewed.

The local regression run passed 77 tests: 57 chain-reader tests, nine continuation
scope/fixture tests, seven diagnostic tests, two source-integrity/observation
checks and two test-partition checks. A rehashed ownership change after cache
warm-up remains rejected; successful read-only observation leaves source files
byte-identical. Source hygiene/package manifests and whitespace checks passed.

## Final-source local result

The complete real-clock 1 MiB rehearsal passed all sixteen fault/integration cases
and fourteen independent signer cases after the list-size-change regression fix.
The final-source run measured **7,835.831 ms**, with **3,448 ms** of positive
completion headroom. Earlier exploratory runs were faster; the final-source
measurement is the acceptance evidence, and no guaranteed host speedup is claimed.

Digest reuse: 9,067 requests, 107 computations, 8,960 hits, no evictions,
9,358,059 retained bytes. Text reuse: 5,484 requests, 75 computations, 5,409 hits,
no evictions, 45,320,472 retained bytes. The parent process peak RSS over the whole
rehearsal was 113,924 KiB (about 111 MiB); this excludes child-process memory and
is a local observation rather than a system-wide memory guarantee.

Final compressed public report SHA-256:
`72f7b51a5a87a291d5aa50f4c81284f9f964a42e5255db51864d213c105421c3`.

Kali remains the next gate. Run only the pinned offline large-fixture CLI and
review its report, including any failure. No production rebuild/restart, live
signing, actual devnet retry, additional generation or merge is part of that test.
