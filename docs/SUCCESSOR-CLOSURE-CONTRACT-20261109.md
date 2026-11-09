# Successor closure contract: unresolved exposure stays held

The original closure supports first-generation flat accounting and releases all
remaining fees. It cannot consume successor accounting while preserving the
retired attempt's unresolved fee exposure. Matching successor balances alone do
not resolve that exposure. This increment implements an explicit read-only
closure assessment and tests that refusal after the connected completion path.

## Supported contract

`successor_closure.status` replays the exact successor, retirement, original
preparation, signing acknowledgments, transport, raw receipt and durable accounting
under the existing source lock and one query-only database snapshot. It takes
only journal identities and a clock. No provider, public report, imported capture,
caller-supplied verdict or release opt-in is accepted.

The result is always `successor-closure-blocked-held`. There is no successful
closure state, writer, new table or reservation update. It identifies the exact
successor, retired preparation, retirement, accounting, receipt and capture.
Missing accounting leaves amounts unknown (`null`), rather than zero. Quarantined
evidence supplies no usable accounting amounts. Failed exits additionally report
the owned residual as a blocker. Semantic corruption fails closed and preserves
the source; an old closure table is not accepted as successor closure.

For usable accounting, the partition is checked against the independently replayed
entry commitment:

`original fee commitment = known paid fees + retired exposure held + other fees held`

Both portions of held fees, source proceeds, residual owned inventory and protected
inventory remain explicit. Zero owned residual is not sufficient for closure.
All release, fresh-balance, non-execution-proof, new-entry and execution-authority
flags stay false. STOP and expiry permit historical review only. Repeated calls
replay current evidence and change no bytes. No result cache survives the call.

## Release is an unresolved dependency

No supported release rule is introduced. A future proposal must supply evidence
and a reviewed policy for the exact retired generation, including contradictory
or unavailable evidence. A missing transaction from one provider, an expired
blockhash or matching current balances must not silently become proof of global
non-execution. If the exposure cannot validly be reconciled, E0 remains blocked
with its commitments held under the agreed time box.

Any future durable successor closure also needs exact generation/accounting
binding; independent receipt and fresh balance validation; an atomic writer
boundary with pre-commit STOP/clock checks; rollback and ambiguous-commit recovery;
idempotent replay; and isolated snapshot/restore coverage. Historical assessment
does not meet those requirements. No new allocation may consume this report.

## Offline Kali acceptance

The CLI accepts only a new output path:

```bash
python3 -B -E -s -W error::ResourceWarning position-book/successor_closure_cli.py --output NEW.json.gz
```

Expect nine focused contract checks and 14 connected cases: the existing 12-case
real-clock, 1 MiB completion path plus blocked closure after matching balances and
repeatable keyless review after STOP. The result must be `offline-integration-passed`,
with `closureContract.state=successor-closure-blocked-held`, positive send/balance
headroom, complete phases and temporary-ledger cleanup. A passing rehearsal
verifies refusal and preservation, not a successful closure or operational result.
The report includes source commit, working-tree state and Python/Node versions
before and after the rehearsal. Kali acceptance requires the clean pinned source
throughout; these local metadata are not independent machine attestation.

Focused cases cover exact identities/fee partition, unknown accounting, failed
exit residuals, STOP/expiry, rehashed erased exposure, wrong generation/foreign
closure, query-only writer exclusion, later receipt conflict, and rejection of
legacy closure/public-report inputs despite matching successor balances.

Providers and keys are disposable. The existing recovery code, original closure,
accounting, deadlines and scanner runtime are unchanged. No operational CLI,
signing, submission, release or phase-wide PR/CI/merge clearance is added.
