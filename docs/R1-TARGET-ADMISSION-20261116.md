# R1.B target/preparation integration and retained-control acceptance

## Current: target binding accepted; finite-session restoration integrated

The supplied target-binding observation ran 16 November 2026,
11:01:21.917845–11:01:22.002406 UTC (12:01:22 CET), at
`332797e05a3165d03ec0e3d4b371204fd52a5e4b`. Its standalone report is identical
to the archive member and all 32 source fingerprints match that revision.
Report SHA-256: `2b8090d936c20387ff4fd218533c5ffa7b1224938fd7581a0266d95b23f4e336`.
The exact original container, image, PID/start generation, restart policy and
readiness configuration projection match the accepted baseline. The newly supplied
full retained configuration SHA-256 is
`b1d164ef7ae0fdfade8fe8ca515b3f1ab4d8e784eb9f2bdc8c8e7e6ccdf1bbf5`.

This accepts the one-inspect target-binding boundary. **Do not repeat it unchanged.**
It is supplied historical host evidence, not a fresh reviewer observation. The
result remains `target-binding-observed-live-blocked`; process namespaces/global
ownership were not reobserved. No activation, production modification or provider
connection occurred.

`shared_session.SharedPrepared` now connects the existing retained controller,
manifest/storage admission and concrete finite supervisor. The original must be
confirmed stopped, with no pending action, before a durable shared-session intent.
The same open controller holds its lock and serializes its operations throughout
the session. The supervisor owns and reaps both the worker and scanner, validates
capture/journal and shutdown evidence, and retains its terminal result before
the bridge can confirm completion. The original is checked again after shutdown.

Explicit start-original and restore-restart operations require the successful
in-process completion witness plus unchanged source, claims, terminal evidence,
manifest/preparation, path identities and sufficient fresh capacity samples. A
saved result cannot reconstruct the witness. Missing/failed writes, changed
evidence, uncertain shutdown or target drift poison the attempt; nothing restores
on exception or context exit. Historical inspection remains read-only.

This integrates the **existing offline worker/scanner session**, not a live
provider launcher. Local tests use real Python/Node child processes and a modeled
Docker original. The native fixture path remains restricted to its fixed image;
the actual scanner image is not silently substituted. Production scanner/runtime
and credential delivery, global ownership, remote preservation and operating terms
remain open. There is no new host script or request for another small rehearsal.
Combine the remaining changed production boundaries for R1.C acceptance.

Validation: 20 new shared-session tests and 45 existing production-control tests
pass (65 total). The new cases exercise actual finite Python/Node children,
including worker failure/reaping, abort cleanup, lost intent/completion durability,
source/target/receipt changes, concurrent operation refusal, preexisting supervision,
capacity loss and read-only recovery. Docker remains modeled locally; no fresh
Kali, provider or E0 observation was obtained. Source hygiene and whitespace checks
are required before publication.

## Supplied native acceptance

Accepted the isolated retained-control run at source
`a858024b326816a15dac8d6406c15035021376e0`, captured 16 November 2026,
10:50:08.092848–10:50:18.223973 UTC (11:50:08–11:50:18 CET).
All 13 producer hashes match, 29 tests passed without failures/errors/skips,
and standalone report/log bytes match their archive members. Four unique owned
container identities have removal and client-reaping receipts. All four complete
claim/journal replays exactly equal the reported recoveries, including source-set
and initial-target bindings.

- Normal: eight records; same original container/image/configuration restored,
  later process generation, original restart policy restored.
- Lost stop: three records, pending stop; no inferred confirmation.
- Lost start: five records, pending start; recorded stopped target is historical
  last-confirmed state, **not current physical state** after the attempted start.
- Configuration drift: four records, stopped target, restoration refused. The
  last observation's changed hash is distinct from the prior confirmed target.

