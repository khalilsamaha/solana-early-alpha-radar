# Capture/session supervision integration — 15 November 2026

## Published base and new behavior

The approved 11-file resource-supervision package was published on
`research/r1-offline-capture-20261111` at
`d7077b50f55ac657ba7e0b4271b5e3774e988e16`. Its tree,
`5157458141f61e3e8c25191c5ec5839bba4b6ece`, exactly matches the tested local
`5ffc5b8` tree. Main was not changed.

The next local increment connects that supervisor to the existing separated
capture/session library. Research/service durations and raw-byte budget now come
from the deployment manifest. The child runs under the manifest-derived kernel
resource limits and the parent's independent aggregate wall deadline. Before
spawn, one new retained storage observation must match preparation paths, directory
identities, capacity budget and this attempt's timestamp. A failed gate or existing
capture directory cannot be retried through another output directory.

The child produces real SQLite capture data, a measurement journal and admission,
retirement and stopped receipts. Child and parent independently verify the closed
database and replay the journal before success. Historical recovery binds the same
artifact bytes and receipts without invoking helpers that could recreate a missing
lock. Missing supervisor terminal evidence remains unresolved even when a stopped
session receipt exists. No current-process or current-lock observation is implied.

The upstream and discovery consumer remain in-process synthetic peers. This adds
no actual provider, production scanner, Unix endpoint, credential or service action.
Fixture sampling is modulus one with a four-message ceiling; it is not a pilot
configuration. Completion means the bounded scenario was verified, including an
adverse outcome; it does not mean every scenario unsubscribed cleanly.

| Scenario | Research cleanup | Discovery after retirement | Local upstream closed |
| --- | --- | --- | --- |
| Normal | unsubscribed | yes | yes |
| Cleanup failure | upstream-aborted | no | yes |
| Operator STOP | upstream-aborted | no | yes |

Each completed scenario binds one synthetic upstream attempt and one research
attachment. All activation/provider/production-authority flags remain false.
Database, journal and receipt budgets are checked before accepting terminal
evidence. The fixture's individual artifact reads are also capped at 256 KiB;
this is not a full-size production exporter or retention implementation.

## Verification and limitations

[Retained validation](evidence/r1-capture-supervision-development-20261115.json):
39 tests, zero failures/errors/skips, 189 matching source hashes. Local Linux run:
2026-11-15 16:22:31.964050–16:22:49.613068 UTC
(17:22:31–17:22:49 CET). No parent diagnostics were captured. Child stderr is
intentionally discarded; this is not a comprehensive child-diagnostics scan.

Thirteen new integration tests exercise actual bounded child processes and capture
files, parent replay, normal/cleanup-failure/STOP, capacity loss before spawn,
storage-gate durability failure, preexisting capture refusal, tampered artifacts,
missing gate, historical inspection without lock recreation, and lost terminal
publication. The original 26 supervision tests also pass. The first integration
run rejected STOP because the new validator incorrectly expected unsubscribe;
review of the retained session outcome showed upstream abort. Only that new
expectation was corrected; existing owner/session cleanup behavior was unchanged.

The supervisor module was renamed from `supervisor.py` to
`manifest_supervisor.py` to avoid shadowing the capture library's existing module.
Callers must use the new module name. Expanded source binding intentionally refuses
old receipts against new source; inspect those at their exact recorded revision.
The earlier 21-source development report remains historical evidence for `d7077b5`.
Accepted capture/session/deployment/native runtime sources are unchanged.

## Next intervention

This integration is locally completed and ready for publication review against
`d7077b50f55ac657ba7e0b4271b5e3774e988e16`. No publication of this new increment
is claimed. No standalone Kali rerun is requested. Host validation should cover
changed boundaries when the real scanner/Unix and owner integration is assembled.

Still open: actual production configuration/ownership and mutation executor,
scanner/Unix integration, real credential provisioning, phase-deadline/shutdown
integration, production resource adequacy, variable-session delivery and retention,
and exact pilot approval. No live-provider operations or source/confirmation study
started. The five-focused-working-day cap is unchanged; consumed/remaining focused
effort remains unquantified and no extra allowance is asserted.

This R1 work adds no E0 closure receipt, journal reconciliation or fresh host/RPC
observation. E0 remains blocked with holds preserved. No current balances are
reported; the November 20 evidence-based checkpoint remains unchanged.
