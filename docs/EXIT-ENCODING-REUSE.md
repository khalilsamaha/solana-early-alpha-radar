# Exact public encoding reuse — November 4, 2026

The accepted host profile located expensive repeated Python evidence and source
replays. A deeper local call profile counted 72,027 public identifier validations,
60,068 Base58 encodings and 2,096 wire decodes during one connected replacement
attempt. This increment reduces repeated immutable conversion work within those
reviews. It does not reuse their state-dependent verdicts.

## Scope and boundaries

`chain-reader/encoding_replay.py` provides an opt-in operation scope. Only
`fresh_exit._run` activates it in the execution path. Existing callers outside that
scope still compute every conversion. Nested scopes are independent; completion
and exceptions clear their contents and restore the previous context.

The memo holds at most 512 successful exact conversions, keyed by operation kind
and the complete immutable input. Public-identifier validation additionally binds
the expected 32- or 64-byte length. Strings are limited to 90 characters and input
bytes to 64 bytes. Only bounded immutable strings/bytes are stored. Subclasses,
larger values and unsupported kinds bypass reuse. Capacity exhaustion computes
normally without eviction or a partial result. Failures are never cached.

There are no cached ledger reads, receipt objects, account balances, ownership
decisions, parsed wire objects, deadlines, STOP state, signature verdicts or
execution permissions. Every original evidence review and source replay still
runs. The separate Node signer and its independent checks are unchanged. The
existing exact-signature scope remains a separate mechanism; this change does
not expand it. An encoding hit cannot authenticate a signature.

Only aggregate counters are exported as `encodingReplay`; no memo keys or values
are included. The standalone phase CLI prints the active version and counters.
The scanner, observer, study, notifications and production Docker image are not
modified or redeployed.

## Local measured comparison

One sequential before/after pair used the same connected phase rehearsal, on the
same development host, with synthetic RPC responses and disposable test keys:

| Measurement | Before | After |
| --- | ---: | ---: |
| Connected attempt elapsed | 3,088.615 ms | 2,097.561 ms |
| Evidence review exclusive time / calls | 1,065.386 ms / 49 | 565.501 ms / 49 |
| Provenance review exclusive time / calls | 708.536 ms / 45 | 420.375 ms / 45 |
| Source replay exclusive time / calls | 870.499 ms / 6 | 780.448 ms / 6 |

This pair is approximately 32.1% faster. It is a single diagnostic sample, not a
statistical estimate or a promise for the Kali host or live RPC. Fixture setup is
outside these attempt durations. Instrumentation adds overhead. Of 154,000
eligible conversion calls, 153,873 reused exact results and 127 computed/stored
new results; there were no capacity bypasses or conversion failures.

Both runs passed twelve connected checks and ten independent signer contract
cases, preserved the source and original preparation, and retained one-send
lost-response recovery. Both reproduced persisted expiry with zero signer/send
calls and refused another collection. All original freshness and shared operation
budgets remain enforced. This does not establish that a real exit will fit them.

## Regression coverage and host gate

Eleven focused conversion tests cover differential valid/malformed behavior,
leading zeros, exact lengths, subclasses, immutable output restrictions, capacity,
cleanup, isolation, signature authentication, and changing policy/clock rejection.
An additional real-journal test warms the conversions and confirms a rehashed
ownership change is still rejected. Reader, intent, journal and instruction-policy
suites run alongside the connected profiler and its expiry reproduction.
Local validation passed 125 reader/intent/journal/policy/ownership tests, all ten
profiler tests and both CI-partition coverage tests. Source hygiene also passed.

Fetch the pinned development commit, then run the existing
`position-book/exit_profile_cli.py --output <new-public-report.json.gz>` with no
wallet or private-directory arguments. Upload that report to compare against the
November 4 06:40:23 UTC host profile. No Docker rebuild is required. Do not rerun
the controlled replacement execution command.

The current real position remains held with its single replacement consumed.
Next: assess the Kali reduction and remaining latency, then design and review a
separate continuation boundary for that preserved state. This performance change
does not grant another replacement, signing attempt, allocation or real-money test.
