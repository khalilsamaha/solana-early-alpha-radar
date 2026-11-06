# Continuation rehearsal prerequisite correction — November 5, 2026

The later Kali run successfully prepared both predecessors, then expired in the
measured continuation before sending. See [the next correction](CANONICAL-EXACT-MATCH.md).

## Kali evidence

The 06:09:35 CET report is `review-required`. Eleven preliminary fault checks
passed, but the connected run stopped while constructing its disposable
replacement predecessor. That phase took 15,256.208 ms and raised
`replacement-expired-before-write`. The original predecessor took 6,880.789 ms.
The captured program size was correctly verified as 1,048,576 bytes.

The optimized continuation was **not entered**: its elapsed time, stage and
diagnostic were null. The independent signer-contract and recovery assertions
were not reached. This is neither a passing host integration result nor a
measurement of the new continuation cache. The report records zero real network
requests, no production wallet/ledger access and removal of its temporary ledgers.

Public compressed report SHA-256:
`318229b9b2fa14d4a08c4128caadd9f6df8e0daa2c2a92103ca3441be758f783`.

## Harness correction

The offline fixture previously called original/replacement preparation directly,
without the bounded reuse scopes already used by the measured continuation.
Those setup calls must create valid predecessor history before the target can be
measured, but their extra repeated work exhausted the original deadline on Kali.

An offline-only `prepare_fixture` wrapper now gives **each** disposable
predecessor its own existing canonical-digest, public-encoding, exact
admission-history and signature-verification scopes. Source reads and validation
requirements are retained. Every scope closes before the next operation.

The setup still passes the actual wall clock through unchanged, uses the existing
monotonic clock and waits for genuine predecessor expiry. No fake clock, timestamp
rewrite, journal edit, expanded deadline or bypass of the failed guard is added.
These optimizations apply only inside the test harness; ordinary production
original/replacement preparation wrappers are unchanged.

Before measuring the continuation, the harness requires all four reuse contexts
to be absent. It repeats the check after the operation. A leak raises the bounded
diagnostic `fixture-reuse-scope-leaked`. The continuation therefore opens its own
fresh caches and retains the real-clock deadline, independent signer and durable
one-send boundary. Setup cache hits cannot be counted as continuation hits.

Reports identify `offline-predecessor-reuse-1`, explicitly state that real clocks
are unchanged and scopes were cleared, and expose bounded setup digest counters.
The additive `continuationStarted` field distinguishes a prerequisite failure
from a measured target attempt. The CLI remains offline-only and accepts no wallet,
private directory, endpoint, execution action or permission flag.

## Validation and next gate

Unit checks verify exact clock-object passthrough, independent empty scopes for
successive setup operations, exception cleanup, unchanged expiry rejection and
refusal of any leaked scope. Existing fixture-size, diagnostic privacy and
command-scope tests remain in place.

The expanded connected rehearsal must still pass all sixteen fault/integration
checks and fourteen independent signer-contract checks, with one synthetic lost
response and keyless recovery that never sends again. Its captured 1 MiB workload,
source/predecessor preservation and completion deadline are unchanged.

Local verification passed all seventeen targeted Python tests (eight scope/fixture
checks, seven diagnostic checks and two partition checks), plus all sixteen
connected fault/integration cases and fourteen independent signer cases. The
same verified 1 MiB workload measured:

| Phase | Local elapsed |
| --- | ---: |
| Disposable original preparation | 1,144.341 ms |
| Disposable replacement preparation | 1,652.018 ms |
| Measured continuation | 8,918.826 ms |
| Continuation completion headroom | +2,176 ms |

The continuation still made 9,067 digest requests with 107 computations and 8,960
hits, consistent with the preceding cold-cache local run. Its recorded setup
flags confirm real clocks unchanged, all four scopes cleared before measurement,
and no changes to production wrappers. Cross-machine setup times are not a
controlled speed comparison. Source hygiene, package manifests, Python syntax
and whitespace checks also passed.

Local public report SHA-256:
`bd426dfec6de18e77f4d4fb41e186deaa60cc3b9b5d73838c8b5d1f5386f14d7`.

Kali acceptance remains pending; the prior report does not authorize an actual devnet retry or
merge. Run the pinned corrected offline rehearsal and preserve its public report,
including any failure. Production services and the scheduled study captures are
unchanged by this harness correction.
