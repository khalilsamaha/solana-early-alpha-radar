# Replanning after a retired, still-held exit

## Host evidence accepted

The November 7 corrected retirement and separate status reports both replayed
`exit-retired-held`, with retirement identity
`58187fb8325ad175689182221481a802277b8e2ae89485a69d15697f7517015f`.
The host completed local replay in 24.763 seconds, RPC collection in 1.900 seconds,
and reported observation age of 13 milliseconds on completion. Status independently
reopened the record with no network requests and no mutation.

Both reports retained 998 owned acquired atomic units, 500000000 protected acquired
atomic units, and 25000 lamports in fee commitments. Paid fees remained 5000 lamports.
Nothing was signed, sent, settled, released, or authorized for replacement.

## This engineering increment

`position-book/retired_exit_replan_cli.py` performs a read-only review tied to
both exact preparation and retirement hashes. It fully replays the local source
before collecting eight bounded reads from the existing fixed devnet endpoint:
cluster, expired blockhash, finalized height, exact signature status, exact
transaction, five scoped accounts, account block time, and cluster again.

A shared SQLite read lock in DELETE journal mode spans replay, observations and
assessment. Source tools also share the existing source lock. Signer attempt and
acknowledgment files are re-read after RPC; the retirement hash is checked again.
RPC context slots, account block time and finalized height cannot regress below
the retirement observation. No second full replay consumes fresh evidence time. The network budget remains
30 seconds, overall acceptance budget 120 seconds, account block time allowance
30 seconds, and post-observation assessment allowance 10 seconds.

The report distinguishes:

- `retired-exit-review-consistent-held`: source and observations agree; required
  successor integration remains outstanding.
- `retired-exit-review-blocked`: valid evidence reveals an account change, returned
  signature/transaction, STOP, or insufficient conservative budget.
- `retired-exit-review-unavailable`: the evidence cannot be validated. No partial
  readiness or budget assessment is published.

A later returned receipt must be reconciled against the old signature. An absent
receipt is only a provider observation, never proof that the signed wire was not
broadcast elsewhere. Account changes, including deposits, remain blockers; a
sufficient balance alone cannot make an unexplained change disappear.

## Budget contract

The output derives ceilings from the existing policy and replayed scoped accounting.
It preserves the exact owned quantity, protected inventory, paid fees and held fees.
Paid plus held fees cannot exceed the original total fee cap. Proposed per-exit fees
cannot exceed either the original exit fee cap or remaining held fees.

For this review, the retired signature conservatively occupies one attempt slot.
This is an explicit proposed successor constraint, not a rewrite of the old ledger's
attempt count. Zero conservative slots or insufficient coverage of the original
per-exit fee cap block review. No reservation is increased, released or credited.

## Next implementation boundary

A consistent report supports implementing a separate unsigned successor; it is
not accepted as an input capability. That implementation must:

1. Recollect and validate fresh reverse-pool pricing, exact account state, fee quote
   and unsigned simulation within the existing deadlines.
2. Bind a durable successor to the original reservation, retired signature and
   retirement hash, preserving all historical preparation generations.
3. Keep the retired sender denied, use an explicitly separate signing generation,
   and prevent concurrent or overlapping send boundaries.
4. Count the retired attempt conservatively, preserve cumulative fee accounting,
   and route any later old-signature receipt to reconciliation without double release.
5. Require separate explicit devnet signing/submission approval after unsigned
   preparation is reviewed. Research evidence does not approve real-money trading.

The current increment creates no successor table, packet, key, signature, transaction,
notification, or recurring job. Scanner polling, alerts, study data and deployment
remain unchanged. No Docker rebuild is required.

## Kali validation

Use the pinned commit in chat. Run the `test_retired_exit_replan.py` suite with
ResourceWarning treated as an error, then run `retired_exit_replan_cli.py` with the
private rehearsal directory, wallet, pool, preparation SHA, retirement SHA and a
new output path outside all private source directories. The CLI has no execution,
report-import or custom endpoint flags. Upload only the public JSON gzip report.

## Consolidation acceptance

The November 7 host review reached `retired-exit-review-consistent-held` after
eight reads, with no blockers. All five scoped accounts matched, the original
signature and transaction were absent from the provider response, and one
conservative attempt slot remained. These observations do not authorize a send.

Consolidated PR #78 initially passed eleven CI jobs. Partition 1 was cancelled
at its ten-minute runner limit while still executing the unsigned continuation
suite, without a reported assertion failure. Its runner allowance is now fifteen
minutes; all other jobs keep ten minutes. No tests, product deadlines, or safety
checks are removed or relaxed. The full final-head run must pass before merge.
