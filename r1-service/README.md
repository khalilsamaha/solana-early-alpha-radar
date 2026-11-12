# R1 durable service handoff lifecycle

Runtime acceptance at `bf2d9fcf`: 314 core checks, 23 runtime checks and 121 matching
source hashes passed on Kali. All four workers were reaped and attempted reuse
was refused. Report SHA-256:
`1f5ec524a29c0368e3482d91d21cafe1edcbb60266a169d76c4f27c0670707af`.
The uploaded normal session independently replayed exactly (25,861 bytes), SHA-256
`eabed67599ef56f3c0b495b82d0265860e4b2d4cd81081abad97a2502566b874`.
The failure package was not uploaded; only Kali's reported replay covers it.

This increment implements persistent sequencing and restart refusal for the service
handoff. The coordinator currently accepts only the explicit offline receipt
schema. It has no live deployment CLI, production Docker management adapter, real credential
input, provider connection, trading endpoint or automatic production rollback.
It does not claim that live-service integration is complete.

## Required sequence

1. Disable the direct owner's restart policy.
2. Confirm the original direct owner has stopped and its connection has closed.
3. Establish the shared endpoint.
4. Confirm the shared consumer is ready at that endpoint.
5. Attempt the shared upstream owner once.
6. Close research admission and retire its subscriptions (or abort upstream on
   uncertain cleanup).
7. Confirm shared owner and consumer termination and connection closure.
8. Explicitly restore the direct service and its previous restart policy.

Each step requires the previous confirmation. Receipts bind the operation ID,
actor identities and endpoint identity; stale, aliased, extra-field, false or
missing confirmations are rejected. A callback is trusted to implement and
observe its operation: schema validation alone cannot authenticate physical
process or connection state. Live adapters must supply independently checked
production identities and closure observations; synthetic receipts cannot be
promoted to live evidence by changing a flag.

## Persistence and interrupted operations

A private stable registry is locked for the attempt. Its exclusive, fsynced claim
is consumed before handoff, and cannot be reused with another output directory
or registration ID. The claim and lock are never deleted. This covers that stable
registry, not an operator deleting it or choosing a completely different registry.
A future service must bind its registry path through reviewed configuration and
registration; this is not host/IP-wide connection ownership enforcement.

The journal writes and fsyncs an intent before invoking each adapter, then validates
and fsyncs its confirmation. Records are sequence-checked, hash-chained and capped
at 64 KiB. Replacement, conflicting claims, wrong order, torn records and changed
identities fail closed. A failed callback or confirmation poisons the current
coordinator: it cannot retry, proceed or silently restore direct mode. A partial
or merely valid-prefix journal never permits automatic resume. Read-only recovery
reports the last confirmed state and any pending operation, creates nothing and
never invokes an adapter. Missing/corrupt evidence requires manual reconciliation.
Hashes detect accidental alteration against the retained binding; they are not
signatures against an adversary able to rewrite the whole private registry.

## What the Kali rehearsal actually tests

Disposable native Python processes stand in for the direct service, shared
consumer and shared owner. Their lifetimes, termination and reaping are real;
network connections, endpoint setup and service-manager restart policies are
simulated. The earlier accepted Docker/IPC and shared-wire/runtime tests remain
separate evidence. **This rehearsal is not actual scanner/provider handoff or
production rollback.** No Docker command or production-service control occurs.

The native-process matrix covers normal rollback, cleanup-triggered abort, and
interruption before and after every one of the eight operations (18 scenarios).
It checks at most one synthetic owner process at a time, no automatic retry or
rollback, and cleanup of every fixture. The fixed fixtures have parent-death and
resource guards and no Internet/DNS/child-process capability. Each adapter's waits
are bounded. The coordinator itself does not forcibly interrupt an arbitrary
injected callback; the future live adapter and supervisor must enforce their
registered deadlines.

Upload `report.json` and `journals.json`. The latter contains bounded synthetic
claims and exact journal records for independent replay. Expected overall status:
`offline-lifecycle-passed-live-blocked`. Interrupted scenarios should explicitly
require reconciliation, not pass as a completed handoff. The checker does not ask
for another capture/B2 round trip or rerun unchanged scanner/credential suites;
their accepted, pinned evidence remains valid.

## Next integration boundary

Kali has accepted this coordinator at `c0143106c1a3c3643bdc07907ba4659bcdfe8476`.
The next isolated integration is implemented in [INTEGRATED.md](INTEGRATED.md):
it connects this ordering to the actual broker and scanner, with ownership-scoped
Docker operations on disposable containers. Kali acceptance of that combined
path remains required before any production handoff is considered. Then finish measurement registration, numeric exposure
approval and live-session preservation/retention. The earlier spending figures
remain unapproved proposals. No live feed, ML fitting or trading is enabled.
Full-gate Kali validation still precedes PR/CI consolidation and merge. The existing
five-working-day R1 engineering effort cap is unchanged, not restarted.
