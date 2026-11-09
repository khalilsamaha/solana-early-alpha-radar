# Durable successor receipt accounting

This increment records the previously reviewed exact-successor token and native
fee effects in a separate, single-row admission-ledger table. It does not send a
transaction, collect a receipt, observe current balances or release commitments.
The internal writer requires an explicit accounting opt-in; the only public CLI
is an offline test runner using disposable journals and keys.

The source lock and writer transaction exclude competing updates while all
source, retirement, successor, signing, backend ACK and transport evidence is
replayed. The receipt reviewer retains the first matching terminal capture's hash
and authenticated finish time. The durable record binds that capture and the
complete effects projection; its time must follow the evidence. Canonical shape,
hash, row/byte limits and clock checks apply on every reopen. Rehashed records
cannot override freshly replayed source evidence.

No record is created for incomplete or unusable evidence. A repeated apply
validates and returns the existing record without another write or fee deduction.
A storage failure rolls back the whole transaction. If completion is lost after
commit, read-only status recovers the record and a subsequent apply stays
idempotent. Conflicting later evidence makes accounting unusable while preserving
the existing record and every hold.

Lifecycle and private recovery projections recognize the new table and record
identity. They account for the known successor fee and owned token effects while
preserving the retired attempt's unresolved fee exposure. Original-generation
records remain immutable inputs for historical validation. Missing parent
generations and unsupported or corrupt records fail closed. Existing projections
without successor accounting retain their original behavior.
After successor accounting, first-generation chain/replan tools still refuse the
new phase; successor-aware lifecycle and recovery reports are the accounting view.

The `successor-accounted-flat-held` phase means zero owned residual according to
that exact historical successor receipt. It does not mean current wallet balance,
economic closure, retirement non-execution or released reserves. The failure
phase retains owned inventory. Both keep all proceeds/protected inventory and
remaining fee commitments held. The fee conservation equation is the original
commitment = known paid fees + remaining held fees; unresolved retired exposure
remains inside the latter, never silently deducted or released.

## Acceptance boundary

Run `position-book/successor_accounting_cli.py --output NEW.json.gz` with
`python3 -B -E -s -W error::ResourceWarning` at the pinned development commit.
It includes the prior six receipt-review tests and the durable accounting tests:
idempotent commit, lifecycle/recovery agreement, failed receipts after STOP,
opt-in/evidence refusal, rehashed record/clock/capture tampering, rollback and
lost completion, writer exclusion, orphan generations, and later contradictions.

Kali acceptance is an increment within E0, not phase consolidation. A subsequent
closure contract still needs fresh residual/protected balance evidence and an
explicit treatment of retired exposure. No operational accounting command,
successor execution adapter, new signing authority or closure is enabled here.
