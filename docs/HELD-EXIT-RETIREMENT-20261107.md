# Retire the expired signing attempt, preserve the position

The supplied November 7 expiry observation had no blockers: finalized block
height exceeded the saved last-valid height; both exact signature and transaction
lookups were absent; all five scoped accounts matched; inventory and fee holds
remained covered. These observations support a local denial transition. They do
not prove global non-execution or justify a new transaction.

## What this release implements

An explicit `retire` action makes eight new bounded read-only devnet requests.
It never imports the uploaded report. It binds those observations to the exact
saved preparation, signing state, signed wire, backend acknowledgment, account
roles, and scoped accounting.

Before collection, the source lock and a SQLite immediate transaction protect
the source ledger. Full semantic replay finishes before any fresh RPC evidence is
collected. The writer reservation remains held through collection and commit.
Signer attempt and acknowledgment files are rechecked immediately before writing;
no second full ledger replay consumes the fresh observation window. Stale
evidence or conflicting signer files still prevent writing. A single canonical, hashed `admission_exit_retirement` row is
committed atomically. No original row, signed packet, backend marker, preparation
generation, token ownership, fee commitment, or replacement allowance is changed.

Snapshot review also validates the retirement record and includes its identity
and held amounts in the snapshot projection. Existing snapshots without retirement
retain their previous projection.

The lifecycle reports `exit-retired-held`. Sender preflight, the durable send
boundary, and signing-current checks refuse when any retirement object exists,
even if its contents are corrupt. Full retirement/lifecycle status replays the
stored evidence semantically; a rehashed but contradictory record is unavailable,
not a successful retirement.

This is terminal for the existing application signing attempt. It does not close
the economic position. The ledger's inventory and fees stay held. There is no
new signing generation, replacement authorization, fee refund, allocation credit,
or automatic transaction retry.

## Failure and restart behavior

- No write occurs if fresh RPC evidence is missing, stale, contradictory, or shows
  any account change or returned transaction.
- RPC collection retains its 30-second network and eight-request bounds. A
  retirement has a 120-second acceptance budget. At commit, observation age is
  at most 10 seconds and the snapshot block time remains within 30 seconds.
- Any exception before commit rolls back the new table and row together.
- If output publication or acknowledgment is interrupted after commit, run
  `--action status`. It reopens the record without RPC or another write.
  Unconfirmed completion reports write state as unknown, not as a claimed rollback.
- A repeated explicit retirement of an already valid record returns the same
  retirement identity with zero RPC reads and no mutation.
- A corrupt or conflicting marker blocks sending and cannot be overwritten by
  the retirement command. Preserve all journals for investigation.
- STOP may remain present: this action only adds a restriction. It cannot clear
  STOP or authorize execution.

Status validates historical evidence at its recorded time. It is not a fresh
balance quote or proof that later external activity has not occurred. The exact
saved signature remains available to the existing read-only chain observers.

## Host commands

Use the pinned commit in chat. First run:

```bash
cd "$HOME/apps/solana-radar-dev"
python3 -E -s -W error::ResourceWarning -m unittest discover \
  -s position-book -p test_exit_retirement.py -v
```

The CLI is `position-book/exit_retirement_cli.py`. It requires the existing private
rehearsal directory, wallet, pool, exact preparation SHA, and a new public output
filename. `--action retire --allow-local-retirement` explicitly enables only the
local retirement write. `--action status` is read-only and uses no network.
There is no submission flag, public-report import, or configurable RPC endpoint.

Upload the public retirement and status reports. Never upload the private
rehearsal directory. No Docker rebuild or scanner restart is required. Continue
using a revision that understands the retirement marker; do not delete or edit
the marker to work around a guard.

## Following integration gate

Verify the host's durable retirement and unchanged holds, then design the
separate reconciliation/replanning policy. That policy must preserve the old
signature recovery path, bind fresh account and receipt evidence, keep cumulative
budget accounting, and prevent overlapping sends or double release. This release
does not implement or authorize that transition. Research results and real-money
eligibility are unchanged.

## RPC references

- https://solana.com/docs/rpc/http/getblockheight
- https://solana.com/docs/rpc/http/gettransaction

## Atomic observation correction

The host reports from 05:37 UTC on November 7 did not confirm retirement. The
separate status report established `retirement-not-recorded`. The old report did
not retain the exact exception, so its root cause cannot be established from
those files alone.

Inspection found a timing hazard: the old flow repeated expensive semantic replay
after network collection, before a commit limited to ten seconds. Host status
replay took about twenty seconds. `held-retirement-atomic-2` moves all full replay
before RPC and pins the ledger across the eight reads and commit. It does not
increase the 10-second commit window, 30-second account-age allowance, RPC budget,
or overall acceptance budget.

Reports include a fixed stage, allowlisted diagnostic code, phase durations,
network request count, and observation age. Exceptions before writing report a
refusal with no mutation; uncertain write completion still requires read-only
status. The writer reservation is on the private rehearsal ledger only, not the
scanner's production database. It temporarily excludes other writers to that
rehearsal ledger and is released on errors. The source lock covers cooperating
local tools, not unrelated activity involving the wallet.
