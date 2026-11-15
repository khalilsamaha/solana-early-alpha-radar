# Prepared handoff Kali acceptance — 15 November 2026

Accepted for the bounded offline scope at published R1 revision
`85b07532d3917c435a9978d657a595f62da0890c`, tree
`ec960eab0a41a7fadebcfbff37cd67ef70d5bbfb`.
This is review of supplied artifacts, not reviewer access to Kali or a fresh
live-host/provider/RPC observation.

Uploaded `acceptance(8).zip` contains 54 unique members. SHA-256:
`2aa9a9b7545f2c9d2b9e23fa6ce72133d34d62350f3ee07d47db0546237eed9c`.
Report SHA-256:
`4d5d64348fb63bdf0c942c713bab07ac36ac10ef09825b2f553f2c6f816d3f7f`.
Recorded run: 2026-11-15 14:54:16.130164–14:54:30.808180 UTC
(15:54:16–15:54:30 CET).

All 35 source hashes match the published implementation. The bundle reports
45 tests, zero failures/errors/skips, with no diagnostic matcher hits. Review
verified manifest digests, preparation claims/results and recorded storage gates;
all three control proofs and handoff journals replay to the exact retained states.
Seven unique container identities have removal and client-reaping receipts.
Native image/isolation, source/plan bindings and Unix UID/GID 1000/parent identity
match; scanner receipts record no upstream/fetch attempts. No development fallback
was used. Activation, provider access and production mutation remain false.

| Case | Retained state | Pending action | Removed containers |
| --- | --- | --- | ---: |
| Normal | rolled-back | none | 3 |
| Space lost before owner | consumer-ready | start_owner | 2 |
| Space lost before restoration | shared-stopped | restore_direct | 2 |
| Missing preparation result | preparation-unresolved; no handoff | none dispatched | 0 |

Insufficient space prevents new owner/restoration starts while retirement/shutdown
remain possible. Missing preparation confirmation creates no actors. Disposal does
not confirm pending handoff operations. These are controlled fault cases, not
production resource measurements, retention evidence or a live rollout.

Disposition: `prepared-handoff-offline-passed-live-blocked`. Do not rerun the
unchanged prepared/image/control/native batches. Continue offline work on actual
runtime integration and preservation. The new manifest-bound supervision probe
is a separate development candidate; this uploaded acceptance does not cover it.

Production owner/scanner identity/configuration, credentials, live resource
adequacy, variable-session delivery/retention and approved pilot terms remain
open. The five-focused-working-day cap is unchanged and consumed/remaining effort
is unquantified. No pilot or confirmation clock has started. E0 remains blocked
with holds preserved; this bundle contains no new E0 closure or balance evidence.
