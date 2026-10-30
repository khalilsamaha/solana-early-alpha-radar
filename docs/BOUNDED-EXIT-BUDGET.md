# Bounded separate-transaction exit budget — 30 October 2026

## Accepted atomic host result

The supplied 08:27 UTC atomic observation completed its original freshness gate:
23 devnet requests, two unsigned simulations, quote age 7,626 ms, and 2,375 ms
remaining. Its exact combined fee was 5,000 lamports within a 10,000 cap; the
combined simulation consumed 42,848 compute units. Entry input 1,000 acquired 998,
and the reverse consumed all 998 and returned 997 original-token atomic units.
All four transfer balances reconciled, with zero acquired residual. The report
records matching final token/pool/deployment/oracle effects and unchanged closed
local journal identities. No signatures or transactions were created/sent.

The 21-case portable report matched the local self-check exactly. Review of the
public live report recomputed the quote and reverse arithmetic, public hashes,
flow deltas, scope flags and freshness calculations. Raw RPC payloads are private
in-process evidence and were not exported, so their full replay was performed by
the host collector, not independently repeated from this summary. This acceptance
is limited to one observed controlled devnet rehearsal. It is not latency SLA,
deployed-source equivalence, two independent executions or profitable economics.

## The next engineering gap

An atomic transaction rolls its two swaps back together. Separate entry and exit
transactions leave an acquired position open when the exit fails or remains
unknown. The offline position ledger already reconciles those outcomes from raw
signed evidence. Its existing v1 policy reserves one exit fee at entry and uses a
cumulative fee ceiling thereafter. It has no explicit count of permitted exits
and does not reserve multiple allowed attempts before entry.

The new **opt-in `position-book-policy-2`** adds `maximumExitAttempts`, an integer
from 1 through 3. This count includes the first exit: a value of 2 means the first
exit plus one possible new attempt after a finalized failure. It never permits
blind resubmission, overlapping unknown attempts, or automatic retries.

Existing v1 policy, status and behavior remain unchanged. Existing books cannot
be silently upgraded: their stored policy must match exactly when reopened.
No production migration, controlled sender change or new devnet cycle is included.

## Admission and persistence

Before entry registration commits, the v2 ledger requires both native balance and
remaining cumulative fee budget to cover:

`entry maximum fee + maximumExitAttempts × maximum leg fee`

The count and funds are checked inside the same SQLite transaction that registers
the signed intent and position. Any failed check rolls back all three records.
Initial balances and policy remain trusted caller declarations in this offline
API; this is not proof of actual-wallet funding or user trading approval.

At exit registration, the ledger counts all already registered exits for that
position. A pending/prepared attempt consumes capacity, even if its submission
outcome is not yet known. It reserves the new attempt's own fee cap plus all
remaining future exit caps. The existing full-quantity, account, balance, freshness,
raw-signature, one-active-position and cumulative-fee checks still apply.

| Evidence/state | Fee commitment and position behavior |
|---|---|
| Entry prepared or unknown | Hold principal, entry fee cap and every allowed exit cap |
| Finalized entry success | Record actual entry fee once; keep every exit cap |
| Finalized entry failure | Record actual fee once; release unused principal and exit caps |
| Exit prepared or unknown | Hold its fee cap plus unused future attempt caps; block a replacement |
| Finalized exit failure | Record actual fee once; retain full acquired position and remaining caps |
| Another distinct eligible exit | Require remaining attempt capacity and fresh valid signed intent; never reuse the old signature |
| Attempts exhausted after failure | Keep position/exposure open, show exhaustion, and block further exit registration |
| Finalized exit success | Reconcile exact full exit and fees once; release unused future allowance |
| Contradictory evidence | Keep quarantine and conservative commitments; mark accounting unusable |

Expiry, missing receipts, process death and reopening do not release unknown
commitments. Duplicate registrations/receipts do not consume another attempt or
charge fees twice. Stops continue to block new entries while permitting otherwise
eligible exits. There is no API that raises the limit or resets used attempts.

`position-book-status-2` reports registered attempts, unused capacity, future fee
holds and exhaustion for each position. `feeReserveCovered` describes coverage of
current recorded commitments; when capacity is exhausted the reserve may be zero
while the position remains open. That must not be mistaken for a funded exit.
`registrationEligibilityVerified=false` and `automaticRetryAllowed=false` remain
explicit: the count/state view is not an instruction to send a transaction.

Gross original-token loss and native fees remain different units. Embedded swap
fees are already reflected in token amounts. This release invents neither a native
fee valuation nor net profit. No token extension, account creation, rent, mainnet
route, loss-stop fill guarantee or external-wallet concurrency support is added.

## Validation and host check

Local validation passed: **257 position-ledger regression tests**, including the
14 new adverse-case tests. Source hygiene and staged whitespace checks passed.
The Kali portable check remains the host acceptance gate.

The existing position tests and new adverse-case tests cover fee/native shortfall
rollback, immutable policies, all 1–3 attempt limits, unknown states, raw receipt
reconciliation, failure/duplicate accounting, failed-exit exposure, exhausted
capacity despite ample cash, concurrent readers, process death after the durable
boundary, event-cap rollback, quarantine commitments and private CLI output.

The portable self-check runs **14 cases** using temporary ledgers and the existing
public synthetic signed receipt fixtures. It performs no network requests, signing,
wallet reads, production journal writes or scanner/study changes. Temporary ledgers
are removed after the check. It accepts only an output path, not a live directory.

After fetching the exact published development commit:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/exit_budget_cli.py" \
  --output "$PWD/radar-exit-budget-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected: `offline-checks-passed`, 14 cases. Upload that public report. No sudo,
Docker rebuild, service restart, airdrop or repeat atomic simulation is required.

## Next sequence

1. Accept the host v2 self-check, then consolidate the three development increments
   with one PR/CI cycle under the agreed local-first working rhythm.
2. Bind a narrowly scoped fresh raw quote/fee/funding admission to the durable
   reservation and restricted signing boundary. Public success reports must never
   become execution permits. This adapter and actual sender integration remain pending.
3. Rehearse separate-transaction unknown/failed-exit handling and reconciliation
   through that adapter before considering another controlled execution.
4. Keep the availability confirmation unchanged; preserve November 1, 3, 5 and 6,
   and review November 6 at 00:05 UTC / 01:05 Europe/Amsterdam.
5. Mainnet route support, explicit funded-pilot limits and prospective economic
   evidence remain separate gates. Passing this check does not authorize real money.
