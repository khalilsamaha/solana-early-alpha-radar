# R1 readiness review after complete-session preservation

Date: 2026-11-11. This advances the existing R1 work sequence after accepting
the 287-test Kali report and independently replaying the B2-downloaded complete
synthetic session at `58805ae660e8a62676e186a0d27b2eaa131e8b3b`.
See `R1-SESSION-BACKUP-20261111.md` for exact evidence hashes and scope.

**Decision: synthetic preservation is accepted; one shared authenticated
connection is selected; live activation remains blocked on implementation and
validation.**
No further synthetic backup round trip is requested. The original readiness review changed only documentation. The subsequent shared
integration increment changes development sources, without changing the running
scanner or previously accepted artifacts.

Implementation update: the combined offline owner/scanner/research path is now
implemented; Kali real local IPC review is pending. See
`R1-SHARED-INTEGRATION-20261111.md`. The design requirements below remain the
acceptance criteria; implementation does not imply rollout or live acceptance.

## Remaining acceptance boundaries

| Item | Current evidence | Completion needed |
| --- | --- | --- |
| Bounded capture, transport and wire | Kali offline acceptance, pinned sources and dependency | Actual host TLS/session validation under an accepted connection model |
| Process supervision | Bounded, reaped synthetic worker; private cooperating-run lock | A live worker with credential delivery and connection ownership; the current offline child deliberately blocks networking |
| Local measurement | Selection and local send timing replayed | Freeze pilot measurement terms and distinguish unknown provider acknowledgement, external coverage, finality and billing |
| Complete-session preservation | One synthetic source/upload/download/restore pair accepted | Coverage for real completed and interrupted sessions, independent restore and stated retention terms |
| Source adequacy | Partial historical feasibility only | Establish whether missing initial events, historical state/configuration, ordering and recovery allow the proposed use; unresolved fields remain unknown |
| Connection ownership | Single shared authenticated connection selected from owner guidance; current code still has separate socket owners | Implement and validate shared ownership, scanner dispatch and bounded research shutdown |
| Credential and exposure control | Wire accepts an in-memory secret and redacts known variants | Private credential loading/delivery, owner-approved numeric exposure and no automatic top-ups |
| Full R1 gate | Open | Remaining engineering and Kali acceptance before PR/CI consolidation; measurement pilot and source verdict remain distinct from software checks |

The report does not prove actual provider performance, complete early-trade
coverage, production backup retention or profitability. No ML fitting is enabled.

## Connection decision — selected on November 11

The owner supplied connection guidelines and selected the single-socket route
by providing them in response to the coexistence question. Use **one authenticated
upstream WebSocket** for creation, migration and the pilot's selected token trades.
Do not wait for a two-socket exception or attempt different-key/host workarounds.
This resolves the architecture choice, not implementation acceptance or launch
permission. The earlier request to obtain coexistence clarification is superseded.

