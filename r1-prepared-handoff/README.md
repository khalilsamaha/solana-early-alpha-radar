# Preparation-bound isolated handoff

This connects the new deployment/storage preparation to the accepted native
handoff implementation. It is still an isolated synthetic-owner integration, not
a production executor. `Guard` accepts only the exact native fixture backend;
it cannot select a production target, live upstream or alternative backend.
The manifest, storage, preparation and native image/control/coordinator runtime
sources are unchanged by this bridge. One storage test explicitly chmods its
adverse public-directory fixture so the assertion also runs under umask 077.

Before creating even the inert direct fixture, the bridge requires successful
retained preparation, exact manifest/image/owner-source/registry bindings, and a
fresh sufficient-space observation. It consumes an exclusive bridge claim and
records that observation before dispatch. The claim binds preparation digest,
sources, manifest, configured registry, output and development/native mode.
Changing output cannot reuse the registry. Preparation is never rearmed.

Endpoint/consumer/owner startup and direct restoration require another fresh
observation with unchanged directory identities. The existing coordinator intent
must already be durable before the bridge dispatches any handoff action. Gate
publication failure, missing/incomplete preparation, source/manifest/result drift,
path replacement or insufficient headroom refuses a new start. A rejected start
leaves its coordinator intent pending; disposal cannot confirm it.

Research retirement and shared shutdown do not require sufficient free space.
They keep the accepted native checks of exact process/container/socket identity.
This lets an existing owner shut down under pressure while direct restoration
remains blocked. Recorded observations are not space reservations, provider
closure acknowledgments, billing evidence or host-wide exclusivity proofs.

The consolidated runner executes the 37 deployment tests and new bridge tests,
then four changed-boundary scenarios:

1. Normal preparation, native handoff, research retirement, shutdown and rollback.
2. Storage pressure before owner startup: intent pending, zero owner starts.
3. Storage pressure after research starts: retirement and shutdown complete, then
   restoration stays pending without creating a replacement direct actor.
4. Missing preparation terminal receipt: preparation stays unresolved, no actors.

Pressure is injected only into the read-only free-space sampler; no disk is filled.
Missing terminal evidence is an explicit pre-write interruption, not deletion.
Each fault must record reaching its intended stage. Fixture disposal runs on all
paths and is distinct from operational confirmation. Expected native total: seven
owned disposable containers removed (3 + 2 + 2 + 0). No image build/pull or provider
connection. Development uses real Python/Node processes and pipes with simulated
Docker metadata; it cannot satisfy native Docker/Unix acceptance.

One eventual Kali command is `bash scripts/r1-prepared-handoff-kali.sh` in a clean
pinned checkout named `source`. It reuses the accepted image and existing local
Docker access, with no permission changes or fallback. Return `results/acceptance.zip`,
including on failure. Keep every original directory and do not retry a failed
attempt. The bundle includes manifests, preparation claims/results, gate evidence,
control and handoff journals and exact fixture receipts. No historical passing
standalone image/control/native suite is rerun; the new interaction is exercised.

The production mutation executor, actual owner/scanner configuration, live profile,
credentials, preservation/delivery and pilot limits remain separate open work.
This gate cannot grant activation and does not reconcile the engineering allowance.
