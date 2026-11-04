# Controlled devnet continuation boundary — November 4, 2026

The accepted Kali connected report passed 16 integration/fault and 14 independent
signer checks at 19:13:19 UTC. The original deadline remained enforced. That is
synthetic execution evidence; the held real devnet exit is still unresolved.
The accepted underlying batch was merged in PR #76 after all twelve CI groups
passed. Consolidated main: `c18a6eb6d99a21d3b68515774cfd3deee8275a4e`.

## Commands and scope

`position-book/controlled_continuation_cli.py` defaults to `check`, an offline
command-boundary test. It accepts no operational scope or execution opt-ins in
that mode. `inspect` requires directory, wallet, pool and both predecessor
SHA-256 identities. It opens the existing journals read-only, verifies the exact
expired pair and current ownership, and reports local eligibility and held
quantity/protection/fee constraints. It makes zero RPC calls, reads no signer key,
and appends no preparation. Missing/corrupt/changed records, STOP, an existing
continuation, later evidence or backend marker prevent eligibility. Cleanup
failure clears eligibility and all tentative constraints.

Inspection is a point-in-time local fact, not an execution permit or reservation.
Execution independently rechecks the full state and collects fresh devnet RPC
accounts, quote, fee and simulation evidence. It may still refuse on timing or
state changes even after inspection passed.

`execute` requires both exact, distinct lowercase SHA-256 identities and all of
`--allow-unsigned-continuation`, `--allow-private-key-signing`, and
`--allow-devnet-submit`. The fixed backend is `fresh_exit.continue_sign_submit`.
There is no endpoint, signer, clock, imported-evidence, fee-policy, retry or queue
parameter. At most 20 collection and five transport requests are permitted, with
one signer invocation and one application send. The existing 10-second freshness
window and shared 30-second budget are unchanged.

Reports include bounded public result fields and preparation hashes/flags only.
Signed bytes, raw evidence and private exceptions are not exported. Output is
exclusive mode 0600 and may not be placed inside the private source or either
fixed handoff sibling, including through symlinked parents. A missing output or
write exception after dispatch does not prove rollback. Never repeat execution
to retry; preserve journals and inspect the matching existing recovery path.
Exit code 0 after execution means only an on-time RPC acknowledgment, not a
finalized receipt, realized result, released hold or closed position. Other
execution outcomes return 2 without automatic follow-up.

## Host checks for this release

Fetch the pinned development commit supplied in chat. Run the default boundary
check and then read-only `inspect` with the two already recorded identities. Upload
both public reports. Expected boundary count: 8. Expected inspection for the still
unchanged held position: `continuation-eligible-research-only`. Any different
inspection result requires review; it is not a reason to reset or delete records.

The supplied host commands deliberately do not execute. Review the new local
inspection and latency evidence before issuing an operational command. A third
generation committed before later expiry remains consumed; this release creates
no fourth generation or automatic retry. Live RPC latency remains unproven by
synthetic timings.

## Verification

All 10 local unit/integration tests passed, including the connected wrapper
regression; the default command contains eight portable boundary cases. Two CI
partition checks and source hygiene checks also passed. Tests cover exact opt-ins and both identities, fixed dispatch and injection
rejection, private/exclusive output and symlink handling, publication failure,
unknown execution effects, no retry, real disposable journal inspection, cleanup
failure, and inspection-mode separation. A separate connected wrapper regression
routes through the actual isolated signer with disposable keys and synthetic RPC,
then checks one lost-response send, preserved predecessors, blocked repeat and
keyless recovery. There are no real network or user-wallet tests in this release.

CI assignment preserves every test: the new connected wrapper suite goes to group
4; the existing 53.619-second entry-accounting module moves from group 4 to group
1. Measured consolidation job durations were 421 and 416 seconds respectively.
This leaves room for the new suite within the unchanged ten-minute job limit;
partition coverage tests still require each module exactly once.

Next: host boundary/inspection acceptance, then separately reviewed one-shot
controlled devnet continuation; recover any unknown state without re-executing;
reconcile the exact finalized receipt and fresh balances; close only scoped
commitments. Scanner, quote observer, alerts, backups and study rules are unchanged.