The provider's [real-time documentation](https://pumpportal.fun/data-api/real-time/)
and [FAQ](https://pumpportal.fun/FAQ/) were re-read on November 11. They support
multiplexing, free creation/migration streams, metered token/account trades,
200 subscription messages/second and 5,000 addresses/message ceilings. These
are provider ceilings, not targets: preserve the collector's much smaller
sampling, watch, command and resource limits. Account-trade subscriptions are
not part of this pilot.

The supplied summary additionally asserts IP-level connection counting and bans.
The reviewed official text does not explicitly establish that enforcement scope.
Record this as owner-supplied guidance, not an independently authenticated
provider support reply. This uncertainty does not block the selected single-socket
architecture. Do not equate free creation/migration streams with proof of zero
charges during cleanup or a hard cap on metered billing.

Repository inspection confirms `scanner/src/adapters/pumpportal.js` opens an
unauthenticated socket, subscribes to creation/migration, and reconnects after
disconnects. Its `apiKey` argument gates startup but is not put in the socket
URL. This is code evidence, not a fresh observation of the running Kali process.
The Python collector wire would currently open a separate authenticated socket.

The existing collector controller aborts its wire when capture reaches a terminal
limit. Reusing that wire directly for scanner discovery would close discovery
too. Giving the collector a no-op abort while leaving paid subscriptions on a
shared socket would instead invalidate its current stop/exposure guarantees.
Neither shortcut is an accepted implementation.

## Concrete implementation scope — one combined offline increment

Use the reviewed Python wire as the upstream connection implementation. Add one
owner around it, with exclusive upstream receive/send ownership, serialized
commands and a bounded local discovery interface for the Node scanner. Keep
research capture and its disk work isolated from discovery dispatch. The Node
scanner's shared-source mode must never construct its own provider WebSocket;
source mode is selected at startup, with no automatic direct-feed fallback.

The current scanner container runs as `node` and has no broker IPC mount or
Python runtime. A host broker and private Unix-domain IPC are the proposed
integration boundary. Implementation must establish bounded framing, peer/access
checks, UID/GID and mount compatibility, disconnect reporting and sequence/gap
semantics before this becomes a deployable configuration. Do not casually mount
credentials or grant the scanner write access to broker control state.

Changes belong together in the same offline integration scope:

| Surface | Required implementation |
| --- | --- |
| Python connection owner | Single fixed upstream factory; free subscriptions once; bounded queues and serialized commands; no reconnect within the research session |
| Research transport | Separate research lease/session from upstream lifetime; preserve journal intent/send semantics; revoke trade authority at the original terminal limits |
| Node scanner adapter/startup | Consume local creation/migration events through existing candidate and launch callbacks; mutually exclusive direct/shared modes; no provider fallback |
| Cleanup and failures | Bounded trade unsubscribe on normal stop; failure closes upstream and records discovery/research gaps; no claim that unsubscribe completion proves billing stopped |
| Process/IPC lifecycle | Private endpoint, bounded frame/queue sizes, one owner, worker-death handling, no stale authority restoration, explicit discovery health |
| Acceptance runner | Exercise owner, actual research capture/controller and Node discovery path together with synthetic upstream data; retain complete session and diagnostic evidence |

The owner must track attempted subscriptions, including a send whose completion
is uncertain, so cleanup cannot lose a possibly active paid watch. Cleanup must
remain available after research admission expires; that is permission to send
unsubscribe commands only, never to subscribe after the research deadline.
The present controller's shared capture guard on all sends needs explicit review
for this distinction. Receipt fields must distinguish upstream sends from local
attachment operations; a local bridge acknowledgement is not a provider acknowledgement.

A research stop with successful local unsubscribe transmission should leave
creation/migration dispatch alive. If cleanup fails, deadlines expire during
cleanup, or subscription state is uncertain, close the upstream and expose a
scanner gap. Do not mask that availability tradeoff. Any later discovery-only
restart must be separately controlled and must not restore paid subscriptions.

No production rollout, image rebuild, Compose change or scanner restart is
performed by this record. Preserve the existing scanner until the combined
implementation passes development and Kali checks and a rollout is reviewed.

## Shared-connection acceptance requirements

These are review requirements, not an implemented shared launcher:

1. One component owns the sole upstream connection and serializes subscription
   commands. No independent scanner reconnect loop or collector fallback may
   open another upstream connection while that owner is active.
2. Creation/migration dispatch must preserve existing scanner callback behavior.
   A bounded research queue must not make scanner discovery wait for research
   disk writes; overflow is an explicit research failure/gap, never silent loss.
3. Normal pilot completion must end its trade subscriptions without closing
   discovery. Unsubscribe send completion is not proof of a billing cutoff.
   If cleanup fails or upstream state is unknown, the design must specify the
   tradeoff between closing the socket to limit exposure and preserving scanner
   availability. It cannot guarantee both under every failure.
4. Pilot authority expires at its original limits and is not recreated by an
   owner restart. A resumed discovery connection must not silently re-enable
   trade subscriptions. Failure artifacts are retained, not repaired into a pass.
5. Migration from the existing scanner must prevent socket overlap, expose any
   discovery gap, define rollback and receive an approved rollout plan. No
   deployment or restart is authorized by this design review.

Required offline integration cases include scanner-only operation, active pilot,
normal stop, queue overflow, unsubscribe failure, owner/pilot death, expired
authority after restart and handoff without competing reconnects. Only after
those controls exist is a pinned Kali command appropriate.

## Execution sequence and timeline discipline

1. **Resolved:** single shared authenticated connection selected. No further
   provider reply or collection window is required to begin offline implementation.
2. Complete the chosen launcher/integration, credential/exposure controls and
   real-session preservation. Prepare the measurement registration, including
   definitions, denominators, unknowns and numeric decision thresholds before
   activation; choose them without inspecting pilot trading outcomes.
3. Validate the complete implementation locally, then supply one pinned Kali
   acceptance command for the completed scope. Review exact funding, exposed
   balance and billing uncertainty for explicit owner acceptance. The previous
   0.05 SOL / 0.02 SOL figures remain proposals, not approved amounts.
4. Only after the prerequisites and authorization pass, perform actual provider
   host validation and the capped 24–48-hour measurement pilot, stopping earlier
   on any limit. Real traffic/charges must not be hidden inside an offline test.
5. Return pass/fail/insufficient against the fixed measurement terms. A satisfactory
   pilot permits consideration of a separately registered study, not ML fitting,
   strategy retuning or a profitability claim.

The existing **five-working-day total build/validation effort cap is unchanged**.
This record does not restart it or assert a remaining allowance without an effort
ledger. Elapsed conversation time is not a reliable accounting of engineering
days. If unresolved dependencies exhaust that cap, reassess scope. The connection
choice no longer adds a provider-response wait; implementation and host validation
still prevent a firm live-start date. Full-gate Kali acceptance precedes PR/CI
consolidation and the owner's merge decision.

The documentation-only decision needed no Kali rerun. The subsequent shared
integration increment now has a combined Kali command, documented separately.
Preserve existing evidence and the remote object; do not repeat B2, fund the
wallet or restart the scanner for that offline check.
