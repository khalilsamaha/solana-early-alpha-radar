# Admission-to-receipt integration gate — 30 October 2026

## Accepted base

The host signer-handoff report captured at 13:30:54 UTC matched all 15 synthetic
cases and flags. PR #63 consolidated the pre-sign admission, locked reader and
durable handoff after both CI groups passed. Main commit
`c632bd7388faea410a5bc401e66e27fdff445807` has the exact reviewed tree
`ef9c8241e9519ecae4ec315b31d1f4cfa3a7ab37`.

This is the first increment in the next local-test-first batch. It adds receipt
verification to the saved handoff. It does not connect a production key backend,
send a transaction or authorize a third controlled devnet cycle.

## Integration and accounting behavior

`position-book/admission_receipt.py` opens the existing fixed admission ledger
under the cooperating source lock. It never creates a missing allocation or a
separate position book. Its internal API accepts raw signed transaction evidence;
the CLI accepts no wallet, receipt import, source directory or execution arguments.

The original signed wire and receipt intent must match the saved private handoff
exactly. The existing token-reconciliation validator then checks the signature,
message, finalized status, token identities, transfer flows, amounts and native
fee effects. The two successful transfers must also use the exact admitted input
and output vaults and authorities in order. Compatible token identities alone do
not permit another counterparty. A capture timestamp must follow the saved signature acknowledgment
and not be in the future. Missing evidence remains unknown.

Two bounded tables in the **same admission database** retain the receipt events
and the first terminal raw evidence. The raw evidence and its event commit in one
SQLite transaction. Existing admission events and reservation amounts do not
change. There is no allocation transfer, spendable-balance calculation or release.

| Evidence / interruption | Gate result |
| --- | --- |
| No receipt yet | Awaiting receipt; no submission inferred |
| Missing transaction or incomplete transfers | Receipt unknown; original commitments held |
| Exact successful finalized receipt | Record observed entry fee and net acquired quantity |
| Exact finalized failed receipt | Record fee-only failure and zero acquired quantity |
| Same terminal effects presented again | Idempotent; no repeated fee application or extra event |
| Missing evidence after a terminal receipt | Preserve the verified terminal record |
| Conflicting terminal effects or different wire/intent | Sticky quarantine; hide usable effects, retain the original raw receipt and commitments |
| Process dies after commit | Reopen and replay the saved raw receipt; no signer call |
| Write fails between raw evidence and event | Both changes roll back |
| STOP or original quote expiry | Existing receipt effects can still be recorded; neither allows signing or sending |
| Unsafe/missing ledger, clock regression, size/event cap | Refuse; do not replace the ledger or partially publish results |

On every status/recovery read, the gate verifies the event hash chain, saved raw
evidence hash, exact handoff binding and recomputed accounting effects. Hashes
detect inconsistent local records; they are not protection against an actor able
to replace all private ledger data. Private signed wire, raw RPC payloads and logs
are excluded from the public report.

The limits are 16 receipt events, a 4 MiB raw input cap, a 4 KiB event cap and one
saved terminal package. Repeated identical observations do not consume events.
There is no pruning/reset interface for reaching a cap.

## What this gate does not prove

The receipt's signature authenticates message bytes, **not RPC finality or balance
claims**. This release has no RPC collector/genesis binding and does not manufacture
a local submission boundary. `rpcProvenanceVerified` and
`submissionProvenanceVerified` remain false. Public results describe observed
effects of supplied raw evidence, not authoritative current wallet balances.

Even a fully consistent receipt leaves the original admission reservation held.
The existing handoff outbox remains an immutable historical object, not a current
receipt verdict or spending permit. Any future sender/accounting owner must consult
this gate and its quarantine state before transitioning the allocation.

The current restricted signer is bound to the old fixed simulation/execution and
two-cycle layouts. Reusing those closed paths for this admission would not preserve
their intended scope. A new narrowly scoped key-backend lifecycle, independent
checks and a one-send boundary remain explicit work. No legacy journal is reopened
for a new trade by this release.

## Host check

After fetching and checking out the release commit supplied in chat:

```bash
cd ~/apps/solana-early-alpha-radar
umask 077
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/admission_receipt_cli.py" \
  --output "$PWD/radar-admission-receipt-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, **14 synthetic cases**, zero network requests,
new signatures and sends. It uses an existing public signature fixture, synthetic
RPC claims and disposable ledgers. It does not read production wallet files or
alter the scanner, observer, backups, notifications or fixed research study.

Local validation passed 333 position-book regressions and 52 token-reconciliation
tests. After adding the exact-vault restriction, the complete 22-test receipt-gate
suite passed again, including all 14 portable cases. Source hygiene and package
manifests passed. Host acceptance is pending; these synthetic checks do not
substitute for a future actual receipt integration.

## Next integration gates

1. Accept this synthetic host checkpoint and preserve the unchanged collection.
2. Implement a new restricted devnet signer lifecycle for the exact admitted
   message, with independent scope checks and durable one-shot acknowledgment.
3. Connect submission provenance and the trusted RPC receipt collector, then make
   one accounting owner responsible for the admission/position transition. Unknown
   outcomes and quarantine must retain commitments; no dual spendable budgets.
4. Exercise failed entry, independent delayed exit, lost replies and residual
   exposure in a separately agreed controlled devnet scope before generalizing.

Strategy qualification is independent. Preserve November 1, 3, 5 and 6 captures;
the fixed review remains November 6 at 00:05 UTC / 01:05 Europe/Amsterdam. Nothing
in this release establishes profitability or authorizes a real-money pilot.
