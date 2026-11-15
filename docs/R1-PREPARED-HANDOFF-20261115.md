# Prepared handoff integration — 15 November 2026

**Subsequent disposition:** published at `85b07532d3917c435a9978d657a595f62da0890c`;
[the supplied native batch is accepted](R1-PREPARED-KALI-ACCEPTANCE-20261115.md).
The publication/test instructions below record the earlier review stage and do
not request another run.

## Reviewable publication scope

This package includes the locally completed deployment storage and durable
preparation components, their tests/documentation, and a new bridge to the
accepted native isolated handoff. The remote base verified before preparation is
`4daeeef65d63dceffdb83b1724d52133c0c262c7` on
`research/r1-offline-capture-20261111`. Publication is not yet claimed.

The new bridge consumes a registry-bound claim and rechecks retained preparation,
source, image, owner-source and exact filesystem identities before fixture creation
or new starts. Fresh storage evidence is durably recorded before dispatch. The
existing coordinator intent must precede every bridged operation. Unresolved
preparation cannot create actors. Insufficient space blocks startup/restoration;
retirement and shared shutdown retain exact native checks without a free-space
prerequisite. Failed starts stay pending despite fixture disposal.

There is no production backend selection or provider operation: only the exact
accepted native network-none fixture backend is accepted. The supplied manifest
contains explicit fixture policy and missing production decisions. It is never
promoted to a real deployment approval. The original native/control/coordinator
and manifest runtime files remain unchanged. A storage-test correction explicitly
sets the public-directory adverse fixture's mode under the runner's umask 077.

## Development verification

Final report interval: 15 November 2026, 14:13:47.672825–14:13:48.676857 UTC
(15:13:47–15:13:48 CET). Result:
`prepared-handoff-development-passed-docker-pending`.

- 45 tests: 13 manifest, 11 storage, 13 preparation and eight bridge tests.
- Zero failures/errors/skips and no detected captured diagnostics.
- Four complete retained scenarios; all seven owned development actor processes
  disposed/reaped, plus their owner subprocesses. These are not Docker receipts.
- All 35 source hashes match the final implementation.
- Independently inspected the 54-member bundle: unique members, exact per-case
  results, exact manifest digests, preparation/gate observation replay, and all
  three handoff journal replays matching their retained recovery states.

| Case | Result | Actors | Successful gate observations |
| --- | --- | ---: | ---: |
| Normal | rolled-back; research unsubscribed | 3 | 5 |
| Space lost before owner | start_owner pending; no owner start | 2 | 3 |
| Space lost after owner start | shared stopped; restore_direct pending; no restored actor | 2 | 4 |
| Preparation terminal absent | unresolved preparation; no handoff | 0 | 0 |

The initial combined run is retained as failed evidence: its public-directory test
was masked by umask 077. The corrected explicit chmod fixture passes; no runtime
permission check was weakened. Subsequent added intent/owner-binding tests also
pass in the final batch. Pressure is injected in the free-space sampler; no disk
was filled, and missing terminal evidence is an interruption before publication,
not deletion of a real receipt. No performance or long-duration claim is made.

## Concrete next intervention

Review and approve publication of this combined package to the existing R1 branch.
After publication and exact-tree verification, supply one pinned Kali command:
`bash scripts/r1-prepared-handoff-kali.sh` in a clean checkout named `source`.
The command uses the accepted existing image and actual Docker/Unix, seven owned
disposable containers, and the four changed-boundary scenarios above. It must
return `results/acceptance.zip` even on failure. Keep every directory; never rearm
or retry a failed attempt. No production service, provider, credentials, B2
transfer, build, pull or permission change is part of that batch.

Native acceptance remains pending. Do not repeat the unchanged image/control/native
standalone batches. Their contracts are reused, not relabelled as production
approval. A preparation pass does not establish live resources or retain data.

## Remaining full-R1 boundary

Actual production owner/scanner configuration, mutation executor, live supervision
and credentials, variable-session real delivery, retained capacity and approved
pilot terms remain open. The bridge validates the next combined offline boundary;
it does not finish production readiness or start a measurement/confirmation study.
Main and E0 remain unchanged. The engineering cap has not reset and its remaining
allowance is still unquantified; no calendar or effort extension is asserted.
