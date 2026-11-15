# Native handoff Kali acceptance — 15 November 2026

Accepted for the bounded offline scope at source
`dc2ecb5ee777f64dd3a0f97a063a9750e7051f9c`, tree
`e25aedf82aed8eadac021b1d1a0afa9e468020d2`.
The local clean checkout and remote R1 branch both resolved to this revision
before review. This is supplied artifact evidence, not reviewer access to Kali.

## Evidence and independent review

Uploaded `acceptance(7).zip` contains 37 unique members. SHA-256:
`c188327df12ff2a5ac85c7ad7c9cbbed941cd700eb31d626b0a0b6c17015ddc3`.
Report SHA-256:
`eefe5643b82fdab00cafe2103cc251e907a9378e92258c4a63ca97871afac159`.
Recorded batch: 2026-11-15 13:20:39.695408–13:21:07.220178 UTC
(14:20:39–14:21:07 CET).

- All 18 source hashes match the published implementation.
- Log reports 48 tests, zero failures/errors/skips; no detected diagnostics.
- Each separate case result equals its aggregate report entry.
- Five control proofs and five handoff journals independently replay against
  reviewed source. Handoff states exactly equal the reported recovery states.
- Plans bind the exact claims and source map; operation identities and confirmed
  adapter receipts match the retained journal records.
- Thirteen distinct container identities have removal and client-reaping receipts.
  Image, command, isolation and actor bindings were checked; consumer Unix peers
  bind UID/GID 1000 and process parent identity to the inspected containers.
- Reported owner processes were reaped. Scanner terminal records verify the image
  and report zero upstream/fetch attempts. Native mode is explicit, not fallback.

| Case | Retained state | Pending action | Containers |
| --- | --- | --- | ---: |
| Normal | rolled-back; unsubscribed | none | 3 |
| Cleanup failure | rolled-back; upstream-aborted | none | 3 |
| Lost owner response | consumer-ready | start_owner | 2 |
| Lost shared-stop response | research-retired | stop_shared | 2 |
| Lost restore response | shared-stopped | restore_direct | 3 |

The lost-owner case retains one normal scanner terminal JSON line in disposal
output. It is not an error diagnostic and does not confirm the pending owner-start
operation. The lost-restore fixture was created then removed; its operation still
remains pending. No disposal receipt is promoted into a coordinator confirmation.
Normal terminal output records creation, migration, then a later creation after
research retirement. Cleanup failure retains only the initial two events.

## Disposition and next dependency

Accept `native-handoff-offline-passed-live-blocked`. Do not repeat the unchanged
image, control or native batch. The accepted image remains
`sha256:8c6e3458333f587cb1a5110dbfdc2d6c98f2bdcc6892eb589ee08cf8b9b66140`.
No production owner, provider connection, billing cutoff, live credentials,
remote retention or current E0 observation is established.

The next step is the [remaining-scope reconciliation](R1-REMAINING-SCOPE-20261115.md),
required by the native increment before extending implementation. Full R1 remains
open. This review changes documentation only; no runtime, main, production,
provider, E0 journal or hold changes occur.
