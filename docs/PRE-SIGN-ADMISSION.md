# Raw evidence to durable pre-sign admission — 30 October 2026

## Consolidated base and purpose

PR #62 merged the host-accepted atomic rehearsal and bounded exit-budget batch at
`6ca918927786be8c93ab28765dc47bd5e44a3cde`. Both CI groups passed at its reviewed
head, and the merged tree matched that head. The 14-case bounded-budget host
report exactly matched the portable result except capture time.

The signed-evidence position book registers already signed intents. A live
integration also needs commitments before signing can start. This increment
builds that earlier boundary as a separate, offline admission prototype. It
reuses raw preflight, quote, fee and simulation validators and the private SQLite
journal infrastructure. It does not change the position book, existing controlled
sender, scanner, observer, backups or fixed research experiment.

## What is implemented

`pre_sign_admission.Admission` owns one narrowly scoped unsigned entry reservation
in an explicitly separate `*.admission.sqlite` ledger. Its immutable policy binds
all direct-pool account roles, entry amount, minimum output, compute/fee limits,
1–3 total exit attempts, the exit fee cap and total fee allowance. Hard limits
remain at most 1,000 input atomic units, 10,000 lamports per supported leg and
40,000 lamports overall. These are engineering bounds, not a trading allocation.

Admission replays the private raw evidence:

1. Recompute the initial quote with the existing integer CPMM calculator and
   compare it to the supplied price. Recompute current pool economics as well;
   changed reserves or fee settings are rejected even if rounded output matches.
2. Check exact unsigned message, roles, deployment against the code-selected pin,
   raw token/native balances, current fee evidence and supported simulation effects.
3. Verify the closed local-cycle reservation snapshot and its clock/identity
   bindings. Subtract its declared commitments from the raw observed balances.
4. Require enough token principal and native allowance for the entry fee cap plus
   every allowed exit cap, within the immutable total limit. Priority is included
   in the message fee cap, not charged a second time.
5. Commit the reservation and evidence/message identities in one immediate SQLite
   transaction. Repeat the local clock/deadline check after validation and before
   inserting the event; expiration rolls back the entire operation.

The baseline is selected in code, not accepted as an override from a report.
Synthetic checks patch the pin in-process to their fixture; the CLI has no pin,
raw-input, wallet, directory or execution arguments.

## State and interruption behavior

| Transition or condition | Behavior |
|---|---|
| Empty → reserved | Persist principal and all configured fee caps |
| Identical reservation repeated | Return recorded state; do not refresh clocks or grant permission |
| Different evidence for the same ledger | Reject; no replacement or second allocation |
| Reserved → signing-unknown | Revalidate identical raw evidence, then commit before a future signer could be called |
| Crash after this commit | Keep funds held; refuse another signing boundary |
| Evidence expires | Refuse a new boundary; retain the existing hold |
| Local clock regresses | Reject |
| Stop before admission | Block entry with zero commitment |
| Stop after admission/boundary | Retain all commitments and the prior boundary timestamp |
| Policy change on reopen | Reject; no implicit migration or increased allowance |
| Event cap or write failure | Roll back state transition |

There is no signer invocation, send, retry, cancellation, release, reset, signed
acknowledgment import or receipt-application API in this increment. In particular,
`signing-unknown` describes the durable uncertainty boundary; the synthetic check
never actually signs. Closing a ledger connection does not release funds.

The original signed-evidence position book remains responsible for tested entry /
exit receipt accounting. A production adapter linking these two components has
not been installed, and their ledgers must not be independently treated as two
spendable budgets.

## Trust and scope limits

This is a trusted local caller prototype, not a wallet-wide locking service.
The reservation snapshot currently arrives through the existing internal evidence
shape. Its arithmetic, identities and ordering are checked, but this prototype
does not itself acquire the controlled wallet lock or independently replay its
source journals. That live provenance step and final signing handoff are still
required. Creating another file or using an external sender bypasses local holds.

RPC evidence and timestamps remain provider/caller inputs. Matching pinned bytes
and simulated effects does not prove deployed-source equivalence or successful
execution. Future exit pricing, rent/WSOL/account creation, Token-2022, aggregator
routes and mainnet are outside this scope. Native fees and token principal retain
their units; no net-profit estimate is created.

Public reports keep signing approval, execution approval, live integration,
wallet-wide reservation knowledge and complete round-trip funding false. Reports
contain identities and small reservation summaries, not raw transactions or keys.
They cannot be imported as execution permits.

## Validation and Kali check

The position-ledger regression suite passed **274 tests**. The final 17 focused
admission tests were also rerun successfully after the input-size guard update;
source hygiene and whitespace checks passed.

17 focused local tests cover raw rejection, full budget requirements, schema and
policy immutability, expiry after validation, rollback, independent connections,
actual subprocess death after commit, persistence, stop behavior, corruption and
exclusive private report publication. The portable suite exercises 15 cases in
temporary ledgers, using synthetic raw accounts and unsigned simulation responses.

After fetching the pinned development commit provided in chat:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/pre_sign_cli.py" \
  --output "$PWD/radar-pre-sign-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Expected: `offline-checks-passed`, 15 cases. Upload that public report. No sudo,
service restart, Docker rebuild, RPC call, airdrop or real wallet access is needed.
The temporary test ledgers are removed. Existing output paths are refused.

## Next sequence

1. Accept the portable host result for this admission prototype.
2. Wire the live locked reader into this boundary, then bind the restricted
   signer's result to the exact reserved message without re-signing after an
   unknown acknowledgment. Preserve a durable handoff to receipt accounting.
3. Rehearse failures at each boundary and reconcile separate entry/exit exposure
   before enabling a new controlled devnet execution path.
4. Keep the fixed availability confirmation unchanged: captures November 1, 3, 5
   and 6; review November 6 at 00:05 UTC / 01:05 Europe/Amsterdam.
5. Mainnet execution support, funded pilot limits and positive prospective economic
   evidence remain separate gates. This prototype approves none of them.
