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
implemented and accepted on Kali at `df6cbfa4`, including real local IPC. Host identity
is accepted at `35b89c5e`: UID/GID 1000, same user namespace, no findings. The isolated Docker boundary
is accepted at `747f44ed`, with all three disposable containers removed. The
credential-delivery and supervised-worker boundary is accepted on Kali at `bf2d9fcf`.
The durable handoff coordinator is accepted on Kali at `c0143106`.
The combined isolated service integration is accepted on Kali at `a0003221`.
The next draft measurement contract/evaluator is in `../r1-registration/README.md`.
The production handoff plan remains in `../r1-container-review/README.md`. See
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
| Connection ownership | Shared owner/scanner integration accepted offline on Kali at `df6cbfa4`; production remains on its existing source | Host UID/namespace and isolated container socket boundary accepted at `35b89c5e` / `747f44ed`; actual production startup and rollback remain open |
| Credential and exposure control | Wire accepts an in-memory secret and redacts known variants | Private-file/sealed-descriptor and shared-worker boundary accepted offline on Kali at `bf2d9fcf`; live integration and owner-approved numeric exposure remain open |
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

## Container-boundary development evidence

The separate rehearsal passes 314 core Python checks, 20 container-control
checks and 226 scanner checks. Both development pipe scenarios export/restore
exactly. Docker and real container mounts cannot be tested in this development
environment; no Docker acceptance is inferred. The Kali runner requires the
real isolated boundary and refuses a fallback. Its status must remain live-blocked.

Exact development report: `evidence/r1-container-development-20261111.json`,
SHA-256 `248c7b9dbe479f630153599292d8fb2893477067360706ddf211aa8200c37461`.
This receipt binds 123 source files; actual production rollout/rollback, live
credentials/supervision, registration, numeric exposure and real-session retention
remain open. The accepted host identity report does not close those requirements.

## November 12 acceptance and runtime increment

Kali accepted the isolated Docker boundary at `747f44edfdfbdd8aae62344c368b2189675027dc`:
314 core checks, 20 boundary checks, 226 scanner checks and 123 matching source hashes.
Normal cleanup preserved discovery; deliberately failed cleanup aborted upstream;
missing-endpoint startup refused direct fallback. All three disposable containers
were removed. The full runner took 26.190661 seconds. Report retained in
`evidence/r1-container-kali-20261112.json`, SHA-256
`8107fe3cc7495a184ab49ad314d2c6245f7389c3e7a16607a74f9c248263d4c5`.
The uploaded normal package independently replays exactly; the failure package was
not uploaded and independent replay is not claimed for it.

The new runtime boundary passes 314 core and 23 credential/supervision checks in
development, including parent-death and signal/deadline cleanup, immutable secret
handoff, one-attempt refusal and shared capture/journal replay. Four real child
process scenarios completed in the combined 15.764792-second runner. The unchanged
scanner regression evidence remains the 226 Kali checks at `747f44ed`; it is not
represented as a new scanner run. Exact development report:
`evidence/r1-runtime-development-20261112.json`, SHA-256
`57af55a3bf71afd0d3f50c4a4a7ecfbf47fdaceadc12f475ed17c26b6d4e4054`. It binds 121 source files.

Kali runtime validation is accepted at `bf2d9fcf`. This remains an offline worker and has no live
mode. It cannot close live TLS/subscription behavior, funded exposure, actual
production handoff/recovery/rollback, measurement registration or real-session
preservation/retention. Full R1 remains open; no new timeline or effort-cap reset.

## November 12 runtime acceptance and lifecycle coordinator

The runtime report at `bf2d9fcf0a050ffacd12a24e3908732db145bec3` passes
314 core checks, 23 runtime checks and all 121 source hashes on Python 3.14.6.
All four workers were reaped, forced kill was exercised, and every consumed
attempt refused reuse. Full runner: 27.190253 seconds. Exact report:
`evidence/r1-runtime-kali-20261112.json`, SHA-256
`1f5ec524a29c0368e3482d91d21cafe1edcbb60266a169d76c4f27c0670707af`.
The uploaded normal session independently replays exactly, SHA-256
`eabed67599ef56f3c0b495b82d0265860e4b2d4cd81081abad97a2502566b874`.
Kali reports replay for cleanup failure; its separate ZIP was not supplied.

The next coordinator durably records each handoff intent before execution, binds
receipts to operation/actor identities, consumes one stable-registry allowance,
and refuses retries, out-of-order actions or rollback after uncertain shutdown.
Its recovery reader never executes an operation. Development passes 314 core
checks and 21 lifecycle checks plus an 18-scenario native-process matrix; all
18 journal sequences independently replay. The combined run took 10.131394 seconds.

Exact development report: `evidence/r1-lifecycle-development-20261112.json`,
SHA-256 `eec944d29a4612334c554a37a542161ffa1ac94486749ba1b11acd321ddd02f7`.
Replay evidence: `evidence/r1-lifecycle-development-journals-20261112.json`,
SHA-256 `5e718901dec38980085e88fd0616a1f379c037648084a063d300a9a09586db89`.
These bind 127 source files. The disposable native process lifetimes are real;
endpoint setup, network ownership and restart policies are simulated. This is
not actual scanner/provider handoff or production rollback. The accepted shared
wire, credential and Docker results remain separate evidence.

