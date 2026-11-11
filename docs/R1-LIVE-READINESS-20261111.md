# R1 readiness review after complete-session preservation

Date: 2026-11-11. This advances the existing R1 work sequence after accepting
the 287-test Kali report and independently replaying the B2-downloaded complete
synthetic session at `58805ae660e8a62676e186a0d27b2eaa131e8b3b`.
See `R1-SESSION-BACKUP-20261111.md` for exact evidence hashes and scope.

**Decision: synthetic preservation is accepted; live activation remains blocked.**
No further synthetic backup round trip is requested. This review changes only
documentation, not executable sources, scanner configuration or accepted artifacts.

## Remaining acceptance boundaries

| Item | Current evidence | Completion needed |
| --- | --- | --- |
| Bounded capture, transport and wire | Kali offline acceptance, pinned sources and dependency | Actual host TLS/session validation under an accepted connection model |
| Process supervision | Bounded, reaped synthetic worker; private cooperating-run lock | A live worker with credential delivery and connection ownership; the current offline child deliberately blocks networking |
| Local measurement | Selection and local send timing replayed | Freeze pilot measurement terms and distinguish unknown provider acknowledgement, external coverage, finality and billing |
| Complete-session preservation | One synthetic source/upload/download/restore pair accepted | Coverage for real completed and interrupted sessions, independent restore and stated retention terms |
| Source adequacy | Partial historical feasibility only | Establish whether missing initial events, historical state/configuration, ordering and recovery allow the proposed use; unresolved fields remain unknown |
| Connection ownership | Scanner and collector each currently own their own socket lifecycle | Explicit provider confirmation for the intended coexistence, or separately reviewed and validated shared ownership |
| Credential and exposure control | Wire accepts an in-memory secret and redacts known variants | Private credential loading/delivery, owner-approved numeric exposure and no automatic top-ups |
| Full R1 gate | Open | Remaining engineering and Kali acceptance before PR/CI consolidation; measurement pilot and source verdict remain distinct from software checks |

The report does not prove actual provider performance, complete early-trade
coverage, production backup retention or profitability. No ML fitting is enabled.

## Next dependency: choose a permitted connection model

The provider's [real-time documentation](https://pumpportal.fun/data-api/real-time/)
and [FAQ](https://pumpportal.fun/FAQ/) were re-read on November 11. They direct
clients toward one WebSocket and adding subscriptions to it. Neither reviewed
page explicitly approves the exact two-socket arrangement below or resolves
the restriction's IP/account/key scope. Do not turn that ambiguity into approval
or claim the documentation categorically bans this exact arrangement.

Repository inspection confirms `scanner/src/adapters/pumpportal.js` opens an
unauthenticated socket, subscribes to creation/migration, and reconnects after
disconnects. Its `apiKey` argument gates startup but is not put in the socket
URL. This is code evidence, not a fresh observation of the running Kali process.
The Python collector wire would open a separate authenticated socket.

The existing collector controller aborts its wire when capture reaches a terminal
limit. Reusing that wire directly for scanner discovery would close discovery
too. Giving the collector a no-op abort while leaving paid subscriptions on a
shared socket would instead invalidate its current stop/exposure guarantees.
Neither shortcut is an accepted implementation.

Recommended first action: obtain provider clarification through the owner's
existing support channel before changing the production connection architecture.
No message has been sent on the owner's behalf. Suggested exact question:

> May one existing unauthenticated creation/migration WebSocket and one separate
> authenticated token-trade WebSocket run concurrently on the same host/IP?
> Does your one-connection restriction apply per IP, account or API key? If they
> must share one connection, what handoff is supported without overlap?

Retain the actual reply, its date and scope. A response about generic subscription
limits or different API keys alone does not answer the proposed arrangement.

| Route | Work after the decision | Operational consequence |
| --- | --- | --- |
| Provider explicitly permits the exact coexistence | Complete isolated live-worker credentials, exposure controls, ownership and host checks | Existing scanner can remain unchanged; permission does not itself authorize funding or launch |
| One shared connection required or chosen | Develop an offline integration proposal and validate ownership, dispatch, backpressure, subscription cleanup, failure handling and handoff | Changes scanner connection architecture; requires a separately reviewed rollout before touching production |
| No adequate answer and integration cannot fit the remaining effort | Record blocked/insufficient outcome and reassess scope | No speculative second socket or automatic extension |

## Shared-connection design requirements if needed

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

1. Resolve the connection decision above. This is the current external dependency;
   there is no collection window or calendar date that must elapse first.
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
days. If unresolved dependencies exhaust that cap, reassess scope. Provider
response time is unknown; no firm live-start date is justified yet. Full-gate
Kali acceptance precedes PR/CI consolidation and the owner's merge decision.

No new Kali command is needed for this documentation-only acceptance/readiness
review. Preserve the existing evidence and remote object; do not repeat the B2
upload, fund the wallet or restart the scanner for this step.
