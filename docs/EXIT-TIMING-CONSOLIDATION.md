# Exit timing batch — November 4, 2026

Accepted host source: `716eb42215d9e3e4a58c02e7a3118bc39e306b0f`.
The optimized public report captured at 07:06:09 UTC passed the connected
rehearsal, all twelve integration checks and ten independent signer cases.
Compared with the 06:40:23 UTC profile, elapsed connected time fell from
6,786.773 to 5,236.220 ms (22.8%). These are two synthetic host samples, not a
live latency guarantee. All 49 evidence reviews, 45 provenance reviews and six
source replays remain. The bounded encoding scope computed 127 conversions and
reused 153,973; no capacity bypass or conversion failure occurred.

The expiry reproduction again preserved the replacement with zero signer/send
calls. Repeated execution was refused before more requests. Keyless recovery of
the synthetic lost response never resent, and temporary ledgers were removed.

This batch consolidates the explicit one-replacement command, saved/offline timing
diagnostics and exact encoding reuse. The real November 4 replacement expired
before signing and is still consumed. Original and replacement evidence, acquired
inventory and fee holds remain preserved; the real round trip is not complete.

Local validation passed seven command boundary tests, ten profiling tests,
125 conversion/reader/intent/journal/policy/ownership tests and partition/source
checks. The grouped pull request runs the full CI matrix before merge.

Next engineering scope: a bounded read-only live observation for that exact
expired original/replacement pair, including fresh pool/account/simulation data
and remaining validation time. It must not append a third preparation, change
allowances, sign, submit, release inventory or import an exported report as
authority. Actual continuation still needs a separately reviewed durable and
independently enforced contract. Scanner, observer, notification rules and the
availability study remain unchanged.

CI follow-up: eleven groups passed on the first run; position-book group 3 hit
its ten-minute wall-time limit after passing its tests to that point. Move the
new 85-second profile suite to the lighter group 0. All modules remain covered
once; no test, deadline or runtime guard is removed.
