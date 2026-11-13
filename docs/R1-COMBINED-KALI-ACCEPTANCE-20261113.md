# R1 combined offline Kali acceptance — 13 November 2026

Decision: accept `5a6e26e69d6e7f40e44a361c569c5915a2d3cd3a` for its
bounded offline Docker/Unix integration scope. Status remains
`combined-offline-passed-live-blocked`. This is independent review of supplied
artifacts, not direct Kali access, live provider/RPC observation or remote storage
verification. No unchanged passing batch needs repeating.

The GitHub branch still identified that source at review. Its tree
`49c37e45076b11506ce0c727e3551e8192216f93` equals the local reviewed tree.
All 169 report source hashes match; the separate report and log match the bundle
byte for byte. The log records 26 named tests, zero failures/errors/skips and no
matched resource/async diagnostics, on Python 3.14.6 (10.468 seconds).

All three archive checksums, member bindings, capture/measurement replay,
lifecycle and cleanup receipts pass independent verification and isolated restore.
Their recorded measurement-journal timestamps span **19:12:33–19:12:51 UTC /
20:12:33–20:12:51 CET** on November 13. These are supplied host timestamps,
not reviewer observation times or proof of synchronized clocks.

| Case | Bytes | Result | Direct restorations |
| --- | ---: | --- | ---: |
| normal | 135511 | Complete replay; clean research retirement, discovery receives a second creation | 1 |
| cleanup-failure | 135671 | Complete evidence of failed research cleanup; upstream aborted, failure retained | 1 |
| shutdown-interruption | 122341 | Intended stop_shared fault reached; incomplete evidence remains quarantined | 0 |

Normal and cleanup-failure lifecycle journals have 16 records and end rolled_back.
The interruption journal has 13 records, remains research_retired with stop_shared
pending, requires reconciliation and does not authorize resume. Eight unique owned
Docker containers across the cases have matching staged source hashes and report
creation, read-only mounts, network none, process reaping and removal. Restart
policy transitions are reported as actual Docker operations, not simulation.
These receipts support the isolated fixture result, not current production state.

| Supplied artifact | SHA-256 |
| --- | --- |
| report(20261113-191333).json | `e2ef60c4e60292813fc2a9b9408e3a7126a4ea805933e406cbc50eb3f2cbb73e` |
| validation(20261113-191333).log | `ab14d8a2a16b76772d802b8b0b384d4c7064325acd15182afccf7e29babb38c8` |
| acceptance(4).zip | `7a91079383d2aedc8ab4fbb4abea0749ded3bacbcf93646a4409a8e4c8dac3cc` |
| normal-evidence.zip | `9118b6e0277e3ee57ddfe03c5dd5579db441b2c604fa6845918912cfb68604fc` |
| cleanup-failure-evidence.zip | `bccea2107988d30caeb16807b9972dead5b603a0b4ae7bedd0d3c4a59dea4f44` |
| shutdown-interruption-evidence.zip | `4f3a97212a19caed2d6045fccd704f69bd2a03c42a39504e61c757bdbdb2477a` |

## What the four-point batch closes

1. Separate discovery/research lifetimes work in the connected offline path.
2. Owned disposable service handoff, rollback and read-only recovery work for the
   tested cases; production receipts and adapters remain unimplemented.
3. Finite profile validation and actual subprocess alarm/guard probes pass; the
   executable worker still uses synthetic credentials/upstream and a short bound.
   No 24–48-hour supervision or live provisioning is accepted.
4. Variable complete/interrupted evidence restores and transfers through a mock
   backend. A real bounded backend, capacity allocation and retention remain open.

The test image uses a reviewed source overlay. It is not a verified deployable
shared-scanner image. A short synthetic run does not validate long-duration
resource budgets, provider behavior, billing, initial-event coverage or finality.

## Ordered unblock requirements

| Boundary | Required evidence or decision | Responsible work |
| --- | --- | --- |
| Deployable production candidate | Image digest tied to reviewed source/dependencies; immutable deployment/admission manifest; production receipt adapters and read-only recovery; finite live supervisor and secure credential provisioning | Engineering, then one consolidated isolated host acceptance of changed boundaries |
| Preservation | Bounded real delivery adapter; exact downloaded bytes and independent restore for completed/interrupted evidence; justified simultaneous storage budget; explicit retention duration/runs and remote policy | Engineering plus owner storage/cost policy; later scoped host evidence |
| Source-measurement pilot | Approved exact deployment/profile, measurement thresholds, numeric funding/data-fee/exposed-balance ceilings, retention and rollout authority | Owner decisions after a concrete candidate is reviewable; then separately authorized host/provider validation |
| Reconstruction/simulation | Adequate pilot evidence, defined initial-event/order/recovery/finality limitations, validated applicable reconstruction and simulator | Research/engineering after source adequacy review |
| Confirmation study | Sealed protocol, untouched future evidence, accepted preservation and owner approval before outcomes | Separate study; 21 complete UTC days for a pass, day-14 look failure-only |

The draft pilot is capped at 24–48 hours and may stop earlier at another limit.
It has not started. It is a source measurement, not a profitability study. Numeric
funding/data-fee/exposed-balance terms remain unset; prior suggestions are not
approvals. The engineering allowance remains five working days in total, with no
reliable consumed-effort ledger. Reconcile effort and scope before any extension.
November 19 cannot currently be confirmed as a study start. Conditional later
dates must move with a valid start, never by shortening the observation window.
December 31 remains a scope/verdict checkpoint.

This acceptance record advances the evidence review and agenda only. It does not
implement the open production requirements, start a pilot, merge main, deploy,
activate a provider or change E0. E0's independent November 20 checkpoint and
held-state restrictions remain unchanged.