Kali lifecycle validation is accepted at `c0143106`; the combined isolated
broker/scanner/Docker integration is accepted on Kali at `a0003221`. Measurement registration, numeric exposure approval and actual
live-session preservation/retention remain open. Full R1 remains open; the
five-working-day engineering cap has not been restarted.


## November 12 lifecycle acceptance and service integration

The uploaded `c0143106` report passes 314 core tests, 21 lifecycle tests,
127 matching source hashes and 18 native-process scenarios. All 18 supplied
journals independently replay exactly, including the 16 interrupted-operation
cases. All fixture processes were reaped and maximum simultaneous owners was
one. Full runner: 22.48334 seconds. Exact report SHA-256:
`65027ccc0232dcdcb36fc122e7d8d0a955a193de852f3976f4d6ae1f5d0160fb`;
exact journals SHA-256:
`bb00c3ad04e988104ecbd402869448b250f20500b9952aef242a8a69a8f7ba59`.
Both exact files are retained as `evidence/r1-lifecycle-kali*-20261112.json`.

The new `r1-service/check_integrated.py` joins the coordinator to the actual
broker, sealed synthetic credential, capture/journal thread and scanner adapters.
Default Kali mode uses real Unix IPC and disposable Docker restart-policy
changes; an explicit development pipe mode reports those boundaries pending.
The production scanner is observed read-only. No real provider, wallet, key,
paid feed or trading path is activated. See `../r1-service/INTEGRATED.md`.
Both normal and failed-cleanup session packages are now requested for independent
replay. Full R1, production rollout, provider validation and numeric exposure
approval remain open; no PR/CI consolidation or effort-cap reset.

Development validation passes 314 core, 21 lifecycle and 16 integration tests,
plus both complete process scenarios in 9.93231 seconds. All 142 source hashes
remain stable. Both session archives and both journals independently replay.
The development report explicitly leaves Docker, real Unix IPC and actual
restart policies pending; it cannot substitute for Kali acceptance. Exact report:
`evidence/r1-service-integration-development-20261112.json`, SHA-256
`79c16299ce5ec2ee524d0b094d997997d57eda0729395ec24e8f8653e42edbcc`.
Exact journals: `evidence/r1-service-integration-development-journals-20261112.json`,
SHA-256 `2d49d28286a1a0ffd7b3907216a0a14ba86f7d6b0f28ce5ad62c2c8ae4170319`.


## November 12 isolated integration acceptance and measurement contract

Kali accepted `a0003221ac794ee0741a1908f23c2a0524dd65cc` with 351 tests
(314 core, 21 lifecycle, 16 integration), all 142 matching source hashes,
real Unix IPC and actual disposable-container restart-policy changes. Both
scenarios completed with maximum one synthetic owner, broker/consumer reaping
and all six owned containers removed. Elapsed: 36.87488 seconds.

Both supplied journals and both session archives independently replay exactly.
Exact evidence hashes:

- Report: `82f36ee62342da558faba8e96f198c234e7832391f9d4b4ae9b257ca8e35b787`.
- Journals: `d5abe121b83a5e9a1b7ca9003f16e06edf1dc20c52db36b76ffa6fd91191ad79`.
- Normal session (25,861 bytes): `1bb637b5ef4eeb0ad59d8af57e44b975aa8b9c5e3efacd62ab209a0cfa1dcc12`.
- Cleanup-failure session (25,879 bytes): `71429d38181dd1841e6fcfb093940e7ebfaf2c6c506f4ddd5b0be5866711e249`.

The exact report and journals are retained as
`evidence/r1-service-integration-kali-20261112.json` and
`evidence/r1-service-integration-kali-journals-20261112.json`.
This closes the isolated integration increment, not production/provider rollout.

The next `r1-registration` increment freezes a source-bound **unapproved draft**,
replays complete sessions and evaluates local quality separately from unknown
provider/source adequacy. Preliminary local criteria: 24 selected creations,
maximum one-second local send return, zero recorded gaps/abandoned/unresolved
sends or selected creations without a completed local send. These are engineering
criteria, not statistical power, source completeness or profitability claims.
The normal small synthetic fixture remains insufficient; failed cleanup fails.
A local pass cannot clear the measurement gate while remote evidence is unknown.
Numeric exposure, owner approval, production handoff and live retention remain
open. No activation, CI consolidation, ML fitting or effort-cap reset occurs.

Development validation passes 314 core and 18 contract tests, with both complete
synthetic replay scenarios, in 8.308514 seconds. All 147 source hashes match.
Exact development report: `evidence/r1-contract-development-20261112.json`,
SHA-256 `949523625d409096bd0747b3a369995ebf5b80f876f7e7459dcb05c8d27cb012`.
Frozen draft: `evidence/r1-contract-development-draft-20261112.json`, SHA-256
`c9468e251bd2ed9a6d51c19e907b5421b022eec5a93960ad3ae6726b81575202`.

Both newly uploaded Kali archives were also replayed against that draft:
normal is insufficient; deliberate cleanup failure is fail, as expected. This
retrospective analysis is recorded in
`evidence/r1-contract-kali-retrospective-20261112.json`; it explicitly does not
prove precollection registration. Kali acceptance of the evaluator itself is
next. No additional Docker or synthetic B2 rehearsal is requested.