Report SHA-256: `c63c0afa849e051edbabf7eff69d9d3f2cba830352586ac62d09244f31477af4`.
Archive SHA-256: `abe3a8b5f6e4cd6fb63dca503339049b0e33ddffb32664d9991d1a936cdea37e`.
Log SHA-256: `328ad0757b68e6ab4efeaf652986ff96f1b485fe06ec3f9907340569ef5780a0`.

This accepts the changed isolated control boundary. No unchanged rerun is needed.
The prior failed attempt remains retained and pending. This successful run does
not prove its exact failure cause, production shutdown, provider closure or E0
settlement. No direct reviewer Kali/RPC access was obtained.

## Integrated next boundary

`admission.BoundDocker` now makes one inspection of the exact container ID from
independently pinned accepted readiness bytes. It reconstructs the readiness
producer's configuration projection from that same response, compares its digest,
and checks engine ID/name/image/PID/start/restart, user, resources, hardening,
network mode and mount identities against the accepted record. Complete
Config/HostConfig/Mounts values are hashed in memory for the retained controller;
no raw values are persisted. This supplies the previously missing link between
historical reviewed evidence and the controller's concrete configuration target.
It does not reobserve `/proc` namespaces/process ticks, another workload census or
provider accounts, and grants no global exclusivity/activation claim.

`admission.Prepared` wires that bound backend into the existing durable controller
and existing manifest/storage preparation. It requires exact scanner image,
readiness configuration digest, retained rollback configuration digest, configured
registry and preparation result. An exclusive admission record consumes the attempt.
Fresh storage samples and immutable gate records precede restart disabling,
original startup and restart-policy restoration, after the control intent is
durable. Changed source/preparation/registry/configuration/path identity or
insufficient headroom refuses dispatch. Storage pressure does not block the stop
operation's sampling gate; existing journal writes still must succeed. No claim
of shutdown under a full or broken journal filesystem is made.

`admission.Prepared` remains a **direct-only** control integration. Shared offline
sessions use the additional `SharedPrepared` gate described above. No production
mutation entry point is supplied. The library dispatcher requires separately
scoped caller authority; its tests use a state model and temporary directories.
Unknown manifest/pilot decisions remain blockers, not approved values.

Local validation: 45 adapter/admission/runner/command tests, 51 deployment tests
and 59 production-review tests passed (155 total). This includes comparison with
the actual readiness producer function, metadata/configuration/producer mismatch,
preparation absence, storage loss/replacement, durable intent/gate ordering,
refusal to reuse a registry, read-only recovery and a one-inspect-only collector.
No local Docker validation is claimed. Source hygiene and script syntax pass.

## Historical host request — satisfied at 12:01:22 CET

`scripts/r1-production-binding-kali.sh` locates the retained readiness report by its
previously accepted digest and independently retained producer pins. It performs
**one read-only Docker inspect**, against that report's exact original container
ID, using a temporary empty client configuration. It runs no unit suite or native
rehearsal and creates no containers. It never opens Prepared/Control or calls a
mutation method. Raw Config/HostConfig values, including environment values, exist
only in local memory; the returned report contains sanitized identity/fingerprints.
No credential values, mounted file contents, service modifications or provider/RPC
calls are exported/performed. Original evidence is not overwritten.

The returned `results/production-binding.zip` is accepted above. The original
instructions were to return the archive even for an unavailable/drift result.
Keep the prior evidence. Do not retry or change permissions. A match supplies the
new full configuration fingerprint needed to prepare the actual controller target;
it does not approve shutdown, rollback, capacity, global ownership or pilot terms.
A mismatch must be reviewed, never accepted by silently replacing the baseline.

R1.A overall ownership and R1.B overall production readiness remain open. Next:
production shared-owner/scanner/finite worker/credential
path, preservation/remote retention, and exact numeric pilot/rollout scope. R1.C
combined acceptance and R1.D operating approval remain separate. No live pilot or
confirmation clock has started. Historical engineering effort remains unquantified;
no budget reset or new remaining-allowance claim is made. E0 is unchanged.
